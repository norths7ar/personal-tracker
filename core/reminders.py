from datetime import date, timedelta

from core.constants import RECURRING_PAYMENT_SUBSCRIPTION
from core.expense.db import get_pending_transaction_count
from core.planned_expense.db import get_planned_expenses
from core.subscription.db import get_subscriptions


def get_home_reminders(
    today: date | None = None,
    lookahead_days: int = 3,
) -> dict:
    """Collect actionable items without creating or mutating financial records."""
    today = today or date.today()
    through = today + timedelta(days=max(0, lookahead_days))
    items = []

    for subscription in get_subscriptions(payment_type=RECURRING_PAYMENT_SUBSCRIPTION):
        due_date = _parse_date(subscription.get("next_renewal_date"))
        if due_date is not None and due_date <= through:
            items.append(
                {
                    "source": "subscription",
                    "id": subscription["id"],
                    "description": subscription["name"],
                    "amount": float(subscription.get("amount") or 0),
                    "due_date": due_date.isoformat(),
                    "days_until_due": (due_date - today).days,
                }
            )

    for plan in get_planned_expenses():
        due_date = _parse_date(plan.get("due_date"))
        if due_date is not None and due_date <= through:
            items.append(
                {
                    "source": "plan",
                    "id": plan["id"],
                    "description": plan["description"],
                    "amount": float(plan.get("amount") or 0),
                    "due_date": due_date.isoformat(),
                    "days_until_due": (due_date - today).days,
                }
            )

    items.sort(key=lambda item: (item["due_date"], item["description"]))
    return {
        "items": items,
        "pending_count": get_pending_transaction_count(),
    }


def _parse_date(value) -> date | None:
    try:
        return date.fromisoformat(str(value)) if value else None
    except ValueError:
        return None
