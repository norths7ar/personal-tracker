import sqlite3
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import core.batch.db as batch_db
import core.db as core_db
import core.diet.db as diet_db
import core.expense.db as expense_db
import core.idempotency as idempotency
from api.main import create_app


class NoCloseConnection(core_db.Connection):
    def close(self):
        pass


class EntryApiTest(unittest.TestCase):
    def setUp(self):
        self.raw = sqlite3.connect(":memory:", check_same_thread=False)
        self.raw.row_factory = sqlite3.Row
        self.raw.execute("PRAGMA foreign_keys = ON")
        self.conn = NoCloseConnection(self.raw, "sqlite")
        self.patchers = [
            patch.object(core_db, "_connect", return_value=self.conn),
            patch.object(core_db, "get_backend", return_value="sqlite"),
            patch.object(core_db, "is_postgres", return_value=False),
            patch.object(batch_db, "_connect", return_value=self.conn),
            patch.object(expense_db, "_connect", return_value=self.conn),
            patch.object(expense_db, "is_postgres", return_value=False),
            patch.object(diet_db, "_connect", return_value=self.conn),
            patch.object(idempotency, "_connect", return_value=self.conn),
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

    def test_transaction_create_is_idempotent(self):
        payload = {
            "type": "支出",
            "description": "午饭",
            "amount": 26,
            "date": "2026-08-31",
            "category": "餐饮",
            "subcategory": "堂食",
        }
        headers = {"Idempotency-Key": "transaction-request-1"}

        first = self.client.post(
            "/api/entries/transactions", json=payload, headers=headers
        )
        second = self.client.post(
            "/api/entries/transactions", json=payload, headers=headers
        )

        self.assertEqual(first.status_code, 200)
        self.assertFalse(first.json()["duplicate"])
        self.assertEqual(second.json(), {**first.json(), "duplicate": True})
        count = self.raw.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
        self.assertEqual(count, 1)

    def test_reusing_key_for_different_payload_is_rejected(self):
        payload = {
            "type": "迁移",
            "description": "充值",
            "amount": 100,
            "date": "2026-08-31",
        }
        headers = {"Idempotency-Key": "transaction-request-2"}
        self.client.post("/api/entries/transactions", json=payload, headers=headers)

        response = self.client.post(
            "/api/entries/transactions",
            json={**payload, "amount": 200},
            headers=headers,
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            self.raw.execute("SELECT COUNT(*) FROM transactions").fetchone()[0], 1
        )

    def test_meal_create_is_idempotent(self):
        payload = {
            "date": "2026-08-31",
            "time": "12:30",
            "meal_type": "午餐",
            "description": "米饭和鸡腿",
            "foods": [
                {
                    "food_name": "鸡腿饭",
                    "quantity": "一份",
                    "ingredients": ["米饭", "鸡腿"],
                }
            ],
        }
        headers = {"Idempotency-Key": "meal-request-1"}

        first = self.client.post("/api/entries/meals", json=payload, headers=headers)
        second = self.client.post("/api/entries/meals", json=payload, headers=headers)

        self.assertEqual(first.status_code, 200)
        self.assertTrue(second.json()["duplicate"])
        self.assertEqual(
            self.raw.execute("SELECT COUNT(*) FROM diet_meals").fetchone()[0], 1
        )
        self.assertEqual(
            self.raw.execute("SELECT COUNT(*) FROM diet_foods").fetchone()[0], 1
        )

    def test_income_and_transfer_preparation_do_not_call_llm(self):
        for type_name in ("收入", "迁移"):
            response = self.client.post(
                "/api/entries/transactions/prepare",
                json={"type": type_name, "description": "测试"},
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["status"], "review_required")

    def test_reviewed_batch_save_keeps_existing_submission_idempotency(self):
        payload = {
            "submission_id": "batch-request-1",
            "records": [
                {
                    "record_type": "支出",
                    "date": "2026-08-31",
                    "description": "打车",
                    "amount": 26.19,
                    "category": "交通",
                    "subcategory": "打车租车",
                }
            ],
        }

        first = self.client.post("/api/entries/batch", json=payload)
        second = self.client.post("/api/entries/batch", json=payload)

        self.assertEqual(first.json(), {"saved_count": 1, "duplicate": False})
        self.assertEqual(second.json(), {"saved_count": 1, "duplicate": True})
        self.assertEqual(
            self.raw.execute("SELECT COUNT(*) FROM transactions").fetchone()[0], 1
        )


if __name__ == "__main__":
    unittest.main()
