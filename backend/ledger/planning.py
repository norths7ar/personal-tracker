from calendar import monthrange
from contextlib import closing
from datetime import date, timedelta

from backend.constants import (
    PLANNED_EXPENSE_STATUS_COMPLETED,
    PLANNED_EXPENSE_STATUS_OPEN,
    RENEWAL_MODE_FIXED_DAYS,
    RENEWAL_MODE_SAME_DAY,
    SUBSCRIPTION_STATUS_ACTIVE,
    TYPE_EXPENSE,
)
from backend.db import connect, execute_idempotent, to_cents
from backend.ledger.transactions import (
    TransactionConflict,
    TransactionNotFound,
    get_transaction,
    insert_transaction,
)
from backend.ledger.transactions import update_transaction as write_transaction


def _normalize_subscription(row) -> dict:
    item = dict(row)
    item["amount"] = item["amount_cents"] / 100
    item["auto_renew"] = bool(item.get("auto_renew"))
    item["renewal_mode"] = item.get("renewal_mode") or RENEWAL_MODE_SAME_DAY
    return item


def monthly_equivalent(item: dict) -> float:
    interval = item["renewal_interval"] or 1
    if item["renewal_mode"] == RENEWAL_MODE_FIXED_DAYS:
        return item["amount"] * (365.2425 / 12) / interval
    return item["amount"] / interval


def fixed_cost_for_month(month: str) -> float:
    """Return the monthly-equivalent recurring payment reference for YYYY-MM."""
    month_start = date.fromisoformat(f"{month}-01")
    month_end = month_start.replace(day=monthrange(month_start.year, month_start.month)[1])
    total = 0.0
    for item in get_subscriptions(include_inactive=True):
        start = date.fromisoformat(str(item["start_date"])[:10]) if item.get("start_date") else None
        end = date.fromisoformat(str(item["end_date"])[:10]) if item.get("end_date") else None
        if start and start > month_end:
            continue
        if end and end < month_start:
            continue

        if item.get("status") != SUBSCRIPTION_STATUS_ACTIVE and end is None:
            continue

        total += monthly_equivalent(item)
    return total


