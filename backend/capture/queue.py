"""Durable capture items; business writes and review transitions share one transaction."""

import json
import math
import re
from contextlib import closing, suppress
from datetime import date
from pathlib import Path
from uuid import uuid4

from backend.capture.batch import insert_record
from backend.capture.entries import normalize_batch_record
from backend.constants import PENDING_CATEGORY, TRANSACTION_TYPES, TYPE_MEAL
from backend.db import connect, execute_idempotent
from backend.diet.store import normalize_ingredients
from backend.ledger.transactions import get_pending_transaction_count
from backend.settings.store import load_config

ACTIVE_STATUSES = ("queued", "processing", "review", "failed")


class CaptureNotFound(LookupError):
    pass


class CaptureConflict(ValueError):
    pass


def submit(text: str, default_date: str, idempotency_key: str) -> dict:
    text = text.strip()
    if not text:
        raise ValueError("请输入需要记录的内容")
    date.fromisoformat(default_date)
    payload = {"text": text, "default_date": default_date}

    def insert(conn) -> dict:
        submission_id = conn.execute(
            "INSERT INTO capture_submissions(original_text, default_date) VALUES (?, ?)",
            (text, default_date),
        ).lastrowid
        conn.execute(
            """INSERT INTO capture_items(submission_id, source_text, default_date, status)
               VALUES (?, ?, ?, 'queued')""",
            (submission_id, text, default_date),
        )
        return {"id": submission_id}

    result, duplicate = execute_idempotent("capture_submission", idempotency_key, payload, insert)
    return {**result, "duplicate": duplicate}


def pending() -> dict:
    with closing(connect()) as conn:
        rows = conn.execute(
            """SELECT i.*, s.original_text FROM capture_items i
               JOIN capture_submissions s ON s.id = i.submission_id
               WHERE i.status IN ('queued', 'processing', 'review', 'failed')
               ORDER BY i.id"""
        ).fetchall()
        changes = conn.execute(
            """SELECT COUNT(*), COALESCE(MAX(id),0),
               COALESCE(SUM(status='saved'),0), COALESCE(SUM(status='discarded'),0),
               COALESCE(SUM(status='expanded'),0) FROM capture_items"""
        ).fetchone()
    items = [
        {
            "id": row["id"],
            "submission_id": row["submission_id"],
            "source_text": row["source_text"],
            "original_text": row["original_text"],
            "default_date": row["default_date"],
            "status": row["status"],
            "record": _public_record(row["record_json"]),
            "reason": row["reason"],
            "created_at": row["created_at"],
            "can_retry": bool(row["source_text"]) and row["status"] in {"review", "failed"},
        }
        for row in rows
    ]
    return {
        "items": items,
        "change_token": ":".join(str(value) for value in changes),
        "pending_count": len(items) + get_pending_transaction_count(),
        "processing_count": sum(item["status"] in {"queued", "processing"} for item in items),
    }


def _public_record(raw: str | None) -> dict | None:
    if raw is None:
        return None
    record = json.loads(raw)
    for field in ("category", "subcategory"):
        record[field] = record.get(field) or ""
    return record


def pending_count() -> int:
    with closing(connect()) as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM capture_items WHERE status IN ('queued','processing','review','failed')"
        ).fetchone()[0]
    return count + get_pending_transaction_count()


def _item(conn, item_id: int):
    row = conn.execute("SELECT * FROM capture_items WHERE id = ?", (item_id,)).fetchone()
    if row is None:
        raise CaptureNotFound("收集条目不存在")
    return row


