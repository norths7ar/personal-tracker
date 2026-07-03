import streamlit as st
import pandas as pd
from datetime import date

from core.config import load_config
from core.constants import PENDING_CATEGORY
from core.expense.db import (
    add_transaction,
    get_refunds_for,
    get_transactions,
    refund_total_for,
    restore_transaction,
    update_transaction,
    void_transaction,
    delete_transaction,
)

st.title("开销流水")

if "expense_delete_candidate" not in st.session_state:
    st.session_state.expense_delete_candidate = None


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
        ["支出", "收入", "迁移"] if selected_type == "全部" else [selected_type]
    )
    categories = []
    for type_name in type_names:
        categories.extend(config.get(type_name, {}).keys())
    if "支出" in type_names:
        categories.append(PENDING_CATEGORY)
    return ["全部"] + _unique(categories)


def _subcategory_options(
    config: dict, selected_type: str, selected_category: str
) -> list[str]:
    if selected_category == PENDING_CATEGORY:
        return ["全部", PENDING_CATEGORY]
    type_names = (
        ["支出", "收入", "迁移"] if selected_type == "全部" else [selected_type]
    )
    subcategories = []
    for type_name in type_names:
        categories = config.get(type_name, {})
        if selected_category == "全部":
            for subs in categories.values():
                subcategories.extend(subs or [])
            if type_name == "支出":
                subcategories.append(PENDING_CATEGORY)
        else:
            subcategories.extend(categories.get(selected_category) or [])
    return ["全部"] + _unique(subcategories)


# ── 筛选 ────────────────────────────────────────────────────────────────────
config = load_config()

col1, col2, col3, col4, col5 = st.columns(5)
with col1:
    type_filter = st.selectbox("类型", ["全部", "支出", "收入", "迁移"])
with col2:
    category_filter = st.selectbox("主类别", _category_options(config, type_filter))
with col3:
    subcategory_filter = st.selectbox(
        "子类别", _subcategory_options(config, type_filter, category_filter)
    )
with col4:
    keyword = st.text_input("搜索描述", placeholder="关键词")
with col5:
    status_filter = st.selectbox("状态", ["正常", "已撤销", "全部"])

rows = get_transactions(
    type_=None if type_filter == "全部" else type_filter,
    limit=500,
    include_voided=status_filter == "全部",
    status="voided" if status_filter == "已撤销" else None,
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
        if any(needle in str(r.get(field) or "").lower() for field in search_fields)
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
    "status",
    "refund_for_id",
    "amortization_months",
    "notes",
]
display_df = df[display_cols].copy()
display_df["amount"] = display_df["amount"].apply(lambda x: f"¥{x:.2f}")

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
        "status": st.column_config.TextColumn("状态"),
        "refund_for_id": st.column_config.NumberColumn("退款关联", width="small"),
        "amortization_months": st.column_config.NumberColumn("摊销月数", width="small"),
        "notes": st.column_config.TextColumn("备注"),
    },
)

selected_rows = event.selection.rows
if not selected_rows:
    st.caption("点击一行可编辑或删除。")
    st.stop()

# ── 编辑面板 ────────────────────────────────────────────────────────────────
record = df.iloc[selected_rows[0]].to_dict()
# pandas 将空值读为 float NaN；统一转为 None 避免 "nan" 字符串
record = {
    k: (None if isinstance(v, float) and pd.isna(v) else v) for k, v in record.items()
}
record_id = int(str(record["id"]))
record_type = str(record["type"])
record_desc = str(record["description"])
record_amt = float(str(record["amount"]))
record_date = str(record["date"])
record_status = str(record.get("status") or "active")
st.divider()
st.subheader(f"编辑记录 #{record_id}")
if record_status == "voided":
    st.warning(f"这条记录已撤销。原因：{record.get('void_reason') or '未填写'}")

config = load_config()

entry_type = st.selectbox(
    "类型",
    ["支出", "收入", "迁移"],
    index=["支出", "收入", "迁移"].index(record_type),
    key=f"edit_type_{record_id}",
)
description = st.text_input("描述", value=record_desc)

col1, col2 = st.columns(2)
with col1:
    amount = st.number_input(
        "金额（元）", min_value=0.0, value=record_amt, format="%.2f"
    )
with col2:
    entry_date = st.date_input("日期", value=date.fromisoformat(record_date))

cats = config.get(entry_type, {})
cat_keys = list(cats.keys())
if entry_type == "支出":
    cat_keys.append(PENDING_CATEGORY)
cat_keys = _unique(cat_keys)

col3, col4 = st.columns(2)
with col3:
    cur_cat = record.get("category") or ""
    cat_idx = cat_keys.index(cur_cat) if cur_cat in cat_keys else 0
    if cat_keys:
        category = st.selectbox(
            "主类别", cat_keys, index=cat_idx, key=f"edit_cat_{record_id}"
        )
    else:
        category = st.text_input("主类别", value=cur_cat, key=f"edit_cat_{record_id}")
