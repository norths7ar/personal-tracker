import pandas as pd
import streamlit as st
from datetime import date, datetime

from core.config import load_config
from core.db import init_db
from core.diet.db import add_diet_entry, get_diet_entries
from core.diet.extractor import DietExtractor

init_db()

st.title("🍽️ 饮食记录")

# ── session state 初始化 ────────────────────────────────────────────────────
for key, default in [("pending", None), ("flash", None)]:
    if key not in st.session_state:
        st.session_state[key] = default

# ── flash 消息 ──────────────────────────────────────────────────────────────
if st.session_state.flash:
    st.success(st.session_state.flash)
    st.session_state.flash = None

# ── 侧边栏：今日饮食摘要 ────────────────────────────────────────────────────
with st.sidebar:
    st.subheader("今日饮食")
    today_str = date.today().strftime("%Y-%m-%d")
    try:
        rows = get_diet_entries(start_date=today_str, end_date=today_str, limit=20)
        if rows:
            df = pd.DataFrame(rows)[["time", "meal_type", "food_name", "quantity"]].fillna("")
            st.dataframe(df, hide_index=True, use_container_width=True)
            meal_counts = df["meal_type"].value_counts()
            st.caption(f"今日已记录 {len(rows)} 条饮食")
            for meal_type, count in meal_counts.items():
                st.caption(f"- {meal_type}: {count} 次")
        else:
            st.caption("今日暂无记录")
    except Exception as e:
        st.caption(f"加载失败：{e}")


# ── 工具函数 ────────────────────────────────────────────────────────────────
@st.cache_resource
def get_extractor():
    return DietExtractor(load_config())


def save_and_done(form, meal_type, food_name, quantity, confidence=None):
    record_id = add_diet_entry(
        date=form["date"],
        time=form["time"],
        description=form["description"],
        meal_type=meal_type,
        food_name=food_name,
        quantity=quantity,
        notes=form["notes"],
        confidence=confidence,
    )
    st.session_state.pending = None
    st.session_state.flash = f"✅ 已保存饮食记录（ID {record_id}）：{meal_type} / {food_name}"
    st.rerun()


def cancel():
    st.session_state.pending = None
    st.rerun()


def render_confirm_form(form, result, meal_types):
    """通用确认/修正表单，三个分支共用。"""
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

    col1, col2, col3 = st.columns(3)
    default_meal = result.get("meal_type", meal_types[-1])
    default_idx  = meal_types.index(default_meal) if default_meal in meal_types else len(meal_types) - 1
    with col1:
        meal_type = st.selectbox("餐顿类型", meal_types, index=default_idx)
    with col2:
        food_name = st.text_input(
            "食物名称",
            value=result.get("food_name") or (form["description"] if status == "error" else ""),
        )
    with col3:
        quantity = st.text_input(
            "份量",
            value=result.get("quantity", ""),
            placeholder="如：1碗、2个",
        )

    notes = st.text_area("备注（可选）", value=form.get("notes") or "", height=60)

    save_label = "保存" if status in ("confirmed", "error") else "确认保存"
    c1, c2 = st.columns(2)
    with c1:
        if st.button(save_label, type="primary", use_container_width=True):
            form["notes"] = notes
            save_and_done(form, meal_type, food_name, quantity,
                          confidence=result.get("confidence"))
    with c2:
        if st.button("取消", use_container_width=True):
            cancel()


# ── 确认界面（有 pending 时替代主表单）──────────────────────────────────────
if st.session_state.pending:
    form   = st.session_state.pending["form"]
    result = st.session_state.pending["result"]

    st.caption(
        f"**{form['date']}** {form['time'] or ''}　描述：{form['description']}"
    )
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
            help="24小时制，如 08:00、12:30、18:45"
        )

    description = st.text_area(
        "饮食描述",
        placeholder=(
            "例：早上喝了一杯豆浆，两个包子\n"
            "或：中午吃了麦当劳巨无霸套餐\n"
            "或：晚上在家吃了米饭、青菜和红烧肉"
        ),
        height=100,
        help="用自然语言描述你吃了什么，AI会自动提取餐顿、食物和份量信息",
    )

    notes = st.text_area("备注（可选）", height=68, placeholder="可记录心情、地点、特殊说明等")
    submitted = st.form_submit_button("提交", type="primary", use_container_width=True)

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

    with st.spinner("AI正在分析饮食描述..."):
        result = get_extractor().extract(description.strip())

    st.session_state.pending = {"form": form_data, "result": result}
    st.rerun()
