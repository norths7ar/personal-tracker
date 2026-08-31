import sqlite3
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import core.db as core_db
import core.expense.db as expense_db
from api.main import create_app
from core.constants import TYPE_EXPENSE, TYPE_INCOME


class NoCloseConnection(core_db.Connection):
    def close(self):
        pass


class TransactionApiTest(unittest.TestCase):
    def setUp(self):
        self.raw = sqlite3.connect(":memory:", check_same_thread=False)
        self.raw.row_factory = sqlite3.Row
        self.raw.execute("PRAGMA foreign_keys = ON")
        self.conn = NoCloseConnection(self.raw, "sqlite")
        self.patchers = [
            patch.object(core_db, "_connect", return_value=self.conn),
            patch.object(core_db, "get_backend", return_value="sqlite"),
            patch.object(core_db, "is_postgres", return_value=False),
            patch.object(expense_db, "_connect", return_value=self.conn),
            patch.object(expense_db, "is_postgres", return_value=False),
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
        self.raw.close()

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

    def test_category_configuration_exposes_transaction_types_only(self):
        response = self.client.get("/api/config/categories")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.json()), {"支出", "收入", "迁移"})
        self.assertIn("餐饮", response.json()["支出"])

    def test_empty_update_and_empty_bulk_delete_are_rejected(self):
        response = self.client.patch("/api/transactions/1", json={})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(
            self.client.post(
                "/api/transactions/bulk-delete", json={"ids": []}
            ).status_code,
            422,
        )


if __name__ == "__main__":
    unittest.main()