with col4:
    if category == PENDING_CATEGORY:
        subs = [PENDING_CATEGORY]
    else:
        subs = (cats.get(category) or []) if cat_keys else []
    cur_sub = record.get("subcategory") or ""
    if subs:
        sub_idx = subs.index(cur_sub) if cur_sub in subs else 0
        subcategory = st.selectbox(
            "子类别", subs, index=sub_idx, key=f"edit_sub_{record_id}_{category}"
        )
    else:
        subcategory = st.text_input(
            "子类别（可选）", value=cur_sub, key=f"edit_sub_{record_id}_{category}"
        )

notes = st.text_area("备注", value=record.get("notes") or "", height=68)

if entry_type == "支出":
    st.caption("退款和摊销")
    existing_refunds = get_refunds_for(record_id)
    if existing_refunds:
        total_refund = sum(float(r.get("amount") or 0) for r in existing_refunds)
        st.info(f"已关联退款 ¥{total_refund:.2f}，共 {len(existing_refunds)} 条。")
    amort_months = int(record.get("amortization_months") or 1)
    amort_start = str(record.get("amortization_start") or record_date)[:7]
    acol1, acol2 = st.columns(2)
    with acol1:
        amortization_months = st.number_input(
            "摊销月数",
            min_value=1,
            max_value=120,
            value=max(1, amort_months),
            step=1,
        )
    with acol2:
        amortization_start = st.text_input(
            "摊销开始月份", value=amort_start, placeholder="YYYY-MM"
        )
else:
    amortization_months = None
    amortization_start = None

c1, c2, c3 = st.columns([2, 2, 1])
with c1:
    save = st.button("保存修改", type="primary", width="stretch")
with c2:
    cancel = st.button("取消", width="stretch")
with c3:
    delete = st.button("删除", width="stretch")

if save:
    amortization_start_value = None
    if entry_type == "支出" and amortization_start:
        try:
            amortization_start_value = date.fromisoformat(
                f"{amortization_start}-01"
            ).isoformat()
        except ValueError:
            st.error("摊销开始月份必须是 YYYY-MM 格式。")
            st.stop()
    update_transaction(
        record_id,
        type=entry_type,
        description=description.strip(),
        amount=amount,
        date=entry_date.strftime("%Y-%m-%d"),
        category=category or None,
        subcategory=subcategory or None,
        notes=notes.strip() or None,
        amortization_months=amortization_months if entry_type == "支出" else None,
        amortization_start=amortization_start_value,
    )
    st.session_state.expense_delete_candidate = None
    st.success("已保存。")
    st.rerun()

if cancel:
    st.rerun()

if delete:
    st.session_state.expense_delete_candidate = record_id
    st.rerun()

if st.session_state.expense_delete_candidate == record_id:
    st.warning(f"确认删除记录 #{record_id}？此操作不可撤销。")
    confirm_col, cancel_col = st.columns(2)
    with confirm_col:
        confirm_delete = st.button(
            "确认删除",
            type="primary",
            width="stretch",
            key=f"confirm_delete_{record_id}",
        )
    with cancel_col:
        cancel_delete = st.button(
            "取消删除", width="stretch", key=f"cancel_delete_{record_id}"
        )

    if confirm_delete:
        st.session_state.expense_delete_candidate = None
        delete_transaction(record_id)
        st.success(f"记录 #{record_id} 已删除。")
        st.rerun()
    if cancel_delete:
        st.session_state.expense_delete_candidate = None
        st.rerun()

st.divider()
action_col1, action_col2 = st.columns(2)
with action_col1:
    if record_status == "voided":
        if st.button("恢复记录", width="stretch"):
            restore_transaction(record_id)
            st.rerun()
    else:
        void_reason = st.text_input("撤销原因", key=f"void_reason_{record_id}")
        if st.button("撤销记录", width="stretch"):
            void_transaction(record_id, void_reason.strip() or None)
            st.rerun()

with action_col2:
    if record_type == "支出" and record_status != "voided":
        with st.form(f"refund_form_{record_id}"):
            st.caption("新增关联退款")
            refunded = refund_total_for(record_id)
            default_amount = max(0.0, record_amt - refunded)
            refund_amount = st.number_input(
                "退款金额", min_value=0.0, value=default_amount, format="%.2f"
            )
            refund_date = st.date_input("退款日期", value=date.today())
            refund_desc = st.text_input("退款描述", value=f"{record_desc} 退款")
            submitted = st.form_submit_button("保存退款", width="stretch")
            if submitted and refund_amount > 0:
                add_transaction(
                    "收入",
                    refund_desc.strip() or f"{record_desc} 退款",
                    refund_amount,
                    refund_date.isoformat(),
                    category="退款",
                    subcategory=None,
                    notes=f"关联支出 #{record_id}",
                    refund_for_id=record_id,
                )
                st.rerun()
