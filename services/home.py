from datetime import date

from core.constants import TYPE_EXPENSE
from core.diet.db import get_meals
from core.expense.db import get_transactions
from core.reminders import get_home_reminders


def get_home_summary() -> dict:
    today = date.today().isoformat()
    reminders = get_home_reminders()
    transactions = get_transactions(start_date=today, end_date=today, limit=500)
    meals = get_meals(start_date=today, end_date=today)
    return {
        "reminders": reminders["items"],
        "pending_count": reminders["pending_count"],
        "today_expense": sum(
            float(item.get("amount") or 0)
            for item in transactions
            if item.get("type") == TYPE_EXPENSE
        ),
        "today_meals": [
            {
                "id": meal["id"],
                "time": meal.get("time"),
                "meal_type": meal.get("meal_type"),
                "foods": [food["food_name"] for food in meal.get("foods", [])],
            }
            for meal in meals
        ],
    }
