from calendar import isleap
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


def _previous_month(month: str) -> str:
    year, month_number = map(int, month.split("-"))
    return f"{year - 1}-12" if month_number == 1 else f"{year}-{month_number - 1:02d}"


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


def get_expense_analysis(
    granularity: str,
    period: str | None,
    basis: str,
) -> dict:
    months = get_active_months()
    years = get_active_years()
    if granularity == "month":
        selected = period if period in months else _default_month(months)
        if selected is None:
            return {"months": [], "years": years, "selected_period": None}
        start, end, days = _month_range(selected)
        previous_start, previous_end, _ = _month_range(_previous_month(selected))
        recent = months[:12][::-1]
        timeline = []
        for item in recent:
            item_start, item_end, _ = _month_range(item)
            data = _period_data(item_start, item_end, basis)
            timeline.append(
                {"label": item, "income": data["income"], "expense": data["expense"]}
            )
        cash_current = _period_data(start, end, "cash")
        cash_previous = _period_data(previous_start, previous_end, "cash")
        return {
            "months": months,
            "years": years,
            "selected_period": selected,
            "days": days,
            "current": _period_data(start, end, basis),
            "previous": _period_data(previous_start, previous_end, basis),
            "cash_current": cash_current,
            "cash_previous": cash_previous,
            "timeline": timeline,
            "comparison": [],
            "fixed_monthly_cost": fixed_cost_for_month(selected),
            "budget": get_month_budget(selected),
            "cash_expense": cash_current["expense"],
            "amortized_expense": _period_data(start, end, "amortized")["expense"],
        }

    selected = period if period in years else _default_year(years)
    if selected is None:
        return {"months": months, "years": [], "selected_period": None}
    previous_year = str(int(selected) - 1)
    start, end = f"{selected}-01-01", f"{selected}-12-31"
    previous_start, previous_end = f"{previous_year}-01-01", f"{previous_year}-12-31"
    timeline = []
    for month_number in range(1, 13):
        item = f"{selected}-{month_number:02d}"
        item_start, item_end, _ = _month_range(item)
        data = _period_data(item_start, item_end, basis)
        timeline.append(
            {
                "label": f"{month_number}月",
                "income": data["income"],
                "expense": data["expense"],
            }
        )
    comparison = []
    for year in years[::-1]:
        data = _period_data(f"{year}-01-01", f"{year}-12-31", basis)
        comparison.append(
            {"label": year, "income": data["income"], "expense": data["expense"]}
        )
    return {
        "months": months,
        "years": years,
        "selected_period": selected,
        "days": 366 if isleap(int(selected)) else 365,
        "current": _period_data(start, end, basis),
        "previous": _period_data(previous_start, previous_end, basis),
        "cash_current": _period_data(start, end, "cash"),
        "cash_previous": _period_data(previous_start, previous_end, "cash"),
        "timeline": timeline,
        "comparison": comparison,
        "fixed_monthly_cost": None,
        "budget": None,
        "cash_expense": None,
        "amortized_expense": None,
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
