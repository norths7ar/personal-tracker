import pandas as pd
import streamlit as st
from datetime import date, datetime

from core.config import load_config
from core.db import init_db
from core.diet.db import add_meal, get_meals
from core.diet.extractor import DietExtractor

init_db()

st.title("🍽️ 饮食记录")

# ── session state ───────────────────────────────────────────────────────────
for key, default in [("pending", None), ("flash", None),
                      ("processing", False), ("processing_form", None)]:
    if key not in st.session_state:
        st.session_state[key] = default

if st.session_state.flash:
    st.success(st.session_state.flash)
    st.session_state.flash = None

# ── 侧边栏：今日饮食摘要 ────────────────────────────────────────────────────
with st.sidebar:
    st.subheader("今日饮食")
    today_str = date.today().strftime("%Y-%m-%d")
    try:
        meals = get_meals(start_date=today_str, end_date=today_str)
        if meals:
            for meal in meals:
                time_tag = f" {meal['time']}" if meal.get("time") else ""
                st.caption(f"**{meal['meal_type']}**{time_tag}")
                foods_str = "、".join(
                    f"{f['food_name']}{'×'+f['quantity'] if f.get('quantity') else ''}"
                    for f in meal["foods"]
                )
                st.caption(f"　{foods_str}")
            st.caption(f"今日已记录 {len(meals)} 餐")
        else:
            st.caption("今日暂无记录")
    except Exception as e:
        st.caption(f"加载失败：{e}")


# ── 工具函数 ────────────────────────────────────────────────────────────────
@st.cache_resource
def get_extractor():
    return DietExtractor(load_config())


def save_and_done(form, meal_type, foods, confidence=None):
    meal_id = add_meal(
        date=form["date"],
        time=form["time"],
        meal_type=meal_type,
        description=form["description"],
        notes=form["notes"],
        confidence=confidence,
        foods=foods,
    )
    foods_str = "、".join(f["food_name"] for f in foods)
    st.session_state.pending = None
    st.session_state.flash = f"✅ 已保存（ID {meal_id}）：{meal_type} / {foods_str}"
    st.rerun()


def cancel():
    st.session_state.pending = None
    st.rerun()


def render_confirm_form(form, result, meal_types):
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

    default_meal = result.get("meal_type", meal_types[-1])
    default_idx  = meal_types.index(default_meal) if default_meal in meal_types else len(meal_types) - 1
    meal_type = st.selectbox("餐顿类型", meal_types, index=default_idx)

    st.caption("食物清单（可编辑、增删行）")
    foods_df = pd.DataFrame(result.get("foods", [{"food_name": "", "quantity": ""}]))
    edited_df = st.data_editor(
        foods_df,
        num_rows="dynamic",
        column_config={
            "food_name": st.column_config.TextColumn("食物名称", required=True),
            "quantity":  st.column_config.TextColumn("份量"),
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
                {"food_name": str(row["food_name"]), "quantity": str(row.get("quantity") or "")}
                for _, row in edited_df.iterrows()
                if pd.notna(row["food_name"]) and str(row["food_name"]).strip()
            ]
            if not foods:
                st.error("请至少填写一种食物")
                return
            form["notes"] = notes
            save_and_done(form, meal_type, foods, result.get("confidence"))
    with c2:
        if st.button("取消", width="stretch"):
            cancel()


# ── LLM 处理 ────────────────────────────────────────────────────────────────
if st.session_state.processing:
    form = st.session_state.processing_form
    with st.spinner("AI正在分析饮食描述..."):
        result = get_extractor().extract(form["description"])
    if result["status"] == "confirmed":
        foods_str = "、".join(f["food_name"] for f in result["foods"])
        meal_id = add_meal(
            date=form["date"], time=form["time"],
            meal_type=result["meal_type"], description=form["description"],
            notes=form["notes"], confidence=result["confidence"],
            foods=result["foods"],
        )
        st.session_state.flash = (
            f"✅ 已保存（ID {meal_id}）：{result['meal_type']} / {foods_str}"
            f"（{result['confidence']:.0%}｜{result['reasoning']}）"
        )
        st.session_state.processing = False
    else:
        st.session_state.pending = {"form": form, "result": result}
        st.session_state.processing = False
    st.rerun()

# ── 确认界面 ────────────────────────────────────────────────────────────────
if st.session_state.pending:
    form   = st.session_state.pending["form"]
    result = st.session_state.pending["result"]
    st.caption(f"**{form['date']}** {form['time'] or ''}　描述：{form['description']}")
    st.divider()
    render_confirm_form(form, result, get_extractor().meal_types)
    st.stop()


# ── 主输入表单 ──────────────────────────────────────────────────────────────
with st.form("diet_form", clear_on_submit=True):
    col1, col2 = st.columns(2)
    with col1:
        entry_date = st.date_input("日期", value=date.today())
    with col2:
        time_str = st.text_input(
            "时间（可选）", placeholder="如：12:30",
            help="24小时制，如 08:00、12:30、18:45",
        )

    description = st.text_area(
        "饮食描述",
        placeholder=(
            "例：早上喝了一杯豆浆，两个包子\n"
            "或：中午吃了麦当劳巨无霸套餐\n"
            "或：晚上在家吃了米饭、青菜和红烧肉"
        ),
        height=100,
        help="用自然语言描述你吃了什么，AI会自动提取餐顿和每种食物",
    )
    notes    = st.text_area("备注（可选）", height=68, placeholder="可记录心情、地点、特殊说明等")
    submitted = st.form_submit_button("提交", type="primary", width="stretch")

if submitted:
    if not description.strip():
        st.error("请填写饮食描述")
        st.stop()

    time_value = None
    if time_str.strip():
        try:
            datetime.strptime(time_str.strip(), "%H:%M")
            time_value = time_str.strip()
        except ValueError:
            st.warning(f"时间格式可能不正确，将保存为文本：{time_str}")
            time_value = time_str.strip()

    form_data = {
        "date":        entry_date.strftime("%Y-%m-%d"),
        "time":        time_value,
        "description": description.strip(),
        "notes":       notes.strip() or None,
    }

    st.session_state.processing_form = form_data
    st.session_state.processing = True
    st.rerun()
