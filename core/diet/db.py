from contextlib import closing

from core.db import (
    _connect,
    placeholders,
)
from core.diet.ingredients import normalize_ingredients
from core.diet.meal_time import require_meal_time


def _normalize_foods(foods: list[dict]) -> list[dict]:
    normalized = []
    for food in foods:
        food_name = str(food.get("food_name") or "").strip()
        if not food_name:
            continue
        normalized.append(
            {
                "food_name": food_name,
                "quantity": str(food.get("quantity") or "").strip(),
                "ingredients": normalize_ingredients(food.get("ingredients")),
            }
        )
    if not normalized:
        raise ValueError("请至少填写一种食物")
    return normalized


def _insert_foods(conn, meal_id: int, foods: list[dict]) -> None:
    for food in _normalize_foods(foods):
        cur = conn.execute(
            "INSERT INTO diet_foods (meal_id, food_name, quantity) VALUES (?, ?, ?)",
            (meal_id, food["food_name"], food["quantity"]),
        )
        food_id = cur.lastrowid
        if food["ingredients"]:
            conn.executemany(
                """INSERT INTO diet_ingredients (food_id, ingredient_name)
                   VALUES (?, ?)""",
                [(food_id, ingredient) for ingredient in food["ingredients"]],
            )


def add_meal(
    date: str,
    time: str,
    meal_type: str | None,
    description: str,
    notes: str | None,
    confidence: float | None,
    foods: list[dict],
) -> int:
    """
    Insert one meal + its food items atomically.
    foods: [{"food_name": str, "quantity": str, "ingredients": [str, ...]}, ...]
    Returns meal_id.
    """
    with closing(_connect()) as conn:
        meal_id = _insert_meal(
            conn,
            date,
            time,
            meal_type,
            description,
            notes,
            confidence,
            foods,
        )
        conn.commit()
    return meal_id


def _insert_meal(
    conn,
    date: str,
    time: str,
    meal_type: str | None,
    description: str,
    notes: str | None,
    confidence: float | None,
    foods: list[dict],
) -> int:
    normalized_time = require_meal_time(time)
    normalized_meal_type = str(meal_type or "").strip() or None
    cur = conn.execute(
        """INSERT INTO diet_meals
           (date, time, meal_type, description, notes, confidence)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            date,
            normalized_time,
            normalized_meal_type,
            description,
            notes,
            confidence,
        ),
    )
    meal_id = cur.lastrowid
    _insert_foods(conn, meal_id, foods)
    return meal_id


def get_meals(
    start_date: str | None = None,
    end_date: str | None = None,
    meal_type: str | None = None,
    limit: int = 200,
) -> list[dict]:
    """
    Return list of meal dicts, each with a 'foods' key:
    [{"id", "date", "time", "meal_type", "description", "notes", "confidence",
      "created_at", "foods": [{"food_name", "quantity", "ingredients"}, ...]}, ...]
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
        food_rows = conn.execute(
            (
                "SELECT * FROM diet_foods "
                f"WHERE meal_id IN ({placeholders(len(meal_ids))}) "
                "ORDER BY id"
            ),
            meal_ids,
        ).fetchall()
        food_ids = [food["id"] for food in food_rows]
        ingredient_rows = (
            conn.execute(
                (
                    "SELECT * FROM diet_ingredients "
                    f"WHERE food_id IN ({placeholders(len(food_ids))}) "
                    "ORDER BY id"
                ),
                food_ids,
            ).fetchall()
            if food_ids
            else []
        )

    ingredients_by_food: dict[int, list[str]] = {}
    for ingredient in ingredient_rows:
        ingredients_by_food.setdefault(ingredient["food_id"], []).append(
            ingredient["ingredient_name"]
        )
    foods_by_meal: dict = {}
    for f in food_rows:
        foods_by_meal.setdefault(f["meal_id"], []).append(
            {
                "food_name": f["food_name"],
                "quantity": f["quantity"] or "",
                "ingredients": ingredients_by_food.get(f["id"], []),
            }
        )
    for meal in meals:
        meal["foods"] = foods_by_meal.get(meal["id"], [])
    return meals


def update_meal_with_foods(meal_id: int, foods: list, **fields):
    """Update meal metadata and replace food items atomically in one transaction."""
    allowed = {"date", "time", "meal_type", "description", "notes", "confidence"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if "time" in updates:
        updates["time"] = require_meal_time(updates["time"])
    if "meal_type" in updates:
        updates["meal_type"] = str(updates["meal_type"] or "").strip() or None
    with closing(_connect()) as conn:
        if updates:
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            conn.execute(
                f"UPDATE diet_meals SET {set_clause} WHERE id = ?",
                [*updates.values(), meal_id],
            )
        conn.execute("DELETE FROM diet_foods WHERE meal_id = ?", (meal_id,))
        _insert_foods(conn, meal_id, foods)
        conn.commit()


def delete_meal(meal_id: int):
    with closing(_connect()) as conn:
        conn.execute("DELETE FROM diet_meals WHERE id = ?", (meal_id,))
        conn.commit()


def get_diet_summary(start_date: str, end_date: str) -> dict:
    """Sidebar/quick stats: meal_type counts + recent meals with food list."""
    with closing(_connect()) as conn:
        meal_stats = conn.execute(
            """SELECT meal_type, COUNT(*) as count
               FROM diet_meals
               WHERE date >= ? AND date <= ?
                 AND meal_type IS NOT NULL AND meal_type <> ''
               GROUP BY meal_type ORDER BY count DESC""",
            (start_date, end_date),
        ).fetchall()

        recent_sql = """SELECT m.date, m.meal_type, m.time,
                               GROUP_CONCAT(f.food_name, '、') as foods
                        FROM diet_meals m
                        LEFT JOIN diet_foods f ON f.meal_id = m.id
                        WHERE m.date >= ? AND m.date <= ?
                        GROUP BY m.id
                        ORDER BY m.date DESC, m.time DESC
                        LIMIT 10"""
        recent = conn.execute(recent_sql, (start_date, end_date)).fetchall()

    return {
        "meal_stats": [dict(r) for r in meal_stats],
        "recent": [dict(r) for r in recent],
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
        meal_times = conn.execute(
            """SELECT date, time FROM diet_meals
               WHERE date >= ? AND date <= ?
                 AND time IS NOT NULL AND time <> ''
               ORDER BY date, time""",
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
                 AND meal_type IS NOT NULL AND meal_type <> ''
               GROUP BY meal_type ORDER BY count DESC""",
            (start_date, end_date),
        ).fetchall()

    return {
        "meal_times": [dict(r) for r in meal_times],
        "food_freq": [dict(r) for r in food_freq],
        "daily_meals": [dict(r) for r in daily_meals],
        "meal_type_dist": [dict(r) for r in meal_type_dist],
    }
