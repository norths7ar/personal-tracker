from datetime import date as Date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from backend.auth import require_api_auth
from backend.capture import entries as entry_service
from backend.capture.batch import BatchSubmissionConflict
from backend.db import IdempotencyConflict
from backend.diet.models import FoodInput
from backend.http import IdempotencyKey
from backend.ledger import analysis as home_service
from backend.llm import LLMError

router = APIRouter(
    prefix="/api/capture", tags=["capture"], dependencies=[Depends(require_api_auth)]
)

TransactionType = Literal["支出", "收入", "迁移"]


class TransactionPreparationRequest(BaseModel):
    type: TransactionType
    description: str = Field(min_length=1)


class ClassificationCandidate(BaseModel):
    category: str
    subcategory: str
    confidence: float


class TransactionPreparationResponse(BaseModel):
    status: str
    category: str
    subcategory: str
    confidence: float | None = None
    reasoning: str = ""
    candidates: list[ClassificationCandidate] = Field(default_factory=list)


class TransactionCreateRequest(BaseModel):
    type: TransactionType
    description: str = Field(min_length=1)
    amount: float = Field(gt=0)
    date: Date
    category: str | None = None
    subcategory: str | None = None
    notes: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    reviewed: bool = False


class MealPreparationRequest(BaseModel):
    description: str = Field(min_length=1)
    time: str = Field(pattern=r"^\d{2}:\d{2}$")


class MealPreparationResponse(BaseModel):
    status: str
    meal_type: str | None = None
    foods: list[FoodInput]
    confidence: float
    reasoning: str = ""


class MealCreateRequest(BaseModel):
    date: Date
    time: str = Field(pattern=r"^\d{2}:\d{2}$")
    meal_type: str | None = None
    description: str = Field(min_length=1)
    notes: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    foods: list[FoodInput] = Field(min_length=1)


class CreateResponse(BaseModel):
    id: int
    duplicate: bool


class BatchRecord(BaseModel):
    include: bool = True
    record_type: Literal["支出", "收入", "迁移", "饮食"]
    date: Date
    time: str = ""
    description: str = Field(min_length=1)
    amount: float | None = None
    category: str = ""
    subcategory: str = ""
    meal_type: str | None = None
    foods: list[FoodInput] = Field(default_factory=list)
    notes: str | None = None
    confidence: float = Field(default=0, ge=0, le=1)
    reasoning: str = ""


class BatchPrepareRequest(BaseModel):
    text: str = Field(min_length=1)
    default_date: Date


class BatchDiagnostics(BaseModel):
    rejected_records: list[dict] = Field(default_factory=list)
    reasoning: str = ""


class BatchPrepareResponse(BaseModel):
    status: str
    records: list[BatchRecord]
    diagnostics: BatchDiagnostics


class BatchSaveRequest(BaseModel):
    submission_id: str = Field(min_length=8)
    records: list[BatchRecord] = Field(min_length=1)


class BatchSaveResponse(BaseModel):
    saved_count: int
    duplicate: bool


@router.post("/transactions/prepare", response_model=TransactionPreparationResponse)
def prepare_transaction(
    body: TransactionPreparationRequest,
) -> dict:
    try:
        return entry_service.prepare_transaction(body.type, body.description.strip())
    except LLMError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc


@router.post("/transactions", response_model=CreateResponse)
def create_transaction(body: TransactionCreateRequest, idempotency_key: IdempotencyKey) -> dict:
    payload = body.model_dump(mode="json")
    payload["description"] = body.description.strip()
    try:
        return entry_service.create_transaction(payload, idempotency_key)
    except IdempotencyConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post("/meals/prepare", response_model=MealPreparationResponse)
def prepare_meal(body: MealPreparationRequest) -> dict:
    try:
        return entry_service.prepare_meal(body.description.strip(), body.time)
    except (ValueError, LLMError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc


@router.post("/meals", response_model=CreateResponse)
def create_meal(body: MealCreateRequest, idempotency_key: IdempotencyKey) -> dict:
    payload = body.model_dump(mode="json")
    payload["description"] = body.description.strip()
    try:
        return entry_service.create_meal(payload, idempotency_key)
    except IdempotencyConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc


@router.post("/batch/prepare", response_model=BatchPrepareResponse)
def prepare_batch(body: BatchPrepareRequest) -> dict:
    try:
        return entry_service.prepare_batch(body.text.strip(), body.default_date.isoformat())
    except LLMError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc


@router.post("/batch", response_model=BatchSaveResponse)
def save_batch(body: BatchSaveRequest) -> dict:
    try:
        return entry_service.save_reviewed_batch(
            body.submission_id,
            [record.model_dump(mode="json") for record in body.records],
        )
    except BatchSubmissionConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc


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


@router.get("/home", response_model=HomeSummary)
def home_summary() -> dict:
    return home_service.get_home_summary()
