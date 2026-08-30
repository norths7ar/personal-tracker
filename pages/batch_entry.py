from datetime import date

import pandas as pd
import streamlit as st

from core.auth import require_login
from core.batch.db import save_batch
from core.batch.extractor import BatchExtractor
from core.batch.state import (
    ensure_batch_state,
    mark_batch_error,
    mark_batch_saving,
    reset_batch_draft,
    start_batch_review,
)
from core.config import config_version, load_config
from core.constants import (
    BATCH_RECORD_TYPES,
    PENDING_CATEGORY,
    TRANSACTION_TYPES,
    TYPE_EXPENSE,
    TYPE_INCOME,
    TYPE_MEAL,
    TYPE_TRANSFER,
)
from core.diet.db import add_meal, get_meals
from core.diet.extractor import DietExtractor
from core.diet.ingredients import ingredients_to_text, normalize_ingredients
from core.diet.meal_time import normalize_meal_time, resolve_meal_type
from core.expense.classifier import Classifier
from core.expense.db import add_transaction, get_transactions
from core.reminders import get_home_reminders
from core.text import display_text, optional_text

require_login(show_logout=False)

st.title("记录")


# ── 缓存资源 ──────────────────────────────────────────────────────────────────


@st.cache_resource
def get_batch_extractor(version: int):
    return BatchExtractor(load_config())


@st.cache_resource
def get_classifier(version: int):
    return Classifier(load_config())


@st.cache_resource
def get_diet_extractor(version: int):
    return DietExtractor(load_config())


# ── session state ─────────────────────────────────────────────────────────────

ensure_batch_state(st.session_state)

for key, default in [
    ("batch_flash", None),
    ("expense_pending", None),
    ("expense_flash", None),
    ("expense_processing", False),
    ("expense_processing_form", None),
    ("diet_pending", None),
    ("diet_flash", None),
    ("diet_processing", False),
    ("diet_processing_form", None),
]:
    if key not in st.session_state:
        st.session_state[key] = default


def _due_label(days_until_due: int) -> str:
    if days_until_due < 0:
        return f"逾期 {-days_until_due} 天"
    if days_until_due == 0:
        return "今天"
    return f"{days_until_due} 天后"


def _render_home_reminders() -> None:
    reminders = get_home_reminders()
    items = reminders["items"]
    pending_count = reminders["pending_count"]
    if not items and not pending_count:
        return

    with st.container(border=True):
        st.markdown("**待办提醒**")
        for item in items[:4]:
            amount = f" · ¥{item['amount']:,.2f}" if item["amount"] else ""
            due_label = _due_label(item["days_until_due"])
            st.markdown(f"- {item['description']} · {due_label}{amount}")
        if len(items) > 4:
            st.caption(f"另有 {len(items) - 4} 项付款提醒")
        if pending_count:
            st.markdown(f"- 待分类支出 · {pending_count} 笔")

        action_columns = st.columns([1, 1, 4])
        if items:
            action_columns[0].page_link("pages/subscriptions.py", label="处理跨期费用")
        if pending_count:
            action_columns[1].page_link("pages/expense_pending.py", label="处理待分类")


_render_home_reminders()


# ── 侧边栏：今日概览 ──────────────────────────────────────────────────────────

with st.sidebar:
    st.subheader("今日")
    today_str = date.today().strftime("%Y-%m-%d")
    try:
        today_rows = get_transactions(
            start_date=today_str, end_date=today_str, limit=50
        )
        expense_total = sum(
            r["amount"] for r in today_rows if r["type"] == TYPE_EXPENSE
        )
        if expense_total:
            st.caption(f"支出合计 ¥{expense_total:.2f}")
        else:
            st.caption("今日暂无开销记录")
    except Exception:
        pass
    try:
        today_meals = get_meals(start_date=today_str, end_date=today_str)
        if today_meals:
            for meal in today_meals:
                foods_str = "、".join(f["food_name"] for f in meal["foods"])
                label = display_text(meal.get("meal_type"))
                prefix = meal.get("time") or "--:--"
                if label:
                    prefix += f" · {label}"
                st.caption(f"**{prefix}** {foods_str}")
        else:
            st.caption("今日暂无饮食记录")
    except Exception:
        pass


