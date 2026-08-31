from fastapi import APIRouter, Depends

from api.routes.transactions import TransactionResponse
from api.security import require_api_auth
from core.expense.db import get_pending_transactions

router = APIRouter(
    prefix="/api/pending-transactions",
    tags=["pending-transactions"],
    dependencies=[Depends(require_api_auth)],
)


@router.get("", response_model=list[TransactionResponse])
def list_pending_transactions() -> list[dict]:
    return get_pending_transactions()
