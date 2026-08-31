from datetime import date

from core.constants import (
    RECURRING_PAYMENT_PREPAID,
    RECURRING_PAYMENT_SUBSCRIPTION,
    RENEWAL_MODE_FIXED_DAYS,
    RENEWAL_MODE_SAME_DAY,
    SUBSCRIPTION_CYCLE_CUSTOM,
    SUBSCRIPTION_CYCLE_MONTHLY,
    SUBSCRIPTION_CYCLE_QUARTERLY,
    SUBSCRIPTION_CYCLE_YEARLY,
)
from core.idempotency import execute_idempotent
from core.planned_expense.db import (
    _confirm_planned_expense,
    _insert_planned_expense,
    delete_planned_expense,
    get_planned_expenses,
    update_planned_expense,
)
from core.subscription.db import (
    _create_prepaid_with_transaction,
    _insert_subscription,
    _record_subscription_payment,
    delete_prepaid_subscription,
    delete_subscription,
    get_subscriptions,
    update_prepaid_with_transaction,
    update_subscription,
)


def list_cross_period() -> dict[str, list[dict]]:
    expected = []
    for item in get_subscriptions(payment_type=RECURRING_PAYMENT_SUBSCRIPTION):
        expected.append(_expected_subscription(item))
    for item in get_planned_expenses():
        expected.append(_expected_plan(item))
    expected.sort(
        key=lambda item: (
            item["next_date"] is None,
            item["next_date"] or "",
            item["description"],
        )
    )
    prepaid = [
        _prepaid(item)
        for item in get_subscriptions(payment_type=RECURRING_PAYMENT_PREPAID)
    ]
    return {"expected": expected, "prepaid": prepaid}


def create_expected(payload: dict, idempotency_key: str) -> dict:
    def insert(conn) -> dict:
        if payload["recurring"]:
            cycle, interval_months = _cycle_from_months(payload["renewal_interval"])
            record_id = _insert_subscription(
                conn,
                name=payload["description"],
                amount=payload["amount"],
                billing_cycle=cycle,
                billing_interval_months=interval_months,
                next_renewal_date=payload["due_date"],
                category=payload.get("category"),
                subcategory=payload.get("subcategory"),
                auto_renew=True,
                notes=payload.get("notes"),
                payment_type=RECURRING_PAYMENT_SUBSCRIPTION,
                renewal_mode=payload["renewal_mode"],
                renewal_interval=payload["renewal_interval"],
                renewal_anchor_day=(
                    date.fromisoformat(payload["due_date"]).day
                    if payload["renewal_mode"] == RENEWAL_MODE_SAME_DAY
                    else None
                ),
            )
            return {"id": record_id, "source": "subscription"}
        record_id = _insert_planned_expense(
            conn,
            payload["description"],
            payload["amount"],
            payload.get("due_date"),
            payload.get("category"),
            payload.get("subcategory"),
            payload.get("notes"),
        )
        return {"id": record_id, "source": "plan"}

    result, duplicate = execute_idempotent(
        "create_expected", idempotency_key, payload, insert
    )
    return {**result, "duplicate": duplicate}


def update_expected(source: str, record_id: int, payload: dict) -> None:
    _find_expected(source, record_id)
    if source == "subscription":
        cycle, interval_months = _cycle_from_months(payload["renewal_interval"])
        update_subscription(
            record_id,
            name=payload["description"],
            amount=payload["amount"],
            billing_cycle=cycle,
            billing_interval_months=interval_months,
            next_renewal_date=payload["due_date"],
            category=payload.get("category"),
            subcategory=payload.get("subcategory"),
            notes=payload.get("notes"),
            renewal_mode=payload["renewal_mode"],
            renewal_interval=payload["renewal_interval"],
            renewal_anchor_day=(
                date.fromisoformat(payload["due_date"]).day
                if payload["renewal_mode"] == RENEWAL_MODE_SAME_DAY
                else None
            ),
        )
        return
    update_planned_expense(
        record_id,
        description=payload["description"],
        amount=payload["amount"],
        due_date=payload.get("due_date"),
        category=payload.get("category"),
        subcategory=payload.get("subcategory"),
        notes=payload.get("notes"),
    )


def confirm_expected(
    source: str, record_id: int, payload: dict, idempotency_key: str
) -> dict:
    def insert(conn) -> dict:
        if source == "subscription":
            transaction_id = _record_subscription_payment(
                conn,
                record_id,
                payload["description"],
                payload["amount"],
                payload["payment_date"],
                payload.get("category"),
                payload.get("subcategory"),
                payload.get("notes"),
            )
        else:
            transaction_id = _confirm_planned_expense(
                conn,
                record_id,
                payload["description"],
                payload["amount"],
                payload["payment_date"],
                payload.get("category"),
                payload.get("subcategory"),
                payload.get("notes"),
            )
        return {"transaction_id": transaction_id}

    result, duplicate = execute_idempotent(
        f"confirm_expected_{source}_{record_id}", idempotency_key, payload, insert
    )
    return {**result, "duplicate": duplicate}


