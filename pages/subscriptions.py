from datetime import date

import pandas as pd
import streamlit as st

from core.config import load_config
from core.constants import (
    RECURRING_PAYMENT_PREPAID,
    RECURRING_PAYMENT_SUBSCRIPTION,
    RENEWAL_MODE_FIXED_DAYS,
    RENEWAL_MODE_SAME_DAY,
    SUBSCRIPTION_CYCLE_CUSTOM,
    SUBSCRIPTION_CYCLE_MONTHLY,
    SUBSCRIPTION_CYCLE_ONE_TIME,
    SUBSCRIPTION_CYCLE_QUARTERLY,
    SUBSCRIPTION_CYCLE_YEARLY,
    TYPE_EXPENSE,
)
from core.expense.db import add_transaction, delete_transaction, update_transaction
from core.planned_expense.db import (
    add_planned_expense,
    confirm_planned_expense,
    delete_planned_expense,
    get_planned_expenses,
    update_planned_expense,
)
from core.subscription.db import (
    add_subscription,
    delete_prepaid_subscription,
    delete_subscription,
    get_subscriptions,
    record_subscription_payment,
    update_subscription,
)
from core.text import display_text, is_blank, optional_text

st.title("跨期费用")

config = load_config()
expense_categories = config.get(TYPE_EXPENSE, {})
today = date.today()


def _positive_int(value, default: int = 1) -> int:
    if is_blank(value):
        return default
    try:
        return max(1, int(float(value)))
    except (TypeError, ValueError):
        return default


def _optional_date(value) -> date | None:
    text = display_text(value)
    return date.fromisoformat(text) if text else None


def _category_fields(
    key_prefix: str,
    current_category: str = "",
    current_subcategory: str = "",
) -> tuple[str, str | None]:
    categories = list(expense_categories)
    default_category = (
        current_category
        if current_category in categories
        else "通讯"
        if "通讯" in categories
        else categories[0]
    )
    category = st.selectbox(
        "主类别",
        categories,
        index=categories.index(default_category),
        key=f"{key_prefix}_category",
    )
    subcategories = expense_categories.get(category) or []
    if not subcategories:
        return category, None
    default_subcategory = (
        current_subcategory
        if current_subcategory in subcategories
        else "平台会员"
        if "平台会员" in subcategories
        else subcategories[0]
    )
    subcategory = st.selectbox(
        "子类别",
        subcategories,
        index=subcategories.index(default_subcategory),
        key=f"{key_prefix}_subcategory_{category}",
    )
    return category, subcategory


def _cycle_from_months(months: int) -> tuple[str, int | None]:
    if months == 1:
        return SUBSCRIPTION_CYCLE_MONTHLY, None
    if months == 3:
        return SUBSCRIPTION_CYCLE_QUARTERLY, None
    if months == 12:
        return SUBSCRIPTION_CYCLE_YEARLY, None
    return SUBSCRIPTION_CYCLE_CUSTOM, months


def _cycle_label(record: dict) -> str:
    if record["source"] == "plan":
        return "一次性"
    interval = _positive_int(record.get("renewal_interval"))
    if record.get("renewal_mode") == RENEWAL_MODE_FIXED_DAYS:
        return f"每{interval}天"
    return {1: "月付", 3: "季付", 12: "年付"}.get(
        interval, f"每{interval}个月"
    )


def _due_state(record: dict) -> str:
    due = _optional_date(record.get("next_date"))
    if due is None:
        return "长期计划"
    if due < today:
        return "已过期"
    if due == today:
        return "今日待确认"
    return "待确认"


def _render_recurrence_fields(
    key_prefix: str,
    mode: str = RENEWAL_MODE_SAME_DAY,
    interval: int = 1,
) -> tuple[str, int]:
    renewal_mode = st.radio(
        "续费方式",
        [RENEWAL_MODE_SAME_DAY, RENEWAL_MODE_FIXED_DAYS],
        format_func=lambda value: (
            "按月同日" if value == RENEWAL_MODE_SAME_DAY else "固定天数"
        ),
        horizontal=True,
        index=0 if mode == RENEWAL_MODE_SAME_DAY else 1,
        key=f"{key_prefix}_renewal_mode",
    )
    if renewal_mode == RENEWAL_MODE_SAME_DAY:
        renewal_interval = st.number_input(
            "每几个月",
            min_value=1,
            max_value=120,
            value=interval if mode == RENEWAL_MODE_SAME_DAY else 1,
            step=1,
            key=f"{key_prefix}_month_interval",
        )
    else:
        renewal_interval = st.number_input(
            "每几天",
            min_value=1,
            max_value=730,
            value=interval if mode == RENEWAL_MODE_FIXED_DAYS else 30,
            step=1,
            key=f"{key_prefix}_day_interval",
        )
    return renewal_mode, int(renewal_interval)


