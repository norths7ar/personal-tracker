import sqlite3
import unittest
from unittest.mock import patch

import core.budget.db as budget_db
import core.db as core_db
import core.expense.db as expense_db
import core.planned_expense.db as planned_expense_db
import core.subscription.db as subscription_db
from core.constants import (
    PENDING_CATEGORY,
    RECURRING_PAYMENT_PREPAID,
    RENEWAL_MODE_FIXED_DAYS,
    RENEWAL_MODE_SAME_DAY,
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
            patch.object(planned_expense_db, "_connect", return_value=self.conn),
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

    def test_pending_transactions_include_pending_category_but_not_normal_null_subcategory(
        self,
    ):
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
            "SELECT last_payment_date, next_renewal_date FROM subscriptions WHERE id = ?",
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