def delete_expected(source: str, record_id: int) -> None:
    _find_expected(source, record_id)
    if source == "subscription":
        delete_subscription(record_id)
    else:
        delete_planned_expense(record_id)


def create_prepaid(payload: dict, idempotency_key: str) -> dict:
    def insert(conn) -> dict:
        transaction_id, subscription_id = _create_prepaid_with_transaction(
            conn,
            payload["description"],
            payload["amount"],
            payload["payment_date"],
            payload["months"],
            f"{payload['start_month']}-01",
            payload.get("category"),
            payload.get("subcategory"),
            payload.get("notes"),
        )
        return {"transaction_id": transaction_id, "subscription_id": subscription_id}

    result, duplicate = execute_idempotent(
        "create_prepaid", idempotency_key, payload, insert
    )
    return {**result, "duplicate": duplicate}


def update_prepaid(record_id: int, payload: dict) -> None:
    record = _find_prepaid(record_id)
    update_prepaid_with_transaction(
        record_id,
        record["transaction_id"],
        payload["description"],
        payload["months"],
        f"{payload['start_month']}-01",
        payload.get("category"),
        payload.get("subcategory"),
        payload.get("notes"),
    )


def delete_prepaid(record_id: int) -> None:
    record = _find_prepaid(record_id)
    delete_prepaid_subscription(record_id, record["transaction_id"])


def _find_expected(source: str, record_id: int) -> dict:
    records = list_cross_period()["expected"]
    record = next(
        (
            item
            for item in records
            if item["source"] == source and item["id"] == record_id
        ),
        None,
    )
    if record is None:
        raise ValueError("预计支出不存在或已处理")
    return record


def _find_prepaid(record_id: int) -> dict:
    record = next(
        (item for item in list_cross_period()["prepaid"] if item["id"] == record_id),
        None,
    )
    if record is None:
        raise ValueError("预付摊销不存在")
    return record


def _expected_subscription(item: dict) -> dict:
    interval = max(1, int(item.get("renewal_interval") or 1))
    mode = item.get("renewal_mode") or RENEWAL_MODE_SAME_DAY
    return {
        "id": item["id"],
        "source": "subscription",
        "description": item["name"],
        "amount": item["amount"],
        "next_date": item.get("next_renewal_date"),
        "cycle": (
            f"每{interval}天"
            if mode == RENEWAL_MODE_FIXED_DAYS
            else _month_cycle(interval)
        ),
        "category": item.get("category"),
        "subcategory": item.get("subcategory"),
        "notes": item.get("notes"),
        "renewal_mode": mode,
        "renewal_interval": interval,
        "state": _due_state(item.get("next_renewal_date")),
    }


def _expected_plan(item: dict) -> dict:
    return {
        "id": item["id"],
        "source": "plan",
        "description": item["description"],
        "amount": item["amount"],
        "next_date": item.get("due_date"),
        "cycle": "一次性",
        "category": item.get("category"),
        "subcategory": item.get("subcategory"),
        "notes": item.get("notes"),
        "renewal_mode": None,
        "renewal_interval": None,
        "state": _due_state(item.get("due_date")),
    }


def _prepaid(item: dict) -> dict:
    start = date.fromisoformat(str(item["start_date"])[:10])
    months = max(1, int(item.get("billing_interval_months") or 1))
    today = date.today()
    elapsed = (today.year - start.year) * 12 + today.month - start.month
    return {
        "id": item["id"],
        "transaction_id": item["transaction_id"],
        "description": item["name"],
        "amount": item["amount"],
        "monthly_equivalent": item["monthly_equivalent"],
        "months": months,
        "remaining_months": max(0, months - max(0, elapsed)),
        "start_month": start.strftime("%Y-%m"),
        "category": item.get("category"),
        "subcategory": item.get("subcategory"),
        "notes": item.get("notes"),
    }


def _cycle_from_months(months: int) -> tuple[str, int | None]:
    if months == 1:
        return SUBSCRIPTION_CYCLE_MONTHLY, None
    if months == 3:
        return SUBSCRIPTION_CYCLE_QUARTERLY, None
    if months == 12:
        return SUBSCRIPTION_CYCLE_YEARLY, None
    return SUBSCRIPTION_CYCLE_CUSTOM, months


def _month_cycle(months: int) -> str:
    return {1: "月付", 3: "季付", 12: "年付"}.get(months, f"每{months}个月")


def _due_state(value: str | None) -> str:
    if value is None:
        return "长期计划"
    due = date.fromisoformat(str(value)[:10])
    if due < date.today():
        return "已过期"
    if due == date.today():
        return "今日待确认"
    return "待确认"
