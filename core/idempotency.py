import hashlib
import json
from collections.abc import Callable
from contextlib import closing
from datetime import UTC, datetime
from typing import Any

from core.db import _connect


class IdempotencyConflict(ValueError):
    pass


def execute_idempotent(
    operation: str,
    idempotency_key: str,
    payload: dict,
    action: Callable[[Any], dict],
) -> tuple[dict, bool]:
    key = str(idempotency_key or "").strip()
    if not key:
        raise ValueError("写入请求缺少 Idempotency-Key")
    payload_hash = hash_payload(payload)

    with closing(_connect()) as conn:
        try:
            inserted = conn.execute(
                """INSERT INTO idempotency_keys
                   (idempotency_key, operation, payload_hash, response_json, created_at)
                   VALUES (?, ?, ?, NULL, ?)
                   ON CONFLICT(idempotency_key) DO NOTHING""",
                (
                    key,
                    operation,
                    payload_hash,
                    datetime.now(UTC).isoformat(),
                ),
            )
            if inserted.rowcount == 0:
                existing = conn.execute(
                    """SELECT operation, payload_hash, response_json
                       FROM idempotency_keys WHERE idempotency_key = ?""",
                    (key,),
                ).fetchone()
                if (
                    existing is None
                    or existing["operation"] != operation
                    or existing["payload_hash"] != payload_hash
                    or not existing["response_json"]
                ):
                    raise IdempotencyConflict("同一幂等键已用于不同的写入请求")
                return json.loads(existing["response_json"]), True

            response = action(conn)
            conn.execute(
                """UPDATE idempotency_keys SET response_json = ?
                   WHERE idempotency_key = ?""",
                (
                    json.dumps(response, ensure_ascii=False, default=str),
                    key,
                ),
            )
            conn.commit()
            return response, False
        except Exception:
            conn.rollback()
            raise


def hash_payload(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()
