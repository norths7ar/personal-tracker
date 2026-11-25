from calendar import monthrange
from collections.abc import Iterator
from contextlib import closing
from datetime import date, timedelta

from backend.constants import REFUND_CATEGORY, TYPE_EXPENSE, TYPE_INCOME
from backend.db import connect, to_cents
from backend.diet.store import get_meals
from backend.ledger.planning import get_planned_expenses, get_subscriptions
from backend.ledger.transactions import (
    get_pending_transaction_count,
    get_transactions,
    normalize_transaction,
)


def _coverage_months() -> Iterator[str]:
    with closing(connect()) as conn:
        rows = conn.execute(
            "SELECT coverage_start, coverage_end FROM transactions WHERE coverage_start IS NOT NULL"
        ).fetchall()
    for row in rows:
        start = date.fromisoformat(row["coverage_start"])
        end = date.fromisoformat(row["coverage_end"])
        first = start.year * 12 + start.month - 1
        last = end.year * 12 + end.month - 1
        for index in range(first, last + 1):
            year, month = divmod(index, 12)
            yield f"{year:04d}-{month + 1:02d}"


def _allocations_in_period(
    row: dict, start: date, end: date, basis: str
) -> Iterator[tuple[str, int]]:
    amount = row["amount_cents"]
    if basis != "amortized" or row["type"] != TYPE_EXPENSE or row["coverage_start"] is None:
        if start.isoformat() <= row["date"] <= end.isoformat():
            yield row["date"], amount
        return

    first_day = date.fromisoformat(row["coverage_start"])
    last_day = date.fromisoformat(row["coverage_end"])
    cents_per_day, remainder = divmod(amount, (last_day - first_day).days + 1)
    first_offset = (max(first_day, start) - first_day).days
    last_offset = (min(last_day, end) - first_day).days
    for offset in range(first_offset, last_offset + 1):
        day = first_day + timedelta(days=offset)
        yield day.isoformat(), cents_per_day + (offset < remainder)


def get_period_data(start_date: str, end_date: str, basis: str = "cash") -> dict:
    """Aggregate the same signed contributions used for transaction drilldown."""
    with closing(connect()) as conn:
        rows = conn.execute(
            "SELECT * FROM transactions WHERE type IN (?, ?) ORDER BY date, id",
            (TYPE_INCOME, TYPE_EXPENSE),
        ).fetchall()
    transactions = [normalize_transaction(row) for row in rows]
    by_id = {row["id"]: row for row in transactions}
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    entries = []
    for row in transactions:
        original = by_id.get(row.get("refund_for_id"))
        linked_refund = (
            row["type"] == TYPE_INCOME
            and row.get("category") == REFUND_CATEGORY
            and original is not None
            and original["type"] == TYPE_EXPENSE
        )
        bucket = "expense" if row["type"] == TYPE_EXPENSE or linked_refund else "income"
        category_source = original if linked_refund else row
        for allocation_date, allocation_cents in _allocations_in_period(row, start, end, basis):
            cents = -allocation_cents if linked_refund else allocation_cents
            entries.append(
                {
                    "id": row["id"],
                    "date": row["date"],
                    "allocation_date": allocation_date,
                    "description": row["description"],
                    "category": category_source.get("category") or "",
                    "subcategory": category_source.get("subcategory") or "",
                    "amount": row["amount"],
                    "contribution_cents": cents,
                    "type": row["type"],
                    "bucket": bucket,
                }
            )
    daily = {}
    breakdown = {"income": {}, "expense": {}}
    totals = {"income": 0, "expense": 0}
    counted_ids = {"income": {}, "expense": {}}
    for entry in entries:
        bucket = entry["bucket"]
        cents = entry.pop("contribution_cents")
        entry["contribution"] = cents / 100
        totals[bucket] += cents
        day = daily.setdefault(
            entry["allocation_date"],
            {
                "date": entry["allocation_date"],
                TYPE_INCOME: 0,
                TYPE_EXPENSE: 0,
            },
        )
        day[TYPE_INCOME if bucket == "income" else TYPE_EXPENSE] += cents
        key = (entry["category"], entry["subcategory"])
        group = breakdown[bucket].setdefault(
            key,
            {
                "category": key[0],
                "subcategory": key[1],
                "total": 0,
                "count": 0,
            },
        )
        group["total"] += cents
        ids = counted_ids[bucket].setdefault(key, set())
        if cents >= 0:
            ids.add(entry["id"])
        group["count"] = len(ids)
    return {
        "income": totals["income"] / 100,
        "expense": totals["expense"] / 100,
        "balance": (totals["income"] - totals["expense"]) / 100,
        "daily": [
            {
                "date": row["date"],
                TYPE_INCOME: row[TYPE_INCOME] / 100,
                TYPE_EXPENSE: row[TYPE_EXPENSE] / 100,
            }
            for row in sorted(daily.values(), key=lambda row: row["date"])
        ],
        **{
            f"{bucket}_breakdown": [
                {**row, "total": row["total"] / 100}
                for row in sorted(groups.values(), key=lambda row: row["total"], reverse=True)
            ]
            for bucket, groups in breakdown.items()
        },
        "entries": sorted(
            entries, key=lambda row: (row["allocation_date"], row["id"]), reverse=True
        ),
    }


def get_active_months() -> list[str]:
    sql = """SELECT DISTINCT strftime('%Y-%m', date) as month
             FROM transactions
             ORDER BY month DESC"""
    with closing(connect()) as conn:
        rows = conn.execute(sql).fetchall()
    months = {r["month"] for r in rows}
    months.update(_coverage_months())
    return sorted(months, reverse=True)


def _amount_from_cents(value) -> float | None:
    return value / 100 if value is not None else None


