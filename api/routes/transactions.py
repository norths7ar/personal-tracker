from datetime import date as Date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, model_validator

from api.routes.entries import IdempotencyKey
from api.security import require_api_auth
from services import transactions as transaction_service

router = APIRouter(
    prefix="/api/transactions",
    tags=["transactions"],
    dependencies=[Depends(require_api_auth)],
)

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

    @model_validator(mode="after")
    def require_a_change(self):
        if not self.model_fields_set:
            raise ValueError("At least one field is required")
        return self


class BulkDeleteRequest(BaseModel):
    ids: list[int] = Field(min_length=1)


class BulkDeleteResponse(BaseModel):
    deleted_count: int


class RefundCreate(BaseModel):
    description: str = Field(min_length=1)
    amount: float = Field(gt=0)
    date: Date


class SubscriptionCreate(BaseModel):
    name: str = Field(min_length=1)
    billing_cycle: Literal["月付", "季付", "年付", "自定义"]
    billing_interval_months: int | None = Field(default=None, ge=1, le=120)
    next_renewal_date: Date
    renewal_mode: Literal["same_day", "fixed_days"]
    renewal_interval: int = Field(ge=1, le=730)
    renewal_anchor_day: int | None = Field(default=None, ge=1, le=31)


class CreatedRecord(BaseModel):
    id: int
    duplicate: bool


@router.get("", response_model=list[TransactionResponse])
def list_transactions() -> list[dict]:
    return transaction_service.list_transactions()


@router.patch("/{transaction_id}", response_model=TransactionResponse)
def update_transaction(transaction_id: int, body: TransactionUpdate) -> dict:
    changes = body.model_dump(exclude_unset=True)
    for field in ("date", "amortization_start"):
        if isinstance(changes.get(field), Date):
            changes[field] = changes[field].isoformat()
    try:
        return transaction_service.update_transaction(transaction_id, changes)
    except transaction_service.TransactionNotFound as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except transaction_service.TransactionConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc


@router.post("/bulk-delete", response_model=BulkDeleteResponse)
def bulk_delete_transactions(body: BulkDeleteRequest) -> BulkDeleteResponse:
    try:
        deleted_count = transaction_service.delete_transactions(body.ids)
    except transaction_service.TransactionConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    return BulkDeleteResponse(deleted_count=deleted_count)


@router.post("/{transaction_id}/refunds", response_model=CreatedRecord)
def create_refund(
    transaction_id: int, body: RefundCreate, idempotency_key: IdempotencyKey
) -> dict:
    payload = body.model_dump(mode="json")
    try:
        return transaction_service.create_refund(
            transaction_id, payload, idempotency_key
        )
    except transaction_service.TransactionConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc


@router.post("/{transaction_id}/subscription", response_model=CreatedRecord)
def create_subscription(
    transaction_id: int,
    body: SubscriptionCreate,
    idempotency_key: IdempotencyKey,
) -> dict:
    payload = body.model_dump(mode="json")
    try:
        return transaction_service.create_subscription(
            transaction_id, payload, idempotency_key
        )
    except transaction_service.TransactionConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