def insert_subscription(
    conn,
    name: str,
    amount: float,
    vendor: str | None = None,
    start_date: str | None = None,
    next_renewal_date: str | None = None,
    end_date: str | None = None,
    category: str | None = None,
    subcategory: str | None = None,
    payment_method: str | None = None,
    auto_renew: bool = True,
    status: str = SUBSCRIPTION_STATUS_ACTIVE,
    notes: str | None = None,
    renewal_mode: str = RENEWAL_MODE_SAME_DAY,
    renewal_interval: int | None = None,
    renewal_anchor_day: int | None = None,
    last_payment_date: str | None = None,
    coverage_unit: str | None = None,
    coverage_interval: int | None = None,
) -> int:
    amount_cents = to_cents(amount)
    cur = conn.execute(
        """INSERT INTO subscriptions
           (name, vendor, amount, amount_cents,
            start_date, next_renewal_date, end_date, category, subcategory,
            payment_method, auto_renew, status, notes, renewal_mode,
            renewal_interval, renewal_anchor_day, last_payment_date,
            coverage_unit, coverage_interval)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            name,
            vendor,
            amount_cents / 100,
            amount_cents,
            start_date,
            next_renewal_date,
            end_date,
            category,
            subcategory,
            payment_method,
            1 if auto_renew else 0,
            status,
            notes,
            renewal_mode,
            renewal_interval,
            renewal_anchor_day,
            last_payment_date,
            coverage_unit,
            coverage_interval,
        ),
    )
    return cur.lastrowid


def get_subscriptions(
    include_inactive: bool = False,
    limit: int = 500,
) -> list[dict]:
    query = "SELECT * FROM subscriptions WHERE 1=1"
    params: list = []
    if not include_inactive:
        query += " AND status = ?"
        params.append(SUBSCRIPTION_STATUS_ACTIVE)
    query += " ORDER BY next_renewal_date IS NULL, next_renewal_date, name LIMIT ?"
    params.append(limit)
    with closing(connect()) as conn:
        rows = conn.execute(query, params).fetchall()
    return [_normalize_subscription(row) for row in rows]


def update_subscription(id_: int, **fields) -> None:
    allowed = {
        "name",
        "vendor",
        "amount",
        "start_date",
        "next_renewal_date",
        "end_date",
        "category",
        "subcategory",
        "payment_method",
        "auto_renew",
        "status",
        "notes",
        "renewal_mode",
        "renewal_interval",
        "renewal_anchor_day",
        "last_payment_date",
        "coverage_unit",
        "coverage_interval",
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
    with closing(connect()) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        current = conn.execute(
            "SELECT next_renewal_date, renewal_mode, renewal_anchor_day FROM subscriptions "
            "WHERE id = ?",
            (id_,),
        ).fetchone()
        if current is None:
            raise ValueError("预计支出不存在或已处理")
        if (
            updates.get("next_renewal_date") == current["next_renewal_date"]
            and updates.get("renewal_mode") == current["renewal_mode"]
            and current["renewal_anchor_day"] is not None
        ):
            updates.pop("renewal_anchor_day", None)
        set_clause = ", ".join(f"{key} = ?" for key in updates)
        conn.execute(
            f"UPDATE subscriptions SET {set_clause} WHERE id = ?",
            [*updates.values(), id_],
        )


def delete_subscription(id_: int) -> None:
    with closing(connect()) as conn:
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


def next_renewal_date(subscription: dict, payment_date: str) -> str:
    """Advance from the confirmed payment date without month-end drift."""
    paid = date.fromisoformat(payment_date)
    interval = max(1, int(subscription.get("renewal_interval") or 1))
    mode = subscription.get("renewal_mode") or RENEWAL_MODE_SAME_DAY
    if mode == RENEWAL_MODE_FIXED_DAYS:
        return _add_days(paid, interval).isoformat()

    anchor_day = int(subscription.get("renewal_anchor_day") or paid.day)
    return _add_months(paid, interval, anchor_day).isoformat()


def _add_months(start: date, months: int, anchor_day: int) -> date:
    month_index = start.month - 1 + months
    year = start.year + month_index // 12
    month = month_index % 12 + 1
    if year > date.max.year:
        raise ValueError("日期超出 YYYY-MM-DD 的范围")
    return date(year, month, min(anchor_day, monthrange(year, month)[1]))


def _add_days(start: date, days: int) -> date:
    try:
        return start + timedelta(days=days)
    except OverflowError as exc:
        raise ValueError("日期超出 YYYY-MM-DD 的范围") from exc


def _coverage_for_due_date(
    due_date: str | None, unit: str | None, interval: int | None
) -> tuple[str | None, str | None]:
    if unit is None and interval is None:
        return None, None
    if unit not in {"months", "days"} or interval is None or interval < 1:
        raise ValueError("生效期长度必须同时设置单位和正整数")
    if due_date is None:
        raise ValueError("自动生效期需要计划付款日")

    start = date.fromisoformat(due_date)
    if unit == "months":
        end = _add_months(start, interval, start.day) - timedelta(days=1)
    else:
        end = _add_days(start, interval - 1)
    return start.isoformat(), end.isoformat()


def record_subscription_payment(
    conn,
    subscription_id: int,
    description: str,
    amount: float,
    payment_date: str,
    category: str | None,
    subcategory: str | None,
    notes: str | None,
) -> int:
    raw_subscription = conn.execute(
        "SELECT * FROM subscriptions WHERE id = ?", (subscription_id,)
    ).fetchone()
    if raw_subscription is None:
        raise ValueError("订阅不存在")
    subscription = _normalize_subscription(raw_subscription)
    start, end = _coverage_for_due_date(
        subscription["next_renewal_date"],
        subscription["coverage_unit"],
        subscription["coverage_interval"],
    )
    next_date = next_renewal_date(subscription, payment_date)
    transaction_id = insert_transaction(
        conn,
        TYPE_EXPENSE,
        description,
        amount,
        payment_date,
        category=category,
        subcategory=subcategory,
        notes=notes,
        coverage_start=start,
        coverage_end=end,
        subscription_id=subscription_id,
    )
    conn.execute(
        """UPDATE subscriptions
           SET last_payment_date = ?,
               start_date = COALESCE(start_date, ?),
               next_renewal_date = ?
           WHERE id = ?""",
        (payment_date, payment_date, next_date, subscription_id),
    )
    return transaction_id


def create_subscription_from_transaction(
    conn,
    transaction_id: int,
    name: str,
    next_renewal_date: str,
    renewal_mode: str,
    renewal_interval: int,
    renewal_anchor_day: int | None,
    coverage_unit: str | None = None,
    coverage_interval: int | None = None,
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

    _coverage_for_due_date(next_renewal_date, coverage_unit, coverage_interval)
    subscription_id = insert_subscription(
        conn,
        name,
        item["amount_cents"] / 100,
        start_date=item["date"],
        next_renewal_date=next_renewal_date,
        category=item.get("category"),
        subcategory=item.get("subcategory"),
        notes=item.get("notes"),
        renewal_mode=renewal_mode,
        renewal_interval=renewal_interval,
        renewal_anchor_day=renewal_anchor_day,
        last_payment_date=item["date"],
        coverage_unit=coverage_unit,
        coverage_interval=coverage_interval,
    )
    conn.execute(
        "UPDATE transactions SET subscription_id = ? WHERE id = ?",
        (subscription_id, transaction_id),
    )
    return subscription_id


def _normalize(row) -> dict:
    item = dict(row)
    item["amount"] = item["amount_cents"] / 100
    return item


def insert_planned_expense(
    conn,
    description: str,
    amount: float,
    due_date: str | None = None,
    category: str | None = None,
    subcategory: str | None = None,
    notes: str | None = None,
) -> int:
    amount_cents = to_cents(amount)
    cur = conn.execute(
        """INSERT INTO planned_expenses
           (description, amount, amount_cents, due_date, category, subcategory,
            notes, status)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            description,
            amount_cents / 100,
            amount_cents,
            due_date,
            category,
            subcategory,
            notes,
            PLANNED_EXPENSE_STATUS_OPEN,
        ),
    )
    return cur.lastrowid


