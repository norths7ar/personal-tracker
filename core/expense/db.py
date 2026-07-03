from contextlib import closing
from datetime import date, timedelta

from core.db import _connect, inserted_id, is_postgres, returning_id_clause


def _to_cents(amount) -> int:
    return int(round(float(amount) * 100))


def _amount_expr() -> str:
    return "COALESCE(amount_cents / 100.0, amount)"


def _normalize_transaction(row) -> dict:
    item = dict(row)
    if item.get("amount_cents") is not None:
        item["amount"] = item["amount_cents"] / 100
    return item


def add_transaction(
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
) -> int:
    amount_cents = _to_cents(amount)
    with closing(_connect()) as conn:
        cur = conn.execute(
            """INSERT INTO transactions
               (type, description, amount, amount_cents, date, category, subcategory, notes, confidence,
                status, refund_for_id, amortization_months, amortization_start)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?)"""
            + returning_id_clause(),
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
            ),
        )
        record_id = inserted_id(cur)
        conn.commit()
        return record_id


def get_transactions(
    start_date: str | None = None,
    end_date: str | None = None,
    type_: str | None = None,
    limit: int = 500,
    include_voided: bool = False,
    status: str | None = None,
) -> list[dict]:
    query = "SELECT * FROM transactions WHERE 1=1"
    params = []
    if status:
        query += " AND status = ?"
        params.append(status)
    elif not include_voided:
        query += " AND COALESCE(status, 'active') = 'active'"
    if start_date:
        query += " AND date >= ?"
        params.append(start_date)
    if end_date:
        query += " AND date <= ?"
        params.append(end_date)
    if type_:
        query += " AND type = ?"
        params.append(type_)
    query += " ORDER BY date DESC, created_at DESC LIMIT ?"
    params.append(limit)

    with closing(_connect()) as conn:
        rows = conn.execute(query, params).fetchall()
    return [_normalize_transaction(r) for r in rows]


def get_monthly_summary(year: int, month: int) -> dict:
    """返回指定月份的收支结余及三类明细。迁移不参与收支计算。"""
    start = f"{year:04d}-{month:02d}-01"
    end = f"{year + 1:04d}-01-01" if month == 12 else f"{year:04d}-{month + 1:02d}-01"

    def breakdown_by_type(conn, type_):
        return conn.execute(
            f"""SELECT category, subcategory, SUM({_amount_expr()}) as total, COUNT(*) as count
               FROM transactions
               WHERE date >= ? AND date < ? AND type = ?
                 AND COALESCE(status, 'active') = 'active'
               GROUP BY category, subcategory
               ORDER BY total DESC""",
            (start, end, type_),
        ).fetchall()

    with closing(_connect()) as conn:
        totals_rows = conn.execute(
            f"""SELECT type, SUM({_amount_expr()}) as total
               FROM transactions
               WHERE date >= ? AND date < ? AND type IN ('收入', '支出')
                 AND COALESCE(status, 'active') = 'active'
               GROUP BY type""",
            (start, end),
        ).fetchall()
        totals = {r["type"]: r["total"] for r in totals_rows}

        expense_bd = breakdown_by_type(conn, "支出")
        income_bd = breakdown_by_type(conn, "收入")
        transfer_bd = breakdown_by_type(conn, "迁移")

    income = totals.get("收入", 0) or 0
    expense = totals.get("支出", 0) or 0
    return {
        "income": income,
        "expense": expense,
        "balance": income - expense,
        "expense_breakdown": [dict(r) for r in expense_bd],
        "income_breakdown": [dict(r) for r in income_bd],
        "transfer_breakdown": [dict(r) for r in transfer_bd],
    }


def update_transaction(id_: int, **fields) -> None:
    allowed = {
        "type",
        "description",
        "amount",
        "date",
        "category",
        "subcategory",
        "notes",
        "confidence",
        "status",
        "void_reason",
        "refund_for_id",
        "amortization_months",
        "amortization_start",
    }
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return
    if "amount" in updates:
        amount_cents = _to_cents(updates["amount"])
        updates["amount"] = amount_cents / 100
        updates["amount_cents"] = amount_cents
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    with closing(_connect()) as conn:
        conn.execute(
            f"UPDATE transactions SET {set_clause} WHERE id = ?",
            [*updates.values(), id_],
        )
        conn.commit()


def delete_transaction(id_: int) -> None:
    with closing(_connect()) as conn:
        conn.execute("DELETE FROM transactions WHERE id = ?", (id_,))
        conn.commit()


