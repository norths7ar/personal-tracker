from datetime import date as Date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

from api.security import require_api_auth
from core.batch.db import BatchSubmissionConflict
from core.idempotency import IdempotencyConflict
from services import entries as entry_service

router = APIRouter(
    prefix="/api/entries",
    tags=["entries"],
    dependencies=[Depends(require_api_auth)],
)

TransactionType = Literal["支出", "收入", "迁移"]
IdempotencyKey = Annotated[str, Header(alias="Idempotency-Key", min_length=8)]


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


class FoodInput(BaseModel):
    food_name: str = Field(min_length=1)
    quantity: str = ""
    ingredients: list[str] = Field(default_factory=list)


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
    return entry_service.prepare_transaction(body.type, body.description.strip())


@router.post("/transactions", response_model=CreateResponse)
def create_transaction(
    body: TransactionCreateRequest, idempotency_key: IdempotencyKey
) -> dict:
    payload = body.model_dump(mode="json")
    payload["description"] = body.description.strip()
    try:
        return entry_service.create_transaction(payload, idempotency_key)
    except IdempotencyConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc


@router.post("/meals/prepare", response_model=MealPreparationResponse)
def prepare_meal(body: MealPreparationRequest) -> dict:
    try:
        return entry_service.prepare_meal(body.description.strip(), body.time)
    except ValueError as exc:
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
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc


@router.post("/batch/prepare", response_model=BatchPrepareResponse)
def prepare_batch(body: BatchPrepareRequest) -> dict:
    return entry_service.prepare_batch(body.text.strip(), body.default_date.isoformat())


@router.post("/batch", response_model=BatchSaveResponse)
def save_batch(body: BatchSaveRequest) -> dict:
    try:
        return entry_service.save_reviewed_batch(
            body.submission_id,
            [record.model_dump(mode="json") for record in body.records],
        )
    except BatchSubmissionConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
