from datetime import date as Date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator, model_validator

from backend.auth import require_api_auth
from backend.db import IdempotencyConflict
from backend.http import IdempotencyKey
from backend.ledger import analysis as analysis_service
from backend.ledger import planning
from backend.ledger import transactions as transaction_service
from backend.ledger.transactions import get_pending_transactions

router = APIRouter(prefix="/api/ledger", tags=["ledger"], dependencies=[Depends(require_api_auth)])

TransactionType = Literal["支出", "收入", "迁移"]


class TransactionResponse(BaseModel):
    id: int
    type: TransactionType
    description: str
    amount: float
    amount_cents: int | None = None
    date: Date
    category: str | None = None
    subcategory: str | None = None
    notes: str | None = None
    confidence: float | None = None
    reviewed: bool = False
    refund_for_id: int | None = None
    amortization_months: int | None = None
    amortization_start: Date | None = None
    subscription_id: int | None = None
    created_at: str | None = None


class TransactionUpdate(BaseModel):
    type: TransactionType | None = None
    description: str | None = Field(default=None, min_length=1)
    amount: float | None = Field(default=None, gt=0)
    date: Date | None = None
    category: str | None = None
    subcategory: str | None = None
    notes: str | None = None
    reviewed: bool | None = None
    amortization_months: int | None = Field(default=None, ge=2, le=120)
    amortization_start: Date | None = None

    @field_validator("type", "description", "amount", "date", "reviewed")
    @classmethod
    def require_non_null(cls, value):
        if value is None:
            raise ValueError("该字段不能清空")
        return value

    @model_validator(mode="after")
    def require_a_change(self):
        if not self.model_fields_set:
            raise ValueError("At least one field is required")
        return self


class BulkDeleteRequest(BaseModel):
    ids: list[int] = Field(min_length=1)


class BulkDeleteResponse(BaseModel):
    deleted_count: int


class BulkTransactionUpdateRequest(BaseModel):
    ids: list[int] = Field(min_length=1)
    category: str | None = None
    subcategory: str | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def require_a_change(self):
        if not (self.model_fields_set - {"ids"}):
            raise ValueError("At least one field is required")
        return self


class BulkCategoryUpdateResponse(BaseModel):
    updated_count: int


class RefundCreate(BaseModel):
    description: str = Field(min_length=1)
    amount: float = Field(gt=0)
    date: Date


class SubscriptionCreate(BaseModel):
    name: str = Field(min_length=1)
    next_renewal_date: Date
    renewal_mode: Literal["same_day", "fixed_days"]
    renewal_interval: int = Field(ge=1, le=730)
    renewal_anchor_day: int | None = Field(default=None, ge=1, le=31)


class CreatedRecord(BaseModel):
    id: int
    duplicate: bool


@router.get("/transactions", response_model=list[TransactionResponse])
def list_transactions() -> list[dict]:
    return transaction_service.get_transactions(limit=None)


@router.patch("/transactions/bulk-update", response_model=BulkCategoryUpdateResponse)
def bulk_update_transactions(
    body: BulkTransactionUpdateRequest,
) -> BulkCategoryUpdateResponse:
    changes = body.model_dump(exclude_unset=True, exclude={"ids"})
    try:
        updated_count = planning.update_transactions(body.ids, changes)
    except transaction_service.TransactionNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except transaction_service.TransactionConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return BulkCategoryUpdateResponse(updated_count=updated_count)


@router.patch("/transactions/{transaction_id}", response_model=TransactionResponse)
def update_transaction(transaction_id: int, body: TransactionUpdate) -> dict:
    changes = body.model_dump(exclude_unset=True)
    for field in ("date", "amortization_start"):
        if isinstance(changes.get(field), Date):
            changes[field] = changes[field].isoformat()
    try:
        return planning.update_transaction(transaction_id, changes)
    except transaction_service.TransactionNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except transaction_service.TransactionConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post("/transactions/bulk-delete", response_model=BulkDeleteResponse)
def bulk_delete_transactions(body: BulkDeleteRequest) -> BulkDeleteResponse:
    try:
        deleted_count = transaction_service.delete_transactions(body.ids)
    except transaction_service.TransactionConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return BulkDeleteResponse(deleted_count=deleted_count)


@router.post("/transactions/{transaction_id}/refunds", response_model=CreatedRecord)
def create_refund(transaction_id: int, body: RefundCreate, idempotency_key: IdempotencyKey) -> dict:
    payload = body.model_dump(mode="json")
    try:
        return transaction_service.create_refund(transaction_id, payload, idempotency_key)
    except transaction_service.TransactionConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post("/transactions/{transaction_id}/subscription", response_model=CreatedRecord)