@st.dialog("新增预计支出", width="small")
def _add_expected_dialog() -> None:
    description = st.text_input("描述", placeholder="例：QQ会员或显卡预算")
    amount = st.number_input(
        "预计金额（元）", min_value=0.0, value=0.0, format="%.2f"
    )
    recurring = st.checkbox("周期性付款", value=False)
    renewal_mode = None
    renewal_interval = None
    if recurring:
        renewal_mode, renewal_interval = _render_recurrence_fields("add_expected")
        due_date = st.date_input("下次付款日", value=today)
    else:
        has_date = st.checkbox("设置预计日期", value=False)
        due_date = st.date_input("预计日期", value=today) if has_date else None
    category, subcategory = _category_fields("add_expected")
    notes = st.text_area("备注", height=68)

    save_col, close_col = st.columns(2)
    with save_col:
        save = st.button("保存", type="primary", key="save_expected")
    with close_col:
        close = st.button("关闭", key="close_expected")

    if close:
        st.rerun()
    if not save:
        return
    if not description.strip():
        st.error("请填写描述。")
        return
    if amount <= 0:
        st.error("金额必须大于 0。")
        return

    if recurring:
        billing_cycle, billing_interval_months = _cycle_from_months(
            renewal_interval
        )
        add_subscription(
            name=description.strip(),
            amount=amount,
            billing_cycle=billing_cycle,
            billing_interval_months=billing_interval_months,
            next_renewal_date=due_date.isoformat(),
            category=category,
            subcategory=optional_text(subcategory),
            auto_renew=True,
            notes=optional_text(notes),
            payment_type=RECURRING_PAYMENT_SUBSCRIPTION,
            renewal_mode=renewal_mode,
            renewal_interval=renewal_interval,
            renewal_anchor_day=(
                due_date.day if renewal_mode == RENEWAL_MODE_SAME_DAY else None
            ),
        )
    else:
        add_planned_expense(
            description.strip(),
            amount,
            due_date=due_date.isoformat() if due_date else None,
            category=category,
            subcategory=optional_text(subcategory),
            notes=optional_text(notes),
        )
    st.rerun()


@st.dialog("编辑预计支出", width="small")
def _edit_expected_dialog(record: dict) -> None:
    periodic = record["source"] == "subscription"
    st.caption("周期性付款" if periodic else "一次性计划")
    description = st.text_input(
        "描述", value=display_text(record.get("description"))
    )
    amount = st.number_input(
        "预计金额（元）",
        min_value=0.0,
        value=float(record.get("amount") or 0),
        format="%.2f",
    )
    renewal_mode = None
    renewal_interval = None
    if periodic:
        renewal_mode, renewal_interval = _render_recurrence_fields(
            f"edit_expected_{record['id']}",
            record.get("renewal_mode") or RENEWAL_MODE_SAME_DAY,
            _positive_int(record.get("renewal_interval")),
        )
        next_date = st.date_input(
            "下次付款日",
            value=_optional_date(record.get("next_date")) or today,
        )
    else:
        has_date = st.checkbox(
            "设置预计日期",
            value=_optional_date(record.get("next_date")) is not None,
        )
        next_date = (
            st.date_input(
                "预计日期",
                value=_optional_date(record.get("next_date")) or today,
            )
            if has_date
            else None
        )
    category, subcategory = _category_fields(
        f"edit_expected_{record['source']}_{record['id']}",
        display_text(record.get("category")),
        display_text(record.get("subcategory")),
    )
    notes = st.text_area(
        "备注", value=display_text(record.get("notes")), height=68
    )

    save_col, close_col = st.columns(2)
    with save_col:
        save = st.button(
            "保存修改", type="primary", key=f"save_expected_{record['source']}_{record['id']}"
        )
    with close_col:
        close = st.button(
            "关闭", key=f"close_expected_{record['source']}_{record['id']}"
        )

    if close:
        st.rerun()
    if not save:
        return
    if not description.strip() or amount <= 0:
        st.error("描述不能为空，金额必须大于 0。")
        return

    if periodic:
        billing_cycle, billing_interval_months = _cycle_from_months(
            renewal_interval
        )
        update_subscription(
            int(record["id"]),
            name=description.strip(),
            amount=amount,
            billing_cycle=billing_cycle,
            billing_interval_months=billing_interval_months,
            next_renewal_date=next_date.isoformat(),
            category=category,
            subcategory=optional_text(subcategory),
            notes=optional_text(notes),
            renewal_mode=renewal_mode,
            renewal_interval=renewal_interval,
            renewal_anchor_day=(
                next_date.day if renewal_mode == RENEWAL_MODE_SAME_DAY else None
            ),
        )
    else:
        update_planned_expense(
            int(record["id"]),
            description=description.strip(),
            amount=amount,
            due_date=next_date.isoformat() if next_date else None,
            category=category,
            subcategory=optional_text(subcategory),
            notes=optional_text(notes),
        )
    st.rerun()