# ── 批量录入辅助函数 ──────────────────────────────────────────────────────────


def _all_categories(config: dict) -> list[str]:
    values = []
    for section in TRANSACTION_TYPES:
        values.extend(config.get(section, {}).keys())
    values.append(PENDING_CATEGORY)
    return [""] + sorted(set(values))


def _validate_category_pair(config, record_type, category, subcategory):
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


def _food_list_to_text(foods):
    parts = []
    for food in foods or []:
        name = display_text(food.get("food_name")).strip()
        quantity = display_text(food.get("quantity")).strip()
        ingredients = ingredients_to_text(food.get("ingredients"))
        if not name:
            continue
        value = f"{name}:{quantity}" if quantity else name
        if ingredients:
            value += f"【{ingredients}】"
        parts.append(value)
    return "；".join(parts)


def _food_text_to_list(text):
    foods = []
    for part in display_text(text).replace("\n", "；").split("；"):
        part = part.strip()
        if not part:
            continue
        ingredients = []
        if part.endswith("】") and "【" in part:
            part, ingredient_text = part.rsplit("【", 1)
            ingredients = normalize_ingredients(ingredient_text[:-1])
        if ":" in part:
            name, quantity = part.split(":", 1)
        elif "：" in part:
            name, quantity = part.split("：", 1)
        else:
            name, quantity = part, ""
        name = name.strip()
        if name:
            foods.append(
                {
                    "food_name": name,
                    "quantity": quantity.strip(),
                    "ingredients": ingredients,
                }
            )
    return foods


def _records_to_df(records):
    return pd.DataFrame(
        [
            {
                "include": r.get("include", True),
                "record_type": r.get("record_type") or "",
                "date": r.get("date") or date.today().isoformat(),
                "time": r.get("time") or "",
                "description": r.get("description") or "",
                "amount": r.get("amount"),
                "category": r.get("category") or "",
                "subcategory": r.get("subcategory") or "",
                "meal_type": r.get("meal_type") or "",
                "foods": _food_list_to_text(r.get("foods", [])),
                "notes": display_text(r.get("notes")),
                "confidence": r.get("confidence", 0.0),
                "reasoning": r.get("reasoning") or "",
            }
            for r in records
        ]
    )


def _validate_row(row, idx, config):
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
        if normalize_meal_time(row.get("time")) is None:
            return f"第 {idx + 1} 行用餐时间必须是 HH:MM"
        if not _food_text_to_list(row.get("foods")):
            return f"第 {idx + 1} 行缺少食物清单"
    else:
        try:
            amount = float(row.get("amount"))
        except (TypeError, ValueError):
            return f"第 {idx + 1} 行金额无效"
        if amount <= 0:
            return f"第 {idx + 1} 行金额必须大于 0"
        err = _validate_category_pair(
            config,
            record_type,
            display_text(row.get("category")).strip(),
            display_text(row.get("subcategory")).strip(),
        )
        if err:
            return f"第 {idx + 1} 行{err}"
    return None


def _save_rows(df, config, submission_id: str):
    records = []
    for idx, row in df.iterrows():
        if not bool(row.get("include")):
            continue
        error = _validate_row(row, idx, config)
        if error:
            raise ValueError(error)
        record_type = display_text(row["record_type"]).strip()
        record = {
            "record_type": record_type,
            "date": display_text(row["date"]).strip(),
            "description": display_text(row["description"]).strip(),
            "notes": optional_text(row.get("notes")),
            "confidence": float(row.get("confidence") or 0),
        }
        if record_type == TYPE_MEAL:
            meal_time = normalize_meal_time(row.get("time"))
            record.update(
                {
                    "time": meal_time,
                    "meal_type": resolve_meal_type(row.get("meal_type"), meal_time),
                    "foods": _food_text_to_list(row.get("foods")),
                }
            )
        else:
            category = optional_text(row.get("category"))
            subcategory = optional_text(row.get("subcategory"))
            if record_type == TYPE_EXPENSE and category == PENDING_CATEGORY:
                subcategory = PENDING_CATEGORY
            record.update(
                {
                    "amount": float(row["amount"]),
                    "category": category,
                    "subcategory": subcategory,
                    "reviewed": True,
                }
            )
        records.append(record)
    return save_batch(submission_id, records)


