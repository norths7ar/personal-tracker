from contextlib import closing

from core.constants import (
    PLANNED_EXPENSE_STATUS_COMPLETED,
    PLANNED_EXPENSE_STATUS_OPEN,
    TYPE_EXPENSE,
)
from core.db import _connect, to_cents


def _normalize(row) -> dict:
    item = dict(row)
    item["amount"] = item["amount_cents"] / 100
    return item


def _insert_planned_expense(
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
    with closing(_connect()) as conn:
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
    with closing(_connect()) as conn:
        conn.execute(
            f"""UPDATE planned_expenses
                SET {set_clause}
                WHERE id = ? AND status = ?""",
            [*updates.values(), id_, PLANNED_EXPENSE_STATUS_OPEN],
        )
        conn.commit()


def delete_planned_expense(id_: int) -> None:
    with closing(_connect()) as conn:
        conn.execute(
            "DELETE FROM planned_expenses WHERE id = ? AND status = ?",
            (id_, PLANNED_EXPENSE_STATUS_OPEN),
        )
        conn.commit()


def _confirm_planned_expense(
    conn,
    id_: int,
    description: str,
    amount: float,
    date_: str,
    category: str | None,
    subcategory: str | None,
    notes: str | None,
) -> int:
    amount_cents = to_cents(amount)
    plan = conn.execute(
        "SELECT * FROM planned_expenses WHERE id = ? AND status = ?",
        (id_, PLANNED_EXPENSE_STATUS_OPEN),
    ).fetchone()
    if plan is None:
        raise ValueError("预计支出不存在或已处理")
    if dict(plan).get("subscription_id") is not None:
        raise ValueError("订阅预计支出必须通过订阅付款流程确认")

    cur = conn.execute(
        """INSERT INTO transactions
           (type, description, amount, amount_cents, date, category,
            subcategory, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            TYPE_EXPENSE,
            description,
            amount_cents / 100,
            amount_cents,
            date_,
            category,
            subcategory,
            notes,
        ),
    )
    transaction_id = cur.lastrowid
    conn.execute(
        """UPDATE planned_expenses
           SET status = ?, transaction_id = ? WHERE id = ?""",
        (PLANNED_EXPENSE_STATUS_COMPLETED, transaction_id, id_),
    )
    return transaction_id
