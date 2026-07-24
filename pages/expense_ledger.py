from datetime import date

import pandas as pd
import streamlit as st

from core.config import load_config
from core.constants import (
    PENDING_CATEGORY,
    REFUND_CATEGORY,
    RENEWAL_MODE_FIXED_DAYS,
    RENEWAL_MODE_SAME_DAY,
    SUBSCRIPTION_CYCLE_CUSTOM,
    SUBSCRIPTION_CYCLE_MONTHLY,
    SUBSCRIPTION_CYCLE_QUARTERLY,
    SUBSCRIPTION_CYCLE_YEARLY,
    TRANSACTION_TYPES,
    TYPE_EXPENSE,
    TYPE_INCOME,
)
from core.expense.db import (
    add_transaction,
    delete_transaction,
    get_transactions,
    refund_total_for,
    update_transaction,
)
from core.subscription.db import create_subscription_from_transaction
from core.text import display_text, is_blank, optional_text

st.title("账目")


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _category_options(config: dict, selected_type: str) -> list[str]:
    types = TRANSACTION_TYPES if selected_type == "全部" else (selected_type,)
    categories = [
        category for type_name in types for category in config.get(type_name, {})
    ]
    if TYPE_EXPENSE in types:
        categories.append(PENDING_CATEGORY)
    return ["全部", *_unique(categories)]


def _subcategory_options(
    config: dict, selected_type: str, selected_category: str
) -> list[str]:
    if selected_category == PENDING_CATEGORY:
        return ["全部", PENDING_CATEGORY]
    types = TRANSACTION_TYPES if selected_type == "全部" else (selected_type,)
    subcategories: list[str] = []
    for type_name in types:
        categories = config.get(type_name, {})
        if selected_category == "全部":
            subcategories.extend(
                subcategory
                for values in categories.values()
                for subcategory in (values or [])
            )
        else:
            subcategories.extend(categories.get(selected_category) or [])
    return ["全部", *_unique(subcategories)]


def _cycle_from_months(months: int) -> tuple[str, int | None]:
    if months == 1:
        return SUBSCRIPTION_CYCLE_MONTHLY, None
    if months == 3:
        return SUBSCRIPTION_CYCLE_QUARTERLY, None
    if months == 12:
        return SUBSCRIPTION_CYCLE_YEARLY, None
    return SUBSCRIPTION_CYCLE_CUSTOM, months


