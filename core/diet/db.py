from contextlib import closing

from core.db import _connect


def add_diet_entry(date, description, meal_type=None, food_name=None,
                   quantity=None, time=None, notes=None, confidence=None):
    with closing(_connect()) as conn:
        cur = conn.execute(
            """INSERT INTO diet_entries
               (date, time, description, meal_type, food_name, quantity, notes, confidence)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (date, time, description, meal_type, food_name, quantity, notes, confidence)
        )
        conn.commit()
        return cur.lastrowid


def get_diet_entries(start_date=None, end_date=None, meal_type=None, limit=500):
    query = "SELECT * FROM diet_entries WHERE 1=1"
    params = []
    if start_date:
        query += " AND date >= ?"
        params.append(start_date)
    if end_date:
        query += " AND date <= ?"
        params.append(end_date)
    if meal_type:
        query += " AND meal_type = ?"
        params.append(meal_type)
    query += " ORDER BY date DESC, time DESC LIMIT ?"
    params.append(limit)

    with closing(_connect()) as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def update_diet_entry(id_: int, **fields):
    allowed = {"date", "time", "description", "meal_type", "food_name",
               "quantity", "notes", "confidence"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    with closing(_connect()) as conn:
        conn.execute(
            f"UPDATE diet_entries SET {set_clause} WHERE id = ?",
            [*updates.values(), id_]
        )
        conn.commit()


def delete_diet_entry(id_: int):
    with closing(_connect()) as conn:
        conn.execute("DELETE FROM diet_entries WHERE id = ?", (id_,))
        conn.commit()


def get_diet_summary(start_date, end_date):
    with closing(_connect()) as conn:
        meal_stats = conn.execute(
            """SELECT meal_type, COUNT(*) as count
               FROM diet_entries
               WHERE date >= ? AND date <= ?
               GROUP BY meal_type""",
            (start_date, end_date)
        ).fetchall()

        recent = conn.execute(
            """SELECT date, meal_type, food_name, quantity
               FROM diet_entries
               WHERE date >= ? AND date <= ?
               ORDER BY date DESC, time DESC
               LIMIT 10""",
            (start_date, end_date)
        ).fetchall()

    return {
        "meal_stats": [dict(r) for r in meal_stats],
        "recent":     [dict(r) for r in recent],
    }


def get_diet_dates() -> list:
    with closing(_connect()) as conn:
        rows = conn.execute(
            "SELECT DISTINCT date FROM diet_entries ORDER BY date DESC"
        ).fetchall()
    return [r["date"] for r in rows]
