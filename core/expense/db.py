from contextlib import closing

from core.db import _connect


def add_transaction(type_, description, amount, date_,
                    category=None, subcategory=None, notes=None, confidence=None):
    with closing(_connect()) as conn:
        cur = conn.execute(
            """INSERT INTO transactions
               (type, description, amount, date, category, subcategory, notes, confidence)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (type_, description, amount, date_, category, subcategory, notes, confidence)
        )
        conn.commit()
        return cur.lastrowid


def get_transactions(start_date=None, end_date=None, type_=None, limit=500):
    query = "SELECT * FROM transactions WHERE 1=1"
    params = []
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
    return [dict(r) for r in rows]


def get_monthly_summary(year, month):
    """返回指定月份的收支结余及三类明细。迁移不参与收支计算。"""
    start = f"{year:04d}-{month:02d}-01"
    end = f"{year+1:04d}-01-01" if month == 12 else f"{year:04d}-{month+1:02d}-01"

    def breakdown_by_type(conn, type_):
        return conn.execute(
            """SELECT category, subcategory, SUM(amount) as total, COUNT(*) as count
               FROM transactions
               WHERE date >= ? AND date < ? AND type = ?
               GROUP BY category, subcategory
               ORDER BY total DESC""",
            (start, end, type_)
        ).fetchall()

    with closing(_connect()) as conn:
        totals_rows = conn.execute(
            """SELECT type, SUM(amount) as total
               FROM transactions
               WHERE date >= ? AND date < ? AND type IN ('收入', '支出')
               GROUP BY type""",
            (start, end)
        ).fetchall()
        totals = {r["type"]: r["total"] for r in totals_rows}

        expense_bd  = breakdown_by_type(conn, "支出")
        income_bd   = breakdown_by_type(conn, "收入")
        transfer_bd = breakdown_by_type(conn, "迁移")

    income  = totals.get("收入", 0) or 0
    expense = totals.get("支出", 0) or 0
    return {
        "income": income,
        "expense": expense,
        "balance": income - expense,
        "expense_breakdown":  [dict(r) for r in expense_bd],
        "income_breakdown":   [dict(r) for r in income_bd],
        "transfer_breakdown": [dict(r) for r in transfer_bd],
    }


def update_transaction(id_: int, **fields):
    allowed = {"type", "description", "amount", "date", "category", "subcategory", "notes"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    with closing(_connect()) as conn:
        conn.execute(
            f"UPDATE transactions SET {set_clause} WHERE id = ?",
            [*updates.values(), id_]
        )
        conn.commit()


def delete_transaction(id_: int):
    with closing(_connect()) as conn:
        conn.execute("DELETE FROM transactions WHERE id = ?", (id_,))
        conn.commit()


def get_period_data(start_date: str, end_date: str) -> dict:
    """通用期间查询，返回 income/expense/balance/daily/expense_breakdown/income_breakdown。"""
    def bd(conn, type_):
        return conn.execute(
            """SELECT category, subcategory, SUM(amount) as total, COUNT(*) as count
               FROM transactions
               WHERE date >= ? AND date <= ? AND type = ?
               GROUP BY category, subcategory ORDER BY total DESC""",
            (start_date, end_date, type_)
        ).fetchall()

    with closing(_connect()) as conn:
        totals_rows = conn.execute(
            """SELECT type, SUM(amount) as total FROM transactions
               WHERE date >= ? AND date <= ? AND type IN ('收入','支出')
               GROUP BY type""",
            (start_date, end_date)
        ).fetchall()
        totals = {r["type"]: r["total"] or 0 for r in totals_rows}

        daily_rows = conn.execute(
            """SELECT date, type, SUM(amount) as total FROM transactions
               WHERE date >= ? AND date <= ? AND type IN ('收入','支出')
               GROUP BY date, type ORDER BY date""",
            (start_date, end_date)
        ).fetchall()

        expense_bd = bd(conn, "支出")
        income_bd  = bd(conn, "收入")

    daily: dict = {}
    for r in daily_rows:
        d = r["date"]
        if d not in daily:
            daily[d] = {"date": d, "收入": 0.0, "支出": 0.0}
        daily[d][r["type"]] = r["total"]

    income  = totals.get("收入", 0)
    expense = totals.get("支出", 0)
    return {
        "income":  income,
        "expense": expense,
        "balance": income - expense,
        "daily":   list(daily.values()),
        "expense_breakdown": [dict(r) for r in expense_bd],
        "income_breakdown":  [dict(r) for r in income_bd],
    }


def get_active_weeks() -> list:
    """返回有记录的自然周起始日（周一）列表。"""
    with closing(_connect()) as conn:
        rows = conn.execute(
            """SELECT DISTINCT date(date, '-6 days', 'weekday 1') as week_start
               FROM transactions ORDER BY week_start DESC"""
        ).fetchall()
    return [r["week_start"] for r in rows]


def get_active_years() -> list:
    with closing(_connect()) as conn:
        rows = conn.execute(
            """SELECT DISTINCT strftime('%Y', date) as year
               FROM transactions ORDER BY year DESC"""
        ).fetchall()
    return [r["year"] for r in rows]


def get_active_months() -> list:
    with closing(_connect()) as conn:
        rows = conn.execute(
            """SELECT DISTINCT strftime('%Y-%m', date) as month
               FROM transactions ORDER BY month DESC"""
        ).fetchall()
    return [r["month"] for r in rows]
