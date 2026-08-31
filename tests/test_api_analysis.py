import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.main import create_app
from services import analysis as analysis_service


def _period(expense: float) -> dict:
    return {
        "income": 100.0,
        "expense": expense,
        "balance": 100.0 - expense,
        "daily": [{"date": "2026-08-01", "收入": 100.0, "支出": expense}],
        "expense_breakdown": [
            {"category": "餐饮", "subcategory": "堂食", "total": expense, "count": 1}
        ],
        "income_breakdown": [],
    }


class ExpenseAnalysisApiTest(unittest.TestCase):
    @staticmethod
    def _secret(name: str, default: str | None = None) -> str | None:
        return "false" if name == "AUTH_ENABLED" else default

    def setUp(self):
        self.patchers = [
            patch("api.main.init_db"),
            patch("api.security.get_secret", side_effect=self._secret),
            patch.object(
                analysis_service, "get_active_months", return_value=["2026-08"]
            ),
            patch.object(analysis_service, "get_active_years", return_value=["2026"]),
            patch.object(
                analysis_service,
                "get_period_data",
                side_effect=lambda *_: _period(26.0),
            ),
            patch.object(analysis_service, "fixed_cost_for_month", return_value=12.0),
            patch.object(
                analysis_service,
                "get_month_budget",
                return_value={"amortized_total": 1000.0, "cash_total": 1200.0},
            ),
        ]
        for patcher in self.patchers:
            patcher.start()
        self.client_context = TestClient(create_app())
        self.client = self.client_context.__enter__()

    def tearDown(self):
        self.client_context.__exit__(None, None, None)
        for patcher in reversed(self.patchers):
            patcher.stop()

    def test_month_analysis_returns_one_page_payload(self):
        response = self.client.get(
            "/api/analysis/expenses?granularity=month&period=2026-08&basis=amortized"
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["selected_period"], "2026-08")
        self.assertEqual(payload["current"]["expense"], 26.0)
        self.assertEqual(payload["current"]["daily"][0]["expense"], 26.0)
        self.assertEqual(payload["fixed_monthly_cost"], 12.0)
        self.assertEqual(payload["budget"]["cash_total"], 1200.0)

    def test_budget_update_rejects_unknown_month(self):
        response = self.client.put(
            "/api/analysis/budgets/2025-01", json={"cash_total": 1000}
        )

        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
