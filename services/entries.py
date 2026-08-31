from datetime import date
from functools import lru_cache

from core.batch.db import save_batch
from core.batch.extractor import BatchExtractor
from core.config import config_version, load_config
from core.constants import (
    BATCH_RECORD_TYPES,
    PENDING_CATEGORY,
    TYPE_EXPENSE,
    TYPE_INCOME,
    TYPE_MEAL,
    TYPE_TRANSFER,
)
from core.diet.db import _insert_meal
from core.diet.extractor import DietExtractor
from core.diet.meal_time import require_meal_time, resolve_meal_type
from core.expense.classifier import Classifier
from core.expense.db import _insert_transaction
from core.idempotency import execute_idempotent


@lru_cache(maxsize=4)
def _classifier(_: int) -> Classifier:
    return Classifier(load_config())


@lru_cache(maxsize=4)
def _diet_extractor(_: int) -> DietExtractor:
    return DietExtractor(load_config())


@lru_cache(maxsize=4)
def _batch_extractor(_: int) -> BatchExtractor:
    return BatchExtractor(load_config())


def prepare_transaction(type_: str, description: str) -> dict:
    if type_ == TYPE_EXPENSE:
        return _classifier(config_version()).classify(description)
    if type_ == TYPE_INCOME:
        return {
            "status": "review_required",
            "category": "其他",
            "subcategory": "",
            "confidence": None,
            "reasoning": "请选择收入分类",
            "candidates": [],
        }
    if type_ == TYPE_TRANSFER:
        return {
            "status": "review_required",
            "category": "其他",
            "subcategory": "",
            "confidence": None,
            "reasoning": "请选择迁移分类",
            "candidates": [],
        }
    raise ValueError(f"不支持的账目类型：{type_}")


def create_transaction(payload: dict, idempotency_key: str) -> dict:
    def insert(conn) -> dict:
        record_id = _insert_transaction(
            conn,
            payload["type"],
            payload["description"],
            payload["amount"],
            payload["date"],
            category=payload.get("category"),
            subcategory=payload.get("subcategory"),
            notes=payload.get("notes"),
            confidence=payload.get("confidence"),
            reviewed=bool(payload.get("reviewed")),
        )
        return {"id": record_id}

    result, duplicate = execute_idempotent(
        "create_transaction", idempotency_key, payload, insert
    )
    return {**result, "duplicate": duplicate}


def prepare_meal(description: str, meal_time: str) -> dict:
    normalized_time = require_meal_time(meal_time)
    return _diet_extractor(config_version()).extract(description, normalized_time)


def create_meal(payload: dict, idempotency_key: str) -> dict:
    normalized_time = require_meal_time(payload["time"])
    normalized_payload = {
        **payload,
        "time": normalized_time,
        "meal_type": resolve_meal_type(payload.get("meal_type"), normalized_time),
    }

    def insert(conn) -> dict:
        meal_id = _insert_meal(
            conn,
            date=normalized_payload["date"],
            time=normalized_payload["time"],
            meal_type=normalized_payload.get("meal_type"),
            description=normalized_payload["description"],
            notes=normalized_payload.get("notes"),
            confidence=normalized_payload.get("confidence"),
            foods=normalized_payload["foods"],
        )
        return {"id": meal_id}

    result, duplicate = execute_idempotent(
        "create_meal", idempotency_key, normalized_payload, insert
    )
    return {**result, "duplicate": duplicate}


def prepare_batch(text: str, default_date: str) -> dict:
    result = _batch_extractor(config_version()).extract(text, default_date)
    return {
        "status": result["status"],
        "records": result.get("records", []),
        "diagnostics": {
            "raw_count": len(result.get("raw_records", [])),
            "block_count": len(result.get("raw_blocks", [])),
            "kept_count": len(result.get("records", [])),
            "rejected_records": result.get("rejected_records", []),
            "reasoning": result.get("reasoning", ""),
        },
    }


def save_reviewed_batch(submission_id: str, records: list[dict]) -> dict:
    config = load_config()
    normalized = [
        _normalize_batch_record(record, config)
        for record in records
        if record.get("include", True)
    ]
    return save_batch(submission_id, normalized)


def _normalize_batch_record(record: dict, config: dict) -> dict:
    record_type = str(record.get("record_type") or "").strip()
    if record_type not in BATCH_RECORD_TYPES:
        raise ValueError(f"批量记录类型无效：{record_type}")
    record_date = str(record.get("date") or "").strip()
    try:
        date.fromisoformat(record_date)
    except ValueError as exc:
        raise ValueError("批量记录日期必须是 YYYY-MM-DD") from exc
    description = str(record.get("description") or "").strip()
    if not description:
        raise ValueError("批量记录缺少描述")

    normalized = {
        "record_type": record_type,
        "date": record_date,
        "description": description,
        "notes": str(record.get("notes") or "").strip() or None,
        "confidence": float(record.get("confidence") or 0),
    }
    if record_type == TYPE_MEAL:
        normalized["time"] = require_meal_time(record.get("time"))
        normalized["meal_type"] = resolve_meal_type(
            record.get("meal_type"), normalized["time"]
        )
        normalized["foods"] = record.get("foods") or []
        has_food = any(
            str(food.get("food_name") or "").strip()
            for food in normalized["foods"]
        )
        if not has_food:
            raise ValueError("批量饮食记录缺少食物清单")
        return normalized

    amount = float(record.get("amount") or 0)
    if amount <= 0:
        raise ValueError("批量账目金额必须大于 0")
    category = str(record.get("category") or "").strip() or None
    subcategory = str(record.get("subcategory") or "").strip() or None
    if record_type == TYPE_EXPENSE and category == PENDING_CATEGORY:
        subcategory = PENDING_CATEGORY
    elif category:
        categories = config.get(record_type, {})
        if category not in categories:
            raise ValueError(f"{record_type}分类不存在：{category}")
        valid_subcategories = categories.get(category) or []
        if valid_subcategories and subcategory not in valid_subcategories:
            raise ValueError(f"{category} 的子类别不存在：{subcategory or '空'}")
        if not valid_subcategories:
            subcategory = None
    normalized.update(
        {
            "amount": amount,
            "category": category,
            "subcategory": subcategory,
            "reviewed": True,
        }
    )
    return normalized
