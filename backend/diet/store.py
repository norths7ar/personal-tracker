import math
import re
from contextlib import closing
from datetime import date as Date

from backend.db import (
    connect,
    placeholders,
)

_MEAL_TIME_PATTERN = re.compile(r"^(?P<hour>\d{1,2}):(?P<minute>\d{2})$")


def normalize_meal_time(value: object) -> str | None:
    """Normalize a meal time to HH:MM, returning None for blank or invalid input."""
    text = str(value or "").strip()
    match = _MEAL_TIME_PATTERN.fullmatch(text)
    if not match:
        return None

    hour = int(match.group("hour"))
    minute = int(match.group("minute"))
    if hour > 23 or minute > 59:
        return None
    return f"{hour:02d}:{minute:02d}"


def optional_meal_time(value: object) -> str | None:
    if value is None or not str(value).strip():
        return None
    return require_meal_time(value)


def require_meal_time(value: object) -> str:
    normalized = normalize_meal_time(value)
    if normalized is None:
        raise ValueError("用餐时间必须是 HH:MM 格式")
    return normalized


def infer_meal_type(value: object) -> str | None:
    """Infer only conventional meal windows; ambiguous times remain unlabeled."""
    normalized = normalize_meal_time(value)
    if normalized is None:
        return None

    hour, minute = (int(part) for part in normalized.split(":"))
    minutes = hour * 60 + minute
    if 5 * 60 <= minutes < 10 * 60:
        return "早餐"
    if 11 * 60 <= minutes < 14 * 60:
        return "午餐"
    if 17 * 60 <= minutes < 21 * 60:
        return "晚餐"
    return None


def resolve_meal_type(explicit_label: object, meal_time: object) -> str | None:
    label = str(explicit_label or "").strip()
    return label or infer_meal_type(meal_time)


INGREDIENT_SEPARATOR_PATTERN = re.compile(r"[、,，;；\n]+")


def normalize_ingredients(value) -> list[str]:
    """Return unique, nonblank ingredient names while preserving order."""
    values = value if isinstance(value, (list, tuple, set)) else [value]
    normalized = []
    seen = set()
    for item in values:
        for part in INGREDIENT_SEPARATOR_PATTERN.split(display_text(item)):
            name = part.strip()
            if name and name not in seen:
                seen.add(name)
                normalized.append(name)
    return normalized


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


def insert_meal(
    conn,
    date: str,
    time: str | None,
    meal_type: str | None,
    description: str,
    notes: str | None,
    confidence: float | None,
    foods: list[dict],
    *,
    allow_empty_foods: bool = False,
) -> int:
    normalized_time = optional_meal_time(time)
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
    if foods or not allow_empty_foods:
        _insert_foods(conn, meal_id, foods)
    return meal_id


