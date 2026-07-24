import sqlite3
import unittest
from unittest.mock import patch

import core.db as core_db
import core.budget.db as budget_db
import core.expense.db as expense_db
import core.subscription.db as subscription_db
from core.constants import (
    PENDING_CATEGORY,
    RECURRING_PAYMENT_PREPAID,
    SUBSCRIPTION_CYCLE_ONE_TIME,
    TYPE_EXPENSE,
)


class NoCloseConnection(core_db.Connection):
    def close(self):
        pass


class DatabaseWorkflowTest(unittest.TestCase):
    def setUp(self):
        self.raw = sqlite3.connect(":memory:")
        self.raw.row_factory = sqlite3.Row
        self.raw.execute("PRAGMA foreign_keys = ON")
        self.conn = NoCloseConnection(self.raw, "sqlite")

        patches = [
            patch.object(core_db, "_connect", return_value=self.conn),
            patch.object(core_db, "get_backend", return_value="sqlite"),
            patch.object(core_db, "is_postgres", return_value=False),
            patch.object(budget_db, "_connect", return_value=self.conn),
            patch.object(expense_db, "_connect", return_value=self.conn),
            patch.object(expense_db, "is_postgres", return_value=False),
            patch.object(subscription_db, "_connect", return_value=self.conn),
        ]
        self.patchers = patches
        for patcher in self.patchers:
            patcher.start()
        core_db.init_db()

    def tearDown(self):
        for patcher in reversed(self.patchers):
            patcher.stop()
        self.raw.close()

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

        rows = subscription_db.get_subscriptions(
            payment_type=RECURRING_PAYMENT_PREPAID
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["transaction_id"], tx_id)
        self.assertEqual(rows[0]["billing_cycle"], SUBSCRIPTION_CYCLE_ONE_TIME)
        self.assertEqual(rows[0]["billing_interval_months"], 12)
        self.assertEqual(rows[0]["monthly_equivalent"], 10)

        core_db.init_db()
        rows = subscription_db.get_subscriptions(
            payment_type=RECURRING_PAYMENT_PREPAID
        )
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
        rows = subscription_db.get_subscriptions(
            payment_type=RECURRING_PAYMENT_PREPAID
        )
        self.assertEqual(rows, [])

    def test_pending_transactions_include_pending_category_but_not_normal_null_subcategory(self):
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

        budget_db.save_month_budget(
            "2026-07", amortized_total=None, cash_total=None
        )
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
        self.assertEqual(budget_db.get_month_budget("2026-07"), {
            "amortized_total": 8000,
            "cash_total": 10000,
        })

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


if __name__ == "__main__":
    unittest.main()
