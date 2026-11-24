from contextlib import closing
from datetime import date

from backend.constants import (
    DEFAULT_CONFIDENCE_THRESHOLD,
    PENDING_CATEGORY,
    REFUND_CATEGORY,
    TYPE_EXPENSE,
    TYPE_INCOME,
)
from backend.db import connect, execute_idempotent, to_cents


def normalize_transaction(row) -> dict:
    item = dict(row)
    item["amount"] = item["amount_cents"] / 100
    return item


def insert_transaction(
    conn,
    type_: str,
    description: str,
    amount: float,
    date_: str,
    category: str | None = None,
    subcategory: str | None = None,
    notes: str | None = None,
    confidence: float | None = None,
    refund_for_id: int | None = None,
    coverage_start: str | None = None,
    coverage_end: str | None = None,
    subscription_id: int | None = None,
    reviewed: bool = False,
) -> int:
    validate_coverage(type_, coverage_start, coverage_end)
    amount_cents = to_cents(amount)
    cur = conn.execute(
        """INSERT INTO transactions
           (type, description, amount, amount_cents, date, category,
            subcategory, notes, confidence, refund_for_id,
            coverage_start, coverage_end, subscription_id, reviewed)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            type_,
            description,
            amount_cents / 100,
            amount_cents,
            date_,
            category,
            subcategory,
            notes,
            confidence,
            refund_for_id,
            coverage_start,
            coverage_end,
            subscription_id,
            1 if reviewed else 0,
        ),
    )
    return cur.lastrowid


def get_transactions(
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int | None = 500,
) -> list[dict]:
    query = "SELECT * FROM transactions WHERE 1=1"
    params = []
    if start_date:
        query += " AND date >= ?"
        params.append(start_date)
    if end_date:
        query += " AND date <= ?"
        params.append(end_date)
    query += " ORDER BY date DESC, created_at DESC, id DESC"
    if limit is not None:
        query += " LIMIT ?"
        params.append(limit)
    with closing(connect()) as conn:
        return [normalize_transaction(row) for row in conn.execute(query, params)]


def get_transaction(id_: int) -> dict | None:
    with closing(connect()) as conn:
        row = conn.execute("SELECT * FROM transactions WHERE id = ?", (id_,)).fetchone()
    return normalize_transaction(row) if row is not None else None


def update_transaction(conn, id_: int, fields: dict) -> None:
    allowed = {
        "type",
        "description",
        "amount",
        "date",
        "category",
        "subcategory",
        "notes",
        "coverage_start",
        "coverage_end",
        "reviewed",
    }
    updates = {key: value for key, value in fields.items() if key in allowed}
    if not updates:
        return
    original = conn.execute("SELECT * FROM transactions WHERE id = ?", (id_,)).fetchone()
    if original is None:
        raise LookupError(f"Transaction #{id_} does not exist")
    if "amount" in updates:
        updates["amount_cents"] = to_cents(updates["amount"])
        if updates["amount_cents"] <= 0:
            raise ValueError("金额至少为 0.01 元")
        updates["amount"] = updates["amount_cents"] / 100
    if "reviewed" in updates:
        updates["reviewed"] = int(updates["reviewed"])
    current = {**dict(original), **updates}
    _validate_financial_links(conn, current)
    validate_coverage(current["type"], current["coverage_start"], current["coverage_end"])
    set_clause = ", ".join(f"{key} = ?" for key in updates)
    conn.execute(f"UPDATE transactions SET {set_clause} WHERE id = ?", [*updates.values(), id_])


def _validate_financial_links(conn, current: dict) -> None:
    refunded = conn.execute(
        """SELECT COALESCE(SUM(amount_cents), 0), COUNT(*)
           FROM transactions WHERE refund_for_id = ?""",
        (current["id"],),
    ).fetchone()
    if refunded[1] and (current["type"] != TYPE_EXPENSE or current["amount_cents"] < refunded[0]):
        raise ValueError("有关联退款的流水必须保持为支出，金额不能低于已退款总额")
    if current["subscription_id"] is not None and current["type"] != TYPE_EXPENSE:
        raise ValueError("周期付款关联流水必须保持为支出")
    if current["refund_for_id"] is not None:
        if current["type"] != TYPE_INCOME or current["category"] != REFUND_CATEGORY:
            raise ValueError("关联退款必须保持为退款收入")
        original = conn.execute(
            "SELECT amount_cents FROM transactions WHERE id = ? AND type = ?",
            (current["refund_for_id"], TYPE_EXPENSE),
        ).fetchone()
        others = conn.execute(
            """SELECT COALESCE(SUM(amount_cents), 0) FROM transactions
               WHERE refund_for_id = ? AND id <> ?""",
            (current["refund_for_id"], current["id"]),
        ).fetchone()[0]
        if original is None or current["amount_cents"] + others > original["amount_cents"]:
            raise ValueError("退款金额超过原支出剩余可退金额")


def delete_transactions(ids: list[int]) -> int:
    """Delete several transactions atomically after validating every record."""
    transaction_ids = list(dict.fromkeys(int(id_) for id_ in ids))
    if not transaction_ids:
        return 0

    with closing(connect()) as conn:
        try:
            conn.execute("BEGIN IMMEDIATE")
            for transaction_id in transaction_ids:
                _validate_transaction_deletion(conn, transaction_id)

            placeholders = ", ".join("?" for _ in transaction_ids)
            deleted = conn.execute(
                f"DELETE FROM transactions WHERE id IN ({placeholders})",
                transaction_ids,
            ).rowcount
            conn.commit()
            return deleted
        except Exception:
            conn.rollback()
            raise


def _validate_transaction_deletion(conn, id_: int) -> None:
    transaction = conn.execute(
        "SELECT subscription_id FROM transactions WHERE id = ?", (id_,)
    ).fetchone()
    if transaction is None:
        return
    refund = conn.execute(
        "SELECT 1 FROM transactions WHERE refund_for_id = ? LIMIT 1", (id_,)
    ).fetchone()
    if refund is not None:
        raise TransactionConflict(f"记录 #{id_} 存在关联退款，请先删除退款")
    if transaction["subscription_id"] is not None:
        raise TransactionConflict(f"记录 #{id_} 已关联周期计划，请先删除或解除关联")
    planned = conn.execute(
        "SELECT 1 FROM planned_expenses WHERE transaction_id = ? LIMIT 1", (id_,)
    ).fetchone()
    if planned is not None:
        raise TransactionConflict(f"记录 #{id_} 是预计支出的历史入账，不能直接删除")


def get_pending_transactions(limit: int | None = 200) -> list[dict]:
    query = f"""SELECT * FROM transactions
               WHERE type = '{TYPE_EXPENSE}'
                 AND (
                    category = '{PENDING_CATEGORY}'
                    OR subcategory = '{PENDING_CATEGORY}'
                    OR category IS NULL
                    OR category = ''
                    OR (
                        COALESCE(reviewed, 0) = 0
                        AND COALESCE(confidence, 1) < {DEFAULT_CONFIDENCE_THRESHOLD}
                    )
                 )
               ORDER BY date DESC, created_at DESC
               LIMIT ?"""
    with closing(connect()) as conn:
        rows = conn.execute(query, (-1 if limit is None else limit,)).fetchall()
    return [normalize_transaction(r) for r in rows]


def get_pending_transaction_count() -> int:
    query = f"""SELECT COUNT(*) AS count FROM transactions
                WHERE type = '{TYPE_EXPENSE}'
                  AND (
                     category = '{PENDING_CATEGORY}'
                     OR subcategory = '{PENDING_CATEGORY}'
                     OR category IS NULL
                     OR category = ''
                     OR (
                         COALESCE(reviewed, 0) = 0
                         AND COALESCE(confidence, 1) < {DEFAULT_CONFIDENCE_THRESHOLD}
                     )
                  )"""
    with closing(connect()) as conn:
        row = conn.execute(query).fetchone()
    return int(row["count"])


def add_refund(
    conn,
    transaction_id: int,
    description: str,
    amount: float,
    refund_date: str,
) -> int:
    amount_cents = to_cents(amount)
    if amount_cents <= 0:
        raise ValueError("退款金额须大于 0")
    original = conn.execute(
        "SELECT * FROM transactions WHERE id = ?",
        (transaction_id,),
    ).fetchone()
    if original is None or original["type"] != TYPE_EXPENSE:
        raise ValueError("关联支出不存在")

    original_cents = original["amount_cents"]
    refunded_row = conn.execute(
        """SELECT COALESCE(SUM(amount_cents), 0) AS refunded_cents
           FROM transactions WHERE refund_for_id = ?""",
        (transaction_id,),
    ).fetchone()
    remaining_cents = int(original_cents) - int(refunded_row["refunded_cents"] or 0)
    if amount_cents > remaining_cents:
        raise ValueError(f"退款金额超过剩余可退 ¥{remaining_cents / 100:.2f}")

    return insert_transaction(
        conn,
        TYPE_INCOME,
        description,
        amount_cents / 100,
        refund_date,
        category=REFUND_CATEGORY,
        notes=f"关联支出 #{transaction_id}",
        refund_for_id=transaction_id,
        reviewed=True,
    )


def create_refund(transaction_id: int, payload: dict, idempotency_key: str) -> dict:
    def insert(conn) -> dict:
        refund_id = add_refund(
            conn,
            transaction_id,
            payload["description"],
            payload["amount"],
            payload["date"],
        )
        return {"id": refund_id}

    try:
        result, duplicate = execute_idempotent(
            f"create_refund_{transaction_id}", idempotency_key, payload, insert
        )
    except ValueError as exc:
        raise TransactionConflict(str(exc)) from exc
    return {**result, "duplicate": duplicate}


class TransactionConflict(ValueError):
    pass


class TransactionNotFound(LookupError):
    pass


def validate_coverage(type_: str, start: str | None, end: str | None) -> None:
    if start is None and end is None:
        return
    if start is None or end is None:
        raise ValueError("生效期起止日期必须同时填写或同时清空")
    if type_ != TYPE_EXPENSE:
        raise ValueError("只有支出可以设置生效期")
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    if first.isoformat() != start or last.isoformat() != end or first > last:
        raise ValueError("生效期必须为 YYYY-MM-DD，且开始日期不能晚于结束日期")
