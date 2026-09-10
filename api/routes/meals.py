from datetime import date as Date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from api.routes.entries import FoodInput
from api.security import require_api_auth
from core.diet.meal_time import require_meal_time
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


class BulkMealIds(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ids: list[Annotated[int, Field(strict=True, gt=0)]] = Field(min_length=1)


class BulkMealUpdate(BulkMealIds):
    date: Date | None = None
    time: str | None = None
    meal_type: str | None = None
    notes: str | None = None

    @field_validator("date", "time")
    @classmethod
    def require_non_null(cls, value):
        if value is None:
            raise ValueError("日期和时间不能清空")
        return value

    @field_validator("time")
    @classmethod
    def validate_time(cls, value):
        return require_meal_time(value)

    @model_validator(mode="after")
    def require_a_change(self):
        if not self.model_fields_set - {"ids"}:
            raise ValueError("请至少选择一个修改字段")
        return self


class BulkMealUpdateResponse(BaseModel):
    updated_count: int


class BulkMealDeleteResponse(BaseModel):
    deleted_count: int


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


class CountByIngredient(BaseModel):
    ingredient_name: str
    count: int


class DietStatsResponse(BaseModel):
    meal_times: list[MealTimePoint]
    food_freq: list[CountByFood]
    ingredient_freq: list[CountByIngredient]
    ingredient_record_count: int
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


@router.patch("/bulk-update", response_model=BulkMealUpdateResponse)
def bulk_update_meals(body: BulkMealUpdate) -> BulkMealUpdateResponse:
    changes = body.model_dump(mode="json", exclude_unset=True, exclude={"ids"})
    try:
        count = meal_service.update_meals(body.ids, changes)
    except meal_service.MealNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return BulkMealUpdateResponse(updated_count=count)


@router.post("/bulk-delete", response_model=BulkMealDeleteResponse)
def bulk_delete_meals(body: BulkMealIds) -> BulkMealDeleteResponse:
    try:
        count = meal_service.delete_meals(body.ids)
    except meal_service.MealNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return BulkMealDeleteResponse(deleted_count=count)


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
