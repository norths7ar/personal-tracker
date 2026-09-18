from calendar import monthrange
from contextlib import closing
from datetime import date, timedelta

from core.constants import (
    RECURRING_PAYMENT_PREPAID,
    RECURRING_PAYMENT_SUBSCRIPTION,
    RENEWAL_MODE_FIXED_DAYS,
    RENEWAL_MODE_SAME_DAY,
    SUBSCRIPTION_CYCLE_CUSTOM,
    SUBSCRIPTION_CYCLE_MONTHLY,
    SUBSCRIPTION_CYCLE_ONE_TIME,
    SUBSCRIPTION_CYCLE_QUARTERLY,
    SUBSCRIPTION_CYCLE_YEARLY,
    SUBSCRIPTION_STATUS_ACTIVE,
    TYPE_EXPENSE,
)
from core.db import _connect, to_cents
from core.expense.db import _insert_transaction


def _normalize_subscription(row) -> dict:
    item = dict(row)
    item["amount"] = item["amount_cents"] / 100
    item["auto_renew"] = bool(item.get("auto_renew"))
    item["payment_type"] = item.get("payment_type") or RECURRING_PAYMENT_SUBSCRIPTION
    item["renewal_mode"] = item.get("renewal_mode") or RENEWAL_MODE_SAME_DAY
    item["monthly_equivalent"] = monthly_equivalent(item)
    return item


def monthly_equivalent(item: dict) -> float:
    if item["payment_type"] == RECURRING_PAYMENT_PREPAID:
        return item["amount"] / item["billing_interval_months"]
    interval = item["renewal_interval"]
    if item["renewal_mode"] == RENEWAL_MODE_FIXED_DAYS:
        return item["amount"] * (365.2425 / 12) / interval
    return item["amount"] / interval


def cycle_from_months(months: int) -> tuple[str, int | None]:
    cycles = {
        1: SUBSCRIPTION_CYCLE_MONTHLY,
        3: SUBSCRIPTION_CYCLE_QUARTERLY,
        12: SUBSCRIPTION_CYCLE_YEARLY,
    }
    return (
        (cycles[months], None)
        if months in cycles
        else (SUBSCRIPTION_CYCLE_CUSTOM, months)
    )


def fixed_cost_for_month(month: str) -> float:
    """Return recurring and prepaid monthly cost effective in YYYY-MM."""
    month_start = date.fromisoformat(f"{month}-01")
    next_month = (
        date(month_start.year + 1, 1, 1)
        if month_start.month == 12
        else date(month_start.year, month_start.month + 1, 1)
    )
    month_end = next_month - timedelta(days=1)
    total = 0.0
    for item in get_subscriptions(include_inactive=True):
        start = (
            date.fromisoformat(str(item["start_date"])[:10])
            if item.get("start_date")
            else None
        )
        end = (
            date.fromisoformat(str(item["end_date"])[:10])
            if item.get("end_date")
            else None
        )
        if start and start > month_end:
            continue
        if end and end < month_start:
            continue

        if item.get("payment_type") == RECURRING_PAYMENT_PREPAID:
            if start is None:
                continue
            months = max(1, int(item.get("billing_interval_months") or 1))
            month_offset = (
                (month_start.year - start.year) * 12 + month_start.month - start.month
            )
            if not 0 <= month_offset < months:
                continue
        elif item.get("status") != SUBSCRIPTION_STATUS_ACTIVE and end is None:
            continue

        total += monthly_equivalent(item)
    return total


