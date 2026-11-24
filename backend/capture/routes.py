from datetime import date as Date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.auth import require_api_auth
from backend.capture import entries as entry_service
from backend.capture import phrases, queue
from backend.capture.batch import BatchSubmissionConflict
from backend.db import IdempotencyConflict
from backend.diet.models import FoodInput
from backend.http import IdempotencyKey, IsoDate
from backend.ledger import analysis as home_service
from backend.llm import LLMError

router = APIRouter(
    prefix="/api/capture", tags=["capture"], dependencies=[Depends(require_api_auth)]
)

TransactionType = Literal["支出", "收入", "迁移"]


class CaptureInput(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    @field_validator("description", "text", check_fields=False)
    @classmethod
    def nonblank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("内容不能为空")
        return value


class TransactionPreparationRequest(CaptureInput):
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


class TransactionCreateRequest(CaptureInput):
    type: TransactionType = "支出"
    description: str = Field(min_length=1)
    amount: float = Field(gt=0)
    date: Date = Field(default_factory=Date.today)
    category: str | None = None
    subcategory: str | None = None
    notes: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    coverage_start: IsoDate | None = None
    coverage_end: IsoDate | None = None
    reviewed: bool = False


class MealPreparationRequest(CaptureInput):
    description: str = Field(min_length=1)
    time: str | None = None


class MealPreparationResponse(BaseModel):
    status: str
    meal_type: str | None = None
    foods: list[FoodInput]
    confidence: float
    reasoning: str = ""


class MealCreateRequest(CaptureInput):
    date: Date = Field(default_factory=Date.today)
    time: str | None = None
    meal_type: str | None = None
    description: str = Field(min_length=1)
    notes: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    foods: list[FoodInput] = Field(default_factory=list)


class CreateResponse(BaseModel):
    id: int
    duplicate: bool


class BatchRecord(CaptureInput):
    include: bool = True
    record_type: Literal["支出", "收入", "迁移", "饮食"]
    date: Date
    time: str | None = ""
    description: str = Field(min_length=1)
    amount: float | None = None
    category: str = ""
    subcategory: str = ""
    meal_type: str | None = None
    foods: list[FoodInput] = Field(default_factory=list)
    notes: str | None = None
    confidence: float = Field(default=0, ge=0, le=1)
    reasoning: str = ""


class BatchPrepareRequest(CaptureInput):
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


class CaptureSubmission(CaptureInput):
    text: str = Field(min_length=1)
    default_date: Date


class CaptureItem(BaseModel):
    id: int
    submission_id: int
    source_text: str
    original_text: str
    default_date: Date
    status: Literal["queued", "processing", "review", "failed"]
    record: BatchRecord | None
    reason: str
    created_at: str
    can_retry: bool


class PendingCaptureResponse(BaseModel):
    change_token: str
    items: list[CaptureItem]
    pending_count: int
    processing_count: int


class CaptureRetryResponse(BaseModel):
    id: int


class PhraseInput(CaptureInput):
    text: str = Field(min_length=1, max_length=80)


class CaptureSuggestion(BaseModel):
    text: str
    pinned: bool
    count: int


@router.post("/submissions", response_model=CreateResponse, status_code=202)
def submit_capture(body: CaptureSubmission, idempotency_key: IdempotencyKey) -> dict:
    try:
        return queue.submit(body.text, body.default_date.isoformat(), idempotency_key)
    except IdempotencyConflict as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/pending", response_model=PendingCaptureResponse)
def pending_captures() -> dict:
    return queue.pending()


@router.post("/items/{item_id}/confirm", response_model=CreateResponse)
def confirm_capture(item_id: int, body: BatchRecord) -> dict:
    try:
        return queue.confirm(item_id, body.model_dump(mode="json"))
    except queue.CaptureNotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    except queue.CaptureConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/items/{item_id}/retry", response_model=CaptureRetryResponse)
def retry_capture(item_id: int) -> dict:
    try:
        return queue.retry(item_id)
    except queue.CaptureNotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    except queue.CaptureConflict as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/items/{item_id}/discard", status_code=204)
def discard_capture(item_id: int) -> None:
    try:
        queue.discard(item_id)
    except queue.CaptureNotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    except queue.CaptureConflict as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/suggestions", response_model=list[CaptureSuggestion])
def capture_suggestions() -> list[dict]:
    return phrases.suggestions()


@router.put("/phrases", response_model=list[CaptureSuggestion])
def pin_phrase(body: PhraseInput) -> list[dict]:
    try:
        return phrases.pin(body.text)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.delete("/phrases", response_model=list[CaptureSuggestion])
def unpin_phrase(body: PhraseInput) -> list[dict]:
    return phrases.unpin(body.text)


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
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc


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
    description: str


class HomeSummary(BaseModel):
    reminders: list[Reminder]
    pending_count: int
    today_expense: float
    today_meals: list[TodayMeal]


@router.get("/home", response_model=HomeSummary)
def home_summary() -> dict:
    summary = home_service.get_home_summary()
    summary["pending_count"] = queue.pending_count()
    return summary