def _render_diagnostics(diagnostics):
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


# ── Tab 渲染函数 ──────────────────────────────────────────────────────────────


def render_batch_tab():
    if st.session_state.batch_flash:
        st.success(st.session_state.batch_flash)
        st.session_state.batch_flash = None

    config = load_config()

    with st.form("batch_parse_form"):
        default_date = st.date_input("默认日期", value=date.today())
        text = st.text_area(
            "批量描述",
            value=st.session_state.batch_source_text,
            height=160,
            placeholder="例：今天早餐豆浆包子，中午麦当劳 35，晚上超市买菜 86，打车 24",
        )
        submitted = st.form_submit_button("解析", type="primary")

    if submitted:
        if not text.strip():
            st.error("请填写批量描述")
            return
        with st.spinner("正在拆分记录..."):
            result = get_batch_extractor(config_version()).extract(
                text.strip(), default_date=default_date.isoformat()
            )
        if result["status"] == "error":
            st.error(f"解析失败：{result['reasoning']}")
            return
        if not result["records"]:
            st.warning("没有解析出可保存的记录。")
            _render_diagnostics(
                {
                    "raw_count": len(result.get("raw_records", [])),
                    "kept_count": 0,
                    "rejected_records": result.get("rejected_records", []),
                    "reasoning": result.get("reasoning", ""),
                }
            )
            return
        start_batch_review(
            st.session_state,
            source_text=text.strip(),
            records=result["records"],
            diagnostics={
                "raw_count": len(result.get("raw_records", [])),
                "kept_count": len(result["records"]),
                "rejected_records": result.get("rejected_records", []),
                "reasoning": result.get("reasoning", ""),
            },
        )
        st.rerun()

    if not st.session_state.batch_records:
        st.info("输入一段自然语言后，系统会拆分为开销、收入、迁移和饮食记录。")
        return

    st.subheader("确认记录")
    st.caption(
        "当前草稿会在页面切换后保留，保存或放弃后清除。"
        "取消勾选可跳过该行。食物清单格式：食物:份量；食物。"
    )
    if st.session_state.batch_status == "error" and st.session_state.batch_error:
        st.error(st.session_state.batch_error)
    _render_diagnostics(st.session_state.get("batch_diagnostics") or {})

    edited_df = st.data_editor(
        _records_to_df(st.session_state.batch_records),
        key=f"batch_editor_{st.session_state.batch_editor_version}",
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
            "time": st.column_config.TextColumn(
                "时间", help="饮食记录必填 HH:MM；财务记录可留空"
            ),
            "description": st.column_config.TextColumn("描述", required=True),
            "amount": st.column_config.NumberColumn("金额", format="%.2f"),
            "category": st.column_config.SelectboxColumn(
                "主类别", options=_all_categories(config)
            ),
            "subcategory": st.column_config.TextColumn("子类别"),
            "meal_type": st.column_config.TextColumn(
                "餐顿标签", help="可选，例如早餐、brunch、夜宵"
            ),
            "foods": st.column_config.TextColumn(
                "菜品与食材",
                help="格式：菜品:份量【食材1、食材2】；多个菜品用分号分隔",
            ),
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
                mark_batch_saving(st.session_state)
                try:
                    result = _save_rows(
                        edited_df,
                        config,
                        st.session_state.batch_submission_id,
                    )
                except Exception as exc:
                    message = f"保存失败，当前批次已保留，可重试：{exc}"
                    mark_batch_error(st.session_state, message)
                    st.error(message)
                else:
                    if result["duplicate"]:
                        st.session_state.batch_flash = (
                            "该批次已保存，重复提交已忽略"
                            f"（{result['saved_count']} 条）。"
                        )
                    else:
                        st.session_state.batch_flash = (
                            f"已保存 {result['saved_count']} 条记录。"
                        )
                    reset_batch_draft(st.session_state)
                    st.rerun()
    with c2:
        if st.button("放弃批次", width="stretch"):
            reset_batch_draft(st.session_state)
            st.rerun()


def render_expense_tab():
    if st.session_state.expense_flash:
        st.success(st.session_state.expense_flash)
        st.session_state.expense_flash = None

    def _save_and_done(
        form,
        category,
        subcategory,
        confidence=None,
        reviewed=False,
    ):
        record_id = add_transaction(
            form["type"],
            form["description"],
            form["amount"],
            form["date"],
            category=category,
            subcategory=subcategory,
            notes=form["notes"],
            confidence=confidence,
            reviewed=reviewed,
        )
        st.session_state.expense_pending = None
        st.session_state.expense_flash = (
            f"已保存（ID {record_id}）：{form['type']} / "
            f"{form['description']} / ¥{form['amount']:.2f}"
        )
        st.rerun()

    if st.session_state.expense_processing:
        form = st.session_state.expense_processing_form
        with st.spinner("分类中…"):
            result = get_classifier(config_version()).classify(form["description"])
        if result["status"] == "confirmed":
            record_id = add_transaction(
                form["type"],
                form["description"],
                form["amount"],
                form["date"],
                category=result["category"],
                subcategory=result["subcategory"],
                confidence=result["confidence"],
                notes=form["notes"],
            )
            st.session_state.expense_flash = (
                f"已保存（ID {record_id}）：{result['category']} / "
                f"{result['subcategory']}"
                f"（{result['confidence']:.0%}｜{result['reasoning']}）"
            )
            st.session_state.expense_processing = False
        else:
            st.session_state.expense_pending = {"form": form, "result": result}
            st.session_state.expense_processing = False
        st.rerun()
        return

    if st.session_state.expense_pending:
        form = st.session_state.expense_pending["form"]
        result = st.session_state.expense_pending["result"]
        st.caption(
            f"**{form['type']}** {form['description']} "
            f"¥{form['amount']:.2f} {form['date']}"
        )
        st.divider()

        config = load_config()
        if result is None:
            st.subheader("填写收入分类")
            income_cats = config.get(TYPE_INCOME, {})
            col1, col2 = st.columns(2)
            with col1:
                category = st.selectbox("主类别", list(income_cats.keys()) or ["其他"])
            with col2:
                subs = income_cats.get(category) or []
                subcategory = st.selectbox("子类别", subs) if subs else None
                if not subs:
                    st.caption("（无子类别）")
            c1, c2 = st.columns(2)
            with c1:
                if st.button("保存", type="primary", width="stretch"):
                    _save_and_done(form, category, subcategory)
            with c2:
                if st.button("取消", width="stretch"):
                    st.session_state.expense_pending = None
                    st.rerun()
        elif result["status"] in ("low_confidence", "new_category", "error"):
            cats = config.get(TYPE_EXPENSE, {})
            cat_keys = list(cats.keys())
            if result["status"] == "low_confidence":
                st.warning(f"置信度较低（{result['confidence']:.0%}），请确认分类")
            elif result["status"] == "new_category":
                st.warning(
                    f"LLM 建议了未知分类（{result['category']} / "
                    f"{result['subcategory']}），请从下方选择"
                )
            else:
                st.error(f"自动分类失败：{result['reasoning']}")
            if result.get("reasoning") and result["status"] != "error":
                st.caption(f"理由：{result['reasoning']}")
            suggested_cat = result.get("category", "")
            cat_idx = cat_keys.index(suggested_cat) if suggested_cat in cat_keys else 0
            col1, col2 = st.columns(2)
            with col1:
                category = st.selectbox("主类别", cat_keys, index=cat_idx)
            with col2:
                subs = cats.get(category) or []
                suggested_sub = result.get("subcategory", "")
                sub_idx = subs.index(suggested_sub) if suggested_sub in subs else 0
                if subs:
                    subcategory = st.selectbox("子类别", subs, index=sub_idx)
                else:
                    subcategory = category
                    st.caption("（无子类别）")
            c1, c2 = st.columns(2)
            with c1:
                if st.button("确认保存", type="primary", width="stretch"):
                    _save_and_done(
                        form,
                        category,
                        subcategory,
                        confidence=result.get("confidence"),
                        reviewed=True,
                    )
            with c2:
                if st.button("取消", width="stretch"):
                    st.session_state.expense_pending = None
                    st.rerun()
        return

    with st.form("entry_form", clear_on_submit=True):
        entry_type = st.radio("类型", list(TRANSACTION_TYPES), horizontal=True)
        description = st.text_input("描述", placeholder="例：中午麦当劳")
        col1, col2 = st.columns(2)
        with col1:
            amount = st.number_input(
                "金额（元）", min_value=0.0, value=0.0, step=0.1, format="%.2f"
            )
        with col2:
            entry_date = st.date_input("日期", value=date.today())
        notes = st.text_area("备注（可选）", height=68)
        submitted = st.form_submit_button("提交", type="primary", width="stretch")

    if submitted:
        if not description.strip():
            st.error("请填写描述")
            return
        if amount <= 0:
            st.error("金额须大于 0")
            return
        form_data = {
            "type": entry_type,
            "description": description.strip(),
            "amount": amount,
            "date": entry_date.strftime("%Y-%m-%d"),
            "notes": notes.strip() or None,
        }
        if entry_type == TYPE_TRANSFER:
            record_id = add_transaction(
                entry_type,
                description.strip(),
                amount,
                entry_date.strftime("%Y-%m-%d"),
                notes=notes.strip() or None,
            )
            st.session_state.expense_flash = f"迁移记录已保存（ID {record_id}）"
            st.rerun()
        elif entry_type == TYPE_INCOME:
            st.session_state.expense_pending = {"form": form_data, "result": None}
            st.rerun()
        else:
            st.session_state.expense_processing_form = form_data
            st.session_state.expense_processing = True
            st.rerun()


def render_diet_tab():
    if st.session_state.diet_flash:
        st.success(st.session_state.diet_flash)
        st.session_state.diet_flash = None

    extractor = get_diet_extractor(config_version())

    def _save_and_done(form, meal_type, foods, confidence=None):
        resolved_type = resolve_meal_type(meal_type, form["time"])
        meal_id = add_meal(
            date=form["date"],
            time=form["time"],
            meal_type=resolved_type,
            description=form["description"],
            notes=form["notes"],
            confidence=confidence,
            foods=foods,
        )
        foods_str = "、".join(f["food_name"] for f in foods)
        st.session_state.diet_pending = None
        label = f" · {resolved_type}" if resolved_type else ""
        st.session_state.diet_flash = (
            f"✅ 已保存（ID {meal_id}）：{form['time']}{label} / {foods_str}"
        )
        st.rerun()

    if st.session_state.diet_processing:
        form = st.session_state.diet_processing_form
        with st.spinner("AI正在分析饮食描述..."):
            result = extractor.extract(form["description"], form["time"])
        if result["status"] == "confirmed":
            foods_str = "、".join(f["food_name"] for f in result["foods"])
            meal_type = resolve_meal_type(result.get("meal_type"), form["time"])
            meal_id = add_meal(
                date=form["date"],
                time=form["time"],
                meal_type=meal_type,
                description=form["description"],
                notes=form["notes"],
                confidence=result["confidence"],
                foods=result["foods"],
            )
            label = f" · {meal_type}" if meal_type else ""
            st.session_state.diet_flash = (
                f"✅ 已保存（ID {meal_id}）：{form['time']}{label} / {foods_str}"
                f"（{result['confidence']:.0%}｜{result['reasoning']}）"
            )
            st.session_state.diet_processing = False
        else:
            st.session_state.diet_pending = {"form": form, "result": result}
            st.session_state.diet_processing = False
        st.rerun()
        return

    if st.session_state.diet_pending:
        form = st.session_state.diet_pending["form"]
        result = st.session_state.diet_pending["result"]
        st.caption(
            f"**{form['date']}** {form['time'] or ''}　描述：{form['description']}"
        )
        st.divider()

        status = result["status"]
        if status == "confirmed":
            st.success(f"✅ 提取完成（置信度 {result['confidence']:.0%}）")
        elif status == "low_confidence":
            st.warning(f"⚠️ 置信度较低（{result['confidence']:.0%}），请确认信息")
        else:
            st.error(f"❌ 提取失败：{result.get('reasoning', '')}")
            st.info("请手动填写以下信息：")

        if result.get("reasoning") and status != "error":
            st.caption(f"理由：{result['reasoning']}")

        suggested_type = resolve_meal_type(result.get("meal_type"), form["time"])
        meal_type = st.text_input(
            "餐顿标签（可选）",
            value=suggested_type or "",
            placeholder="例如早餐、brunch、夜宵",
        )

        st.caption("食物清单（可编辑、增删行）")
        foods_df = pd.DataFrame(
            [
                {
                    "food_name": food.get("food_name", ""),
                    "quantity": food.get("quantity", ""),
                    "ingredients": ingredients_to_text(food.get("ingredients")),
                }
                for food in result.get(
                    "foods",
                    [{"food_name": "", "quantity": "", "ingredients": []}],
                )
            ]
        )
        edited_df = st.data_editor(
            foods_df,
            num_rows="dynamic",
            column_config={
                "food_name": st.column_config.TextColumn("食物名称", required=True),
                "quantity": st.column_config.TextColumn("份量"),
                "ingredients": st.column_config.TextColumn(
                    "主要食材", help="使用顿号、逗号或分号分隔"
                ),
            },
            hide_index=True,
            width="stretch",
        )

        notes = st.text_area("备注（可选）", value=form.get("notes") or "", height=60)
        save_label = "保存" if status in ("confirmed", "error") else "确认保存"
        c1, c2 = st.columns(2)
        with c1:
            if st.button(save_label, type="primary", width="stretch"):
                foods = [
                    {
                        "food_name": str(row["food_name"]),
                        "quantity": display_text(row.get("quantity")),
                        "ingredients": normalize_ingredients(row.get("ingredients")),
                    }
                    for _, row in edited_df.iterrows()
                    if pd.notna(row["food_name"]) and str(row["food_name"]).strip()
                ]
                if not foods:
                    st.error("请至少填写一种食物")
                else:
                    form["notes"] = notes
                    _save_and_done(form, meal_type, foods, result.get("confidence"))
        with c2:
            if st.button("取消", width="stretch"):
                st.session_state.diet_pending = None
                st.rerun()
        return

    with st.form("diet_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            entry_date = st.date_input("日期", value=date.today())
        with col2:
            time_str = st.text_input(
                "用餐时间",
                placeholder="如：12:30",
                help="必填，使用 24 小时制 HH:MM；大概时间即可",
            )
        description = st.text_area(
            "饮食描述",
            placeholder="例：早上喝了一杯豆浆，两个包子\n或：中午吃了麦当劳巨无霸套餐",
            height=100,
            help="用自然语言描述你吃了什么，AI会提取食物并给出可选餐顿标签",
        )
        notes = st.text_area(
            "备注（可选）", height=68, placeholder="可记录心情、地点、特殊说明等"
        )
        submitted = st.form_submit_button("提交", type="primary", width="stretch")

    if submitted:
        if not description.strip():
            st.error("请填写饮食描述")
            return
        time_value = normalize_meal_time(time_str)
        if time_value is None:
            st.error("请填写有效的用餐时间，格式为 HH:MM")
            return
        st.session_state.diet_processing_form = {
            "date": entry_date.strftime("%Y-%m-%d"),
            "time": time_value,
            "description": description.strip(),
            "notes": notes.strip() or None,
        }
        st.session_state.diet_processing = True
        st.rerun()


# ── 主体 ──────────────────────────────────────────────────────────────────────

tab_batch, tab_expense, tab_diet = st.tabs(["批量录入", "开销", "饮食"])

with tab_batch:
    render_batch_tab()

with tab_expense:
    render_expense_tab()

with tab_diet:
    render_diet_tab()
