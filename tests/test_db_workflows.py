import sqlite3
import unittest
from unittest.mock import patch

import core.db as core_db
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


if __name__ == "__main__":
    unittest.main()
