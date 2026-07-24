import logging
from calendar import monthrange
from contextlib import closing
from datetime import date, timedelta

from core.constants import (
    RECURRING_PAYMENT_PREPAID,
    RECURRING_PAYMENT_SUBSCRIPTION,
    RENEWAL_MODE_FIXED_DAYS,
    RENEWAL_MODE_SAME_DAY,
    PLANNED_EXPENSE_STATUS_COMPLETED,
    PLANNED_EXPENSE_STATUS_OPEN,
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
    item["renewal_mode"] = item.get("renewal_mode") or RENEWAL_MODE_SAME_DAY
    item["monthly_equivalent"] = monthly_equivalent(item)
    return item


def monthly_equivalent(item: dict) -> float:
    amount = float(item.get("amount") or 0)
    payment_type = item.get("payment_type") or RECURRING_PAYMENT_SUBSCRIPTION

    if payment_type == RECURRING_PAYMENT_PREPAID:
        months = int(item.get("billing_interval_months") or 1)
        return amount / max(1, months)

    if item.get("renewal_mode") == RENEWAL_MODE_FIXED_DAYS:
        days = max(1, int(item.get("renewal_interval") or 1))
        return amount * (365.2425 / 12) / days

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
    renewal_mode: str = RENEWAL_MODE_SAME_DAY,
    renewal_interval: int | None = None,
    renewal_anchor_day: int | None = None,
    last_payment_date: str | None = None,
) -> int:
    amount_cents = to_cents(amount)
    with closing(_connect()) as conn:
        cur = conn.execute(
            """INSERT INTO subscriptions
               (name, vendor, amount, amount_cents, billing_cycle, billing_interval_months,
                start_date, next_renewal_date, end_date, category, subcategory,
                payment_method, auto_renew, status, notes, payment_type, transaction_id,
                renewal_mode, renewal_interval, renewal_anchor_day, last_payment_date)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""
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
                renewal_mode,
                renewal_interval,
                renewal_anchor_day,
                last_payment_date,
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
        "renewal_mode", "renewal_interval", "renewal_anchor_day", "last_payment_date",
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


def next_renewal_date(subscription: dict, payment_date: str) -> str:
    """Advance from the confirmed payment date without month-end drift."""
    paid = date.fromisoformat(payment_date)
    interval = max(1, int(subscription.get("renewal_interval") or 1))
    mode = subscription.get("renewal_mode") or RENEWAL_MODE_SAME_DAY
    if mode == RENEWAL_MODE_FIXED_DAYS:
        return (paid + timedelta(days=interval)).isoformat()

    anchor_day = int(subscription.get("renewal_anchor_day") or paid.day)
    month_index = paid.month - 1 + interval
    year = paid.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, min(anchor_day, monthrange(year, month)[1])).isoformat()


def record_subscription_payment(
    subscription_id: int,
    description: str,
    amount: float,
    payment_date: str,
    category: str | None,
    subcategory: str | None,
    notes: str | None,
    next_renewal_override: str | None = None,
    planned_expense_id: int | None = None,
) -> int:
    """Record a confirmed payment and advance its subscription in one transaction."""
    amount_cents = to_cents(amount)
    with closing(_connect()) as conn:
        raw_subscription = conn.execute(
            "SELECT * FROM subscriptions WHERE id = ?", (subscription_id,)
        ).fetchone()
        if raw_subscription is None:
            raise ValueError("订阅不存在")
        subscription = _normalize_subscription(raw_subscription)
        if subscription["payment_type"] != RECURRING_PAYMENT_SUBSCRIPTION:
            raise ValueError("只有订阅可以登记续费付款")

        cur = conn.execute(
            """INSERT INTO transactions
               (type, description, amount, amount_cents, date, category, subcategory,
                notes, subscription_id)
               VALUES ('支出', ?, ?, ?, ?, ?, ?, ?, ?)"""
            + returning_id_clause(),
            (
                description,
                amount_cents / 100,
                amount_cents,
                payment_date,
                category,
                subcategory,
                notes,
                subscription_id,
            ),
        )
        transaction_id = inserted_id(cur)
        next_date = next_renewal_override or next_renewal_date(subscription, payment_date)
        conn.execute(
            """UPDATE subscriptions
               SET last_payment_date = ?,
                   start_date = COALESCE(start_date, ?),
                   next_renewal_date = ?
               WHERE id = ?""",
            (payment_date, payment_date, next_date, subscription_id),
        )
        if planned_expense_id is not None:
            updated = conn.execute(
                """UPDATE planned_expenses
                   SET status = ?, transaction_id = ?
                   WHERE id = ? AND subscription_id = ? AND status = ?""",
                (
                    PLANNED_EXPENSE_STATUS_COMPLETED,
                    transaction_id,
                    planned_expense_id,
                    subscription_id,
                    PLANNED_EXPENSE_STATUS_OPEN,
                ),
            )
            if updated.rowcount != 1:
                raise ValueError("预计支出不存在或已处理")
        conn.commit()
        return transaction_id


def link_existing_transaction(
    subscription_id: int, transaction_id: int, payment_date: str | None = None
) -> None:
    """Explicitly link an existing expense to a subscription; never infer it."""
    with closing(_connect()) as conn:
        subscription_row = conn.execute(
            "SELECT * FROM subscriptions WHERE id = ?", (subscription_id,)
        ).fetchone()
        transaction = conn.execute(
            "SELECT * FROM transactions WHERE id = ?", (transaction_id,)
        ).fetchone()
        if subscription_row is None or transaction is None:
            raise ValueError("订阅或账目不存在")
        transaction_data = dict(transaction)
        if transaction_data.get("type") != "支出":
            raise ValueError("只能关联支出流水")
        paid = payment_date or transaction_data["date"]
        subscription = _normalize_subscription(subscription_row)
        conn.execute(
            "UPDATE transactions SET subscription_id = ? WHERE id = ?",
            (subscription_id, transaction_id),
        )
        conn.execute(
            """UPDATE subscriptions
               SET last_payment_date = ?,
                   start_date = COALESCE(start_date, ?),
                   next_renewal_date = ?
               WHERE id = ?""",
            (paid, paid, next_renewal_date(subscription, paid), subscription_id),
        )
        conn.commit()


def create_subscription_from_transaction(
    transaction_id: int,
    name: str,
    billing_cycle: str,
    billing_interval_months: int | None,
    next_renewal_date: str,
    renewal_mode: str,
    renewal_interval: int,
    renewal_anchor_day: int | None,
) -> int:
    """Use an existing expense as the first confirmed subscription payment."""
    with closing(_connect()) as conn:
        transaction = conn.execute(
            "SELECT * FROM transactions WHERE id = ?", (transaction_id,)
        ).fetchone()
        if transaction is None:
            raise ValueError("账目不存在")
        item = dict(transaction)
        if item.get("type") != "支出":
            raise ValueError("只有支出可以设为周期性付款")
        if item.get("subscription_id") is not None:
            raise ValueError("这笔支出已经关联周期性付款")

        amount_cents = int(
            item.get("amount_cents")
            if item.get("amount_cents") is not None
            else to_cents(item.get("amount") or 0)
        )
        cur = conn.execute(
            """INSERT INTO subscriptions
               (name, amount, amount_cents, billing_cycle,
                billing_interval_months, start_date, next_renewal_date,
                category, subcategory, auto_renew, status, notes, payment_type,
                transaction_id, renewal_mode, renewal_interval,
                renewal_anchor_day, last_payment_date)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?)"""
            + returning_id_clause(),
            (
                name,
                amount_cents / 100,
                amount_cents,
                billing_cycle,
                billing_interval_months,
                item["date"],
                next_renewal_date,
                item.get("category"),
                item.get("subcategory"),
                SUBSCRIPTION_STATUS_ACTIVE,
                item.get("notes"),
                RECURRING_PAYMENT_SUBSCRIPTION,
                transaction_id,
                renewal_mode,
                renewal_interval,
                renewal_anchor_day,
                item["date"],
            ),
        )
        subscription_id = inserted_id(cur)
        conn.execute(
            "UPDATE transactions SET subscription_id = ? WHERE id = ?",
            (subscription_id, transaction_id),
        )
        conn.commit()
        return subscription_id