def void_transaction(id_: int, reason: str | None = None) -> None:
    update_transaction(id_, status="voided", void_reason=reason)


def restore_transaction(id_: int) -> None:
    update_transaction(id_, status="active", void_reason=None)


def get_pending_transactions(limit: int = 200) -> list[dict]:
    query = """SELECT * FROM transactions
               WHERE COALESCE(status, 'active') = 'active'
                 AND type = '支出'
                 AND (
                    category = '待分类'
                    OR subcategory = '待分类'
                    OR category IS NULL
                    OR category = ''
                    OR subcategory IS NULL
                    OR subcategory = ''
                    OR COALESCE(confidence, 1) < 0.75
                 )
               ORDER BY date DESC, created_at DESC
               LIMIT ?"""
    with closing(_connect()) as conn:
        rows = conn.execute(query, (limit,)).fetchall()
    return [_normalize_transaction(r) for r in rows]


def get_refunds_for(transaction_id: int) -> list[dict]:
    with closing(_connect()) as conn:
        rows = conn.execute(
            """SELECT * FROM transactions
               WHERE refund_for_id = ?
                 AND COALESCE(status, 'active') = 'active'
               ORDER BY date DESC, created_at DESC""",
            (transaction_id,),
        ).fetchall()
    return [_normalize_transaction(r) for r in rows]


