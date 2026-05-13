import streamlit as st
import pandas as pd
from datetime import date

from core.config import load_config
from core.expense.db import get_transactions, update_transaction, delete_transaction

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
    type_names = ["支出", "收入", "迁移"] if selected_type == "全部" else [selected_type]
    categories = []
    for type_name in type_names:
        categories.extend(config.get(type_name, {}).keys())
    return ["全部"] + _unique(categories)


def _subcategory_options(config: dict, selected_type: str, selected_category: str) -> list[str]:
    type_names = ["支出", "收入", "迁移"] if selected_type == "全部" else [selected_type]
    subcategories = []
    for type_name in type_names:
        categories = config.get(type_name, {})
        if selected_category == "全部":
            for subs in categories.values():
                subcategories.extend(subs or [])
        else:
            subcategories.extend(categories.get(selected_category) or [])
    return ["全部"] + _unique(subcategories)


# ── 筛选 ────────────────────────────────────────────────────────────────────
config = load_config()

col1, col2, col3, col4 = st.columns(4)
with col1:
    type_filter = st.selectbox("类型", ["全部", "支出", "收入", "迁移"])
with col2:
    category_filter = st.selectbox("主类别", _category_options(config, type_filter))
with col3:
    subcategory_filter = st.selectbox("子类别", _subcategory_options(config, type_filter, category_filter))
with col4:
    keyword = st.text_input("搜索描述", placeholder="关键词")

rows = get_transactions(type_=None if type_filter == "全部" else type_filter, limit=500)

if category_filter != "全部":
    rows = [r for r in rows if r.get("category") == category_filter]

if subcategory_filter != "全部":
    rows = [r for r in rows if r.get("subcategory") == subcategory_filter]

needle = keyword.strip().lower()
if needle:
    search_fields = ("description", "category", "subcategory", "notes")
    rows = [
        r for r in rows
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

display_cols = ["id", "date", "type", "description", "amount", "category", "subcategory", "notes"]
display_df = df[display_cols].copy()
display_df["amount"] = display_df["amount"].apply(lambda x: f"¥{x:.2f}")

event = st.dataframe(
    display_df,
    hide_index=True,
    width="stretch",
    selection_mode="single-row",
    on_select="rerun",
    column_config={
        "id":          st.column_config.NumberColumn("ID", width="small"),
        "date":        st.column_config.TextColumn("日期"),
        "type":        st.column_config.TextColumn("类型"),
        "description": st.column_config.TextColumn("描述"),
        "amount":      st.column_config.TextColumn("金额"),
        "category":    st.column_config.TextColumn("主类别"),
        "subcategory": st.column_config.TextColumn("子类别"),
        "notes":       st.column_config.TextColumn("备注"),
    },
)

selected_rows = event.selection.rows
if not selected_rows:
    st.caption("点击一行可编辑或删除。")
    st.stop()

# ── 编辑面板 ────────────────────────────────────────────────────────────────
record = df.iloc[selected_rows[0]].to_dict()
# pandas 将空值读为 float NaN；统一转为 None 避免 "nan" 字符串
record = {k: (None if isinstance(v, float) and pd.isna(v) else v) for k, v in record.items()}
record_id   = int(str(record["id"]))
record_type = str(record["type"])
record_desc = str(record["description"])
record_amt  = float(str(record["amount"]))
record_date = str(record["date"])
st.divider()
st.subheader(f"编辑记录 #{record_id}")

config = load_config()

entry_type = st.selectbox(
    "类型", ["支出", "收入", "迁移"],
    index=["支出", "收入", "迁移"].index(record_type),
    key=f"edit_type_{record_id}",
)
description = st.text_input("描述", value=record_desc)

col1, col2 = st.columns(2)
with col1:
    amount = st.number_input("金额（元）", min_value=0.0,
                             value=record_amt, format="%.2f")
with col2:
    entry_date = st.date_input("日期", value=date.fromisoformat(record_date))

cats = config.get(entry_type, {})
cat_keys = list(cats.keys())

col3, col4 = st.columns(2)
with col3:
    cur_cat = record.get("category") or ""
    cat_idx = cat_keys.index(cur_cat) if cur_cat in cat_keys else 0
    if cat_keys:
        category = st.selectbox("主类别", cat_keys, index=cat_idx,
                                key=f"edit_cat_{record_id}")
    else:
        category = st.text_input("主类别", value=cur_cat,
                                 key=f"edit_cat_{record_id}")
with col4:
    subs = (cats.get(category) or []) if cat_keys else []
    cur_sub = record.get("subcategory") or ""
    if subs:
        sub_idx = subs.index(cur_sub) if cur_sub in subs else 0
        subcategory = st.selectbox("子类别", subs, index=sub_idx,
                                   key=f"edit_sub_{record_id}_{category}")
    else:
        subcategory = st.text_input("子类别（可选）", value=cur_sub,
                                    key=f"edit_sub_{record_id}_{category}")

notes = st.text_area("备注", value=record.get("notes") or "", height=68)

c1, c2, c3 = st.columns([2, 2, 1])
with c1:
    save = st.button("保存修改", type="primary", width="stretch")
with c2:
    cancel = st.button("取消", width="stretch")
with c3:
    delete = st.button("删除", width="stretch")

if save:
    update_transaction(
        record_id,
        type=entry_type,
        description=description.strip(),
        amount=amount,
        date=entry_date.strftime("%Y-%m-%d"),
        category=category or None,
        subcategory=subcategory or None,
        notes=notes.strip() or None,
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
        confirm_delete = st.button("确认删除", type="primary", width="stretch", key=f"confirm_delete_{record_id}")
    with cancel_col:
        cancel_delete = st.button("取消删除", width="stretch", key=f"cancel_delete_{record_id}")

    if confirm_delete:
        st.session_state.expense_delete_candidate = None
        delete_transaction(record_id)
        st.success(f"记录 #{record_id} 已删除。")
        st.rerun()

    if cancel_delete:
        st.session_state.expense_delete_candidate = None
        st.rerun()