@st.dialog("编辑账目", width="small")
def _show_editor_dialog(record: dict, config: dict) -> None:
    record_id = int(record["id"])
    record_type = display_text(record["type"])
    record_date = display_text(record["date"])
    st.caption(f"#{record_id} · {record_date} · {record_type}")

    edit_tab, amortization_tab, recurring_tab, refund_tab, delete_tab = st.tabs(
        ["编辑", "摊销", "周期付款", "退款", "删除"]
    )
    with edit_tab:
        with st.form(f"transaction_edit_{record_id}"):
            entry_type = st.selectbox(
                "类型",
                TRANSACTION_TYPES,
                index=TRANSACTION_TYPES.index(record_type),
            )
            description = st.text_input("描述", value=display_text(record["description"]))
            amount_col, date_col = st.columns(2)
            with amount_col:
                amount = st.number_input(
                    "金额（元）",
                    min_value=0.0,
                    value=float(record["amount"]),
                    format="%.2f",
                )
            with date_col:
                entry_date = st.date_input("日期", value=date.fromisoformat(record_date))

            categories = config.get(entry_type, {})
            category_options = _unique(
                [*categories, *([PENDING_CATEGORY] if entry_type == TYPE_EXPENSE else [])]
            )
            current_category = display_text(record.get("category"))
            if category_options:
                category = st.selectbox(
                    "主类别",
                    category_options,
                    index=(
                        category_options.index(current_category)
                        if current_category in category_options
                        else 0
                    ),
                )
            else:
                category = st.text_input("主类别", value=current_category)

            subcategory_options = (
                [PENDING_CATEGORY]
                if category == PENDING_CATEGORY
                else categories.get(category) or []
            )
            current_subcategory = display_text(record.get("subcategory"))
            if subcategory_options:
                subcategory = st.selectbox(
                    "子类别",
                    subcategory_options,
                    index=(
                        subcategory_options.index(current_subcategory)
                        if current_subcategory in subcategory_options
                        else 0
                    ),
                )
            else:
                subcategory = st.text_input("子类别（可选）", value=current_subcategory)

            notes = st.text_area(
                "备注", value=display_text(record.get("notes")), height=68
            )
            submitted = st.form_submit_button("保存修改", type="primary")

        if submitted:
            update_transaction(
                record_id,
                type=entry_type,
                description=description.strip(),
                amount=amount,
                date=entry_date.isoformat(),
                category=optional_text(category),
                subcategory=optional_text(subcategory),
                notes=optional_text(notes),
            )
            st.rerun()

    with amortization_tab:
        if record_type != TYPE_EXPENSE:
            st.info("只有支出记录可以设置摊销。")
        else:
            raw_months = record.get("amortization_months")
            current_months = (
                12 if is_blank(raw_months) else max(2, int(float(raw_months)))
            )
            current_start = (
                display_text(record.get("amortization_start")) or record_date
            )[:7]
            st.caption("把这笔已发生的支出分摊到多个自然月。")
            with st.form(f"amortization_form_{record_id}"):
                months = st.number_input(
                    "摊销月数",
                    min_value=2,
                    max_value=120,
                    value=current_months,
                    step=1,
                )
                start_month = st.text_input(
                    "摊销开始月份",
                    value=current_start,
                    placeholder="YYYY-MM",
                )
                amortization_submitted = st.form_submit_button(
                    "保存摊销", type="primary"
                )
            if amortization_submitted:
                try:
                    amortization_start = date.fromisoformat(
                        f"{start_month.strip()}-01"
                    ).isoformat()
                except ValueError:
                    st.error("摊销开始月份必须是 YYYY-MM 格式。")
                    return
                update_transaction(
                    record_id,
                    amortization_months=int(months),
                    amortization_start=amortization_start,
                )
                st.rerun()

    with refund_tab:
        if record_type != TYPE_EXPENSE:
            st.info("只有支出记录可以关联退款。")
        else:
            refunded = refund_total_for(record_id)
            default_refund = max(0.0, float(record["amount"]) - refunded)
            st.caption(f"已关联退款 ¥{refunded:,.2f}，剩余可退 ¥{default_refund:,.2f}")
            with st.form(f"refund_form_{record_id}"):
                refund_amount = st.number_input(
                    "退款金额", min_value=0.0, value=default_refund, format="%.2f"
                )
                refund_date = st.date_input("退款日期", value=date.today())
                refund_description = st.text_input(
                    "退款描述", value=f"{display_text(record['description'])} 退款"
                )
                refund_submitted = st.form_submit_button("保存退款", type="primary")
            if refund_submitted:
                if refund_amount <= 0:
                    st.error("退款金额须大于 0。")
                else:
                    add_transaction(
                        TYPE_INCOME,
                        refund_description.strip()
                        or f"{display_text(record['description'])} 退款",
                        refund_amount,
                        refund_date.isoformat(),
                        category=REFUND_CATEGORY,
                        notes=f"关联支出 #{record_id}",
                        refund_for_id=record_id,
                    )
                    st.rerun()

    with recurring_tab:
        if record_type != TYPE_EXPENSE:
            st.info("只有支出记录可以设为周期性付款。")
        elif not is_blank(record.get("subscription_id")):
            st.info("这笔支出已经关联周期性付款。")
        else:
            st.caption("用这笔支出作为首次付款，后续到期时再确认入账。")
            recurring_name = st.text_input(
                "描述",
                value=display_text(record.get("description")),
                key=f"recurring_name_{record_id}",
            )
            next_payment_date = st.date_input(
                "下次付款日",
                value=date.today(),
                key=f"recurring_next_date_{record_id}",
            )
            renewal_mode = st.radio(
                "续费方式",
                [RENEWAL_MODE_SAME_DAY, RENEWAL_MODE_FIXED_DAYS],
                format_func=lambda value: (
                    "按月同日"
                    if value == RENEWAL_MODE_SAME_DAY
                    else "固定天数"
                ),
                horizontal=True,
                key=f"recurring_mode_{record_id}",
            )
            if renewal_mode == RENEWAL_MODE_SAME_DAY:
                renewal_interval = int(
                    st.number_input(
                        "每几个月",
                        min_value=1,
                        max_value=120,
                        value=1,
                        step=1,
                        key=f"recurring_months_{record_id}",
                    )
                )
            else:
                renewal_interval = int(
                    st.number_input(
                        "每几天",
                        min_value=1,
                        max_value=730,
                        value=30,
                        step=1,
                        key=f"recurring_days_{record_id}",
                    )
                )
            if st.button(
                "创建周期性付款",
                type="primary",
                key=f"create_recurring_{record_id}",
            ):
                if not recurring_name.strip():
                    st.error("请填写描述。")
                else:
                    billing_cycle, billing_interval_months = _cycle_from_months(
                        renewal_interval
                    )
                    create_subscription_from_transaction(
                        transaction_id=record_id,
                        name=recurring_name.strip(),
                        billing_cycle=billing_cycle,
                        billing_interval_months=billing_interval_months,
                        next_renewal_date=next_payment_date.isoformat(),
                        renewal_mode=renewal_mode,
                        renewal_interval=renewal_interval,
                        renewal_anchor_day=(
                            next_payment_date.day
                            if renewal_mode == RENEWAL_MODE_SAME_DAY
                            else None
                        )
                    )
                    st.rerun()

    with delete_tab:
        delete_key = f"confirm_delete_{record_id}"
        if not st.session_state.get(delete_key):
            st.warning("删除后无法恢复。")
            if st.button("删除这条记录", type="secondary"):
                st.session_state[delete_key] = True
                st.rerun()
        else:
            st.warning("确认永久删除这条记录？")
            cancel_col, confirm_col = st.columns(2)
            with cancel_col:
                if st.button("取消删除"):
                    st.session_state.pop(delete_key, None)
                    st.rerun()
            with confirm_col:
                if st.button("确认删除", type="primary"):
                    delete_transaction(record_id)
                    st.session_state.pop(delete_key, None)
                    st.rerun()


