"""保护数据库写入与关联完整性，并核对现金、摊销分析口径。"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from backend import db
from backend.capture import batch, entries
from backend.constants import TYPE_EXPENSE, TYPE_INCOME
from backend.diet import store as meals
from backend.ledger import analysis, planning, transactions


class DatabaseProtectionTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        database = patch.dict(os.environ, {"TRACKER_DATA_DIR": str(Path(temporary.name))})
        database.start()
        self.addCleanup(database.stop)
        db.init_db()
        self.raw = db.connect()
        self.addCleanup(self.raw.close)

    def _transaction(self, type_, description, amount, date_, **fields):
        return entries.create_transaction(
            {
                "type": type_,
                "description": description,
                "amount": amount,
                "date": date_,
                **fields,
            },
            str(uuid4()),
        )["id"]

    def _refund(self, transaction_id, description, amount, date_):
        return transactions.create_refund(
            transaction_id,
            {"description": description, "amount": amount, "date": date_},
            str(uuid4()),
        )["id"]

    def test_batch_save_is_atomic_and_idempotent(self):
        """同一批次重试不会重复产生账目、饮食及食材。"""
        records = [
            {
                "record_type": TYPE_EXPENSE,
                "date": "2026-08-30",
                "description": "train ticket",
                "amount": 120,
                "category": "旅行",
                "subcategory": "旅行交通",
                "notes": None,
                "confidence": 0.9,
            },
            {
                "record_type": "饮食",
                "date": "2026-08-30",
                "time": "12:30",
                "meal_type": "午餐",
                "description": "noodles",
                "notes": None,
                "confidence": 0.95,
                "foods": [
                    {
                        "food_name": "noodles",
                        "quantity": "1 bowl",
                        "ingredients": ["wheat"],
                    }
                ],
            },
        ]

        first = batch.save_batch("batch-1", records)
        second = batch.save_batch("batch-1", records)

        self.assertEqual(first, {"saved_count": 2, "duplicate": False})
        self.assertEqual(second, {"saved_count": 2, "duplicate": True})
        self.assertEqual(self.raw.execute("SELECT COUNT(*) FROM transactions").fetchone()[0], 1)
        self.assertEqual(self.raw.execute("SELECT COUNT(*) FROM diet_meals").fetchone()[0], 1)
        self.assertEqual(self.raw.execute("SELECT COUNT(*) FROM diet_foods").fetchone()[0], 1)
        self.assertEqual(self.raw.execute("SELECT COUNT(*) FROM diet_ingredients").fetchone()[0], 1)

    def test_batch_failure_rolls_back_and_can_retry_same_submission(self):
        """批次中途失败不留半笔数据，也不占用重试标识。"""
        invalid_records = [
            {
                "record_type": TYPE_EXPENSE,
                "date": "2026-08-30",
                "description": "taxi",
                "amount": 20,
                "category": "旅行",
                "subcategory": "旅行交通",
            },
            {
                "record_type": "饮食",
                "date": "2026-08-30",
                "time": "12:00",
                "description": "noodles",
                "foods": [{"food_name": "noodles", "ingredients": ["wheat"]}],
            },
            {
                "record_type": "饮食",
                "date": "2026-08-30",
                "time": "12:30",
                "description": "invalid meal",
                "foods": [],
            },
        ]

        with self.assertRaises(ValueError):
            batch.save_batch("batch-retry", invalid_records)

        self.assertEqual(
            self.raw.execute("SELECT COUNT(*) FROM batch_submissions").fetchone()[0],
            0,
        )
        self.assertEqual(self.raw.execute("SELECT COUNT(*) FROM transactions").fetchone()[0], 0)
        for table in ("diet_meals", "diet_foods", "diet_ingredients"):
            self.assertEqual(
                self.raw.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0],
                0,
                table,
            )

        valid_records = [invalid_records[0]]
        result = batch.save_batch("batch-retry", valid_records)
        self.assertEqual(result, {"saved_count": 1, "duplicate": False})

    def test_bulk_delete_is_atomic_when_one_record_is_protected(self):
        """有退款关联的账目阻止整批删除，其他选中记录不会先被删掉。"""
        standalone_id = self._transaction(
            TYPE_EXPENSE, "duplicate", 20, "2026-08-01", category="旅行"
        )
        original_id = self._transaction(TYPE_EXPENSE, "hotel", 100, "2026-08-01", category="旅行")
        refund_id = self._refund(original_id, "hotel refund", 20, "2026-08-02")

        with self.assertRaisesRegex(ValueError, f"记录 #{original_id}.*关联退款"):
            transactions.delete_transactions([standalone_id, original_id])

        remaining = self.raw.execute(
            "SELECT id FROM transactions WHERE id IN (?, ?)",
            (standalone_id, original_id),
        ).fetchall()
        self.assertEqual({row["id"] for row in remaining}, {standalone_id, original_id})

        transactions.delete_transactions([refund_id])
        deleted = transactions.delete_transactions([standalone_id, original_id])
        self.assertEqual(deleted, 2)

    def test_refunds_cannot_exceed_remaining_expense(self):
        """累计退款不能超过原始支出。"""
        transaction_id = self._transaction(
            TYPE_EXPENSE,
            "hotel",
            100,
            "2026-08-30",
            category="旅行",
            subcategory="酒店住宿",
            coverage_start="2026-08-30",
            coverage_end="2026-09-01",
        )
        self._refund(transaction_id, "partial refund", 60, "2026-08-31")

        with self.assertRaisesRegex(ValueError, "剩余可退"):
            self._refund(transaction_id, "excess refund", 50, "2026-09-01")

        self._refund(transaction_id, "final refund", 40, "2026-09-01")
        self.assertEqual(
            sum(
                row["amount"]
                for row in transactions.get_transactions()
                if row["refund_for_id"] == transaction_id
            ),
            100,
        )
        with self.assertRaises(ValueError):
            planning.update_transaction(transaction_id, {"amount": 99})
        for basis in ("cash", "amortized"):
            period = analysis.get_period_data("2026-08-30", "2026-09-01", basis)
            self.assertEqual((period["expense"], period["income"]), (0, 0))

    def test_coverage_write_is_atomic_and_has_one_source_of_truth(self):
        """生效期随交易原子保存，非法更新不留半笔数据，不生成独立预付对象。"""
        payload = {
            "type": TYPE_EXPENSE,
            "description": "annual software",
            "amount": 120,
            "date": "2026-07-01",
            "coverage_start": "2026-07-01",
            "coverage_end": "2027-06-30",
        }
        key = str(uuid4())
        transaction_id = entries.create_transaction(payload, key)["id"]
        self.assertTrue(entries.create_transaction(payload, key)["duplicate"])
        self.assertEqual(self.raw.execute("SELECT COUNT(*) FROM subscriptions").fetchone()[0], 0)
        planning.update_transaction(transaction_id, {"amount": 150, "category": "工作"})
        current = transactions.get_transaction(transaction_id)
        self.assertEqual(current["amount_cents"], 15000)
        self.assertEqual(current["coverage_end"], "2027-06-30")
        for invalid in (
            {"coverage_end": None},
            {"coverage_start": "2028-01-01"},
            {"type": TYPE_INCOME},
        ):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                planning.update_transaction(transaction_id, {"amount": 999, **invalid})
            self.assertEqual(transactions.get_transaction(transaction_id), current)
        retry_key = str(uuid4())
        with self.assertRaises(ValueError):
            entries.create_transaction({**payload, "coverage_end": None}, retry_key)
        self.assertEqual(self.raw.execute("SELECT COUNT(*) FROM transactions").fetchone()[0], 1)
        self.assertFalse(entries.create_transaction(payload, retry_key)["duplicate"])
        planning.update_transaction(transaction_id, {"coverage_start": None, "coverage_end": None})
        self.assertIsNone(transactions.get_transaction(transaction_id)["coverage_start"])
        self.assertEqual(transactions.delete_transactions([transaction_id]), 1)

    def _meals(self):
        return [
            entries.create_meal(
                {
                    "date": "2026-09-07",
                    "time": "12:30",
                    "description": description,
                    "foods": [{"food_name": description, "ingredients": ["鸡蛋"]}],
                },
                str(uuid4()),
            )["id"]
            for description in ("炒蛋", "蒸蛋")
        ]

    def test_missing_id_fails_both_operations_atomically(self):
        """选中记录不存在时，批量饮食修改和删除均不产生部分结果。"""
        ids = self._meals()
        before = meals.get_meals()
        with self.assertRaises(meals.MealNotFound):
            meals.update_meals([ids[0], 9999], {"notes": "修改"})
        self.assertEqual(meals.get_meals(), before)
        with self.assertRaises(meals.MealNotFound):
            meals.delete_meals([ids[0], 9999])
        self.assertEqual(meals.get_meals(), before)

    def test_bulk_delete_cascades_and_counts_unique_ids(self):
        """删除饮食记录同时清理食物和食材，重复选择不会误删其他记录。"""
        self._meals()
        tables = ("diet_meals", "diet_foods", "diet_ingredients")
        unselected = {
            table: [dict(row) for row in self.raw.execute(f"SELECT * FROM {table} ORDER BY id")]
            for table in tables
        }
        ids = self._meals()
        self.assertEqual(meals.delete_meals([*ids, ids[0]]), 2)
        for table in tables:
            self.assertTrue(unselected[table], table)
            self.assertEqual(
                [dict(row) for row in self.raw.execute(f"SELECT * FROM {table} ORDER BY id")],
                unselected[table],
                table,
            )

    def test_analysis_reconciles_daily_coverage_refund_and_income_without_new_transactions(
        self,
    ):
        """按天分摊守恒，先用后付仍归属生效期，退款抵扣支出而不新增流水。"""
        self._transaction(
            TYPE_EXPENSE,
            "quarterly rent",
            9000,
            "2025-04-15",
            coverage_start="2025-01-01",
            coverage_end="2025-03-31",
            category="居住",
            subcategory="房租",
        )
        spending_id = self._transaction(
            TYPE_EXPENSE, "groceries", 300, "2025-01-20", category="生活"
        )
        refund_id = self._refund(spending_id, "grocery refund", 60, "2025-01-21")
        self._transaction(TYPE_INCOME, "salary", 2000, "2025-01-25", category="工资")
        before = self.raw.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
        self.assertEqual(before, 4)

        for basis in ("cash", "amortized"):
            january = analysis.get_expense_analysis("month", "2025-01", basis)
            current = january["current"]
            expected_expense = 240 if basis == "cash" else 3340
            self.assertEqual(january["cash_expense"], 240)
            self.assertEqual(january["amortized_expense"], 3340)
            self.assertEqual(current["expense"], expected_expense)
            self.assertEqual(current["income"], 2000)
            self.assertEqual(current["balance"], 2000 - expected_expense)
            self.assertEqual(
                {row["category"]: row["total"] for row in current["expense_breakdown"]},
                {"生活": 240} if basis == "cash" else {"居住": 3100, "生活": 240},
            )
            refunds = [row for row in current["entries"] if row["id"] == refund_id]
            self.assertEqual(len(refunds), 1)
            self.assertEqual((refunds[0]["bucket"], refunds[0]["contribution"]), ("expense", -60))

            for month, cost in (("2025-02", 2800), ("2025-03", 3100)):
                later = analysis.get_expense_analysis("month", month, basis)
                self.assertEqual(later["cash_expense"], 0)
                self.assertEqual(later["amortized_expense"], cost)
                self.assertEqual(later["current"]["expense"], 0 if basis == "cash" else cost)
                self.assertEqual(later["current"]["income"], 0)

            yearly = analysis.get_expense_analysis("year", "2025", basis)
            self.assertEqual(yearly["current"]["expense"], 9240)
            self.assertEqual(yearly["current"]["income"], 2000)
            for data in (current, yearly["current"]):
                for bucket in ("income", "expense"):
                    self.assertEqual(
                        sum(
                            row["contribution"]
                            for row in data["entries"]
                            if row["bucket"] == bucket
                        ),
                        data[bucket],
                    )
                    self.assertEqual(sum(row[bucket] for row in data["daily"]), data[bucket])
                    self.assertEqual(
                        sum(row["total"] for row in data[f"{bucket}_breakdown"]),
                        data[bucket],
                    )
                self.assertEqual(data["balance"], data["income"] - data["expense"])
            for bucket in ("income", "expense"):
                self.assertEqual(
                    sum(row[bucket] for row in yearly["timeline"]),
                    yearly["current"][bucket],
                )
            analysis.get_expense_analysis("year", "2025", basis)
            self.assertEqual(
                self.raw.execute("SELECT COUNT(*) FROM transactions").fetchone()[0],
                before,
            )

        for start, end, amount, daily_cents in (
            ("2024-01-31", "2024-02-01", 10.01, [501, 500]),
            ("2024-02-28", "2024-03-01", 0.01, [1, 0, 0]),
            ("2024-02-01", "2024-02-01", 10.01, [1001]),
        ):
            with self.subTest(start=start, end=end):
                record_id = self._transaction(
                    TYPE_EXPENSE,
                    "shifted cost",
                    amount,
                    "2024-01-01",
                    coverage_start=start,
                    coverage_end=end,
                )
                data = analysis.get_period_data(start, end, "amortized")
                self.assertEqual(
                    [db.to_cents(row[TYPE_EXPENSE]) for row in data["daily"]], daily_cents
                )
                self.assertEqual(db.to_cents(data["expense"]), sum(daily_cents))
                self.assertEqual(analysis.get_period_data(start, end, "cash")["expense"], 0)
                self.assertEqual(transactions.delete_transactions([record_id]), 1)