def create_subscription(
    transaction_id: int,
    body: SubscriptionCreate,
    idempotency_key: IdempotencyKey,
) -> dict:
    payload = body.model_dump(mode="json")
    try:
        return planning.create_subscription(transaction_id, payload, idempotency_key)
    except transaction_service.TransactionConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


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


@router.get("/cross-period", response_model=CrossPeriodResponse)
def list_cross_period() -> dict:
    return planning.list_cross_period()


@router.post("/cross-period/expected", response_model=WriteResult)
def create_expected(body: ExpectedWrite, idempotency_key: IdempotencyKey) -> dict:
    payload = body.model_dump(mode="json")
    if body.recurring and body.due_date is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="周期性付款必须设置付款日",
        )
    try:
        return planning.create_expected(payload, idempotency_key)
    except IdempotencyConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.patch("/cross-period/expected/{source}/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
def update_expected(source: Source, record_id: int, body: ExpectedWrite) -> None:
    payload = body.model_dump(mode="json")
    if source == "subscription" and body.due_date is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="周期性付款必须设置付款日",
        )
    _run_value_error(planning.update_expected, source, record_id, payload)


@router.post("/cross-period/expected/{source}/{record_id}/confirm", response_model=WriteResult)
def confirm_expected(
    source: Source,
    record_id: int,
    body: ConfirmExpected,
    idempotency_key: IdempotencyKey,
) -> dict:
    try:
        return planning.confirm_expected(
            source, record_id, body.model_dump(mode="json"), idempotency_key
        )
    except IdempotencyConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc


@router.delete(
    "/cross-period/expected/{source}/{record_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_expected(source: Source, record_id: int) -> None:
    _run_value_error(planning.delete_expected, source, record_id)


@router.post("/cross-period/prepaid", response_model=WriteResult)
def create_prepaid(body: PrepaidWrite, idempotency_key: IdempotencyKey) -> dict:
    try:
        return planning.create_prepaid(body.model_dump(mode="json"), idempotency_key)
    except IdempotencyConflict as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.patch("/cross-period/prepaid/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
def update_prepaid(record_id: int, body: PrepaidUpdate) -> None:
    _run_value_error(planning.update_prepaid, record_id, body.model_dump(mode="json"))


@router.delete("/cross-period/prepaid/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_prepaid(record_id: int) -> None:
    _run_value_error(planning.delete_prepaid, record_id)


def _run_value_error(function, *args) -> None:
    try:
        function(*args)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc


class BreakdownItem(BaseModel):
    category: str | None
    subcategory: str | None
    total: float
    count: int


class DailyPoint(BaseModel):
    date: str
    income: float
    expense: float


class AnalysisEntry(BaseModel):
    id: int
    date: str
    allocation_date: str
    description: str
    category: str
    subcategory: str
    amount: float
    contribution: float
    type: str
    bucket: Literal["income", "expense"]


class PeriodData(BaseModel):
    income: float
    expense: float
    balance: float
    daily: list[DailyPoint]
    expense_breakdown: list[BreakdownItem]
    income_breakdown: list[BreakdownItem]
    entries: list[AnalysisEntry] = Field(default_factory=list)


class PeriodSummary(BaseModel):
    label: str
    income: float
    expense: float


class MonthBudget(BaseModel):
    amortized_total: float | None
    cash_total: float | None


class ExpenseAnalysisResponse(BaseModel):
    months: list[str]
    years: list[str]
    selected_period: str | None
    days: int | None = None
    start_date: str | None = None
    end_date: str | None = None
    current: PeriodData | None = None
    cash_current: PeriodData | None = None
    timeline: list[PeriodSummary] = Field(default_factory=list)
    fixed_monthly_cost: float | None = None
    budget: MonthBudget | None = None
    cash_expense: float | None = None
    amortized_expense: float | None = None


class MonthBudgetUpdate(BaseModel):
    amortized_total: float | None = Field(default=None, ge=0)
    cash_total: float | None = Field(default=None, ge=0)


@router.get("/analysis", response_model=ExpenseAnalysisResponse)
def expense_analysis(
    granularity: Literal["month", "year"] = Query(default="month"),
    period: str | None = None,
    basis: Literal["cash", "amortized"] = Query(default="amortized"),
) -> dict:
    return analysis_service.get_expense_analysis(granularity, period, basis)


@router.put("/budgets/{month}", response_model=MonthBudget)
def update_budget(month: str, body: MonthBudgetUpdate) -> dict:
    try:
        return analysis_service.update_month_budget(month, body.amortized_total, body.cash_total)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc


@router.get("/pending", response_model=list[TransactionResponse])
def list_pending_transactions() -> list[dict]:
    return get_pending_transactions(limit=None)