def get_planned_expenses(include_closed: bool = False, limit: int = 500) -> list[dict]:
    query = "SELECT * FROM planned_expenses"
    params: list = []
    if not include_closed:
        query += " WHERE status = ?"
        params.append(PLANNED_EXPENSE_STATUS_OPEN)
    query += " ORDER BY due_date IS NULL, due_date, created_at DESC LIMIT ?"
    params.append(limit)
    with closing(connect()) as conn:
        rows = conn.execute(query, params).fetchall()
    return [_normalize(row) for row in rows]


def update_planned_expense(id_: int, **fields) -> None:
    allowed = {
        "description",
        "amount",
        "due_date",
        "category",
        "subcategory",
        "notes",
    }
    updates = {key: value for key, value in fields.items() if key in allowed}
    if not updates:
        return
    if "amount" in updates:
        amount_cents = to_cents(updates["amount"])
        updates["amount"] = amount_cents / 100
        updates["amount_cents"] = amount_cents
    set_clause = ", ".join(f"{key} = ?" for key in updates)
    with closing(connect()) as conn:
        conn.execute(
            f"""UPDATE planned_expenses
                SET {set_clause}
                WHERE id = ? AND status = ?""",
            [*updates.values(), id_, PLANNED_EXPENSE_STATUS_OPEN],
        )
        conn.commit()


def delete_planned_expense(id_: int) -> None:
    with closing(connect()) as conn:
        conn.execute(
            "DELETE FROM planned_expenses WHERE id = ? AND status = ?",
            (id_, PLANNED_EXPENSE_STATUS_OPEN),
        )
        conn.commit()


