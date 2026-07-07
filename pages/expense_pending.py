from datetime import date

import pandas as pd
import streamlit as st

from core.config import load_config
from core.constants import PENDING_CATEGORY, TYPE_EXPENSE
from core.expense.db import (
    get_pending_transactions,
    update_transaction,
)
from core.text import display_text, optional_text

st.title("待处理")

config = load_config()
expense_categories = config.get(TYPE_EXPENSE, {})
rows = get_pending_transactions()

if not rows:
    st.info("暂无待处理支出。")
    st.stop()

st.caption("包含待分类、空分类、空子类和低置信度支出。")

df = pd.DataFrame(rows)
display_cols = [
    "id",
    "date",
    "description",
    "amount",
    "category",
    "subcategory",
    "confidence",
    "notes",
]
display_df = df[display_cols].copy()
display_df["amount"] = display_df["amount"].apply(lambda x: f"¥{float(x or 0):.2f}")
display_df["confidence"] = display_df["confidence"].apply(
    lambda x: "" if pd.isna(x) else f"{float(x):.0%}"
)
display_df["notes"] = display_df["notes"].apply(display_text)

event = st.dataframe(
    display_df,
    hide_index=True,
    width="stretch",
    selection_mode="single-row",
    on_select="rerun",
    column_config={
        "id": st.column_config.NumberColumn("ID", width="small"),
        "date": st.column_config.TextColumn("日期"),
        "description": st.column_config.TextColumn("描述"),
        "amount": st.column_config.TextColumn("金额"),
        "category": st.column_config.TextColumn("主类别"),
        "subcategory": st.column_config.TextColumn("子类别"),
        "confidence": st.column_config.TextColumn("置信度"),
        "notes": st.column_config.TextColumn("备注"),
    },
)

if not event.selection.rows:
    st.caption("选择一行处理。")
    st.stop()

record = df.iloc[event.selection.rows[0]].to_dict()
record_id = int(record["id"])

st.divider()
st.subheader(f"处理 #{record_id}")

description = st.text_input("描述", value=display_text(record.get("description")))
amount = st.number_input(
    "金额（元）",
    min_value=0.0,
    value=float(record.get("amount") or 0),
    format="%.2f",
)
entry_date = st.date_input(
    "日期", value=date.fromisoformat(display_text(record.get("date")))
)

cat_options = list(expense_categories.keys()) + [PENDING_CATEGORY]
cur_cat = display_text(record.get("category")) or PENDING_CATEGORY
cat_idx = cat_options.index(cur_cat) if cur_cat in cat_options else len(cat_options) - 1

col1, col2 = st.columns(2)
with col1:
    category = st.selectbox("主类别", cat_options, index=cat_idx)
with col2:
    if category == PENDING_CATEGORY:
        subcategory = PENDING_CATEGORY
        st.selectbox("子类别", [PENDING_CATEGORY], disabled=True)
    else:
        subs = expense_categories.get(category) or []
        cur_sub = display_text(record.get("subcategory"))
        if subs:
            sub_idx = subs.index(cur_sub) if cur_sub in subs else 0
            subcategory = st.selectbox("子类别", subs, index=sub_idx)
        else:
            subcategory = category
            st.caption("（无子类别）")

notes = st.text_area("备注", value=display_text(record.get("notes")), height=72)

c1, c2, c3 = st.columns(3)
with c1:
    if st.button("保存分类", type="primary", width="stretch"):
        update_transaction(
            record_id,
            description=description.strip(),
            amount=amount,
            date=entry_date.isoformat(),
            category=category,
            subcategory=subcategory,
            notes=optional_text(notes),
            confidence=1.0,
        )
        st.success("已更新。")
        st.rerun()
with c2:
    if st.button("保持待分类", width="stretch"):
        update_transaction(
            record_id,
            category=PENDING_CATEGORY,
            subcategory=PENDING_CATEGORY,
            notes=optional_text(notes),
        )
        st.rerun()
