from core.diet import db as diet_db


class MealNotFound(LookupError):
    pass


def list_meals() -> list[dict]:
    return diet_db.get_meals(limit=10_000)


def get_meal(meal_id: int) -> dict:
    meal = next((item for item in list_meals() if item["id"] == meal_id), None)
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


def get_stats(start_date: str, end_date: str) -> dict:
    return diet_db.get_diet_stats(start_date, end_date)