def confirm_planned_expense(
    conn,
    id_: int,
    description: str,
    amount: float,
    date_: str,
    category: str | None,
    subcategory: str | None,
    notes: str | None,
) -> int:
    plan = conn.execute(
        "SELECT * FROM planned_expenses WHERE id = ? AND status = ?",
        (id_, PLANNED_EXPENSE_STATUS_OPEN),
    ).fetchone()
    if plan is None:
        raise ValueError("预计支出不存在或已处理")
    if dict(plan).get("subscription_id") is not None:
        raise ValueError("订阅预计支出必须通过订阅付款流程确认")

    transaction_id = insert_transaction(
        conn,
        TYPE_EXPENSE,
        description,
        amount,
        date_,
        category=category,
        subcategory=subcategory,
        notes=notes,
    )
    conn.execute(
        """UPDATE planned_expenses
           SET status = ?, transaction_id = ? WHERE id = ?""",
        (PLANNED_EXPENSE_STATUS_COMPLETED, transaction_id, id_),
    )
    return transaction_id


def list_plans() -> dict[str, list[dict]]:
    expected = []
    for item in get_subscriptions():
        expected.append(_expected_subscription(item))
    for item in get_planned_expenses():
        expected.append(_expected_plan(item))
    expected.sort(
        key=lambda item: (
            item["next_date"] is None,
            item["next_date"] or "",
            item["description"],
        )
    )
    return {"expected": expected}


def _recurring_fields(payload: dict) -> dict:
    due = payload.get("due_date")
    if due is None:
        raise ValueError("周期性付款必须设置付款日")
    unit, interval = payload.get("coverage_unit"), payload.get("coverage_interval")
    _coverage_for_due_date(due, unit, interval)
    mode = payload["renewal_mode"]
    return {
        "next_renewal_date": due,
        "renewal_mode": mode,
        "renewal_interval": payload["renewal_interval"],
        "renewal_anchor_day": date.fromisoformat(due).day
        if mode == RENEWAL_MODE_SAME_DAY
        else None,
        "coverage_unit": unit,
        "coverage_interval": interval,
    }


def _validate_one_time_plan(payload: dict) -> None:
    if payload.get("coverage_unit") is not None or payload.get("coverage_interval") is not None:
        raise ValueError("只有周期性付款可以设置自动生效期")


def create_expected(payload: dict, idempotency_key: str) -> dict:
    def insert(conn) -> dict:
        if payload["recurring"]:
            record_id = insert_subscription(
                conn,
                name=payload["description"],
                amount=payload["amount"],
                category=payload.get("category"),
                subcategory=payload.get("subcategory"),
                auto_renew=True,
                notes=payload.get("notes"),
                **_recurring_fields(payload),
            )
            return {"id": record_id, "source": "subscription"}
        _validate_one_time_plan(payload)
        record_id = insert_planned_expense(
            conn,
            payload["description"],
            payload["amount"],
            payload.get("due_date"),
            payload.get("category"),
            payload.get("subcategory"),
            payload.get("notes"),
        )
        return {"id": record_id, "source": "plan"}

    result, duplicate = execute_idempotent("create_expected", idempotency_key, payload, insert)
    return {**result, "duplicate": duplicate}


def update_expected(source: str, record_id: int, payload: dict) -> None:
    _find_expected(source, record_id)
    if source == "subscription":
        update_subscription(
            record_id,
            name=payload["description"],
            amount=payload["amount"],
            category=payload.get("category"),
            subcategory=payload.get("subcategory"),
            notes=payload.get("notes"),
            **_recurring_fields(payload),
        )
        return
    _validate_one_time_plan(payload)
    update_planned_expense(
        record_id,
        description=payload["description"],
        amount=payload["amount"],
        due_date=payload.get("due_date"),
        category=payload.get("category"),
        subcategory=payload.get("subcategory"),
        notes=payload.get("notes"),
    )


def confirm_expected(source: str, record_id: int, payload: dict, idempotency_key: str) -> dict:
    def insert(conn) -> dict:
        if source == "subscription":
            transaction_id = record_subscription_payment(
                conn,
                record_id,
                payload["description"],
                payload["amount"],
                payload["payment_date"],
                payload.get("category"),
                payload.get("subcategory"),
                payload.get("notes"),
            )
        else:
            transaction_id = confirm_planned_expense(
                conn,
                record_id,
                payload["description"],
                payload["amount"],
                payload["payment_date"],
                payload.get("category"),
                payload.get("subcategory"),
                payload.get("notes"),
            )
        return {"transaction_id": transaction_id}

    result, duplicate = execute_idempotent(
        f"confirm_expected_{source}_{record_id}", idempotency_key, payload, insert
    )
    return {**result, "duplicate": duplicate}


