from contextlib import closing
from datetime import date, timedelta

from backend.constants import (
    RECURRING_PAYMENT_SUBSCRIPTION,
    REFUND_CATEGORY,
    TYPE_EXPENSE,
    TYPE_INCOME,
)
from backend.db import connect, to_cents
from backend.diet.store import get_meals
from backend.ledger.planning import fixed_cost_for_month, get_planned_expenses, get_subscriptions
from backend.ledger.transactions import (
    get_pending_transaction_count,
    get_transactions,
    normalize_transaction,
)


def _next_month(month_start: date) -> date:
    if month_start.month == 12:
        return date(month_start.year + 1, 1, 1)
    return date(month_start.year, month_start.month + 1, 1)


def _month_starts(start: str, months: int) -> list[str]:
    first = date.fromisoformat(start[:7] + "-01")
    values = []
    cur = first
    for _ in range(max(1, int(months or 1))):
        values.append(cur.isoformat())
        cur = _next_month(cur)
    return values


def _amortization_allocation_dates() -> list[str]:
    with closing(connect()) as conn:
        rows = conn.execute(
            f"""SELECT date, amortization_start, amortization_months
               FROM transactions
               WHERE type = '{TYPE_EXPENSE}'
                 AND COALESCE(amortization_months, 1) > 1"""
        ).fetchall()

    dates = []
    for raw in rows:
        row = dict(raw)
        dates.extend(
            _month_starts(
                row.get("amortization_start") or row.get("date"),
                row.get("amortization_months") or 1,
            )
        )
    return dates


def get_period_data(start_date: str, end_date: str, basis: str = "cash") -> dict:
    """Aggregate the same signed contributions used for transaction drilldown."""
    with closing(connect()) as conn:
        rows = conn.execute(
            "SELECT * FROM transactions WHERE type IN (?, ?) ORDER BY date, id",
            (TYPE_INCOME, TYPE_EXPENSE),
        ).fetchall()
    transactions = [normalize_transaction(row) for row in rows]
    by_id = {row["id"]: row for row in transactions}
    entries = []
    for row in transactions:
        if row["date"] > end_date:
            continue
        original = by_id.get(row.get("refund_for_id"))
        linked_refund = (
            row["type"] == TYPE_INCOME
            and row.get("category") == REFUND_CATEGORY
            and original is not None
            and original["type"] == TYPE_EXPENSE
        )
        bucket = "expense" if row["type"] == TYPE_EXPENSE or linked_refund else "income"
        category_source = original if linked_refund else row
        amount = float(row.get("amount") or 0)
        allocations = [(row["date"], amount)]
        if (
            basis == "amortized"
            and row["type"] == TYPE_EXPENSE
            and int(row.get("amortization_months") or 1) > 1
        ):
            months = int(row["amortization_months"])
            # Integer cents keep daily, category and detail totals consistent.
            cents, remainder = divmod(to_cents(amount), months)
            allocations = [
                (month, (cents + (index < remainder)) / 100)
                for index, month in enumerate(
                    _month_starts(row.get("amortization_start") or row["date"], months)
                )
            ]
        for allocation_date, allocation in allocations:
            if not start_date <= allocation_date <= end_date:
                continue
            entries.append(
                {
                    "id": row["id"],
                    "date": row["date"],
                    "allocation_date": allocation_date,
                    "description": row["description"],
                    "category": category_source.get("category") or "",
                    "subcategory": category_source.get("subcategory") or "",
                    "amount": amount,
                    "contribution": -allocation if linked_refund else allocation,
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
        cents = to_cents(entry["contribution"])
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
        if entry["contribution"] >= 0:
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


def get_active_years() -> list:
    sql = """SELECT DISTINCT strftime('%Y', date) as year
             FROM transactions
             ORDER BY year DESC"""
    with closing(connect()) as conn:
        rows = conn.execute(sql).fetchall()
    years = {r["year"] for r in rows}
    years.update(d[:4] for d in _amortization_allocation_dates())
    return sorted(years, reverse=True)


def get_active_months() -> list:
    sql = """SELECT DISTINCT strftime('%Y-%m', date) as month
             FROM transactions
             ORDER BY month DESC"""
    with closing(connect()) as conn:
        rows = conn.execute(sql).fetchall()
    months = {r["month"] for r in rows}
    months.update(d[:7] for d in _amortization_allocation_dates())
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
    first = date(year, month_number, 1)
    next_first = date(year + 1, 1, 1) if month_number == 12 else date(year, month_number + 1, 1)
    return (
        first.isoformat(),
        (next_first - timedelta(days=1)).isoformat(),
        (next_first - first).days,
    )


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


def get_expense_analysis(
    granularity: str,
    period: str | None,
    basis: str,
) -> dict:
    months = get_active_months()
    years = get_active_years()
    choices = months if granularity == "month" else years
    default = _default_month(months) if granularity == "month" else _default_year(years)
    selected = period if period in choices else default
    if selected is None:
        return {"months": months, "years": years, "selected_period": None}
    if granularity == "month":
        start, end, _ = _month_range(selected)
        timeline_months = []
    else:
        start, end = f"{selected}-01-01", f"{selected}-12-31"
        timeline_months = [
            f"{selected}-{number:02d}"
            for number in range(1, 13)
            if f"{selected}-{number:02d}" <= date.today().strftime("%Y-%m")
        ]
    end, days = _elapsed_range(start, end)
    timeline = []
    for item in timeline_months:
        item_start, item_end, _ = _month_range(item)
        item_end, _ = _elapsed_range(item_start, item_end)
        data = _period_data(item_start, item_end, basis)
        timeline.append(
            {
                "label": item if granularity == "month" else f"{int(item[-2:])}月",
                "income": data["income"],
                "expense": data["expense"],
            }
        )
    cash = _period_data(start, end, "cash")
    amortized = _period_data(start, end, "amortized")
    return {
        "months": months,
        "years": years,
        "selected_period": selected,
        "start_date": start,
        "end_date": end,
        "days": days,
        "current": cash if basis == "cash" else amortized,
        "cash_current": cash,
        "timeline": timeline,
        "fixed_monthly_cost": fixed_cost_for_month(selected) if granularity == "month" else None,
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
