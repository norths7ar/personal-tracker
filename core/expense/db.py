from contextlib import closing
from datetime import date

from core.constants import (
    DEFAULT_CONFIDENCE_THRESHOLD,
    PENDING_CATEGORY,
    REFUND_CATEGORY,
    TYPE_EXPENSE,
    TYPE_INCOME,
)
from core.db import _connect, to_cents


def _normalize_transaction(row) -> dict:
    item = dict(row)
    item["amount"] = item["amount_cents"] / 100
    return item


def _insert_transaction(
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
    amortization_months: int | None = None,
    amortization_start: str | None = None,
    subscription_id: int | None = None,
    reviewed: bool = False,
) -> int:
    amount_cents = to_cents(amount)
    cur = conn.execute(
        """INSERT INTO transactions
           (type, description, amount, amount_cents, date, category,
            subcategory, notes, confidence, refund_for_id,
            amortization_months, amortization_start, subscription_id, reviewed)
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
            amortization_months,
            amortization_start,
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
    with closing(_connect()) as conn:
        return [_normalize_transaction(row) for row in conn.execute(query, params)]


def get_transaction(id_: int) -> dict | None:
    with closing(_connect()) as conn:
        row = conn.execute("SELECT * FROM transactions WHERE id = ?", (id_,)).fetchone()
    return _normalize_transaction(row) if row is not None else None


def update_transaction(id_: int, **fields) -> None:
    update_transactions([id_], fields)


def update_transactions(ids: list[int], fields: dict) -> None:
    with closing(_connect()) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        for id_ in dict.fromkeys(ids):
            _update_transaction(conn, id_, fields)


def _update_transaction(conn, id_: int, fields: dict) -> None:
    from core.subscription.db import _sync_prepaid_transaction

    allowed = {
        "type",
        "description",
        "amount",
        "date",
        "category",
        "subcategory",
        "notes",
        "amortization_months",
        "amortization_start",
        "reviewed",
    }
    updates = {key: value for key, value in fields.items() if key in allowed}
    if not updates:
        return
    original = conn.execute(
        "SELECT * FROM transactions WHERE id = ?", (id_,)
    ).fetchone()
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
    months = current["amortization_months"]
    if months is not None:
        if current["type"] != TYPE_EXPENSE:
            raise ValueError("只有支出可以设置摊销")
        if not 1 <= months <= 120:
            raise ValueError("摊销月数必须在 1 到 120 之间")
        if not current["amortization_start"]:
            current["amortization_start"] = current["date"][:7] + "-01"
            updates["amortization_start"] = current["amortization_start"]
    else:
        if current["amortization_start"] and "amortization_months" not in updates:
            raise ValueError("设置摊销开始日期时必须提供摊销月数")
        current["amortization_start"] = None
        if "amortization_months" in updates:
            updates["amortization_start"] = None
    set_clause = ", ".join(f"{key} = ?" for key in updates)
    conn.execute(
        f"UPDATE transactions SET {set_clause} WHERE id = ?", [*updates.values(), id_]
    )
    _sync_prepaid_transaction(conn, current)


def _validate_financial_links(conn, current: dict) -> None:
    refunded = conn.execute(
        """SELECT COALESCE(SUM(amount_cents), 0), COUNT(*)
           FROM transactions WHERE refund_for_id = ?""",
        (current["id"],),
    ).fetchone()
    if refunded[1] and (
        current["type"] != TYPE_EXPENSE or current["amount_cents"] < refunded[0]
    ):
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
        if (
            original is None
            or current["amount_cents"] + others > original["amount_cents"]
        ):
            raise ValueError("退款金额超过原支出剩余可退金额")


def delete_transactions(ids: list[int]) -> int:
    """Delete several transactions atomically after validating every record."""
    transaction_ids = list(dict.fromkeys(int(id_) for id_ in ids))
    if not transaction_ids:
        return 0

    with closing(_connect()) as conn:
        try:
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
        raise ValueError(f"记录 #{id_} 存在关联退款，请先删除退款")
    prepaid = conn.execute(
        "SELECT 1 FROM subscriptions WHERE transaction_id = ? LIMIT 1", (id_,)
    ).fetchone()
    if transaction["subscription_id"] is not None or prepaid is not None:
        raise ValueError(f"记录 #{id_} 已关联跨期费用，请先删除或解除关联")
    planned = conn.execute(
        "SELECT 1 FROM planned_expenses WHERE transaction_id = ? LIMIT 1", (id_,)
    ).fetchone()
    if planned is not None:
        raise ValueError(f"记录 #{id_} 是预计支出的历史入账，不能直接删除")


def get_pending_transactions(limit: int = 200) -> list[dict]:
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
    with closing(_connect()) as conn:
        rows = conn.execute(query, (limit,)).fetchall()
    return [_normalize_transaction(r) for r in rows]


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
    with closing(_connect()) as conn:
        row = conn.execute(query).fetchone()
    return int(row["count"])


def _add_refund(
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

    return _insert_transaction(
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
    with closing(_connect()) as conn:
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
    with closing(_connect()) as conn:
        rows = conn.execute(
            "SELECT * FROM transactions WHERE type IN (?, ?) ORDER BY date, id",
            (TYPE_INCOME, TYPE_EXPENSE),
        ).fetchall()
    transactions = [_normalize_transaction(row) for row in rows]
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
                for row in sorted(
                    groups.values(), key=lambda row: row["total"], reverse=True
                )
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
    with closing(_connect()) as conn:
        rows = conn.execute(sql).fetchall()
    years = {r["year"] for r in rows}
    years.update(d[:4] for d in _amortization_allocation_dates())
    return sorted(years, reverse=True)


def get_active_months() -> list:
    sql = """SELECT DISTINCT strftime('%Y-%m', date) as month
             FROM transactions
             ORDER BY month DESC"""
    with closing(_connect()) as conn:
        rows = conn.execute(sql).fetchall()
    months = {r["month"] for r in rows}
    months.update(d[:7] for d in _amortization_allocation_dates())
    return sorted(months, reverse=True)
