from core.diet import db as diet_db


class MealNotFound(LookupError):
    pass


def list_meals() -> list[dict]:
    return diet_db.get_meals(limit=None)


def get_meal(meal_id: int) -> dict:
    records = diet_db.get_meals(meal_id=meal_id)
    meal = records[0] if records else None
    if meal is None:
        raise MealNotFound(f"Meal #{meal_id} does not exist")
    return meal


def update_meal(meal_id: int, foods: list[dict], changes: dict) -> dict:
    get_meal(meal_id)
    diet_db.update_meal_with_foods(meal_id, foods, **changes)
    return get_meal(meal_id)


def delete_meal(meal_id: int) -> None:
    get_meal(meal_id)
    diet_db.delete_meal(meal_id)


def update_meals(meal_ids: list[int], changes: dict) -> int:
    try:
        return diet_db.update_meals(meal_ids, changes)
    except LookupError as exc:
        raise MealNotFound(str(exc)) from exc


def delete_meals(meal_ids: list[int]) -> int:
    try:
        return diet_db.delete_meals(meal_ids)
    except LookupError as exc:
        raise MealNotFound(str(exc)) from exc


def get_stats(start_date: str, end_date: str) -> dict:
    return diet_db.get_diet_stats(start_date, end_date)
