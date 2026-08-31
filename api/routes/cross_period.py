from datetime import date as Date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from api.routes.entries import IdempotencyKey
from api.security import require_api_auth
from core.idempotency import IdempotencyConflict
from services import cross_period as cross_period_service

router = APIRouter(
    prefix="/api/cross-period",
    tags=["cross-period"],
    dependencies=[Depends(require_api_auth)],
)

Source = Literal["subscription", "plan"]
RenewalMode = Literal["same_day", "fixed_days"]


class ExpectedRecord(BaseModel):
    id: int
    source: Source
    description: str
    amount: float
    next_date: str | None
    cycle: str
    category: str | None
    subcategory: str | None
    notes: str | None
    renewal_mode: RenewalMode | None
    renewal_interval: int | None
    state: str


class PrepaidRecord(BaseModel):
    id: int
    transaction_id: int
    description: str
    amount: float
    monthly_equivalent: float
    months: int
    remaining_months: int
    start_month: str
    category: str | None
    subcategory: str | None
    notes: str | None


class CrossPeriodResponse(BaseModel):
    expected: list[ExpectedRecord]
    prepaid: list[PrepaidRecord]


class ExpectedWrite(BaseModel):
    description: str = Field(min_length=1)
    amount: float = Field(gt=0)
    recurring: bool = False
    due_date: Date | None = None
    category: str | None = None
    subcategory: str | None = None
    notes: str | None = None
    renewal_mode: RenewalMode = "same_day"
    renewal_interval: int = Field(default=1, ge=1, le=730)


class ConfirmExpected(BaseModel):
    description: str = Field(min_length=1)
    amount: float = Field(gt=0)
    payment_date: Date
    category: str | None = None
    subcategory: str | None = None
    notes: str | None = None


class PrepaidWrite(BaseModel):
    description: str = Field(min_length=1)
    amount: float = Field(gt=0)
    payment_date: Date
    months: int = Field(ge=1, le=120)
    start_month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    category: str | None = None
    subcategory: str | None = None
    notes: str | None = None


class PrepaidUpdate(BaseModel):
    description: str = Field(min_length=1)
    months: int = Field(ge=1, le=120)
    start_month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    category: str | None = None
    subcategory: str | None = None
    notes: str | None = None


class WriteResult(BaseModel):
    id: int | None = None
    source: str | None = None
    transaction_id: int | None = None
    subscription_id: int | None = None
    duplicate: bool


@router.get("", response_model=CrossPeriodResponse)
def list_cross_period() -> dict:
    return cross_period_service.list_cross_period()


@router.post("/expected", response_model=WriteResult)
def create_expected(body: ExpectedWrite, idempotency_key: IdempotencyKey) -> dict:
    payload = body.model_dump(mode="json")
    if body.recurring and body.due_date is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="周期性付款必须设置付款日",
        )
    try:
        return cross_period_service.create_expected(payload, idempotency_key)
    except IdempotencyConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc


@router.patch("/expected/{source}/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
def update_expected(source: Source, record_id: int, body: ExpectedWrite) -> None:
    payload = body.model_dump(mode="json")
    if source == "subscription" and body.due_date is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="周期性付款必须设置付款日",
        )
    _run_value_error(cross_period_service.update_expected, source, record_id, payload)


@router.post("/expected/{source}/{record_id}/confirm", response_model=WriteResult)
def confirm_expected(
    source: Source,
    record_id: int,
    body: ConfirmExpected,
    idempotency_key: IdempotencyKey,
) -> dict:
    try:
        return cross_period_service.confirm_expected(
            source, record_id, body.model_dump(mode="json"), idempotency_key
        )
    except IdempotencyConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc


@router.delete("/expected/{source}/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_expected(source: Source, record_id: int) -> None:
    _run_value_error(cross_period_service.delete_expected, source, record_id)


@router.post("/prepaid", response_model=WriteResult)
def create_prepaid(body: PrepaidWrite, idempotency_key: IdempotencyKey) -> dict:
    try:
        return cross_period_service.create_prepaid(
            body.model_dump(mode="json"), idempotency_key
        )
    except IdempotencyConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc


@router.patch("/prepaid/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
def update_prepaid(record_id: int, body: PrepaidUpdate) -> None:
    _run_value_error(
        cross_period_service.update_prepaid, record_id, body.model_dump(mode="json")
    )


@router.delete("/prepaid/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_prepaid(record_id: int) -> None:
    _run_value_error(cross_period_service.delete_prepaid, record_id)


def _run_value_error(function, *args) -> None:
    try:
        function(*args)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
