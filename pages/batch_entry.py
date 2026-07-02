from datetime import date

import pandas as pd
import streamlit as st

from core.batch.extractor import BatchExtractor
from core.config import config_version, load_config
from core.db import init_db
from core.diet.db import add_meal
from core.expense.db import add_transaction

init_db()

st.title("批量记录")


@st.cache_resource
def get_batch_extractor(_version: int):
    return BatchExtractor(load_config())


def _all_categories(config: dict) -> list[str]:
    values = []
    for section in ("支出", "收入", "迁移"):
        values.extend(config.get(section, {}).keys())
    return [""] + sorted(set(values))


def _food_list_to_text(foods: list[dict]) -> str:
    parts = []
    for food in foods or []:
        name = str(food.get("food_name") or "").strip()
        quantity = str(food.get("quantity") or "").strip()
        if not name:
            continue
        parts.append(f"{name}:{quantity}" if quantity else name)
    return "；".join(parts)


def _food_text_to_list(text: str) -> list[dict]:
    foods = []
    for part in str(text or "").replace("\n", "；").split("；"):
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
        rows.append({
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
            "notes": record.get("notes") or "",
            "confidence": record.get("confidence", 0.0),
            "reasoning": record.get("reasoning") or "",
        })
    return pd.DataFrame(rows)


def _validate_row(row: pd.Series, idx: int) -> str | None:
    record_type = str(row.get("record_type") or "").strip()
    if record_type not in {"支出", "收入", "迁移", "饮食"}:
        return f"第 {idx + 1} 行类型无效"
    row_date = str(row.get("date") or "").strip()
    if not row_date:
        return f"第 {idx + 1} 行缺少日期"
    try:
        date.fromisoformat(row_date)
    except ValueError:
        return f"第 {idx + 1} 行日期必须是 YYYY-MM-DD"
    if not str(row.get("description") or "").strip():
        return f"第 {idx + 1} 行缺少描述"

    if record_type == "饮食":
        if not str(row.get("meal_type") or "").strip():
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
    return None


def _save_rows(df: pd.DataFrame) -> tuple[int, list[str]]:
    saved = 0
    errors = []
    for idx, row in df.iterrows():
        if not bool(row.get("include")):
            continue
        error = _validate_row(row, idx)
        if error:
            errors.append(error)
            continue

        record_type = str(row["record_type"]).strip()
        if record_type == "饮食":
            add_meal(
                date=str(row["date"]).strip(),
                time=str(row.get("time") or "").strip() or None,
                meal_type=str(row["meal_type"]).strip(),
                description=str(row["description"]).strip(),
                notes=str(row.get("notes") or "").strip() or None,
                confidence=float(row.get("confidence") or 0),
                foods=_food_text_to_list(row.get("foods")),
            )
        else:
            add_transaction(
                record_type,
                str(row["description"]).strip(),
                float(row["amount"]),
                str(row["date"]).strip(),
                category=str(row.get("category") or "").strip() or None,
                subcategory=str(row.get("subcategory") or "").strip() or None,
                notes=str(row.get("notes") or "").strip() or None,
                confidence=float(row.get("confidence") or 0),
            )
        saved += 1
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
meal_types = config.get("diet", {}).get("meal_types", ["早餐", "午餐", "晚餐", "零食", "其他"])

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
            "类型", options=["支出", "收入", "迁移", "饮食"], required=True
        ),
        "date": st.column_config.TextColumn("日期", required=True),
        "time": st.column_config.TextColumn("时间"),
        "description": st.column_config.TextColumn("描述", required=True),
        "amount": st.column_config.NumberColumn("金额", format="%.2f"),
        "category": st.column_config.SelectboxColumn("主类别", options=_all_categories(config)),
        "subcategory": st.column_config.TextColumn("子类别"),
        "meal_type": st.column_config.SelectboxColumn("餐顿", options=[""] + meal_types),
        "foods": st.column_config.TextColumn("食物"),
        "notes": st.column_config.TextColumn("备注"),
        "confidence": st.column_config.NumberColumn("置信度", min_value=0.0, max_value=1.0, format="%.2f"),
        "reasoning": st.column_config.TextColumn("理由"),
    },
)

c1, c2 = st.columns(2)
with c1:
    if st.button("全部保存", type="primary", width="stretch"):
        saved, errors = _save_rows(edited_df)
        if errors:
            st.error("；".join(errors))
        if saved:
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
