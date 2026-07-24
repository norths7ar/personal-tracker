from datetime import date

import pandas as pd
import streamlit as st

from core.config import load_config
from core.constants import PENDING_CATEGORY, TYPE_EXPENSE
from core.expense.db import get_pending_transactions, update_transaction
from core.text import display_text, optional_text

st.title("待处理")

config = load_config()
expense_categories = config.get(TYPE_EXPENSE, {})
rows = get_pending_transactions()


def _render_category_form(record: dict) -> None:
    record_id = int(record["id"])
    st.divider()
    st.subheader("确认分类")
    st.caption(f"#{record_id} · {display_text(record.get('date'))}")

    with st.form(f"pending_form_{record_id}"):
        description = st.text_input(
            "描述", value=display_text(record.get("description"))
        )
        amount_col, date_col = st.columns(2)
        with amount_col:
            amount = st.number_input(
                "金额（元）",
                min_value=0.0,
                value=float(record.get("amount") or 0),
                format="%.2f",
            )
        with date_col:
            entry_date = st.date_input(
                "日期", value=date.fromisoformat(display_text(record.get("date")))
            )

        category_options = [*expense_categories, PENDING_CATEGORY]
        current_category = display_text(record.get("category")) or PENDING_CATEGORY
        category_index = (
            category_options.index(current_category)
            if current_category in category_options
            else len(category_options) - 1
        )
        category = st.selectbox("主类别", category_options, index=category_index)
        if category == PENDING_CATEGORY:
            subcategory = PENDING_CATEGORY
            st.caption("保留为待分类后，它会继续留在此列表。")
        else:
            options = expense_categories.get(category) or []
            current_subcategory = display_text(record.get("subcategory"))
            if options:
                subcategory = st.selectbox(
                    "子类别",
                    options,
                    index=(
                        options.index(current_subcategory)
                        if current_subcategory in options
                        else 0
                    ),
                )
            else:
                subcategory = None

        notes = st.text_area(
            "备注", value=display_text(record.get("notes")), height=68
        )
        submitted = st.form_submit_button("保存分类", type="primary")

    if submitted:
        update_transaction(
            record_id,
            description=description.strip(),
            amount=amount,
            date=entry_date.isoformat(),
            category=category,
            subcategory=subcategory,
            notes=optional_text(notes),
            confidence=1.0 if category != PENDING_CATEGORY else record.get("confidence"),
        )
        st.rerun()

if not rows:
    st.info("暂无待处理支出。")
    st.stop()

st.caption("处理待分类、缺失分类或低置信度的支出。")
df = pd.DataFrame(rows)
display_df = df[
    ["id", "date", "description", "amount", "category", "subcategory", "confidence"]
].copy()
display_df["amount"] = display_df["amount"].map(lambda value: f"¥{float(value or 0):.2f}")
display_df["confidence"] = display_df["confidence"].map(
    lambda value: "" if pd.isna(value) else f"{float(value):.0%}"
)
for column in ("category", "subcategory"):
    display_df[column] = display_df[column].map(display_text)

event = st.dataframe(
    display_df,
    hide_index=True,
    width="stretch",
    selection_mode="single-row",
    on_select="rerun",
    column_config={
        "id": st.column_config.NumberColumn("ID", width="small"),
        "date": st.column_config.TextColumn("日期", width="small"),
        "description": st.column_config.TextColumn("描述", width="large"),
        "amount": st.column_config.TextColumn("金额", width="small"),
        "category": st.column_config.TextColumn("主类别", width="medium"),
        "subcategory": st.column_config.TextColumn("子类别", width="medium"),
        "confidence": st.column_config.TextColumn("置信度", width="small"),
    },
)

if event.selection.rows:
    selected_record = df.iloc[event.selection.rows[0]].to_dict()
    _render_category_form(selected_record)
