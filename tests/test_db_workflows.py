import sqlite3
import unittest
from unittest.mock import patch

import core.batch.db as batch_db
import core.budget.db as budget_db
import core.db as core_db
import core.diet.db as diet_db
import core.expense.db as expense_db
import core.planned_expense.db as planned_expense_db
import core.subscription.db as subscription_db
from core.constants import (
    PENDING_CATEGORY,
    RECURRING_PAYMENT_PREPAID,
    REIMBURSEMENT_CATEGORY,
    RENEWAL_MODE_FIXED_DAYS,
    RENEWAL_MODE_SAME_DAY,
    SUBSCRIPTION_CYCLE_ONE_TIME,
    TYPE_EXPENSE,
    TYPE_INCOME,
)


class NoCloseConnection(sqlite3.Connection):
    def close(self):
        pass


class DatabaseWorkflowTest(unittest.TestCase):
    def setUp(self):
        self.raw = sqlite3.connect(":memory:", factory=NoCloseConnection)
        self.raw.row_factory = sqlite3.Row
        self.raw.execute("PRAGMA foreign_keys = ON")
        self.conn = self.raw

        patches = [
            patch.object(core_db, "_connect", return_value=self.conn),
            patch.object(budget_db, "_connect", return_value=self.conn),
            patch.object(batch_db, "_connect", return_value=self.conn),
            patch.object(diet_db, "_connect", return_value=self.conn),
            patch.object(expense_db, "_connect", return_value=self.conn),
            patch.object(subscription_db, "_connect", return_value=self.conn),
            patch.object(planned_expense_db, "_connect", return_value=self.conn),
        ]
        self.patchers = patches
        for patcher in self.patchers:
            patcher.start()
        core_db.init_db()

    def tearDown(self):
        for patcher in reversed(self.patchers):
            patcher.stop()
        sqlite3.Connection.close(self.raw)

    def test_amount_cents_are_kept_in_sync_for_transactions(self):
        tx_id = expense_db.add_transaction(
            TYPE_EXPENSE,
            "lunch",
            12.345,
            "2026-07-20",
            category="餐饮",
            subcategory="堂食",
        )

        row = self.raw.execute(
            "SELECT amount, amount_cents FROM transactions WHERE id = ?",
            (tx_id,),
        ).fetchone()
        self.assertEqual(row["amount_cents"], 1234)
        self.assertEqual(row["amount"], 12.34)

        expense_db.update_transaction(tx_id, amount=45.678)
        row = self.raw.execute(
            "SELECT amount, amount_cents FROM transactions WHERE id = ?",
            (tx_id,),
        ).fetchone()
        self.assertEqual(row["amount_cents"], 4568)
        self.assertEqual(row["amount"], 45.68)

    def test_transaction_filters_are_database_backed_and_paginated(self):
        expense_db.add_transaction(
            TYPE_EXPENSE,
            "airport train",
            80,
            "2026-08-03",
            category="旅行",
            subcategory="旅行交通",
            notes="summer trip",
        )
        expense_db.add_transaction(
            TYPE_EXPENSE,
            "city taxi",
            30,
            "2026-08-02",
            category="交通",
            subcategory="打车租车",
        )
        expense_db.add_transaction(
            TYPE_EXPENSE,
            "hotel",
            200,
            "2026-08-01",
            category="旅行",
            subcategory="酒店住宿",
        )

        self.assertEqual(
            expense_db.count_transactions(category="旅行", keyword="trip"), 1
        )
        travel = expense_db.get_transactions(category="旅行", limit=None)
        self.assertEqual(
            [row["description"] for row in travel], ["airport train", "hotel"]
        )
        second_page = expense_db.get_transactions(limit=1, offset=1)
        self.assertEqual(second_page[0]["description"], "city taxi")

    def test_batch_save_is_atomic_and_idempotent(self):
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

    def test_batch_rejects_reusing_submission_id_for_different_payload(self):
        first = [
            {
                "record_type": TYPE_EXPENSE,
                "date": "2026-08-30",
                "description": "taxi",
                "amount": 20,
            }
        ]
        second = [{**first[0], "amount": 30}]
        batch_db.save_batch("batch-conflict", first)

        with self.assertRaises(batch_db.BatchSubmissionConflict):
            batch_db.save_batch("batch-conflict", second)

        amount = self.raw.execute(
            "SELECT amount_cents FROM transactions WHERE description = 'taxi'"
        ).fetchone()["amount_cents"]
        self.assertEqual(amount, 2000)

    def test_existing_amortized_transactions_migrate_to_prepaid_subscriptions(self):
        tx_id = expense_db.add_transaction(
            TYPE_EXPENSE,
            "annual software",
            120,
            "2026-07-01",
            category="通讯",
            subcategory="订阅服务",
            amortization_months=12,
            amortization_start="2026-07-01",
        )

        core_db.init_db()

        rows = subscription_db.get_subscriptions(payment_type=RECURRING_PAYMENT_PREPAID)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["transaction_id"], tx_id)
        self.assertEqual(rows[0]["billing_cycle"], SUBSCRIPTION_CYCLE_ONE_TIME)
        self.assertEqual(rows[0]["billing_interval_months"], 12)
        self.assertEqual(rows[0]["monthly_equivalent"], 10)

        core_db.init_db()
        rows = subscription_db.get_subscriptions(payment_type=RECURRING_PAYMENT_PREPAID)
        self.assertEqual(len(rows), 1)

    def test_deleting_prepaid_subscription_clears_linked_amortization(self):
        tx_id = expense_db.add_transaction(
            TYPE_EXPENSE,
            "annual software",
            120,
            "2026-07-01",
            category="通讯",
            subcategory="订阅服务",
            amortization_months=12,
            amortization_start="2026-07-01",
        )
        sub_id = subscription_db.add_subscription(
            name="annual software",
            amount=120,
            billing_cycle=SUBSCRIPTION_CYCLE_ONE_TIME,
            billing_interval_months=12,
            start_date="2026-07-01",
            category="通讯",
            subcategory="订阅服务",
            auto_renew=False,
            payment_type=RECURRING_PAYMENT_PREPAID,
            transaction_id=tx_id,
        )

        subscription_db.delete_prepaid_subscription(sub_id, tx_id)

        transaction = self.raw.execute(
            """SELECT amortization_months, amortization_start
               FROM transactions WHERE id = ?""",
            (tx_id,),
        ).fetchone()
        remaining = self.raw.execute(
            "SELECT COUNT(*) AS count FROM subscriptions WHERE id = ?",
            (sub_id,),
        ).fetchone()["count"]
        self.assertIsNone(transaction["amortization_months"])
        self.assertIsNone(transaction["amortization_start"])
        self.assertEqual(remaining, 0)

        core_db.init_db()
        rows = subscription_db.get_subscriptions(payment_type=RECURRING_PAYMENT_PREPAID)
        self.assertEqual(rows, [])

    def test_prepaid_creation_is_atomic_and_ledger_edits_stay_in_sync(self):
        transaction_id, subscription_id = (
            subscription_db.create_prepaid_with_transaction(
                "annual software",
                120,
                "2026-07-01",
                12,
                "2026-07-01",
                "通讯",
                "订阅服务",
                "work tool",
            )
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
            subscription_db.create_prepaid_with_transaction(
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

    def test_prepaid_metadata_update_is_atomic(self):
        transaction_id, subscription_id = (
            subscription_db.create_prepaid_with_transaction(
                "quarterly rent",
                3000,
                "2026-07-01",
                3,
                "2026-07-01",
                "居住",
                "房租",
                None,
            )
        )

        subscription_db.update_prepaid_with_transaction(
            subscription_id,
            transaction_id,
            "four month rent",
            4,
            "2026-08-01",
            "居住",
            "房租",
            "renewed",
        )

        transaction = self.raw.execute(
            """SELECT description, amortization_months, amortization_start, notes
               FROM transactions WHERE id = ?""",
            (transaction_id,),
        ).fetchone()
        subscription = self.raw.execute(
            """SELECT name, billing_interval_months, start_date, notes
               FROM subscriptions WHERE id = ?""",
            (subscription_id,),
        ).fetchone()
        self.assertEqual(transaction["description"], subscription["name"])
        self.assertEqual(
            transaction["amortization_months"],
            subscription["billing_interval_months"],
        )
        self.assertEqual(transaction["amortization_start"], subscription["start_date"])
        self.assertEqual(transaction["notes"], subscription["notes"])

    def test_linked_transactions_cannot_be_deleted_out_of_order(self):
        original_id = expense_db.add_transaction(
            TYPE_EXPENSE, "hotel", 100, "2026-08-01", category="旅行"
        )
        refund_id = expense_db.add_refund(original_id, "hotel refund", 20, "2026-08-02")
        with self.assertRaisesRegex(ValueError, "关联退款"):
            expense_db.delete_transaction(original_id)
        expense_db.delete_transaction(refund_id)
        expense_db.delete_transaction(original_id)

        prepaid_tx, prepaid_id = subscription_db.create_prepaid_with_transaction(
            "annual service",
            120,
            "2026-08-01",
            12,
            "2026-08-01",
            "通讯",
            "订阅服务",
            None,
        )
        with self.assertRaisesRegex(ValueError, "跨期费用"):
            expense_db.delete_transaction(prepaid_tx)
        subscription_db.delete_prepaid_subscription(prepaid_id, prepaid_tx)
        expense_db.delete_transaction(prepaid_tx)

    def test_bulk_delete_is_atomic_when_one_record_is_protected(self):
        standalone_id = expense_db.add_transaction(
            TYPE_EXPENSE, "duplicate", 20, "2026-08-01", category="旅行"
        )
        original_id = expense_db.add_transaction(
            TYPE_EXPENSE, "hotel", 100, "2026-08-01", category="旅行"
        )
        refund_id = expense_db.add_refund(original_id, "hotel refund", 20, "2026-08-02")

        with self.assertRaisesRegex(ValueError, f"记录 #{original_id}.*关联退款"):
            expense_db.delete_transactions([standalone_id, original_id])

        remaining = self.raw.execute(
            "SELECT id FROM transactions WHERE id IN (?, ?)",
            (standalone_id, original_id),
        ).fetchall()
        self.assertEqual({row["id"] for row in remaining}, {standalone_id, original_id})

        expense_db.delete_transaction(refund_id)
        deleted = expense_db.delete_transactions([standalone_id, original_id])
        self.assertEqual(deleted, 2)

    def test_deleting_subscription_detaches_related_history(self):
        subscription_id = subscription_db.add_subscription(
            "video service",
            30,
            "月付",
            category="通讯",
            subcategory="平台会员",
        )
        transaction_id = expense_db.add_transaction(
            TYPE_EXPENSE,
            "video service",
            30,
            "2026-08-01",
            subscription_id=subscription_id,
        )
        planned_id = planned_expense_db.add_planned_expense(
            "video service",
            30,
            "2026-09-01",
            subscription_id=subscription_id,
        )

        subscription_db.delete_subscription(subscription_id)

        transaction = self.raw.execute(
            "SELECT subscription_id FROM transactions WHERE id = ?", (transaction_id,)
        ).fetchone()
        planned = self.raw.execute(
            "SELECT subscription_id FROM planned_expenses WHERE id = ?", (planned_id,)
        ).fetchone()
        self.assertIsNone(transaction["subscription_id"])
        self.assertIsNone(planned["subscription_id"])

    def test_pending_category_excludes_normal_null_subcategory(self):
        pending_id = expense_db.add_transaction(
            TYPE_EXPENSE,
            "unknown expense",
            30,
            "2026-07-20",
            category=PENDING_CATEGORY,
            subcategory=PENDING_CATEGORY,
            confidence=1.0,
        )
        normal_id = expense_db.add_transaction(
            TYPE_EXPENSE,
            "insurance",
            100,
            "2026-07-20",
            category="保险",
            subcategory=None,
            confidence=1.0,
        )

        rows = expense_db.get_pending_transactions()
        ids = {row["id"] for row in rows}
        self.assertIn(pending_id, ids)
        self.assertNotIn(normal_id, ids)

    def test_manual_review_resolves_low_confidence_without_overwriting_it(self):
        transaction_id = expense_db.add_transaction(
            TYPE_EXPENSE,
            "ambiguous expense",
            30,
            "2026-08-30",
            category="其他",
            subcategory="其他",
            confidence=0.4,
        )
        self.assertEqual(
            [row["id"] for row in expense_db.get_pending_transactions()],
            [transaction_id],
        )

        expense_db.update_transaction(transaction_id, reviewed=True)

        self.assertEqual(expense_db.get_pending_transactions(), [])
        row = self.raw.execute(
            "SELECT confidence, reviewed FROM transactions WHERE id = ?",
            (transaction_id,),
        ).fetchone()
        self.assertEqual(row["confidence"], 0.4)
        self.assertEqual(row["reviewed"], 1)

    def test_refunds_cannot_exceed_remaining_expense(self):
        transaction_id = expense_db.add_transaction(
            TYPE_EXPENSE,
            "hotel",
            100,
            "2026-08-30",
            category="旅行",
            subcategory="酒店住宿",
        )
        expense_db.add_refund(transaction_id, "partial refund", 60, "2026-08-31")

        with self.assertRaisesRegex(ValueError, "剩余可退"):
            expense_db.add_refund(transaction_id, "excess refund", 50, "2026-09-01")

        expense_db.add_refund(transaction_id, "final refund", 40, "2026-09-01")
        self.assertEqual(expense_db.refund_total_for(transaction_id), 100)

    def test_refunds_reconcile_expense_totals_and_original_category(self):
        transaction_id = expense_db.add_transaction(
            TYPE_EXPENSE,
            "hotel",
            100,
            "2026-08-01",
            category="旅行",
            subcategory="酒店住宿",
        )
        expense_db.add_refund(transaction_id, "hotel refund", 30, "2026-08-02")

        for basis in ("cash", "amortized"):
            period = expense_db.get_period_data("2026-08-01", "2026-08-31", basis)
            self.assertEqual(period["expense"], 70)
            self.assertEqual(period["income"], 0)
            self.assertEqual(
                sum(row["total"] for row in period["expense_breakdown"]), 70
            )
            self.assertEqual(period["expense_breakdown"][0]["category"], "旅行")
            self.assertEqual(period["income_breakdown"], [])

    def test_reimbursements_reduce_net_expense_without_counting_as_income(self):
        expense_db.add_transaction(
            TYPE_EXPENSE,
            "trip",
            1296,
            "2026-08-01",
            category="旅行",
            subcategory="旅行交通",
        )
        expense_db.add_transaction(
            TYPE_INCOME,
            "family reimbursement",
            1300,
            "2026-08-02",
            category=REIMBURSEMENT_CATEGORY,
        )

        for basis in ("cash", "amortized"):
            period = expense_db.get_period_data("2026-08-01", "2026-08-31", basis)
            self.assertEqual(period["expense"], -4)
            self.assertEqual(period["income"], 0)
            self.assertEqual(period["balance"], 4)
            self.assertEqual(
                sum(row["total"] for row in period["expense_breakdown"]), 1296
            )
            self.assertNotIn(
                REIMBURSEMENT_CATEGORY,
                {row["category"] for row in period["expense_breakdown"]},
            )
            self.assertEqual(period["income_breakdown"], [])

    def test_fixed_cost_uses_the_selected_month(self):
        subscription_db.add_subscription(
            "video service",
            30,
            "月付",
            start_date="2026-08-15",
            end_date="2026-10-15",
            category="通讯",
        )
        subscription_db.create_prepaid_with_transaction(
            "quarterly rent",
            3000,
            "2026-07-01",
            3,
            "2026-07-01",
            "住房",
            "租房物业",
            None,
        )

        self.assertEqual(subscription_db.fixed_cost_for_month("2026-06"), 0)
        self.assertEqual(subscription_db.fixed_cost_for_month("2026-07"), 1000)
        self.assertEqual(subscription_db.fixed_cost_for_month("2026-08"), 1030)
        self.assertEqual(subscription_db.fixed_cost_for_month("2026-09"), 1030)
        self.assertEqual(subscription_db.fixed_cost_for_month("2026-10"), 30)
        self.assertEqual(subscription_db.fixed_cost_for_month("2026-11"), 0)

    def test_month_budget_replaces_only_the_selected_month(self):
        budget_db.save_month_budget(
            "2026-07",
            amortized_total=8000,
            cash_total=10000,
        )
        budget_db.save_month_budget(
            "2026-08",
            amortized_total=9000,
            cash_total=None,
        )
        budget_db.save_month_budget(
            "2026-07",
            amortized_total=8500,
            cash_total=None,
        )

        july = budget_db.get_month_budget("2026-07")
        august = budget_db.get_month_budget("2026-08")
        self.assertEqual(july["amortized_total"], 8500)
        self.assertIsNone(july["cash_total"])
        self.assertEqual(august["amortized_total"], 9000)

        budget_db.save_month_budget("2026-07", amortized_total=None, cash_total=None)
        self.assertEqual(
            budget_db.get_month_budget("2026-07"),
            {"amortized_total": None, "cash_total": None},
        )

    def test_legacy_category_budget_table_preserves_monthly_totals(self):
        self.raw.execute("DROP TABLE budgets")
        self.raw.execute(
            """CREATE TABLE budgets (
                id INTEGER PRIMARY KEY,
                month TEXT NOT NULL,
                scope TEXT NOT NULL,
                category TEXT NOT NULL,
                amortized_budget_cents INTEGER,
                cash_budget_cents INTEGER
            )"""
        )
        self.raw.execute(
            """INSERT INTO budgets
               VALUES (1, '2026-07', 'overall', '', 800000, 1000000)"""
        )
        self.raw.execute(
            """INSERT INTO budgets
               VALUES (2, '2026-07', 'category', '餐饮', 200000, NULL)"""
        )

        core_db.init_db()

        columns = {
            row["name"] for row in self.raw.execute("PRAGMA table_info(budgets)")
        }
        self.assertEqual(
            columns,
            {"month", "amortized_budget_cents", "cash_budget_cents"},
        )
        self.assertEqual(
            budget_db.get_month_budget("2026-07"),
            {
                "amortized_total": 8000,
                "cash_total": 10000,
            },
        )

    def test_budget_can_compare_cash_and_amortized_costs(self):
        expense_db.add_transaction(
            TYPE_EXPENSE,
            "annual software",
            120,
            "2026-07-01",
            category="通讯",
            subcategory="订阅服务",
            amortization_months=3,
            amortization_start="2026-07-01",
        )

        july_cash = expense_db.get_period_data("2026-07-01", "2026-07-31", "cash")
        july_amortized = expense_db.get_period_data(
            "2026-07-01", "2026-07-31", "amortized"
        )
        august_amortized = expense_db.get_period_data(
            "2026-08-01", "2026-08-31", "amortized"
        )

        self.assertEqual(july_cash["expense"], 120)
        self.assertEqual(july_amortized["expense"], 40)
        self.assertEqual(august_amortized["expense"], 40)

    def test_confirming_a_planned_expense_creates_one_transaction(self):
        plan_id = planned_expense_db.add_planned_expense(
            "graphics card", 20000, category="购物", subcategory="数码电子"
        )

        transaction_id = planned_expense_db.confirm_planned_expense(
            plan_id,
            "graphics card",
            19888,
            "2026-07-24",
            "购物",
            "数码电子",
            "final price",
        )

        plan = self.raw.execute(
            "SELECT status, transaction_id FROM planned_expenses WHERE id = ?",
            (plan_id,),
        ).fetchone()
        transaction = self.raw.execute(
            "SELECT description, amount_cents FROM transactions WHERE id = ?",
            (transaction_id,),
        ).fetchone()
        self.assertEqual(plan["status"], "completed")
        self.assertEqual(plan["transaction_id"], transaction_id)
        self.assertEqual(transaction["description"], "graphics card")
        self.assertEqual(transaction["amount_cents"], 1988800)

    def test_subscription_payment_advances_same_day_without_month_end_drift(self):
        subscription_id = subscription_db.add_subscription(
            "month end service",
            30,
            "月付",
            category="通讯",
            subcategory="平台会员",
            renewal_mode=RENEWAL_MODE_SAME_DAY,
            renewal_interval=1,
            renewal_anchor_day=31,
        )

        transaction_id = subscription_db.record_subscription_payment(
            subscription_id,
            "month end service",
            30,
            "2026-01-31",
            "通讯",
            "平台会员",
            None,
        )
        subscription = self.raw.execute(
            """SELECT last_payment_date, next_renewal_date
               FROM subscriptions WHERE id = ?""",
            (subscription_id,),
        ).fetchone()
        transaction = self.raw.execute(
            "SELECT subscription_id FROM transactions WHERE id = ?", (transaction_id,)
        ).fetchone()
        self.assertEqual(subscription["last_payment_date"], "2026-01-31")
        self.assertEqual(subscription["next_renewal_date"], "2026-02-28")
        self.assertEqual(transaction["subscription_id"], subscription_id)

        self.assertEqual(
            subscription_db.next_renewal_date(
                dict(
                    self.raw.execute(
                        "SELECT * FROM subscriptions WHERE id = ?", (subscription_id,)
                    ).fetchone()
                ),
                "2026-02-28",
            ),
            "2026-03-31",
        )

    def test_subscription_payment_supports_fixed_day_cycles(self):
        subscription_id = subscription_db.add_subscription(
            "thirty day service",
            30,
            "自定义",
            category="通讯",
            subcategory="平台会员",
            renewal_mode=RENEWAL_MODE_FIXED_DAYS,
            renewal_interval=30,
        )

        subscription_db.record_subscription_payment(
            subscription_id,
            "thirty day service",
            30,
            "2026-01-31",
            "通讯",
            "平台会员",
            None,
        )
        next_date = self.raw.execute(
            "SELECT next_renewal_date FROM subscriptions WHERE id = ?",
            (subscription_id,),
        ).fetchone()["next_renewal_date"]
        self.assertEqual(next_date, "2026-03-02")

    def test_existing_transaction_can_atomically_create_subscription(self):
        transaction_id = expense_db.add_transaction(
            TYPE_EXPENSE,
            "music service",
            18,
            "2026-07-24",
            category="通讯",
            subcategory="平台会员",
        )

        subscription_id = subscription_db.create_subscription_from_transaction(
            transaction_id,
            "music service",
            "月付",
            None,
            "2026-08-24",
            RENEWAL_MODE_SAME_DAY,
            1,
            24,
        )

        transaction = self.raw.execute(
            "SELECT subscription_id FROM transactions WHERE id = ?",
            (transaction_id,),
        ).fetchone()
        subscription = self.raw.execute(
            """SELECT transaction_id, last_payment_date, next_renewal_date
               FROM subscriptions WHERE id = ?""",
            (subscription_id,),
        ).fetchone()
        self.assertEqual(transaction["subscription_id"], subscription_id)
        self.assertEqual(subscription["transaction_id"], transaction_id)
        self.assertEqual(subscription["last_payment_date"], "2026-07-24")
        self.assertEqual(subscription["next_renewal_date"], "2026-08-24")

        with self.assertRaises(ValueError):
            subscription_db.create_subscription_from_transaction(
                transaction_id,
                "duplicate",
                "月付",
                None,
                "2026-09-24",
                RENEWAL_MODE_SAME_DAY,
                1,
                24,
            )

    def test_confirming_subscription_plan_links_the_payment_and_closes_plan(self):
        subscription_id = subscription_db.add_subscription(
            "video service",
            30,
            "月付",
            category="通讯",
            subcategory="平台会员",
            renewal_mode=RENEWAL_MODE_SAME_DAY,
            renewal_interval=1,
            renewal_anchor_day=15,
        )
        plan_id = planned_expense_db.add_planned_expense(
            "video service",
            30,
            "2026-07-15",
            "通讯",
            "平台会员",
            subscription_id=subscription_id,
        )

        transaction_id = subscription_db.record_subscription_payment(
            subscription_id,
            "video service",
            31,
            "2026-07-16",
            "通讯",
            "平台会员",
            None,
            planned_expense_id=plan_id,
        )

        plan = self.raw.execute(
            "SELECT status, transaction_id FROM planned_expenses WHERE id = ?",
            (plan_id,),
        ).fetchone()
        subscription = self.raw.execute(
            "SELECT next_renewal_date FROM subscriptions WHERE id = ?",
            (subscription_id,),
        ).fetchone()
        self.assertEqual(plan["status"], "completed")
        self.assertEqual(plan["transaction_id"], transaction_id)
        self.assertEqual(subscription["next_renewal_date"], "2026-08-15")


if __name__ == "__main__":
    unittest.main()