def get_meals(
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int | None = 200,
    *,
    meal_id: int | None = None,
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
    if meal_id is not None:
        query += " AND id = ?"
        params.append(meal_id)
    query += " ORDER BY date DESC, time DESC, id DESC"
    if limit is not None:
        query += " LIMIT ?"
        params.append(limit)

    with closing(connect()) as conn:
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
        updates["time"] = optional_meal_time(updates["time"])
    if "meal_type" in updates:
        updates["meal_type"] = str(updates["meal_type"] or "").strip() or None
    with closing(connect()) as conn:
        if updates:
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            conn.execute(
                f"UPDATE diet_meals SET {set_clause} WHERE id = ?",
                [*updates.values(), meal_id],
            )
        conn.execute("DELETE FROM diet_foods WHERE meal_id = ?", (meal_id,))
        if foods:
            _insert_foods(conn, meal_id, foods)
        conn.commit()


def delete_meal(meal_id: int):
    get_meal(meal_id)
    with closing(connect()) as conn:
        conn.execute("DELETE FROM diet_meals WHERE id = ?", (meal_id,))
        conn.commit()


def _require_meals(conn, meal_ids: list[int]) -> list[int]:
    ids = list(dict.fromkeys(meal_ids))
    if not ids:
        raise ValueError("请至少选择一条饮食记录")
    found = {
        row["id"]
        for row in conn.execute(
            f"SELECT id FROM diet_meals WHERE id IN ({placeholders(len(ids))})", ids
        )
    }
    missing = set(ids) - found
    if missing:
        raise MealNotFound(f"Meal IDs do not exist: {sorted(missing)}")
    return ids


def update_meals(meal_ids: list[int], changes: dict) -> int:
    """Update only shared metadata, preserving foods and historical missing times."""
    if not changes or changes.keys() - {"date", "time", "meal_type", "notes"}:
        raise ValueError("批量编辑仅支持日期、时间、餐顿标签和备注")
    updates = dict(changes)
    if "date" in updates:
        updates["date"] = Date.fromisoformat(str(updates["date"])).isoformat()
    if "time" in updates:
        updates["time"] = optional_meal_time(updates["time"])
    if "meal_type" in updates:
        updates["meal_type"] = str(updates["meal_type"] or "").strip() or None
    with closing(connect()) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        ids = _require_meals(conn, meal_ids)
        set_clause = ", ".join(f"{field} = ?" for field in updates)
        conn.execute(
            f"UPDATE diet_meals SET {set_clause} WHERE id IN ({placeholders(len(ids))})",
            [*updates.values(), *ids],
        )
    return len(ids)


def delete_meals(meal_ids: list[int]) -> int:
    """Delete selected meals and cascading food/ingredient rows atomically."""
    with closing(connect()) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        ids = _require_meals(conn, meal_ids)
        conn.execute(f"DELETE FROM diet_meals WHERE id IN ({placeholders(len(ids))})", ids)
    return len(ids)


def get_diet_stats(start_date, end_date) -> dict:
    """Data for the analysis page."""
    with closing(connect()) as conn:
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

        # A shared ingredient in multiple dishes counts once per eating record.
        ingredient_freq = conn.execute(
            """SELECT i.ingredient_name, COUNT(DISTINCT m.id) as count
               FROM diet_ingredients i
               JOIN diet_foods f ON f.id = i.food_id
               JOIN diet_meals m ON m.id = f.meal_id
               WHERE m.date >= ? AND m.date <= ?
               GROUP BY i.ingredient_name
               ORDER BY count DESC, i.ingredient_name
               LIMIT 20""",
            (start_date, end_date),
        ).fetchall()
        ingredient_record_count = conn.execute(
            """SELECT COUNT(DISTINCT m.id)
               FROM diet_meals m
               JOIN diet_foods f ON f.meal_id = m.id
               JOIN diet_ingredients i ON i.food_id = f.id
               WHERE m.date >= ? AND m.date <= ?""",
            (start_date, end_date),
        ).fetchone()[0]

        # Counts of records, not inferred meals; absent dates are unrecorded.
        daily_meals = conn.execute(
            """SELECT date, COUNT(*) as count
               FROM diet_meals
               WHERE date >= ? AND date <= ?
               GROUP BY date ORDER BY date""",
            (start_date, end_date),
        ).fetchall()

    return {
        "meal_times": [dict(r) for r in meal_times],
        "food_freq": [dict(r) for r in food_freq],
        "ingredient_freq": [dict(r) for r in ingredient_freq],
        "ingredient_record_count": ingredient_record_count,
        "daily_meals": [dict(r) for r in daily_meals],
    }


class MealNotFound(LookupError):
    pass


def get_meal(meal_id: int) -> dict:
    records = get_meals(meal_id=meal_id)
    meal = records[0] if records else None
    if meal is None:
        raise MealNotFound(f"Meal #{meal_id} does not exist")
    return meal


def update_meal(meal_id: int, foods: list[dict] | None, changes: dict) -> dict:
    current = get_meal(meal_id)
    update_meal_with_foods(meal_id, current["foods"] if foods is None else foods, **changes)
    return get_meal(meal_id)


def display_text(value: object) -> str:
    """Normalize optional ingredient and quantity text from extraction results."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    if isinstance(value, str) and (not value.strip() or value.strip().lower() == "nan"):
        return ""
    return str(value)