@st.dialog("确认入账", width="small")
def _confirm_expected_dialog(record: dict) -> None:
    description = st.text_input(
        "描述", value=display_text(record.get("description"))
    )
    amount = st.number_input(
        "实际金额（元）",
        min_value=0.0,
        value=float(record.get("amount") or 0),
        format="%.2f",
    )
    payment_date = st.date_input("付款日期", value=today)
    category, subcategory = _category_fields(
        f"confirm_expected_{record['source']}_{record['id']}",
        display_text(record.get("category")),
        display_text(record.get("subcategory")),
    )
    notes = st.text_area(
        "备注", value=display_text(record.get("notes")), height=68
    )

    confirm_col, close_col = st.columns(2)
    with confirm_col:
        confirm = st.button(
            "确认并记账",
            type="primary",
            key=f"confirm_expected_{record['source']}_{record['id']}",
        )
    with close_col:
        close = st.button(
            "关闭", key=f"close_confirm_{record['source']}_{record['id']}"
        )

    if close:
        st.rerun()
    if not confirm:
        return
    if not description.strip() or amount <= 0:
        st.error("描述不能为空，金额必须大于 0。")
        return

    if record["source"] == "subscription":
        record_subscription_payment(
            int(record["id"]),
            description.strip(),
            amount,
            payment_date.isoformat(),
            category,
            optional_text(subcategory),
            optional_text(notes),
        )
    else:
        confirm_planned_expense(
            int(record["id"]),
            description.strip(),
            amount,
            payment_date.isoformat(),
            category,
            optional_text(subcategory),
            optional_text(notes),
        )
    st.rerun()


@st.dialog("删除预计支出", width="small")
def _delete_expected_dialog(record: dict) -> None:
    st.warning(f"确认删除“{record['description']}”？已生成的历史流水不会受影响。")
    delete_col, close_col = st.columns(2)
    with delete_col:
        delete = st.button(
            "确认删除",
            type="primary",
            key=f"delete_expected_{record['source']}_{record['id']}",
        )
    with close_col:
        close = st.button(
            "取消", key=f"cancel_delete_expected_{record['source']}_{record['id']}"
        )
    if close:
        st.rerun()
    if delete:
        if record["source"] == "subscription":
            delete_subscription(int(record["id"]))
        else:
            delete_planned_expense(int(record["id"]))
        st.rerun()


@st.dialog("新增预付摊销", width="small")
def _add_prepaid_dialog() -> None:
    description = st.text_input("描述", placeholder="例：季度房租")
    amount = st.number_input(
        "总金额（元）", min_value=0.0, value=0.0, format="%.2f"
    )
    payment_date = st.date_input("付款日期", value=today)
    months = st.number_input(
        "摊销月数", min_value=1, max_value=120, value=12, step=1
    )
    start_month = st.text_input(
        "摊销开始月份", value=payment_date.strftime("%Y-%m"), placeholder="YYYY-MM"
    )
    category, subcategory = _category_fields("add_prepaid")
    notes = st.text_area("备注", height=68)

    save_col, close_col = st.columns(2)
    with save_col:
        save = st.button("保存并记账", type="primary", key="save_prepaid")
    with close_col:
        close = st.button("关闭", key="close_prepaid")
    if close:
        st.rerun()
    if not save:
        return
    if not description.strip() or amount <= 0:
        st.error("描述不能为空，金额必须大于 0。")
        return
    try:
        amortization_start = date.fromisoformat(
            f"{start_month.strip()}-01"
        ).isoformat()
    except ValueError:
        st.error("摊销开始月份必须是 YYYY-MM。")
        return

    transaction_id = add_transaction(
        TYPE_EXPENSE,
        description.strip(),
        amount,
        payment_date.isoformat(),
        category=category,
        subcategory=optional_text(subcategory),
        notes=optional_text(notes),
        amortization_months=int(months),
        amortization_start=amortization_start,
    )
    try:
        add_subscription(
            name=description.strip(),
            amount=amount,
            billing_cycle=SUBSCRIPTION_CYCLE_ONE_TIME,
            billing_interval_months=int(months),
            start_date=amortization_start,
            category=category,
            subcategory=optional_text(subcategory),
            auto_renew=False,
            notes=optional_text(notes),
            payment_type=RECURRING_PAYMENT_PREPAID,
            transaction_id=transaction_id,
        )
    except Exception:
        delete_transaction(transaction_id)
        raise
    st.rerun()


