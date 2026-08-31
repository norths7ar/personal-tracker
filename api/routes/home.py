from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.security import require_api_auth
from services import home as home_service

router = APIRouter(
    prefix="/api/home",
    tags=["home"],
    dependencies=[Depends(require_api_auth)],
)


class Reminder(BaseModel):
    source: str
    id: int
    description: str
    amount: float
    due_date: str
    days_until_due: int


class TodayMeal(BaseModel):
    id: int
    time: str | None
    meal_type: str | None
    foods: list[str]


class HomeSummary(BaseModel):
    reminders: list[Reminder]
    pending_count: int
    today_expense: float
    today_meals: list[TodayMeal]


@router.get("", response_model=HomeSummary)
def home_summary() -> dict:
    return home_service.get_home_summary()