def delete_expected(source: str, record_id: int) -> None:
    _find_expected(source, record_id)
    if source == "subscription":
        delete_subscription(record_id)
    else:
        delete_planned_expense(record_id)


def _find_expected(source: str, record_id: int) -> dict:
    records = list_plans()["expected"]
    record = next(
        (item for item in records if item["source"] == source and item["id"] == record_id),
        None,
    )
    if record is None:
        raise ValueError("预计支出不存在或已处理")
    return record


def _expected_subscription(item: dict) -> dict:
    interval = max(1, int(item.get("renewal_interval") or 1))
    mode = item.get("renewal_mode") or RENEWAL_MODE_SAME_DAY
    return {
        "id": item["id"],
        "source": "subscription",
        "description": item["name"],
        "amount": item["amount"],
        "next_date": item.get("next_renewal_date"),
        "cycle": (f"每{interval}天" if mode == RENEWAL_MODE_FIXED_DAYS else _month_cycle(interval)),
        "category": item.get("category"),
        "subcategory": item.get("subcategory"),
        "notes": item.get("notes"),
        "renewal_mode": mode,
        "renewal_interval": interval,
        "coverage_unit": item.get("coverage_unit"),
        "coverage_interval": item.get("coverage_interval"),
        "state": _due_state(item.get("next_renewal_date")),
    }


def _expected_plan(item: dict) -> dict:
    return {
        "id": item["id"],
        "source": "plan",
        "description": item["description"],
        "amount": item["amount"],
        "next_date": item.get("due_date"),
        "cycle": "一次性",
        "category": item.get("category"),
        "subcategory": item.get("subcategory"),
        "notes": item.get("notes"),
        "renewal_mode": None,
        "renewal_interval": None,
        "coverage_unit": None,
        "coverage_interval": None,
        "state": _due_state(item.get("due_date")),
    }


def _month_cycle(months: int) -> str:
    return {1: "月付", 3: "季付", 12: "年付"}.get(months, f"每{months}个月")


def _due_state(value: str | None) -> str:
    if value is None:
        return "长期计划"
    due = date.fromisoformat(str(value)[:10])
    if due < date.today():
        return "已过期"
    if due == date.today():
        return "今日待确认"
    return "待确认"


def update_transaction(transaction_id: int, changes: dict) -> dict:
    _update_transactions([transaction_id], changes)
    result = get_transaction(transaction_id)
    if result is None:
        raise TransactionNotFound(f"Transaction #{transaction_id} does not exist")
    return result


def update_transactions(ids: list[int], fields: dict) -> int:
    updates = dict(fields)
    if "category" in updates or "subcategory" in updates:
        updates["reviewed"] = True
    return _update_transactions(ids, updates)


def _update_transactions(ids: list[int], fields: dict) -> int:
    try:
        with closing(connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            for id_ in dict.fromkeys(ids):
                write_transaction(conn, id_, fields)
    except LookupError as exc:
        raise TransactionNotFound(str(exc)) from exc
    except ValueError as exc:
        raise TransactionConflict(str(exc)) from exc
    return len(set(ids))


def create_subscription(transaction_id: int, payload: dict, idempotency_key: str) -> dict:
    def insert(conn) -> dict:
        subscription_id = create_subscription_from_transaction(
            conn,
            transaction_id,
            payload["name"],
            payload["next_renewal_date"],
            payload["renewal_mode"],
            payload["renewal_interval"],
            payload.get("renewal_anchor_day"),
            payload.get("coverage_unit"),
            payload.get("coverage_interval"),
        )
        return {"id": subscription_id}

    try:
        result, duplicate = execute_idempotent(
            f"create_subscription_{transaction_id}",
            idempotency_key,
            payload,
            insert,
        )
    except ValueError as exc:
        raise TransactionConflict(str(exc)) from exc
    return {**result, "duplicate": duplicate}