def _remaining_months(record: dict) -> int:
    start = _optional_date(record.get("start_date"))
    total = _positive_int(record.get("billing_interval_months"))
    if start is None:
        return total
    elapsed = (today.year - start.year) * 12 + today.month - start.month
    return max(0, total - max(0, elapsed))


@st.dialog("编辑预付摊销", width="small")
def _edit_prepaid_dialog(record: dict) -> None:
    transaction_id = int(record["transaction_id"])
    st.caption(
        f"关联流水 #{transaction_id}；金额 ¥{float(record['amount']):,.2f}，"
        "金额和付款日期请到账目页修改。"
    )
    description = st.text_input(
        "描述", value=display_text(record.get("name"))
    )
    months = st.number_input(
        "摊销月数",
        min_value=1,
        max_value=120,
        value=_positive_int(record.get("billing_interval_months")),
        step=1,
    )
    start = _optional_date(record.get("start_date")) or today
    start_month = st.text_input(
        "摊销开始月份", value=start.strftime("%Y-%m"), placeholder="YYYY-MM"
    )
    category, subcategory = _category_fields(
        f"edit_prepaid_{record['id']}",
        display_text(record.get("category")),
        display_text(record.get("subcategory")),
    )
    notes = st.text_area(
        "备注", value=display_text(record.get("notes")), height=68
    )

    save_col, close_col = st.columns(2)
    with save_col:
        save = st.button(
            "保存修改", type="primary", key=f"save_prepaid_{record['id']}"
        )
    with close_col:
        close = st.button("关闭", key=f"close_prepaid_{record['id']}")
    if close:
        st.rerun()
    if not save:
        return
    if not description.strip():
        st.error("请填写描述。")
        return
    try:
        amortization_start = date.fromisoformat(
            f"{start_month.strip()}-01"
        ).isoformat()
    except ValueError:
        st.error("摊销开始月份必须是 YYYY-MM。")
        return

    update_subscription(
        int(record["id"]),
        name=description.strip(),
        billing_interval_months=int(months),
        start_date=amortization_start,
        category=category,
        subcategory=optional_text(subcategory),
        notes=optional_text(notes),
    )
    update_transaction(
        transaction_id,
        description=description.strip(),
        category=category,
        subcategory=optional_text(subcategory),
        notes=optional_text(notes),
        amortization_months=int(months),
        amortization_start=amortization_start,
    )
    st.rerun()


@st.dialog("删除预付摊销", width="small")
def _delete_prepaid_dialog(record: dict) -> None:
    st.warning(
        f"确认删除“{record['name']}”的摊销设置？关联流水不会删除，"
        "但摊销月数和开始月份会被清空。"
    )
    delete_col, close_col = st.columns(2)
    with delete_col:
        delete = st.button(
            "确认删除", type="primary", key=f"delete_prepaid_{record['id']}"
        )
    with close_col:
        close = st.button("取消", key=f"cancel_delete_prepaid_{record['id']}")
    if close:
        st.rerun()
    if delete:
        delete_prepaid_subscription(
            int(record["id"]), int(record["transaction_id"])
        )
        st.rerun()