config = load_config()
filter_type, filter_category, filter_subcategory, filter_keyword = st.columns([2, 3, 3, 4])
with filter_type:
    type_filter = st.selectbox("类型", ["全部", *TRANSACTION_TYPES])
with filter_category:
    category_filter = st.selectbox("主类别", _category_options(config, type_filter))
with filter_subcategory:
    subcategory_filter = st.selectbox(
        "子类别", _subcategory_options(config, type_filter, category_filter)
    )
with filter_keyword:
    keyword = st.text_input("搜索", placeholder="描述、分类或备注")

rows = get_transactions(type_=None if type_filter == "全部" else type_filter, limit=500)
if category_filter != "全部":
    rows = [row for row in rows if row.get("category") == category_filter]
if subcategory_filter != "全部":
    rows = [row for row in rows if row.get("subcategory") == subcategory_filter]
if keyword.strip():
    needle = keyword.strip().lower()
    rows = [
        row
        for row in rows
        if any(
            needle in display_text(row.get(field)).lower()
            for field in ("description", "category", "subcategory", "notes")
        )
    ]

if not rows:
    st.info("没有符合条件的记录。")
    st.stop()

df = pd.DataFrame(rows)
display_df = df[
    ["id", "date", "type", "description", "amount", "category", "subcategory", "amortization_months"]
].copy()
display_df["amount"] = display_df["amount"].map(lambda value: f"¥{float(value):.2f}")
for column in ("category", "subcategory"):
    display_df[column] = display_df[column].map(display_text)

export_col, count_col = st.columns([1, 4])
with export_col:
    st.download_button(
        "导出 CSV",
        data=df.to_csv(index=False, encoding="utf-8-sig"),
        file_name=f"流水_{date.today():%Y%m%d}.csv",
        mime="text/csv",
    )
with count_col:
    st.caption(f"{len(rows)} 条记录")

event = st.dataframe(
    display_df,
    hide_index=True,
    width="stretch",
    selection_mode="single-row",
    on_select="rerun",
    column_config={
        "id": st.column_config.NumberColumn("ID", width="small"),
        "date": st.column_config.TextColumn("日期", width="small"),
        "type": st.column_config.TextColumn("类型", width="small"),
        "description": st.column_config.TextColumn("描述", width="large"),
        "amount": st.column_config.TextColumn("金额", width="small"),
        "category": st.column_config.TextColumn("主类别", width="medium"),
        "subcategory": st.column_config.TextColumn("子类别", width="medium"),
        "amortization_months": st.column_config.NumberColumn("摊销月", width="small"),
    },
)

if event.selection.rows:
    selected_record = df.iloc[event.selection.rows[0]].to_dict()
    if st.button("编辑所选记录", type="primary"):
        _show_editor_dialog(selected_record, config)