def _insert_subscription(
    conn,
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
    cur = conn.execute(
        """INSERT INTO subscriptions
           (name, vendor, amount, amount_cents, billing_cycle,
            billing_interval_months,
            start_date, next_renewal_date, end_date, category, subcategory,
            payment_method, auto_renew, status, notes, payment_type, transaction_id,
            renewal_mode, renewal_interval, renewal_anchor_day, last_payment_date)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
    return cur.lastrowid


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


def update_subscription(id_: int, **fields) -> None:
    allowed = {
        "name",
        "vendor",
        "amount",
        "billing_cycle",
        "billing_interval_months",
        "start_date",
        "next_renewal_date",
        "end_date",
        "category",
        "subcategory",
        "payment_method",
        "auto_renew",
        "status",
        "notes",
        "payment_type",
        "transaction_id",
        "renewal_mode",
        "renewal_interval",
        "renewal_anchor_day",
        "last_payment_date",
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
        conn.execute(
            "UPDATE transactions SET subscription_id = NULL WHERE subscription_id = ?",
            (id_,),
        )
        conn.execute(
            """UPDATE planned_expenses
               SET subscription_id = NULL WHERE subscription_id = ?""",
            (id_,),
        )
        conn.execute("DELETE FROM subscriptions WHERE id = ?", (id_,))
        conn.commit()


def delete_prepaid_subscription(id_: int, transaction_id: int) -> None:
    with closing(_connect()) as conn:
        linked = conn.execute(
            """SELECT 1 FROM subscriptions
               WHERE id = ? AND transaction_id = ? AND payment_type = ?""",
            (id_, transaction_id, RECURRING_PAYMENT_PREPAID),
        ).fetchone()
        if linked is None:
            raise ValueError("预付摊销与关联流水不匹配")
        conn.execute(
            """UPDATE transactions
               SET amortization_months = NULL,
                   amortization_start = NULL
               WHERE id = ?""",
            (transaction_id,),
        )
        conn.execute("DELETE FROM subscriptions WHERE id = ?", (id_,))
        conn.commit()


def _create_prepaid_with_transaction(
    conn,
    description: str,
    amount: float,
    payment_date: str,
    months: int,
    amortization_start: str,
    category: str | None,
    subcategory: str | None,
    notes: str | None,
) -> tuple[int, int]:
    transaction_id = _insert_transaction(
        conn,
        TYPE_EXPENSE,
        description,
        amount,
        payment_date,
        category=category,
        subcategory=subcategory,
        notes=notes,
        amortization_months=months,
        amortization_start=amortization_start,
    )
    transaction = dict(
        conn.execute(
            "SELECT * FROM transactions WHERE id = ?", (transaction_id,)
        ).fetchone()
    )
    subscription_id = _sync_prepaid_transaction(conn, transaction)
    return transaction_id, subscription_id


def _sync_prepaid_transaction(conn, transaction: dict) -> int | None:
    """Keep both prepaid entry points attached to the same actual payment."""
    existing = conn.execute(
        "SELECT id FROM subscriptions WHERE transaction_id = ? AND payment_type = ?",
        (transaction["id"], RECURRING_PAYMENT_PREPAID),
    ).fetchone()
    if transaction["amortization_months"] is None:
        if existing:
            conn.execute("DELETE FROM subscriptions WHERE id = ?", (existing["id"],))
        return None
    if transaction["type"] != TYPE_EXPENSE:
        raise ValueError("预付摊销关联流水必须保持为支出")
    fields = {
        "name": transaction["description"],
        "amount": transaction["amount"],
        "billing_interval_months": transaction["amortization_months"],
        "start_date": transaction["amortization_start"],
        "category": transaction["category"],
        "subcategory": transaction["subcategory"],
        "notes": transaction["notes"],
    }
    if existing is None:
        return _insert_subscription(
            conn,
            **fields,
            billing_cycle=SUBSCRIPTION_CYCLE_ONE_TIME,
            auto_renew=False,
            payment_type=RECURRING_PAYMENT_PREPAID,
            transaction_id=transaction["id"],
        )
    fields["amount_cents"] = transaction["amount_cents"]
    set_clause = ", ".join(f"{field} = ?" for field in fields)
    conn.execute(
        f"UPDATE subscriptions SET {set_clause} WHERE id = ?",
        [*fields.values(), existing["id"]],
    )
    return existing["id"]


def update_prepaid_with_transaction(
    subscription_id: int,
    transaction_id: int,
    description: str,
    months: int,
    amortization_start: str,
    category: str | None,
    subcategory: str | None,
    notes: str | None,
) -> None:
    """Edit the actual payment and its management record in one transaction."""
    from core.expense.db import _update_transaction

    with closing(_connect()) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        linked = conn.execute(
            """SELECT 1 FROM subscriptions
               WHERE id = ? AND transaction_id = ? AND payment_type = ?""",
            (subscription_id, transaction_id, RECURRING_PAYMENT_PREPAID),
        ).fetchone()
        if linked is None:
            raise ValueError("预付摊销与关联流水不匹配")
        _update_transaction(
            conn,
            transaction_id,
            {
                "description": description,
                "amortization_months": months,
                "amortization_start": amortization_start,
                "category": category,
                "subcategory": subcategory,
                "notes": notes,
            },
        )


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


def _record_subscription_payment(
    conn,
    subscription_id: int,
    description: str,
    amount: float,
    payment_date: str,
    category: str | None,
    subcategory: str | None,
    notes: str | None,
) -> int:
    amount_cents = to_cents(amount)
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
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            TYPE_EXPENSE,
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
    transaction_id = cur.lastrowid
    next_date = next_renewal_date(subscription, payment_date)
    conn.execute(
        """UPDATE subscriptions
           SET last_payment_date = ?,
               start_date = COALESCE(start_date, ?),
               next_renewal_date = ?
           WHERE id = ?""",
        (payment_date, payment_date, next_date, subscription_id),
    )
    return transaction_id


def _create_subscription_from_transaction(
    conn,
    transaction_id: int,
    name: str,
    next_renewal_date: str,
    renewal_mode: str,
    renewal_interval: int,
    renewal_anchor_day: int | None,
) -> int:
    transaction = conn.execute(
        "SELECT * FROM transactions WHERE id = ?", (transaction_id,)
    ).fetchone()
    if transaction is None:
        raise ValueError("账目不存在")
    item = dict(transaction)
    if item.get("type") != TYPE_EXPENSE:
        raise ValueError("只有支出可以设为周期性付款")
    if item.get("subscription_id") is not None:
        raise ValueError("这笔支出已经关联周期性付款")

    amount_cents = item["amount_cents"]
    billing_cycle, billing_interval_months = cycle_from_months(renewal_interval)
    cur = conn.execute(
        """INSERT INTO subscriptions
           (name, amount, amount_cents, billing_cycle,
            billing_interval_months, start_date, next_renewal_date,
            category, subcategory, auto_renew, status, notes, payment_type,
            transaction_id, renewal_mode, renewal_interval,
            renewal_anchor_day, last_payment_date)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
    subscription_id = cur.lastrowid
    conn.execute(
        "UPDATE transactions SET subscription_id = ? WHERE id = ?",
        (subscription_id, transaction_id),
    )
    return subscription_id
