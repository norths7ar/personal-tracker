from datetime import date

import pandas as pd
import streamlit as st

from core.batch.extractor import BatchExtractor
from core.config import config_version, load_config
from core.constants import (
    BATCH_RECORD_TYPES,
    DEFAULT_MEAL_TYPES,
    PENDING_CATEGORY,
    TRANSACTION_TYPES,
    TYPE_EXPENSE,
    TYPE_MEAL,
)
from core.diet.db import add_meal
from core.expense.db import add_transaction
from core.text import display_text, optional_text

st.title("批量记录")


@st.cache_resource
def get_batch_extractor(version: int):
    return BatchExtractor(load_config())


def _all_categories(config: dict) -> list[str]:
    values = []
    for section in TRANSACTION_TYPES:
        values.extend(config.get(section, {}).keys())
    values.append(PENDING_CATEGORY)
    return [""] + sorted(set(values))


def _validate_category_pair(
    config: dict,
    record_type: str,
    category: str,
    subcategory: str,
) -> str | None:
    if record_type == TYPE_EXPENSE and category == PENDING_CATEGORY:
        return (
            None
            if subcategory in {"", PENDING_CATEGORY}
            else f"{PENDING_CATEGORY} 必须搭配 {PENDING_CATEGORY}"
        )

    categories = config.get(record_type, {})
    if not category:
        return None
    if category not in categories:
        return f"{record_type}分类不存在：{category}"

    subs = categories.get(category) or []
    if not subs:
        return None
    if subcategory not in subs:
        return f"{category} 的子类别不存在：{subcategory or '空'}"
    return None


def _food_list_to_text(foods: list[dict]) -> str:
    parts = []
    for food in foods or []:
        name = display_text(food.get("food_name")).strip()
        quantity = display_text(food.get("quantity")).strip()
        if not name:
            continue
        parts.append(f"{name}:{quantity}" if quantity else name)
    return "；".join(parts)


def _food_text_to_list(text: str) -> list[dict]:
    foods = []
    for part in display_text(text).replace("\n", "；").split("；"):
        part = part.strip()
        if not part:
            continue
        if ":" in part:
            name, quantity = part.split(":", 1)
        elif "：" in part:
            name, quantity = part.split("：", 1)
        else:
            name, quantity = part, ""
        name = name.strip()
        if name:
            foods.append({"food_name": name, "quantity": quantity.strip()})
    return foods


def _records_to_df(records: list[dict]) -> pd.DataFrame:
    rows = []
    for record in records:
        rows.append(
            {
                "include": record.get("include", True),
                "record_type": record.get("record_type") or "",
                "date": record.get("date") or date.today().isoformat(),
                "time": record.get("time") or "",
                "description": record.get("description") or "",
                "amount": record.get("amount"),
                "category": record.get("category") or "",
                "subcategory": record.get("subcategory") or "",
                "meal_type": record.get("meal_type") or "",
                "foods": _food_list_to_text(record.get("foods", [])),
                "notes": display_text(record.get("notes")),
                "confidence": record.get("confidence", 0.0),
                "reasoning": record.get("reasoning") or "",
            }
        )
    return pd.DataFrame(rows)


def _validate_row(row: pd.Series, idx: int, config: dict) -> str | None:
    record_type = display_text(row.get("record_type")).strip()
    if record_type not in BATCH_RECORD_TYPES:
        return f"第 {idx + 1} 行类型无效"
    row_date = display_text(row.get("date")).strip()
    if not row_date:
        return f"第 {idx + 1} 行缺少日期"
    try:
        date.fromisoformat(row_date)
    except ValueError:
        return f"第 {idx + 1} 行日期必须是 YYYY-MM-DD"
    if not display_text(row.get("description")).strip():
        return f"第 {idx + 1} 行缺少描述"

    if record_type == TYPE_MEAL:
        if not display_text(row.get("meal_type")).strip():
            return f"第 {idx + 1} 行缺少餐顿类型"
        if not _food_text_to_list(row.get("foods")):
            return f"第 {idx + 1} 行缺少食物清单"
    else:
        try:
            amount = float(row.get("amount"))
        except (TypeError, ValueError):
            return f"第 {idx + 1} 行金额无效"
        if amount <= 0:
            return f"第 {idx + 1} 行金额必须大于 0"
        category = display_text(row.get("category")).strip()
        subcategory = display_text(row.get("subcategory")).strip()
        category_error = _validate_category_pair(
            config, record_type, category, subcategory
        )
        if category_error:
            return f"第 {idx + 1} 行{category_error}"
    return None


def _save_rows(df: pd.DataFrame, config: dict) -> tuple[int, list[str]]:
    saved = 0
    errors = []
    for idx, row in df.iterrows():
        if not bool(row.get("include")):
            continue
        error = _validate_row(row, idx, config)
        if error:
            errors.append(error)
            continue

        record_type = display_text(row["record_type"]).strip()
        try:
            if record_type == TYPE_MEAL:
                add_meal(
                    date=display_text(row["date"]).strip(),
                    time=optional_text(row.get("time")),
                    meal_type=display_text(row["meal_type"]).strip(),
                    description=display_text(row["description"]).strip(),
                    notes=optional_text(row.get("notes")),
                    confidence=float(row.get("confidence") or 0),
                    foods=_food_text_to_list(row.get("foods")),
                )
            else:
                category = optional_text(row.get("category"))
                subcategory = optional_text(row.get("subcategory"))
                if record_type == TYPE_EXPENSE and category == PENDING_CATEGORY:
                    subcategory = PENDING_CATEGORY
                add_transaction(
                    record_type,
                    display_text(row["description"]).strip(),
                    float(row["amount"]),
                    display_text(row["date"]).strip(),
                    category=category,
                    subcategory=subcategory,
                    notes=optional_text(row.get("notes")),
                    confidence=float(row.get("confidence") or 0),
                )
            saved += 1
        except Exception as e:
            errors.append(f"第 {idx + 1} 行写入失败：{e}")
    return saved, errors


