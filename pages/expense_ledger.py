import streamlit as st
import pandas as pd
from datetime import date

from core.config import load_config
from core.constants import (
    PENDING_CATEGORY,
    REFUND_CATEGORY,
    TRANSACTION_TYPES,
    TYPE_EXPENSE,
    TYPE_INCOME,
)
from core.expense.db import (
    add_transaction,
    get_transactions,
    refund_total_for,
    update_transaction,
    delete_transaction,
)
from core.text import display_text, is_blank, optional_text

st.title("开销流水")


def _unique(values):
    seen = set()
    result = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _category_options(config: dict, selected_type: str) -> list[str]:
    type_names = (
        list(TRANSACTION_TYPES) if selected_type == "全部" else [selected_type]
    )
    categories = []
    for type_name in type_names:
        categories.extend(config.get(type_name, {}).keys())
    if TYPE_EXPENSE in type_names:
        categories.append(PENDING_CATEGORY)
    return ["全部"] + _unique(categories)


def _subcategory_options(
    config: dict, selected_type: str, selected_category: str
) -> list[str]:
    if selected_category == PENDING_CATEGORY:
        return ["全部", PENDING_CATEGORY]
    type_names = (
        list(TRANSACTION_TYPES) if selected_type == "全部" else [selected_type]
    )
    subcategories = []
    for type_name in type_names:
        categories = config.get(type_name, {})
        if selected_category == "全部":
            for subs in categories.values():
                subcategories.extend(subs or [])
            if type_name == TYPE_EXPENSE:
                subcategories.append(PENDING_CATEGORY)
        else:
            subcategories.extend(categories.get(selected_category) or [])
    return ["全部"] + _unique(subcategories)


# ── 筛选 ────────────────────────────────────────────────────────────────────
config = load_config()

row1_c1, row1_c2, row1_c3 = st.columns(3)
with row1_c1:
    type_filter = st.selectbox("类型", ["全部", *TRANSACTION_TYPES])
with row1_c2:
    category_filter = st.selectbox("主类别", _category_options(config, type_filter))
with row1_c3:
    subcategory_filter = st.selectbox(
        "子类别", _subcategory_options(config, type_filter, category_filter)
    )

row2_c1, _ = st.columns([4, 1])
with row2_c1:
    keyword = st.text_input("搜索", placeholder="描述 / 分类 / 备注")

rows = get_transactions(
    type_=None if type_filter == "全部" else type_filter,
    limit=500,
)

if category_filter != "全部":
    rows = [r for r in rows if r.get("category") == category_filter]

if subcategory_filter != "全部":
    rows = [r for r in rows if r.get("subcategory") == subcategory_filter]

needle = keyword.strip().lower()
if needle:
    search_fields = ("description", "category", "subcategory", "notes")
    rows = [
        r
        for r in rows
        if any(needle in display_text(r.get(field)).lower() for field in search_fields)
    ]

if not rows:
    st.info("没有符合条件的记录。")
    st.stop()

# ── 导出 + 表格 ─────────────────────────────────────────────────────────────
df = pd.DataFrame(rows)

col_export, col_count = st.columns([1, 3])
with col_export:
    csv = df.to_csv(index=False, encoding="utf-8-sig")
    st.download_button(
        "导出为CSV",
        data=csv,
        file_name=f"流水_{date.today().strftime('%Y%m%d')}.csv",
        mime="text/csv",
        help="包含置信度、创建时间等所有字段",
    )
with col_count:
    st.caption(f"共 {len(rows)} 条记录")

display_cols = [
    "id",
    "date",
    "type",
    "description",
    "amount",
    "category",
    "subcategory",
    "amortization_months",
]
display_df = df[[c for c in display_cols if c in df.columns]].copy()
display_df["amount"] = display_df["amount"].apply(lambda x: f"¥{x:.2f}")
for text_col in ("category", "subcategory"):
    display_df[text_col] = display_df[text_col].apply(display_text)

event = st.dataframe(
    display_df,
    hide_index=True,
    width="stretch",
    selection_mode="single-row",
    on_select="rerun",
    column_config={
        "id": st.column_config.NumberColumn("ID", width="small"),
        "date": st.column_config.TextColumn("日期"),
        "type": st.column_config.TextColumn("类型"),
        "description": st.column_config.TextColumn("描述"),
        "amount": st.column_config.TextColumn("金额"),
        "category": st.column_config.TextColumn("主类别"),
        "subcategory": st.column_config.TextColumn("子类别"),
        "amortization_months": st.column_config.NumberColumn("摊销月", width="small"),
    },
)

selected_rows = event.selection.rows
if not selected_rows:
    st.caption("点击一行可编辑或删除。")
    st.stop()

# ── 操作面板 ─────────────────────────────────────────────────────────────────
record = df.iloc[selected_rows[0]].to_dict()
record_id = int(str(record["id"]))
record_type = display_text(record["type"])
record_desc = display_text(record["description"])
record_amt = float(str(record["amount"]))
record_date = display_text(record["date"])

# 切换行时重置操作状态
if st.session_state.get("ledger_selected_id") != record_id:
    st.session_state.ledger_selected_id = record_id
    st.session_state.ledger_action = None

st.divider()
st.caption(f"#{record_id}  ·  {record_date}  ·  {record_type}  ·  {record_desc}  ·  ¥{record_amt:.2f}")

can_refund = record_type == TYPE_EXPENSE

btn1, btn2, btn3 = st.columns(3)
with btn1:
    if st.button("编辑", width="stretch", type="primary"):
        st.session_state.ledger_action = "edit"
        st.rerun()
