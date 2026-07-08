import logging
from contextlib import closing

from core.constants import (
    RECURRING_PAYMENT_PREPAID,
    RECURRING_PAYMENT_SUBSCRIPTION,
    SUBSCRIPTION_CYCLE_CUSTOM,
    SUBSCRIPTION_CYCLE_MONTHLY,
    SUBSCRIPTION_CYCLE_ONE_TIME,
    SUBSCRIPTION_CYCLE_QUARTERLY,
    SUBSCRIPTION_CYCLE_YEARLY,
    SUBSCRIPTION_STATUS_ACTIVE,
)
from core.db import _connect, inserted_id, returning_id_clause, to_cents


def _normalize_subscription(row) -> dict:
    item = dict(row)
    if item.get("amount_cents") is not None:
        item["amount"] = item["amount_cents"] / 100
    item["auto_renew"] = bool(item.get("auto_renew"))
    item["payment_type"] = item.get("payment_type") or RECURRING_PAYMENT_SUBSCRIPTION
    item["monthly_equivalent"] = monthly_equivalent(item)
    return item


def monthly_equivalent(item: dict) -> float:
    amount = float(item.get("amount") or 0)
    payment_type = item.get("payment_type") or RECURRING_PAYMENT_SUBSCRIPTION

    if payment_type == RECURRING_PAYMENT_PREPAID:
        months = int(item.get("billing_interval_months") or 1)
        return amount / max(1, months)

    cycle = item.get("billing_cycle")
    if cycle == SUBSCRIPTION_CYCLE_MONTHLY:
        return amount
    if cycle == SUBSCRIPTION_CYCLE_QUARTERLY:
        return amount / 3
    if cycle == SUBSCRIPTION_CYCLE_YEARLY:
        return amount / 12
    if cycle == SUBSCRIPTION_CYCLE_CUSTOM:
        months = int(item.get("billing_interval_months") or 1)
        return amount / max(1, months)
    if cycle == SUBSCRIPTION_CYCLE_ONE_TIME:
        return 0.0
    logging.getLogger(__name__).warning("monthly_equivalent: unknown billing_cycle %r, defaulting to 0", cycle)
    return 0.0


def add_subscription(
    name: str,
    amount: float,
    billing_cycle: str,
    vendor: str | None = None,
    billing_interval_months: int | None = None,
    start_date: str | None = None,
    next_renewal_date: str | None = None,
    end_date: str | None = None,
    category: str | None = None,
    subcategory: str | None = None,
    payment_method: str | None = None,
    auto_renew: bool = True,
    status: str = SUBSCRIPTION_STATUS_ACTIVE,
    notes: str | None = None,
    payment_type: str = RECURRING_PAYMENT_SUBSCRIPTION,
    transaction_id: int | None = None,
) -> int:
    amount_cents = to_cents(amount)
    with closing(_connect()) as conn:
        cur = conn.execute(
            """INSERT INTO subscriptions
               (name, vendor, amount, amount_cents, billing_cycle, billing_interval_months,
                start_date, next_renewal_date, end_date, category, subcategory,
                payment_method, auto_renew, status, notes, payment_type, transaction_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""
            + returning_id_clause(),
            (
                name,
                vendor,
                amount_cents / 100,
                amount_cents,
                billing_cycle,
                billing_interval_months,
                start_date,
                next_renewal_date,
                end_date,
                category,
                subcategory,
                payment_method,
                1 if auto_renew else 0,
                status,
                notes,
                payment_type,
                transaction_id,
            ),
        )
        subscription_id = inserted_id(cur)
        conn.commit()
        return subscription_id


def get_subscriptions(
    include_inactive: bool = False,
    payment_type: str | None = None,
    limit: int = 500,
) -> list[dict]:
    query = "SELECT * FROM subscriptions WHERE 1=1"
    params: list = []
    if not include_inactive:
        query += " AND status = ?"
        params.append(SUBSCRIPTION_STATUS_ACTIVE)
    if payment_type is not None:
        query += " AND payment_type = ?"
        params.append(payment_type)
    query += " ORDER BY next_renewal_date IS NULL, next_renewal_date, name LIMIT ?"
    params.append(limit)
    with closing(_connect()) as conn:
        rows = conn.execute(query, params).fetchall()
    return [_normalize_subscription(row) for row in rows]


def get_upcoming_subscriptions(start_date: str, end_date: str) -> list[dict]:
    with closing(_connect()) as conn:
        rows = conn.execute(
            """SELECT * FROM subscriptions
               WHERE status = ?
                 AND payment_type = ?
                 AND auto_renew = 1
                 AND next_renewal_date IS NOT NULL
                 AND next_renewal_date >= ?
                 AND next_renewal_date <= ?
               ORDER BY next_renewal_date, amount_cents DESC, name""",
            (SUBSCRIPTION_STATUS_ACTIVE, RECURRING_PAYMENT_SUBSCRIPTION, start_date, end_date),
        ).fetchall()
    return [_normalize_subscription(row) for row in rows]


def update_subscription(id_: int, **fields) -> None:
    allowed = {
        "name", "vendor", "amount", "billing_cycle", "billing_interval_months",
        "start_date", "next_renewal_date", "end_date", "category", "subcategory",
        "payment_method", "auto_renew", "status", "notes", "payment_type", "transaction_id",
    }
    updates = {key: value for key, value in fields.items() if key in allowed}
    if not updates:
        return
    if "amount" in updates:
        amount_cents = to_cents(updates["amount"])
        updates["amount"] = amount_cents / 100
        updates["amount_cents"] = amount_cents
    if "auto_renew" in updates:
        updates["auto_renew"] = 1 if updates["auto_renew"] else 0
    set_clause = ", ".join(f"{key} = ?" for key in updates)
    with closing(_connect()) as conn:
        conn.execute(
            f"UPDATE subscriptions SET {set_clause} WHERE id = ?",
            [*updates.values(), id_],
        )
        conn.commit()


def delete_subscription(id_: int) -> None:
    with closing(_connect()) as conn:
        conn.execute("DELETE FROM subscriptions WHERE id = ?", (id_,))
        conn.commit()


def delete_prepaid_subscription(id_: int, transaction_id: int) -> None:
    with closing(_connect()) as conn:
        conn.execute(
            """UPDATE transactions
               SET amortization_months = NULL,
                   amortization_start = NULL
               WHERE id = ?""",
            (transaction_id,),
        )
        conn.execute("DELETE FROM subscriptions WHERE id = ?", (id_,))
        conn.commit()