def confirm(item_id: int, record: dict) -> dict:
    config = load_config()
    normalized = normalize_batch_record(record, config, allow_empty_foods=True)
    with closing(connect()) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        row = _item(conn, item_id)
        if row["status"] == "saved":
            if json.loads(row["record_json"]) != normalized:
                raise CaptureConflict("此条目已按其他内容入账，请到记录页面修改")
            return {"id": row["result_id"], "duplicate": True}
        if row["status"] not in {"review", "failed"}:
            raise CaptureConflict("条目状态已变化，请刷新后再操作")
        result_id = insert_record(conn, normalized, allow_empty_foods=True)
        conn.execute(
            """UPDATE capture_items SET status='saved', record_json=?, result_id=?,
               result_type=?, reason='', claim_token=NULL WHERE id=?""",
            (
                json.dumps(normalized, ensure_ascii=False),
                result_id,
                normalized["record_type"],
                item_id,
            ),
        )
    return {"id": result_id, "duplicate": False}


def retry(item_id: int) -> dict:
    with closing(connect()) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        row = _item(conn, item_id)
        if row["status"] in {"queued", "processing"}:
            return {"id": item_id}
        if row["status"] not in {"review", "failed"} or not row["source_text"]:
            raise CaptureConflict("此条目不能重新解析，请手动补全或刷新状态")
        conn.execute(
            "UPDATE capture_items SET status='queued', reason='', claim_token=NULL WHERE id=?",
            (item_id,),
        )
    return {"id": item_id}


def discard(item_id: int) -> None:
    with closing(connect()) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        row = _item(conn, item_id)
        if row["status"] == "discarded":
            return
        if row["status"] not in ACTIVE_STATUSES:
            raise CaptureConflict("此条目已处理，不能丢弃已入账记录")
        # Clearing the token fences off a running parser before it can commit.
        conn.execute(
            "UPDATE capture_items SET status='discarded', claim_token=NULL WHERE id=?", (item_id,)
        )


def recover_processing(database: Path) -> None:
    """Called only by the process holding the instance worker lock."""
    with closing(connect(database)) as conn, conn:
        conn.execute(
            """UPDATE capture_items SET status='failed', claim_token=NULL,
               reason='上次解析被中断，原文已保留，请重试'
               WHERE status='processing'"""
        )


def claim_next(database: Path) -> dict | None:
    with closing(connect(database)) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT * FROM capture_items WHERE status='queued' ORDER BY id LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        token = uuid4().hex
        conn.execute(
            "UPDATE capture_items SET status='processing', claim_token=? WHERE id=?",
            (token, row["id"]),
        )
        return {**dict(row), "claim_token": token}


def fail(item: dict, reason: str, database: Path) -> None:
    with closing(connect(database)) as conn, conn:
        conn.execute(
            """UPDATE capture_items SET status='failed', reason=?, claim_token=NULL
               WHERE id=? AND status='processing' AND claim_token=?""",
            (reason, item["id"], item["claim_token"]),
        )


def _review_reason(record: dict, config: dict) -> tuple[dict | None, str]:
    try:
        normalized = normalize_batch_record(record, config)
    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        return None, str(exc)
    confidence = normalized["confidence"]
    if not math.isfinite(confidence) or confidence < config["llm"]["confidence_threshold"]:
        return normalized, "解析置信度较低，请确认内容"
    if normalized["record_type"] in TRANSACTION_TYPES:
        category = normalized.get("category")
        if not category or category == PENDING_CATEGORY:
            return normalized, "分类待定，请选择分类"
    return normalized, ""


def _record_source(record: dict) -> str:
    """Reparse only this record, including the amount stripped from its description."""
    parts = [str(record.get("record_type") or ""), str(record.get("description") or "")]
    amount = record.get("amount")
    mentioned = re.findall(r"\d+(?:\.\d+)?", str(record.get("description") or ""))
    if amount is not None and not any(float(value) == amount for value in mentioned):
        parts.append(f"{amount}元")
    if record.get("meal_type"):
        parts.append(str(record["meal_type"]))
    if record.get("time"):
        parts.append(str(record["time"]))
    return " ".join(part for part in parts if part).strip()


