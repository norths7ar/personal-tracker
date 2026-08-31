from datetime import date as Date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from api.routes.entries import FoodInput
from api.security import require_api_auth
from services import meals as meal_service

router = APIRouter(
    prefix="/api/meals",
    tags=["meals"],
    dependencies=[Depends(require_api_auth)],
)


class MealResponse(BaseModel):
    id: int
    date: Date
    time: str | None = None
    meal_type: str | None = None
    description: str
    notes: str | None = None
    confidence: float | None = None
    created_at: str | None = None
    foods: list[FoodInput]


class MealUpdate(BaseModel):
    date: Date
    time: str = Field(pattern=r"^\d{2}:\d{2}$")
    meal_type: str | None = None
    description: str = Field(min_length=1)
    notes: str | None = None
    foods: list[FoodInput] = Field(min_length=1)


class CountByDate(BaseModel):
    date: Date
    count: int


class CountByMealType(BaseModel):
    meal_type: str
    count: int


class CountByFood(BaseModel):
    food_name: str
    count: int


class MealTimePoint(BaseModel):
    date: Date
    time: str


class DietStatsResponse(BaseModel):
    meal_times: list[MealTimePoint]
    food_freq: list[CountByFood]
    daily_meals: list[CountByDate]
    meal_type_dist: list[CountByMealType]


@router.get("", response_model=list[MealResponse])
def list_meals() -> list[dict]:
    return meal_service.list_meals()


@router.get("/stats", response_model=DietStatsResponse)
def diet_stats(
    start_date: Annotated[Date, Query()], end_date: Annotated[Date, Query()]
) -> dict:
    return meal_service.get_stats(start_date.isoformat(), end_date.isoformat())


@router.patch("/{meal_id}", response_model=MealResponse)
def update_meal(meal_id: int, body: MealUpdate) -> dict:
    payload = body.model_dump(mode="json")
    foods = payload.pop("foods")
    payload["description"] = body.description.strip()
    try:
        return meal_service.update_meal(meal_id, foods, payload)
    except meal_service.MealNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc


@router.delete("/{meal_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_meal(meal_id: int) -> None:
    try:
        meal_service.delete_meal(meal_id)
    except meal_service.MealNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
