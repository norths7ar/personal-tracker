import hashlib
import json
from contextlib import closing

from core.constants import TRANSACTION_TYPES, TYPE_MEAL
from core.db import _connect
from core.diet.db import _insert_meal
from core.expense.db import _insert_transaction


class BatchSubmissionConflict(ValueError):
    pass


def save_batch(submission_id: str, records: list[dict]) -> dict:
    """Save one reviewed batch atomically and make retries idempotent."""
    submission_id = str(submission_id or "").strip()
    if not submission_id:
        raise ValueError("批次缺少 submission_id")
    if not records:
        raise ValueError("批次没有可保存记录")

    payload_hash = _payload_hash(records)
    with closing(_connect()) as conn:
        try:
            inserted = conn.execute(
                """INSERT INTO batch_submissions
                   (submission_id, payload_hash, record_count)
                   VALUES (?, ?, ?)
                   ON CONFLICT(submission_id) DO NOTHING""",
                (submission_id, payload_hash, len(records)),
            )
            if inserted.rowcount == 0:
                existing = conn.execute(
                    """SELECT payload_hash, record_count FROM batch_submissions
                       WHERE submission_id = ?""",
                    (submission_id,),
                ).fetchone()
                if existing is None or existing["payload_hash"] != payload_hash:
                    raise BatchSubmissionConflict("同一批次已使用不同内容保存")
                return {
                    "saved_count": int(existing["record_count"]),
                    "duplicate": True,
                }

            for record in records:
                _insert_record(conn, record)
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    return {"saved_count": len(records), "duplicate": False}


def _payload_hash(records: list[dict]) -> str:
    payload = json.dumps(
        records,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _insert_record(conn, record: dict) -> int:
    record_type = str(record.get("record_type") or "").strip()
    if record_type == TYPE_MEAL:
        return _insert_meal(
            conn,
            date=str(record.get("date") or "").strip(),
            time=str(record.get("time") or "").strip(),
            meal_type=record.get("meal_type"),
            description=str(record.get("description") or "").strip(),
            notes=record.get("notes"),
            confidence=record.get("confidence"),
            foods=record.get("foods") or [],
        )
    if record_type not in TRANSACTION_TYPES:
        raise ValueError(f"不支持的批量记录类型：{record_type}")
    return _insert_transaction(
        conn,
        record_type,
        str(record.get("description") or "").strip(),
        float(record.get("amount")),
        str(record.get("date") or "").strip(),
        category=record.get("category"),
        subcategory=record.get("subcategory"),
        notes=record.get("notes"),
        confidence=record.get("confidence"),
        reviewed=bool(record.get("reviewed")),
    )