def _expected_records() -> list[dict]:
    records = []
    for subscription in get_subscriptions(
        payment_type=RECURRING_PAYMENT_SUBSCRIPTION
    ):
        records.append(
            {
                **subscription,
                "source": "subscription",
                "description": subscription["name"],
                "next_date": subscription.get("next_renewal_date"),
            }
        )
    for plan in get_planned_expenses():
        records.append(
            {
                **plan,
                "source": "plan",
                "next_date": plan.get("due_date"),
            }
        )
    return sorted(
        records,
        key=lambda record: (
            record.get("next_date") is None,
            record.get("next_date") or "",
            record["description"],
        ),
    )


expected_tab, prepaid_tab = st.tabs(["预计支出", "预付摊销"])

with expected_tab:
    if st.button("新增预计支出", type="primary", key="open_add_expected"):
        _add_expected_dialog()

    expected_records = _expected_records()
    if not expected_records:
        st.info("暂无预计支出。")
    else:
        expected_display = pd.DataFrame(
            [
                {
                    "描述": record["description"],
                    "金额": f"¥{float(record.get('amount') or 0):,.2f}",
                    "下次日期": display_text(record.get("next_date")) or "—",
                    "周期": _cycle_label(record),
                    "主类别": display_text(record.get("category")),
                    "状态": _due_state(record),
                }
                for record in expected_records
            ]
        )
        expected_event = st.dataframe(
            expected_display,
            hide_index=True,
            width="stretch",
            selection_mode="single-row",
            on_select="rerun",
            column_config={
                "描述": st.column_config.TextColumn("描述", width="large"),
                "金额": st.column_config.TextColumn("金额", width="small"),
                "下次日期": st.column_config.TextColumn("下次日期", width="small"),
                "周期": st.column_config.TextColumn("周期", width="small"),
                "主类别": st.column_config.TextColumn("主类别", width="small"),
                "状态": st.column_config.TextColumn("状态", width="small"),
            },
        )
        if expected_event.selection.rows:
            selected = expected_records[expected_event.selection.rows[0]]
            confirm_col, edit_col, delete_col = st.columns([1, 1, 4])
            with confirm_col:
                if st.button(
                    "确认入账",
                    type="primary",
                    key=f"open_confirm_{selected['source']}_{selected['id']}",
                ):
                    _confirm_expected_dialog(selected)
            with edit_col:
                if st.button(
                    "编辑",
                    key=f"open_edit_{selected['source']}_{selected['id']}",
                ):
                    _edit_expected_dialog(selected)
            with delete_col:
                if st.button(
                    "删除",
                    key=f"open_delete_{selected['source']}_{selected['id']}",
                ):
                    _delete_expected_dialog(selected)

with prepaid_tab:
    if st.button("新增预付摊销", type="primary", key="open_add_prepaid"):
        _add_prepaid_dialog()

    prepaid_records = get_subscriptions(payment_type=RECURRING_PAYMENT_PREPAID)
    if not prepaid_records:
        st.info("暂无预付摊销。")
    else:
        prepaid_display = pd.DataFrame(
            [
                {
                    "描述": record["name"],
                    "总金额": f"¥{float(record.get('amount') or 0):,.2f}",
                    "月均": f"¥{float(record.get('monthly_equivalent') or 0):,.2f}",
                    "剩余月数": _remaining_months(record),
                    "摊销开始": display_text(record.get("start_date"))[:7],
                    "主类别": display_text(record.get("category")),
                }
                for record in prepaid_records
            ]
        )
        prepaid_event = st.dataframe(
            prepaid_display,
            hide_index=True,
            width="stretch",
            selection_mode="single-row",
            on_select="rerun",
            column_config={
                "描述": st.column_config.TextColumn("描述", width="large"),
                "总金额": st.column_config.TextColumn("总金额", width="small"),
                "月均": st.column_config.TextColumn("月均", width="small"),
                "剩余月数": st.column_config.NumberColumn(
                    "剩余月数", width="small"
                ),
                "摊销开始": st.column_config.TextColumn(
                    "摊销开始", width="small"
                ),
                "主类别": st.column_config.TextColumn("主类别", width="small"),
            },
        )
        if prepaid_event.selection.rows:
            selected = prepaid_records[prepaid_event.selection.rows[0]]
            edit_col, delete_col = st.columns([1, 5])
            with edit_col:
                if st.button(
                    "编辑", key=f"open_edit_prepaid_{selected['id']}"
                ):
                    _edit_prepaid_dialog(selected)
            with delete_col:
                if st.button(
                    "删除", key=f"open_delete_prepaid_{selected['id']}"
                ):
                    _delete_prepaid_dialog(selected)