def _review_record(raw: object, default_date: str) -> dict | None:
    if not isinstance(raw, dict):
        return None
    kind = raw.get("record_type") or raw.get("event_type")
    if kind not in (*TRANSACTION_TYPES, TYPE_MEAL):
        return None
    description = str(raw.get("description") or raw.get("text") or "").strip()
    if not description:
        return None
    record_date = str(raw.get("date") or default_date)
    try:
        date.fromisoformat(record_date)
    except ValueError:
        record_date = default_date
    amount = raw.get("amount")
    try:
        amount = float(amount)
        if not math.isfinite(amount):
            amount = None
    except TypeError, ValueError:
        amount = None
    return {
        "record_type": kind,
        "date": record_date,
        "description": description,
        "amount": amount,
        "time": str(raw.get("time") or ""),
        "meal_type": str(raw.get("meal_type") or raw.get("meal_type_hint") or "") or None,
        "category": str(raw.get("category") or raw.get("category_hint") or ""),
        "subcategory": str(raw.get("subcategory") or raw.get("subcategory_hint") or ""),
        "foods": [
            {
                "food_name": food["food_name"].strip(),
                "quantity": str(food.get("quantity") or ""),
                "ingredients": normalize_ingredients(food.get("ingredients")),
            }
            for food in (raw.get("foods") if isinstance(raw.get("foods"), list) else [])
            if isinstance(food, dict)
            and isinstance(food.get("food_name"), str)
            and food["food_name"].strip()
        ],
        "notes": str(raw.get("notes") or "") or None,
        "confidence": 0.0,
        "reasoning": str(raw.get("reasoning") or ""),
    }


def complete(item: dict, result: dict, config: dict, database: Path) -> bool:
    """Commit all parsed descendants and eligible business records, or nothing."""
    records = result.get("records") or []
    rejected = result.get("rejected_records") or []
    if result.get("status") == "error" or not (records or rejected):
        fail(item, result.get("reasoning") or "未能提取记录，请补充描述后重试", database)
        return False
    with closing(connect(database)) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        current = _item(conn, item["id"])
        if current["status"] != "processing" or current["claim_token"] != item["claim_token"]:
            return False
        for record in records:
            normalized, reason = _review_reason(record, config)
            stored = (
                normalized
                if normalized is not None
                else _review_record(record, item["default_date"])
            )
            result_id = insert_record(conn, normalized) if not reason else None
            conn.execute(
                """INSERT INTO capture_items(submission_id, parent_id, source_text, default_date,
                   status, record_json, reason, result_id, result_type)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    item["submission_id"],
                    item["id"],
                    _record_source(record),
                    (stored["date"] if stored else item["default_date"]),
                    "review" if reason else "saved",
                    json.dumps(stored, ensure_ascii=False) if stored is not None else None,
                    reason,
                    result_id,
                    normalized["record_type"] if result_id is not None else None,
                ),
            )
        for rejection in rejected:
            raw = rejection.get("record")
            # Never replay the original batch for an unlocatable rejected fragment.
            source = (
                str(raw.get("text") or raw.get("description") or "").strip()
                if isinstance(raw, dict)
                else ""
            )
            draft = _review_record(raw, item["default_date"])
            fragment_date = item["default_date"]
            if isinstance(raw, dict) and raw.get("date"):
                with suppress(ValueError):
                    fragment_date = date.fromisoformat(str(raw["date"])).isoformat()
            if draft is not None:
                source = _record_source(draft)
                fragment_date = draft["date"]
            conn.execute(
                """INSERT INTO capture_items(submission_id, parent_id, source_text, default_date,
                   status, record_json, reason) VALUES (?, ?, ?, ?, 'review', ?, ?)""",
                (
                    item["submission_id"],
                    item["id"],
                    source,
                    fragment_date,
                    json.dumps(draft, ensure_ascii=False) if draft is not None else None,
                    str(rejection.get("reason") or "片段无法识别，请人工补全"),
                ),
            )
        conn.execute(
            "UPDATE capture_items SET status='expanded', claim_token=NULL, reason='' WHERE id=?",
            (item["id"],),
        )
    return True
