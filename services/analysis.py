from datetime import date, timedelta

from core.budget.db import get_month_budget, save_month_budget
from core.expense.db import get_active_months, get_active_years, get_period_data
from core.subscription.db import fixed_cost_for_month


def _month_range(month: str) -> tuple[str, str, int]:
    year, month_number = map(int, month.split("-"))
    first = date(year, month_number, 1)
    next_first = (
        date(year + 1, 1, 1) if month_number == 12 else date(year, month_number + 1, 1)
    )
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
            {**row, "total": _money(row.get("total"))}
            for row in data["expense_breakdown"]
        ],
        "income_breakdown": [
            {**row, "total": _money(row.get("total"))}
            for row in data["income_breakdown"]
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
        "fixed_monthly_cost": fixed_cost_for_month(selected)
        if granularity == "month"
        else None,
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
