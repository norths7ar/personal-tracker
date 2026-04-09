import streamlit as st
import pandas as pd
from datetime import date

from core.config import load_config
from core.expense.db import get_transactions, update_transaction, delete_transaction

st.title("开销流水")

# ── 筛选 ────────────────────────────────────────────────────────────────────
col1, col2 = st.columns(2)
with col1:
    type_filter = st.selectbox("类型", ["全部", "支出", "收入", "迁移"])
with col2:
    keyword = st.text_input("搜索描述", placeholder="关键词")

rows = get_transactions(type_=None if type_filter == "全部" else type_filter, limit=500)

if keyword:
    rows = [r for r in rows if keyword.lower() in r["description"].lower()]

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

# ── 编辑表单 ────────────────────────────────────────────────────────────────
record = df.iloc[selected_rows[0]].to_dict()
st.divider()
st.subheader(f"编辑记录 #{int(record['id'])}")

config = load_config()

with st.form("edit_form"):
    entry_type = st.selectbox("类型", ["支出", "收入", "迁移"],
                              index=["支出", "收入", "迁移"].index(record["type"]))
    description = st.text_input("描述", value=record["description"])

    col1, col2 = st.columns(2)
    with col1:
        amount = st.number_input("金额（元）", min_value=0.0,
                                 value=float(record["amount"]), format="%.2f")
    with col2:
        entry_date = st.date_input("日期", value=date.fromisoformat(record["date"]))

    # 分类选择：根据类型读对应的 config 分类
    cats = config.get(entry_type, {})
    cat_keys = list(cats.keys())

    col3, col4 = st.columns(2)
    with col3:
        cur_cat = record.get("category") or ""
        cat_idx = cat_keys.index(cur_cat) if cur_cat in cat_keys else 0
        category = st.selectbox("主类别", cat_keys, index=cat_idx) if cat_keys else \
                   st.text_input("主类别", value=cur_cat)
    with col4:
        subs = (cats.get(category) or []) if cat_keys else []
        cur_sub = record.get("subcategory") or ""
        if subs:
            sub_idx = subs.index(cur_sub) if cur_sub in subs else 0
            subcategory = st.selectbox("子类别", subs, index=sub_idx)
        else:
            subcategory = st.text_input("子类别（可选）", value=cur_sub)

    notes = st.text_area("备注", value=record.get("notes") or "", height=68)

    c1, c2, c3 = st.columns([2, 2, 1])
    with c1:
        save = st.form_submit_button("保存修改", type="primary", width="stretch")
    with c2:
        cancel = st.form_submit_button("取消", width="stretch")
    with c3:
        delete = st.form_submit_button("删除", width="stretch")

if save:
    update_transaction(
        int(record["id"]),
        type=entry_type,
        description=description.strip(),
        amount=amount,
        date=entry_date.strftime("%Y-%m-%d"),
        category=category or None,
        subcategory=subcategory or None,
        notes=notes.strip() or None,
    )
    st.success("已保存。")
    st.rerun()

if cancel:
    st.rerun()

if delete:
    delete_transaction(int(record["id"]))
    st.success(f"记录 #{int(record['id'])} 已删除。")
    st.rerun()