def refund_total_for(transaction_id: int) -> float:
    refunds = get_refunds_for(transaction_id)
    return sum(float(r.get("amount") or 0) for r in refunds)


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
            """SELECT date, amortization_start, amortization_months
               FROM transactions
               WHERE COALESCE(status, 'active') = 'active'
                 AND type = '支出'
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


def _week_start(value: str) -> str:
    current = date.fromisoformat(value)
    return (current - timedelta(days=current.weekday())).isoformat()


def _cash_period_data(start_date: str, end_date: str) -> dict:
    """通用期间查询，返回 income/expense/balance/daily/expense_breakdown/income_breakdown。"""

    def bd(conn, type_):
        return conn.execute(
            f"""SELECT category, subcategory, SUM({_amount_expr()}) as total, COUNT(*) as count
               FROM transactions
               WHERE date >= ? AND date <= ? AND type = ?
                 AND COALESCE(status, 'active') = 'active'
               GROUP BY category, subcategory ORDER BY total DESC""",
            (start_date, end_date, type_),
        ).fetchall()

    with closing(_connect()) as conn:
        totals_rows = conn.execute(
            f"""SELECT type, category, SUM({_amount_expr()}) as total FROM transactions
               WHERE date >= ? AND date <= ? AND type IN ('收入','支出')
                 AND COALESCE(status, 'active') = 'active'
               GROUP BY type, category""",
            (start_date, end_date),
        ).fetchall()

        daily_rows = conn.execute(
            f"""SELECT date, type, category, SUM({_amount_expr()}) as total FROM transactions
               WHERE date >= ? AND date <= ? AND type IN ('收入','支出')
                 AND COALESCE(status, 'active') = 'active'
               GROUP BY date, type, category ORDER BY date""",
            (start_date, end_date),
        ).fetchall()

        expense_bd = bd(conn, "支出")
        income_bd = bd(conn, "收入")

    income = 0.0
    expense = 0.0
    for raw in totals_rows:
        row = dict(raw)
        total = row["total"] or 0
        if row["type"] == "收入" and row.get("category") == "退款":
            expense -= total
        elif row["type"] == "收入":
            income += total
        elif row["type"] == "支出":
            expense += total

    daily: dict = {}
    for raw in daily_rows:
        r = dict(raw)
        d = r["date"]
        if d not in daily:
            daily[d] = {"date": d, "收入": 0.0, "支出": 0.0}
        if r["type"] == "收入" and r.get("category") == "退款":
            daily[d]["支出"] -= r["total"] or 0
        else:
            daily[d][r["type"]] += r["total"] or 0

    return {
        "income": income,
        "expense": expense,
        "balance": income - expense,
        "daily": list(daily.values()),
        "expense_breakdown": [dict(r) for r in expense_bd],
        "income_breakdown": [dict(r) for r in income_bd],
    }


def get_period_data(start_date: str, end_date: str, basis: str = "cash") -> dict:
    if basis != "amortized":
        return _cash_period_data(start_date, end_date)
    return get_amortized_period_data(start_date, end_date)


def get_amortized_period_data(start_date: str, end_date: str) -> dict:
    with closing(_connect()) as conn:
        rows = conn.execute(
            """SELECT * FROM transactions
               WHERE COALESCE(status, 'active') = 'active'
                 AND type IN ('收入','支出')
               ORDER BY date""",
        ).fetchall()

    daily: dict = {}
    breakdown: dict[tuple[str, str], dict] = {}
    income = 0.0
    expense = 0.0

    for raw in rows:
        row = _normalize_transaction(raw)
        type_ = row.get("type")
        amount = float(row.get("amount") or 0)
        if type_ == "支出" and int(row.get("amortization_months") or 0) > 1:
            months = int(row.get("amortization_months") or 1)
            allocation = amount / months
            starts = _month_starts(
                row.get("amortization_start") or row.get("date"), months
            )
            entries = [(month, allocation) for month in starts]
        else:
            entries = [(row.get("date"), amount)]

        for entry_date, entry_amount in entries:
            if not entry_date or entry_date < start_date or entry_date > end_date:
                continue
            day = daily.setdefault(
                entry_date, {"date": entry_date, "收入": 0.0, "支出": 0.0}
            )
            if type_ == "收入" and row.get("category") == "退款":
                day["支出"] -= entry_amount
                expense -= entry_amount
            elif type_ == "收入":
                day["收入"] += entry_amount
                income += entry_amount
            elif type_ == "支出":
                day["支出"] += entry_amount
                expense += entry_amount
                key = (row.get("category") or "", row.get("subcategory") or "")
                current = breakdown.setdefault(
                    key,
                    {
                        "category": key[0],
                        "subcategory": key[1],
                        "total": 0.0,
                        "count": 0,
                    },
                )
                current["total"] += entry_amount
                current["count"] += 1

    income_breakdown = _cash_period_data(start_date, end_date)["income_breakdown"]
    return {
        "income": income,
        "expense": expense,
        "balance": income - expense,
        "daily": sorted(daily.values(), key=lambda r: r["date"]),
        "expense_breakdown": sorted(
            breakdown.values(), key=lambda r: r["total"], reverse=True
        ),
        "income_breakdown": income_breakdown,
    }


def get_active_weeks() -> list:
    """返回有记录的自然周起始日（周一）列表。"""
    if is_postgres():
        sql = """SELECT DISTINCT
                    ((date::date - ((EXTRACT(ISODOW FROM date::date)::int - 1) * INTERVAL '1 day'))::date)::text
                    as week_start
                 FROM transactions
                 WHERE COALESCE(status, 'active') = 'active'
                 ORDER BY week_start DESC"""
    else:
        sql = """SELECT DISTINCT date(date, '-6 days', 'weekday 1') as week_start
                 FROM transactions
                 WHERE COALESCE(status, 'active') = 'active'
                 ORDER BY week_start DESC"""
    with closing(_connect()) as conn:
        rows = conn.execute(sql).fetchall()
    weeks = {r["week_start"] for r in rows}
    weeks.update(_week_start(d) for d in _amortization_allocation_dates())
    return sorted(weeks, reverse=True)


def get_active_years() -> list:
    if is_postgres():
        sql = """SELECT DISTINCT to_char(date::date, 'YYYY') as year
                 FROM transactions
                 WHERE COALESCE(status, 'active') = 'active'
                 ORDER BY year DESC"""
    else:
        sql = """SELECT DISTINCT strftime('%Y', date) as year
                 FROM transactions
                 WHERE COALESCE(status, 'active') = 'active'
                 ORDER BY year DESC"""
    with closing(_connect()) as conn:
        rows = conn.execute(sql).fetchall()
    years = {r["year"] for r in rows}
    years.update(d[:4] for d in _amortization_allocation_dates())
    return sorted(years, reverse=True)


def get_active_months() -> list:
    if is_postgres():
        sql = """SELECT DISTINCT to_char(date::date, 'YYYY-MM') as month
                 FROM transactions
                 WHERE COALESCE(status, 'active') = 'active'
                 ORDER BY month DESC"""
    else:
        sql = """SELECT DISTINCT strftime('%Y-%m', date) as month
                 FROM transactions
                 WHERE COALESCE(status, 'active') = 'active'
                 ORDER BY month DESC"""
    with closing(_connect()) as conn:
        rows = conn.execute(sql).fetchall()
    months = {r["month"] for r in rows}
    months.update(d[:7] for d in _amortization_allocation_dates())
    return sorted(months, reverse=True)