def _render_diagnostics(diagnostics: dict):
    if not diagnostics:
        return
    with st.expander("解析诊断"):
        st.caption(
            f"事件拆分返回 {diagnostics.get('raw_count', 0)} 条；"
            f"保留 {diagnostics.get('kept_count', 0)} 条；"
            f"过滤 {len(diagnostics.get('rejected_records', []))} 条。"
        )
        if diagnostics.get("reasoning"):
            st.caption(f"整体说明：{diagnostics['reasoning']}")
        if diagnostics.get("rejected_records"):
            st.json(diagnostics["rejected_records"])


for key, default in [
    ("batch_records", None),
    ("batch_diagnostics", None),
    ("batch_source_text", ""),
    ("batch_flash", None),
]:
    if key not in st.session_state:
        st.session_state[key] = default

if st.session_state.batch_flash:
    st.success(st.session_state.batch_flash)
    st.session_state.batch_flash = None

config = load_config()
meal_types = config.get("diet", {}).get(
    "meal_types", list(DEFAULT_MEAL_TYPES)
)

with st.form("batch_parse_form"):
    default_date = st.date_input("默认日期", value=date.today())
    text = st.text_area(
        "批量描述",
        value=st.session_state.batch_source_text,
        height=160,
        placeholder="例：今天早餐豆浆包子，中午麦当劳 35，晚上超市买菜 86，打车 24",
    )
    submitted = st.form_submit_button("解析", type="primary", width="stretch")

if submitted:
    if not text.strip():
        st.error("请填写批量描述")
        st.stop()
    with st.spinner("正在拆分记录..."):
        result = get_batch_extractor(config_version()).extract(
            text.strip(), default_date=default_date.isoformat()
        )
    if result["status"] == "error":
        st.error(f"解析失败：{result['reasoning']}")
        st.stop()
    if not result["records"]:
        diagnostics = {
            "raw_count": len(result.get("raw_records", [])),
            "kept_count": 0,
            "rejected_records": result.get("rejected_records", []),
            "reasoning": result.get("reasoning", ""),
        }
        st.warning("没有解析出可保存的记录。")
        _render_diagnostics(diagnostics)
        st.stop()
    st.session_state.batch_source_text = text.strip()
    st.session_state.batch_records = result["records"]
    st.session_state.batch_diagnostics = {
        "raw_count": len(result.get("raw_records", [])),
        "kept_count": len(result["records"]),
        "rejected_records": result.get("rejected_records", []),
        "reasoning": result.get("reasoning", ""),
    }
    st.rerun()

if not st.session_state.batch_records:
    st.info("输入一段自然语言后，系统会拆分为开销、收入、迁移和饮食记录。")
    st.stop()

st.subheader("确认记录")
st.caption("取消勾选可跳过该行。食物清单格式：食物:份量；食物。")

diagnostics = st.session_state.get("batch_diagnostics") or {}
_render_diagnostics(diagnostics)

df = _records_to_df(st.session_state.batch_records)
edited_df = st.data_editor(
    df,
    hide_index=True,
    num_rows="dynamic",
    width="stretch",
    column_order=[
        "include",
        "record_type",
        "date",
        "time",
        "description",
        "amount",
        "category",
        "subcategory",
        "meal_type",
        "foods",
        "notes",
        "confidence",
        "reasoning",
    ],
    column_config={
        "include": st.column_config.CheckboxColumn("保存"),
        "record_type": st.column_config.SelectboxColumn(
            "类型", options=list(BATCH_RECORD_TYPES), required=True
        ),
        "date": st.column_config.TextColumn("日期", required=True),
        "time": st.column_config.TextColumn("时间"),
        "description": st.column_config.TextColumn("描述", required=True),
        "amount": st.column_config.NumberColumn("金额", format="%.2f"),
        "category": st.column_config.SelectboxColumn(
            "主类别", options=_all_categories(config)
        ),
        "subcategory": st.column_config.TextColumn("子类别"),
        "meal_type": st.column_config.SelectboxColumn(
            "餐顿", options=[""] + meal_types
        ),
        "foods": st.column_config.TextColumn("食物"),
        "notes": st.column_config.TextColumn("备注"),
        "confidence": st.column_config.NumberColumn(
            "置信度", min_value=0.0, max_value=1.0, format="%.2f"
        ),
        "reasoning": st.column_config.TextColumn("理由"),
    },
)

c1, c2 = st.columns(2)
with c1:
    if st.button("全部保存", type="primary", width="stretch"):
        # Validate all included rows first so no rows are lost on error.
        val_errors = []
        for idx, row in edited_df.iterrows():
            if not bool(row.get("include")):
                continue
            err = _validate_row(row, idx, config)
            if err:
                val_errors.append(err)
        if val_errors:
            st.error("；".join(val_errors))
        else:
            saved, db_errors = _save_rows(edited_df, config)
            if db_errors:
                st.error("；".join(db_errors))
                if saved:
                    st.warning(
                        f"已部分写入 {saved} 条，失败行请修改后重试（注意勾选情况避免重复提交）"
                    )
            elif saved:
                st.session_state.batch_records = None
                st.session_state.batch_diagnostics = None
                st.session_state.batch_source_text = ""
                st.session_state.batch_flash = f"已保存 {saved} 条记录。"
                st.rerun()
with c2:
    if st.button("清空", width="stretch"):
        st.session_state.batch_records = None
        st.session_state.batch_diagnostics = None
        st.session_state.batch_source_text = ""
        st.rerun()
