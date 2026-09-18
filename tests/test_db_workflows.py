"""只保留会造成重复入账、部分写入或关联数据损坏的数据库保护。"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import core.batch.db as batch_db
import core.db as core_db
import core.diet.db as diet_db
import core.expense.db as expense_db
import core.subscription.db as subscription_db
from core.constants import TYPE_EXPENSE
from services import cross_period, entries, meals, transactions


class DatabaseProtectionTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        database = patch.object(core_db, "DB_PATH", Path(temporary.name) / "test.db")
        database.start()
        self.addCleanup(database.stop)
        core_db.init_db()
        self.raw = core_db._connect()
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

    def _prepaid(
        self,
        description,
        amount,
        payment_date,
        months,
        start,
        category,
        subcategory,
        notes,
    ):
        result = cross_period.create_prepaid(
            {
                "description": description,
                "amount": amount,
                "payment_date": payment_date,
                "months": months,
                "start_month": start[:7],
                "category": category,
                "subcategory": subcategory,
                "notes": notes,
            },
            str(uuid4()),
        )
        return result["transaction_id"], result["subscription_id"]

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

        first = batch_db.save_batch("batch-1", records)
        second = batch_db.save_batch("batch-1", records)

        self.assertEqual(first, {"saved_count": 2, "duplicate": False})
        self.assertEqual(second, {"saved_count": 2, "duplicate": True})
        self.assertEqual(
            self.raw.execute("SELECT COUNT(*) FROM transactions").fetchone()[0], 1
        )
        self.assertEqual(
            self.raw.execute("SELECT COUNT(*) FROM diet_meals").fetchone()[0], 1
        )
        self.assertEqual(
            self.raw.execute("SELECT COUNT(*) FROM diet_foods").fetchone()[0], 1
        )
        self.assertEqual(
            self.raw.execute("SELECT COUNT(*) FROM diet_ingredients").fetchone()[0], 1
        )

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
                "time": "12:30",
                "description": "invalid meal",
                "foods": [],
            },
        ]

        with self.assertRaises(ValueError):
            batch_db.save_batch("batch-retry", invalid_records)

        self.assertEqual(
            self.raw.execute("SELECT COUNT(*) FROM batch_submissions").fetchone()[0],
            0,
        )
        self.assertEqual(
            self.raw.execute("SELECT COUNT(*) FROM transactions").fetchone()[0], 0
        )

        valid_records = [invalid_records[0]]
        result = batch_db.save_batch("batch-retry", valid_records)
        self.assertEqual(result, {"saved_count": 1, "duplicate": False})

    def test_bulk_delete_is_atomic_when_one_record_is_protected(self):
        """有退款关联的账目阻止整批删除，其他选中记录不会先被删掉。"""
        standalone_id = self._transaction(
            TYPE_EXPENSE, "duplicate", 20, "2026-08-01", category="旅行"
        )
        original_id = self._transaction(
            TYPE_EXPENSE, "hotel", 100, "2026-08-01", category="旅行"
        )
        refund_id = self._refund(original_id, "hotel refund", 20, "2026-08-02")

        with self.assertRaisesRegex(ValueError, f"记录 #{original_id}.*关联退款"):
            expense_db.delete_transactions([standalone_id, original_id])

        remaining = self.raw.execute(
            "SELECT id FROM transactions WHERE id IN (?, ?)",
            (standalone_id, original_id),
        ).fetchall()
        self.assertEqual({row["id"] for row in remaining}, {standalone_id, original_id})

        expense_db.delete_transactions([refund_id])
        deleted = expense_db.delete_transactions([standalone_id, original_id])
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
        )
        self._refund(transaction_id, "partial refund", 60, "2026-08-31")

        with self.assertRaisesRegex(ValueError, "剩余可退"):
            self._refund(transaction_id, "excess refund", 50, "2026-09-01")

        self._refund(transaction_id, "final refund", 40, "2026-09-01")
        self.assertEqual(
            sum(
                row["amount"]
                for row in expense_db.get_transactions()
                if row["refund_for_id"] == transaction_id
            ),
            100,
        )

    def test_prepaid_creation_is_atomic_and_ledger_edits_stay_in_sync(self):
        """预付记录与流水一起成功或失败，后续编辑保持一致。"""
        transaction_id, subscription_id = self._prepaid(
            "annual software",
            120,
            "2026-07-01",
            12,
            "2026-07-01",
            "通讯",
            "订阅服务",
            "work tool",
        )

        transaction = self.raw.execute(
            "SELECT * FROM transactions WHERE id = ?", (transaction_id,)
        ).fetchone()
        subscription = self.raw.execute(
            "SELECT * FROM subscriptions WHERE id = ?", (subscription_id,)
        ).fetchone()
        self.assertEqual(transaction["amortization_months"], 12)
        self.assertEqual(subscription["transaction_id"], transaction_id)

        expense_db.update_transaction(
            transaction_id,
            description="renamed software",
            amount=150,
            category="工作",
        )
        subscription = self.raw.execute(
            "SELECT name, amount_cents, category FROM subscriptions WHERE id = ?",
            (subscription_id,),
        ).fetchone()
        self.assertEqual(subscription["name"], "renamed software")
        self.assertEqual(subscription["amount_cents"], 15000)
        self.assertEqual(subscription["category"], "工作")

        before = self.raw.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
        with (
            patch.object(
                subscription_db,
                "_insert_subscription",
                side_effect=RuntimeError("insert failed"),
            ),
            self.assertRaisesRegex(RuntimeError, "insert failed"),
        ):
            self._prepaid(
                "broken prepaid",
                50,
                "2026-08-01",
                2,
                "2026-08-01",
                "其他",
                None,
                None,
            )
        after = self.raw.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
        self.assertEqual(after, before)

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
        before = diet_db.get_meals()
        with self.assertRaises(meals.MealNotFound):
            meals.update_meals([ids[0], 9999], {"notes": "修改"})
        self.assertEqual(diet_db.get_meals(), before)
        with self.assertRaises(meals.MealNotFound):
            meals.delete_meals([ids[0], 9999])
        self.assertEqual(diet_db.get_meals(), before)

    def test_bulk_delete_cascades_and_counts_unique_ids(self):
        """删除饮食记录同时清理食物和食材，重复选择不会误删其他记录。"""
        ids = self._meals()
        self.assertEqual(meals.delete_meals([*ids, ids[0]]), 2)
        for table in ("diet_meals", "diet_foods", "diet_ingredients"):
            self.assertEqual(
                self.raw.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 0
            )