def get_month_budget(month: str) -> dict:
    """Return the configured targets for one YYYY-MM month."""
    with closing(connect()) as conn:
        row = conn.execute(
            """SELECT amortized_budget_cents, cash_budget_cents
               FROM budgets WHERE month = ?""",
            (month,),
        ).fetchone()

    if row is None:
        return {"amortized_total": None, "cash_total": None}
    return {
        "amortized_total": _amount_from_cents(row["amortized_budget_cents"]),
        "cash_total": _amount_from_cents(row["cash_budget_cents"]),
    }


def save_month_budget(
    month: str,
    amortized_total: float | None,
    cash_total: float | None,
) -> None:
    """Save the two optional total targets for one month."""
    amortized_cents = to_cents(amortized_total) if amortized_total is not None else None
    cash_cents = to_cents(cash_total) if cash_total is not None else None

    with closing(connect()) as conn:
        if amortized_cents is not None or cash_cents is not None:
            conn.execute(
                """INSERT INTO budgets
                   (month, amortized_budget_cents, cash_budget_cents)
                   VALUES (?, ?, ?)
                   ON CONFLICT(month) DO UPDATE SET
                       amortized_budget_cents = excluded.amortized_budget_cents,
                       cash_budget_cents = excluded.cash_budget_cents""",
                (month, amortized_cents, cash_cents),
            )
        else:
            conn.execute("DELETE FROM budgets WHERE month = ?", (month,))
        conn.commit()


def _month_range(month: str) -> tuple[str, str, int]:
    year, month_number = map(int, month.split("-"))
    days = monthrange(year, month_number)[1]
    return f"{month}-01", f"{month}-{days:02d}", days


def _period_data(start: str, end: str, basis: str) -> dict:
    data = get_period_data(start, end, basis)
    return {
        **data,
        "income": _money(data["income"]),
        "expense": _money(data["expense"]),
        "balance": _money(data["balance"]),
        "daily": [
            {
                "date": row["date"],
                "income": _money(row.get("收入")),
                "expense": _money(row.get("支出")),
            }
            for row in data["daily"]
        ],
        "expense_breakdown": [
            {**row, "total": _money(row.get("total"))} for row in data["expense_breakdown"]
        ],
        "income_breakdown": [
            {**row, "total": _money(row.get("total"))} for row in data["income_breakdown"]
        ],
    }


def _money(value) -> float:
    return round(float(value or 0), 2)


def _elapsed_range(start: str, end: str) -> tuple[str, int]:
    cutoff = min(date.fromisoformat(end), date.today())
    return cutoff.isoformat(), max(0, (cutoff - date.fromisoformat(start)).days + 1)


def _monthly_timeline(year: str, end: str, daily: list[dict]) -> list[dict]:
    totals = {
        f"{year}-{month:02d}": {"income": 0, "expense": 0}
        for month in range(1, 13)
        if f"{year}-{month:02d}" <= end[:7]
    }
    for day in daily:
        month = totals[day["date"][:7]]
        month["income"] += to_cents(day["income"])
        month["expense"] += to_cents(day["expense"])
    return [
        {
            "label": f"{int(month[-2:])}月",
            "income": amounts["income"] / 100,
            "expense": amounts["expense"] / 100,
        }
        for month, amounts in totals.items()
    ]


def get_expense_analysis(
    granularity: str,
    period: str | None,
    basis: str,
) -> dict:
    months = get_active_months()
    years = sorted({month[:4] for month in months}, reverse=True)
    choices = months if granularity == "month" else years
    default = _default_month(months) if granularity == "month" else _default_year(years)
    selected = period if period in choices else default
    if selected is None:
        return {"months": months, "years": years, "selected_period": None}
    if granularity == "month":
        start, full_end, total_days = _month_range(selected)
        elapsed_end, elapsed_days = _elapsed_range(start, full_end)
        cash = _period_data(start, elapsed_end, "cash")
        amortized = _period_data(start, full_end, "amortized")
        end = full_end
    else:
        start, full_end = f"{selected}-01-01", f"{selected}-12-31"
        end, elapsed_days = _elapsed_range(start, full_end)
        total_days = None
        cash = _period_data(start, end, "cash")
        amortized = _period_data(start, end, "amortized")
    current = cash if basis == "cash" else amortized
    return {
        "months": months,
        "years": years,
        "selected_period": selected,
        "start_date": start,
        "end_date": end,
        "days": elapsed_days,
        "total_days": total_days,
        "current": current,
        "cash_current": cash,
        "timeline": _monthly_timeline(selected, end, current["daily"])
        if granularity == "year"
        else [],
        "budget": get_month_budget(selected) if granularity == "month" else None,
        "cash_expense": cash["expense"] if granularity == "month" else None,
        "amortized_expense": amortized["expense"] if granularity == "month" else None,
    }


def update_month_budget(
    month: str, amortized_total: float | None, cash_total: float | None
) -> dict:
    if month not in get_active_months():
        raise ValueError("月份不在现有账目范围内")
    save_month_budget(month, amortized_total, cash_total)
    return get_month_budget(month)


def _default_month(months: list[str]) -> str | None:
    current = date.today().strftime("%Y-%m")
    return current if current in months else (months[0] if months else None)


def _default_year(years: list[str]) -> str | None:
    current = str(date.today().year)
    return current if current in years else (years[0] if years else None)


def get_home_reminders(
    today: date | None = None,
    lookahead_days: int = 3,
) -> dict:
    """Collect actionable items without creating or mutating financial records."""
    today = today or date.today()
    through = today + timedelta(days=max(0, lookahead_days))
    items = []

    for subscription in get_subscriptions():
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
                "description": meal["description"],
            }
            for meal in meals
        ],
    }
