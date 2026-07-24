from contextlib import closing

from core.db import _connect, to_cents


def _amount_from_cents(value) -> float | None:
    return value / 100 if value is not None else None


def get_month_budget(month: str) -> dict:
    """Return the configured targets for one YYYY-MM month."""
    with closing(_connect()) as conn:
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

    with closing(_connect()) as conn:
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
