import sqlite3
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import core.db as core_db
import core.expense.db as expense_db
import core.idempotency as idempotency
import core.subscription.db as subscription_db
from api.main import create_app
from core.constants import TYPE_EXPENSE, TYPE_INCOME


class NoCloseConnection(sqlite3.Connection):
    def close(self):
        pass


class TransactionApiTest(unittest.TestCase):
    def setUp(self):
        self.raw = sqlite3.connect(
            ":memory:", check_same_thread=False, factory=NoCloseConnection
        )
        self.raw.row_factory = sqlite3.Row
        self.raw.execute("PRAGMA foreign_keys = ON")
        self.conn = self.raw
        self.patchers = [
            patch.object(core_db, "_connect", return_value=self.conn),
            patch.object(expense_db, "_connect", return_value=self.conn),
            patch.object(idempotency, "_connect", return_value=self.conn),
            patch.object(subscription_db, "_connect", return_value=self.conn),
            patch("api.main.init_db", side_effect=core_db.init_db),
            patch("api.security.get_secret", side_effect=self._secret),
        ]
        for patcher in self.patchers:
            patcher.start()
        self.client_context = TestClient(create_app())
        self.client = self.client_context.__enter__()

    def tearDown(self):
        self.client_context.__exit__(None, None, None)
        for patcher in reversed(self.patchers):
            patcher.stop()
        sqlite3.Connection.close(self.raw)

    @staticmethod
    def _secret(name: str, default: str | None = None) -> str | None:
        return "false" if name == "AUTH_ENABLED" else default

    def test_list_update_and_bulk_delete_transactions(self):
        lunch_id = expense_db.add_transaction(
            TYPE_EXPENSE,
            "午饭",
            26,
            "2026-08-30",
            category="餐饮",
            subcategory="堂食",
        )
        income_id = expense_db.add_transaction(
            TYPE_INCOME,
            "报销",
            100,
            "2026-08-31",
            category="其他",
        )

        listed = self.client.get("/api/transactions")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual([row["id"] for row in listed.json()], [income_id, lunch_id])

        updated = self.client.patch(
            f"/api/transactions/{lunch_id}",
            json={"description": "周日午饭", "amount": 28.5},
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.json()["description"], "周日午饭")
        self.assertEqual(updated.json()["amount_cents"], 2850)

        deleted = self.client.post(
            "/api/transactions/bulk-delete", json={"ids": [lunch_id, income_id]}
        )
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(deleted.json(), {"deleted_count": 2})
        self.assertEqual(self.client.get("/api/transactions").json(), [])

    def test_update_missing_transaction_returns_not_found(self):
        response = self.client.patch(
            "/api/transactions/999", json={"description": "missing"}
        )
        self.assertEqual(response.status_code, 404)

    def test_bulk_update_transaction_categories_and_notes(self):
        first_id = expense_db.add_transaction(
            TYPE_EXPENSE,
            "打车一",
            18.26,
            "2026-08-30",
            category="交通",
            subcategory="打车租车",
        )
        second_id = expense_db.add_transaction(
            TYPE_EXPENSE,
            "打车二",
            11.3,
            "2026-08-30",
            category="交通",
            subcategory="打车租车",
        )

        response = self.client.patch(
            "/api/transactions/bulk-update",
            json={
                "ids": [first_id, second_id],
                "category": "旅游",
                "subcategory": "旅行交通",
                "notes": "父母报销",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"updated_count": 2})
        rows = self.client.get("/api/transactions").json()
        self.assertEqual({row["category"] for row in rows}, {"旅游"})
        self.assertEqual({row["subcategory"] for row in rows}, {"旅行交通"})
        self.assertEqual({row["notes"] for row in rows}, {"父母报销"})
        self.assertTrue(all(row["reviewed"] for row in rows))

    def test_category_configuration_exposes_transaction_types_only(self):
        response = self.client.get("/api/config/categories")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.json()), {"支出", "收入", "迁移"})
        self.assertIn("餐饮", response.json()["支出"])

    def test_pending_endpoint_only_returns_unresolved_expenses(self):
        pending_id = expense_db.add_transaction(
            TYPE_EXPENSE,
            "待确认",
            20,
            "2026-08-31",
            category="待分类",
            subcategory="待分类",
            confidence=0.3,
        )
        expense_db.add_transaction(
            TYPE_EXPENSE,
            "已确认",
            30,
            "2026-08-31",
            category="餐饮",
            subcategory="堂食",
            reviewed=True,
        )

        response = self.client.get("/api/pending-transactions")

        self.assertEqual(response.status_code, 200)
        self.assertEqual([row["id"] for row in response.json()], [pending_id])

    def test_empty_update_and_empty_bulk_delete_are_rejected(self):
        response = self.client.patch("/api/transactions/1", json={})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(
            self.client.post(
                "/api/transactions/bulk-delete", json={"ids": []}
            ).status_code,
            422,
        )
        self.assertEqual(
            self.client.patch(
                "/api/transactions/bulk-update", json={"ids": [1]}
            ).status_code,
            422,
        )

    def test_refund_creation_is_idempotent_and_limited_to_remaining_amount(self):
        expense_id = expense_db.add_transaction(
            TYPE_EXPENSE, "网购", 100, "2026-08-30", category="购物"
        )
        body = {"description": "网购退款", "amount": 40, "date": "2026-08-31"}

        first = self.client.post(
            f"/api/transactions/{expense_id}/refunds",
            json=body,
            headers={"Idempotency-Key": "refund-request-1"},
        )
        retried = self.client.post(
            f"/api/transactions/{expense_id}/refunds",
            json=body,
            headers={"Idempotency-Key": "refund-request-1"},
        )

        self.assertEqual(first.status_code, 200)
        self.assertFalse(first.json()["duplicate"])
        self.assertTrue(retried.json()["duplicate"])
        self.assertEqual(expense_db.refund_total_for(expense_id), 40)
        too_much = self.client.post(
            f"/api/transactions/{expense_id}/refunds",
            json={**body, "amount": 61},
            headers={"Idempotency-Key": "refund-request-2"},
        )
        self.assertEqual(too_much.status_code, 409)

    def test_subscription_creation_from_transaction_is_idempotent(self):
        expense_id = expense_db.add_transaction(
            TYPE_EXPENSE, "会员", 30, "2026-08-30", category="通讯"
        )
        body = {
            "name": "会员",
            "billing_cycle": "月付",
            "next_renewal_date": "2026-09-30",
            "renewal_mode": "same_day",
            "renewal_interval": 1,
            "renewal_anchor_day": 30,
        }

        first = self.client.post(
            f"/api/transactions/{expense_id}/subscription",
            json=body,
            headers={"Idempotency-Key": "subscription-request-1"},
        )
        retried = self.client.post(
            f"/api/transactions/{expense_id}/subscription",
            json=body,
            headers={"Idempotency-Key": "subscription-request-1"},
        )

        self.assertEqual(first.status_code, 200)
        self.assertTrue(retried.json()["duplicate"])
        self.assertEqual(
            len(subscription_db.get_subscriptions(payment_type="subscription")), 1
        )


if __name__ == "__main__":
    unittest.main()
