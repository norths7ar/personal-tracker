from core.expense import db as expense_db
from core.idempotency import execute_idempotent
from core.subscription import db as subscription_db


class TransactionNotFound(LookupError):
    pass


class TransactionConflict(ValueError):
    pass


def list_transactions() -> list[dict]:
    return expense_db.get_transactions(limit=None)


def update_transaction(transaction_id: int, changes: dict) -> dict:
    try:
        expense_db.update_transaction(transaction_id, **changes)
    except LookupError as exc:
        raise TransactionNotFound(str(exc)) from exc
    except ValueError as exc:
        raise TransactionConflict(str(exc)) from exc
    updated = expense_db.get_transaction(transaction_id)
    if updated is None:
        raise TransactionNotFound(f"Transaction #{transaction_id} does not exist")
    return updated


def update_transactions(transaction_ids: list[int], changes: dict) -> int:
    ids = list(dict.fromkeys(transaction_ids))
    updates = dict(changes)
    if "category" in updates or "subcategory" in updates:
        updates["reviewed"] = True
    try:
        expense_db.update_transactions(ids, updates)
    except LookupError as exc:
        raise TransactionNotFound(str(exc)) from exc
    except ValueError as exc:
        raise TransactionConflict(str(exc)) from exc
    return len(ids)


def delete_transactions(transaction_ids: list[int]) -> int:
    try:
        return expense_db.delete_transactions(transaction_ids)
    except ValueError as exc:
        raise TransactionConflict(str(exc)) from exc


def create_refund(transaction_id: int, payload: dict, idempotency_key: str) -> dict:
    def insert(conn) -> dict:
        refund_id = expense_db._add_refund(
            conn,
            transaction_id,
            payload["description"],
            payload["amount"],
            payload["date"],
        )
        return {"id": refund_id}

    try:
        result, duplicate = execute_idempotent(
            f"create_refund_{transaction_id}", idempotency_key, payload, insert
        )
    except ValueError as exc:
        raise TransactionConflict(str(exc)) from exc
    return {**result, "duplicate": duplicate}


def create_subscription(
    transaction_id: int, payload: dict, idempotency_key: str
) -> dict:
    def insert(conn) -> dict:
        subscription_id = subscription_db._create_subscription_from_transaction(
            conn,
            transaction_id,
            payload["name"],
            payload["next_renewal_date"],
            payload["renewal_mode"],
            payload["renewal_interval"],
            payload.get("renewal_anchor_day"),
        )
        return {"id": subscription_id}

    try:
        result, duplicate = execute_idempotent(
            f"create_subscription_{transaction_id}",
            idempotency_key,
            payload,
            insert,
        )
    except ValueError as exc:
        raise TransactionConflict(str(exc)) from exc
    return {**result, "duplicate": duplicate}
