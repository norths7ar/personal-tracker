from contextlib import closing

from core.db import _connect


def add_meal(date, time, meal_type, description, notes, confidence, foods):
    """
    Insert one meal + its food items atomically.
    foods: [{"food_name": str, "quantity": str}, ...]
    Returns meal_id.
    """
    with closing(_connect()) as conn:
        cur = conn.execute(
            """INSERT INTO diet_meals (date, time, meal_type, description, notes, confidence)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (date, time, meal_type, description, notes, confidence),
        )
        meal_id = cur.lastrowid
        conn.executemany(
            "INSERT INTO diet_foods (meal_id, food_name, quantity) VALUES (?, ?, ?)",
            [(meal_id, f["food_name"], f.get("quantity") or "") for f in foods],
        )
        conn.commit()
    return meal_id


def get_meals(start_date=None, end_date=None, meal_type=None, limit=200):
    """
    Return list of meal dicts, each with a 'foods' key:
    [{"id", "date", "time", "meal_type", "description", "notes", "confidence",
      "created_at", "foods": [{"food_name", "quantity"}, ...]}, ...]
    """
    query = "SELECT * FROM diet_meals WHERE 1=1"
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
        meals = [dict(r) for r in conn.execute(query, params).fetchall()]
        if not meals:
            return []
        meal_ids = [m["id"] for m in meals]
        placeholders = ",".join("?" * len(meal_ids))
        food_rows = conn.execute(
            f"SELECT * FROM diet_foods WHERE meal_id IN ({placeholders}) ORDER BY id",
            meal_ids,
        ).fetchall()

    foods_by_meal: dict = {}
    for f in food_rows:
        foods_by_meal.setdefault(f["meal_id"], []).append(
            {"food_name": f["food_name"], "quantity": f["quantity"] or ""}
        )
    for meal in meals:
        meal["foods"] = foods_by_meal.get(meal["id"], [])
    return meals


def update_meal(meal_id: int, **fields):
    allowed = {"date", "time", "meal_type", "description", "notes", "confidence"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return
    set_clause = ", ".join(f"{k} = ?" for k in updates)
    with closing(_connect()) as conn:
        conn.execute(
            f"UPDATE diet_meals SET {set_clause} WHERE id = ?",
            [*updates.values(), meal_id],
        )
        conn.commit()


def update_meal_foods(meal_id: int, foods: list):
    """Replace all food items for a meal (delete + reinsert)."""
    with closing(_connect()) as conn:
        conn.execute("DELETE FROM diet_foods WHERE meal_id = ?", (meal_id,))
        conn.executemany(
            "INSERT INTO diet_foods (meal_id, food_name, quantity) VALUES (?, ?, ?)",
            [(meal_id, f["food_name"], f.get("quantity") or "") for f in foods],
        )
        conn.commit()


def delete_meal(meal_id: int):
    with closing(_connect()) as conn:
        conn.execute("DELETE FROM diet_meals WHERE id = ?", (meal_id,))
        conn.commit()


def get_diet_summary(start_date, end_date):
    """Sidebar/quick stats: meal_type counts + recent meals with food list."""
    with closing(_connect()) as conn:
        meal_stats = conn.execute(
            """SELECT meal_type, COUNT(*) as count
               FROM diet_meals
               WHERE date >= ? AND date <= ?
               GROUP BY meal_type ORDER BY count DESC""",
            (start_date, end_date),
        ).fetchall()

        recent = conn.execute(
            """SELECT m.date, m.meal_type, m.time,
                      GROUP_CONCAT(f.food_name, '、') as foods
               FROM diet_meals m
               LEFT JOIN diet_foods f ON f.meal_id = m.id
               WHERE m.date >= ? AND m.date <= ?
               GROUP BY m.id
               ORDER BY m.date DESC, m.time DESC
               LIMIT 10""",
            (start_date, end_date),
        ).fetchall()

    return {
        "meal_stats": [dict(r) for r in meal_stats],
        "recent":     [dict(r) for r in recent],
    }


def get_diet_dates() -> list:
    with closing(_connect()) as conn:
        rows = conn.execute(
            "SELECT DISTINCT date FROM diet_meals ORDER BY date DESC"
        ).fetchall()
    return [r["date"] for r in rows]


def get_diet_stats(start_date, end_date) -> dict:
    """Data for the analysis page."""
    with closing(_connect()) as conn:
        # Which meal_types were recorded on each date (for coverage heatmap)
        daily_coverage = conn.execute(
            """SELECT date, meal_type FROM diet_meals
               WHERE date >= ? AND date <= ?
               ORDER BY date""",
            (start_date, end_date),
        ).fetchall()

        # Food frequency ranking
        food_freq = conn.execute(
            """SELECT f.food_name, COUNT(*) as count
               FROM diet_foods f
               JOIN diet_meals m ON m.id = f.meal_id
               WHERE m.date >= ? AND m.date <= ?
               GROUP BY f.food_name
               ORDER BY count DESC
               LIMIT 20""",
            (start_date, end_date),
        ).fetchall()

        # Per-day meal count (for trend line)
        daily_meals = conn.execute(
            """SELECT date, COUNT(*) as count
               FROM diet_meals
               WHERE date >= ? AND date <= ?
               GROUP BY date ORDER BY date""",
            (start_date, end_date),
        ).fetchall()

        # Meal type distribution
        meal_type_dist = conn.execute(
            """SELECT meal_type, COUNT(*) as count
               FROM diet_meals
               WHERE date >= ? AND date <= ?
               GROUP BY meal_type ORDER BY count DESC""",
            (start_date, end_date),
        ).fetchall()

    return {
        "daily_coverage": [dict(r) for r in daily_coverage],
        "food_freq":      [dict(r) for r in food_freq],
        "daily_meals":    [dict(r) for r in daily_meals],
        "meal_type_dist": [dict(r) for r in meal_type_dist],
    }
