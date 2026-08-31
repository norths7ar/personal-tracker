from core.expense import db as expense_db


class TransactionNotFound(LookupError):
    pass


class TransactionConflict(ValueError):
    pass


def list_transactions() -> list[dict]:
    return expense_db.get_transactions(limit=None)


def update_transaction(transaction_id: int, changes: dict) -> dict:
    if expense_db.get_transaction(transaction_id) is None:
        raise TransactionNotFound(f"Transaction #{transaction_id} does not exist")
    try:
        expense_db.update_transaction(transaction_id, **changes)
    except ValueError as exc:
        raise TransactionConflict(str(exc)) from exc
    updated = expense_db.get_transaction(transaction_id)
    if updated is None:
        raise TransactionNotFound(f"Transaction #{transaction_id} does not exist")
    return updated


def delete_transactions(transaction_ids: list[int]) -> int:
    try:
        return expense_db.delete_transactions(transaction_ids)
    except ValueError as exc:
        raise TransactionConflict(str(exc)) from exc