with btn2:
    if st.button("记录退款", width="stretch", disabled=not can_refund):
        st.session_state.ledger_action = "refund"
        st.rerun()
with btn3:
    if st.button("删除", width="stretch"):
        st.session_state.ledger_action = "delete"
        st.rerun()

action = st.session_state.get("ledger_action")

# ── 编辑表单 ─────────────────────────────────────────────────────────────────
if action == "edit":
    entry_type = st.selectbox(
        "类型", list(TRANSACTION_TYPES),
        index=list(TRANSACTION_TYPES).index(record_type),
        key=f"edit_type_{record_id}",
    )
    description = st.text_input("描述", value=record_desc)
    col1, col2 = st.columns(2)
    with col1:
        amount = st.number_input("金额（元）", min_value=0.0, value=record_amt, format="%.2f")
    with col2:
        entry_date = st.date_input("日期", value=date.fromisoformat(record_date))

    cats = config.get(entry_type, {})
    cat_keys = _unique(list(cats.keys()) + ([PENDING_CATEGORY] if entry_type == TYPE_EXPENSE else []))
    col3, col4 = st.columns(2)
    with col3:
        cur_cat = display_text(record.get("category"))
        cat_idx = cat_keys.index(cur_cat) if cur_cat in cat_keys else 0
        if cat_keys:
            category = st.selectbox("主类别", cat_keys, index=cat_idx, key=f"edit_cat_{record_id}")
        else:
            category = st.text_input("主类别", value=cur_cat, key=f"edit_cat_{record_id}")
    with col4:
        subs = [PENDING_CATEGORY] if category == PENDING_CATEGORY else ((cats.get(category) or []) if cat_keys else [])
        cur_sub = display_text(record.get("subcategory"))
        if subs:
            sub_idx = subs.index(cur_sub) if cur_sub in subs else 0
            subcategory = st.selectbox("子类别", subs, index=sub_idx, key=f"edit_sub_{record_id}_{category}")
        else:
            subcategory = st.text_input("子类别（可选）", value=cur_sub, key=f"edit_sub_{record_id}_{category}")

    notes = st.text_area("备注", value=display_text(record.get("notes")), height=68)

    amortization_months = None
    amortization_start = None
    if entry_type == TYPE_EXPENSE:
        _amort_raw = record.get("amortization_months")
        amort_months = 1 if is_blank(_amort_raw) else int(float(_amort_raw))
        amort_start = (display_text(record.get("amortization_start")) or record_date)[:7]
        with st.expander("摊销设置", expanded=amort_months > 1):
            acol1, acol2 = st.columns(2)
            with acol1:
                amortization_months = st.number_input("摊销月数", min_value=1, max_value=120,
                                                       value=max(1, amort_months), step=1)
            with acol2:
                amortization_start = st.text_input("摊销开始月份", value=amort_start, placeholder="YYYY-MM")

    c1, c2 = st.columns(2)
    with c1:
        if st.button("保存修改", type="primary", width="stretch"):
            amortization_start_value = None
            if entry_type == TYPE_EXPENSE and amortization_start:
                try:
                    amortization_start_value = date.fromisoformat(f"{amortization_start}-01").isoformat()
                except ValueError:
                    st.error("摊销开始月份必须是 YYYY-MM 格式。")
                    st.stop()
            update_transaction(
                record_id, type=entry_type, description=description.strip(),
                amount=amount, date=entry_date.strftime("%Y-%m-%d"),
                category=category or None, subcategory=subcategory or None,
                notes=optional_text(notes),
                amortization_months=amortization_months if entry_type == TYPE_EXPENSE else None,
                amortization_start=amortization_start_value,
            )
            st.session_state.ledger_action = None
            st.success("已保存。")
            st.rerun()
    with c2:
        if st.button("取消", width="stretch"):
            st.session_state.ledger_action = None
            st.rerun()

# ── 退款表单 ─────────────────────────────────────────────────────────────────
elif action == "refund":
    refunded = refund_total_for(record_id)
    default_refund = max(0.0, record_amt - refunded)
    if refunded > 0:
        st.caption(f"已关联退款 ¥{refunded:.2f}，剩余可退 ¥{default_refund:.2f}")
    with st.form(f"refund_form_{record_id}"):
        refund_amount = st.number_input("退款金额", min_value=0.0, value=default_refund, format="%.2f")
        refund_date = st.date_input("退款日期", value=date.today())
        refund_desc = st.text_input("退款描述", value=f"{record_desc} 退款")
        c1, c2 = st.columns(2)
        with c1:
            submitted = st.form_submit_button("保存退款", type="primary", width="stretch")
        with c2:
            cancelled = st.form_submit_button("取消", width="stretch")
    if submitted:
        if refund_amount <= 0:
            st.error("退款金额须大于 0。")
        else:
            add_transaction(
                TYPE_INCOME,
                refund_desc.strip() or f"{record_desc} 退款",
                refund_amount, refund_date.isoformat(),
                category=REFUND_CATEGORY, subcategory=None,
                notes=f"关联支出 #{record_id}", refund_for_id=record_id,
            )
            st.session_state.ledger_action = None
            st.rerun()
    if cancelled:
        st.session_state.ledger_action = None
        st.rerun()

# ── 删除确认 ─────────────────────────────────────────────────────────────────
elif action == "delete":
    st.warning(f"确认删除记录 #{record_id}？此操作不可撤销。")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("确认删除", type="primary", width="stretch", key=f"confirm_delete_{record_id}"):
            delete_transaction(record_id)
            st.session_state.ledger_action = None
            st.rerun()
    with c2:
        if st.button("取消", width="stretch", key=f"cancel_delete_{record_id}"):
            st.session_state.ledger_action = None
            st.rerun()
