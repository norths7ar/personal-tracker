import sqlite3
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import core.db as core_db
import core.expense.db as expense_db
import core.idempotency as idempotency
import core.planned_expense.db as planned_db
import core.subscription.db as subscription_db
from api.main import create_app


class NoCloseConnection(core_db.Connection):
    def close(self):
        pass


class CrossPeriodApiTest(unittest.TestCase):
    @staticmethod
    def _secret(name: str, default: str | None = None) -> str | None:
        return "false" if name == "AUTH_ENABLED" else default

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
            patch.object(subscription_db, "_connect", return_value=self.conn),
            patch.object(planned_db, "_connect", return_value=self.conn),
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

    def test_plan_create_and_confirm_are_idempotent(self):
        body = {
            "description": "显卡预算",
            "amount": 5000,
            "recurring": False,
            "due_date": "2026-09-15",
            "category": "购物",
        }
        first = self.client.post(
            "/api/cross-period/expected",
            json=body,
            headers={"Idempotency-Key": "expected-create-1"},
        )
        duplicate = self.client.post(
            "/api/cross-period/expected",
            json=body,
            headers={"Idempotency-Key": "expected-create-1"},
        )
        self.assertEqual(first.status_code, 200)
        self.assertFalse(first.json()["duplicate"])
        self.assertTrue(duplicate.json()["duplicate"])
        expected = self.client.get("/api/cross-period").json()["expected"]
        self.assertEqual(len(expected), 1)

        record_id = first.json()["id"]
        payment = {
            "description": "购买显卡",
            "amount": 4800,
            "payment_date": "2026-09-14",
            "category": "购物",
        }
        confirmed = self.client.post(
            f"/api/cross-period/expected/plan/{record_id}/confirm",
            json=payment,
            headers={"Idempotency-Key": "expected-confirm-1"},
        )
        retried = self.client.post(
            f"/api/cross-period/expected/plan/{record_id}/confirm",
            json=payment,
            headers={"Idempotency-Key": "expected-confirm-1"},
        )
        self.assertEqual(confirmed.status_code, 200)
        self.assertEqual(retried.status_code, 200)
        self.assertEqual(
            confirmed.json()["transaction_id"], retried.json()["transaction_id"]
        )
        self.assertTrue(retried.json()["duplicate"])
        count = self.raw.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
        self.assertEqual(count, 1)

    def test_prepaid_create_is_idempotent(self):
        body = {
            "description": "年度服务",
            "amount": 1200,
            "payment_date": "2026-08-31",
            "months": 12,
            "start_month": "2026-08",
            "category": "通讯",
        }
        first = self.client.post(
            "/api/cross-period/prepaid",
            json=body,
            headers={"Idempotency-Key": "prepaid-create-1"},
        )
        duplicate = self.client.post(
            "/api/cross-period/prepaid",
            json=body,
            headers={"Idempotency-Key": "prepaid-create-1"},
        )
        self.assertEqual(first.status_code, 200)
        self.assertTrue(duplicate.json()["duplicate"])
        records = self.client.get("/api/cross-period").json()["prepaid"]
        self.assertEqual(len(records), 1)


if __name__ == "__main__":
    unittest.main()
