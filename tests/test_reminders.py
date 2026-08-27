import unittest
from datetime import date
from unittest.mock import patch

from core.reminders import get_home_reminders


class HomeReminderTest(unittest.TestCase):
    @patch("core.reminders.get_pending_transaction_count", return_value=2)
    @patch(
        "core.reminders.get_planned_expenses",
        return_value=[
            {
                "id": 10,
                "description": "graphics card",
                "amount": 20000,
                "due_date": "2026-08-30",
                "subscription_id": None,
            },
            {
                "id": 11,
                "description": "linked renewal",
                "amount": 20,
                "due_date": "2026-08-27",
                "subscription_id": 1,
            },
            {
                "id": 12,
                "description": "undated plan",
                "amount": 1000,
                "due_date": None,
                "subscription_id": None,
            },
            {
                "id": 13,
                "description": "paused subscription plan",
                "amount": 40,
                "due_date": "2026-08-28",
                "subscription_id": 99,
            },
        ],
    )
    @patch(
        "core.reminders.get_subscriptions",
        return_value=[
            {
                "id": 1,
                "name": "membership",
                "amount": 20,
                "next_renewal_date": "2026-08-27",
            },
            {
                "id": 2,
                "name": "later membership",
                "amount": 30,
                "next_renewal_date": "2026-09-05",
            },
        ],
    )
    def test_collects_actionable_items_without_duplicate_subscription_plan(
        self,
        _subscriptions,
        _plans,
        _pending_count,
    ):
        result = get_home_reminders(today=date(2026, 8, 27), lookahead_days=3)

        self.assertEqual(result["pending_count"], 2)
        self.assertEqual(
            [(item["source"], item["description"]) for item in result["items"]],
            [
                ("subscription", "membership"),
                ("plan", "paused subscription plan"),
                ("plan", "graphics card"),
            ],
        )
        self.assertEqual(result["items"][0]["days_until_due"], 0)
        self.assertEqual(result["items"][1]["days_until_due"], 1)
        self.assertEqual(result["items"][2]["days_until_due"], 3)


if __name__ == "__main__":
    unittest.main()
