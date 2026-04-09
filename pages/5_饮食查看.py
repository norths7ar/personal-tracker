import pandas as pd
import streamlit as st
from datetime import date, timedelta

from core.config import load_config
from core.db import init_db
from core.diet.db import (
    get_meals, update_meal, update_meal_foods, delete_meal,
)

init_db()

st.title("📋 饮食查看")

MEAL_TYPES = load_config().get("diet", {}).get("meal_types", ["早餐", "午餐", "晚餐", "零食", "其他"])

# ── session state ───────────────────────────────────────────────────────────
if "flash" not in st.session_state:
    st.session_state.flash = None

if st.session_state.flash:
    st.success(st.session_state.flash)
    st.session_state.flash = None

# ── 筛选条件 ────────────────────────────────────────────────────────────────
col1, col2, col3 = st.columns(3)
with col1:
    date_range = st.selectbox(
        "时间范围",
        ["今日", "最近7天", "最近30天", "本月", "上月", "全部", "自定义"],
    )
with col2:
    meal_type_filter = st.selectbox("餐顿类型", ["全部"] + MEAL_TYPES)
with col3:
    limit = st.number_input("显示条数", min_value=10, max_value=500, value=100, step=10)

today = date.today()
custom_start = custom_end = None
if date_range == "自定义":
    col1, col2 = st.columns(2)
    with col1:
        custom_start = st.date_input("开始日期", value=today - timedelta(days=7))
    with col2:
        custom_end = st.date_input("结束日期", value=today)

if date_range == "今日":
    start_date = end_date = today.strftime("%Y-%m-%d")
elif date_range == "最近7天":
    start_date = (today - timedelta(days=6)).strftime("%Y-%m-%d")
    end_date   = today.strftime("%Y-%m-%d")
elif date_range == "最近30天":
    start_date = (today - timedelta(days=29)).strftime("%Y-%m-%d")
    end_date   = today.strftime("%Y-%m-%d")
elif date_range == "本月":
    start_date = today.replace(day=1).strftime("%Y-%m-%d")
    end_date   = today.strftime("%Y-%m-%d")
elif date_range == "上月":
    first_this = today.replace(day=1)
    last_prev  = first_this - timedelta(days=1)
    start_date = last_prev.replace(day=1).strftime("%Y-%m-%d")
    end_date   = last_prev.strftime("%Y-%m-%d")
elif date_range == "自定义" and custom_start and custom_end:
    start_date = custom_start.strftime("%Y-%m-%d")
    end_date   = custom_end.strftime("%Y-%m-%d")
else:
    start_date = end_date = None

# ── 获取数据 ────────────────────────────────────────────────────────────────
try:
    meals = get_meals(
        start_date=start_date,
        end_date=end_date,
        meal_type=meal_type_filter if meal_type_filter != "全部" else None,
        limit=int(limit),
    )
except Exception as e:
    st.error(f"加载数据时出错：{e}")
    st.exception(e)
    st.stop()

if not meals:
    st.info("该时间段内没有饮食记录")
    st.stop()


# ── 侧边栏：统计摘要 + 导出 ─────────────────────────────────────────────────
def _meals_to_df(meals_list):
    rows = []
    for m in meals_list:
        rows.append({
            "id":       m["id"],
            "date":     m["date"],
            "time":     m.get("time") or "",
            "meal_type": m.get("meal_type") or "",
            "foods":    "、".join(
                f"{f['food_name']}{'×'+f['quantity'] if f.get('quantity') else ''}"
                for f in m["foods"]
            ),
            "notes":    m.get("notes") or "",
        })
    return pd.DataFrame(rows)


# ── 导出 + 表格 ─────────────────────────────────────────────────────────────
def _meals_to_export_df(meals_list):
    """完整导出：含 confidence、created_at，foods 展开为独立列。"""
    rows = []
    for m in meals_list:
        foods_str = "、".join(
            f"{f['food_name']}{'×'+f['quantity'] if f.get('quantity') else ''}"
            for f in m["foods"]
        )
        rows.append({
            "id":          m["id"],
            "date":        m["date"],
            "time":        m.get("time") or "",
            "meal_type":   m.get("meal_type") or "",
            "foods":       foods_str,
            "description": m.get("description") or "",
            "notes":       m.get("notes") or "",
            "confidence":  m.get("confidence"),
            "created_at":  m.get("created_at") or "",
        })
    return pd.DataFrame(rows)


col_export, col_count = st.columns([1, 3])
with col_export:
    csv = _meals_to_export_df(meals).to_csv(index=False, encoding="utf-8-sig")
    st.download_button(
        "导出为CSV",
        data=csv,
        file_name=f"饮食记录_{today.strftime('%Y%m%d')}.csv",
        mime="text/csv",
        help="包含置信度、创建时间、原始描述等所有字段",
    )
with col_count:
    st.caption(f"共 {len(meals)} 餐")

display_df = _meals_to_df(meals)
st.subheader("饮食记录")
event = st.dataframe(
    display_df,
    hide_index=True,
    width="stretch",
    selection_mode="single-row",
    on_select="rerun",
    column_config={
        "id":        st.column_config.NumberColumn("ID", width="small"),
        "date":      st.column_config.TextColumn("日期"),
        "time":      st.column_config.TextColumn("时间"),
        "meal_type": st.column_config.TextColumn("餐顿"),
        "foods":     st.column_config.TextColumn("食物"),
        "notes":     st.column_config.TextColumn("备注"),
    },
)

selected_rows = event.selection.rows
if not selected_rows:
    st.caption("点击一行可编辑或删除。")
    st.stop()

# ── 编辑 / 删除面板 ─────────────────────────────────────────────────────────
meal = meals[selected_rows[0]]
meal_id = meal["id"]
st.divider()
st.subheader(f"操作记录 #{meal_id}")

tab_edit, tab_delete = st.tabs(["编辑", "删除"])

with tab_edit:
    with st.form("edit_form"):
        col1, col2 = st.columns(2)
        with col1:
            edit_date = st.date_input("日期", value=date.fromisoformat(meal["date"]))
        with col2:
            edit_time = st.text_input("时间", value=meal.get("time") or "")

        cur_meal = meal.get("meal_type") or MEAL_TYPES[-1]
        meal_idx = MEAL_TYPES.index(cur_meal) if cur_meal in MEAL_TYPES else len(MEAL_TYPES) - 1
        edit_meal_type   = st.selectbox("餐顿类型", MEAL_TYPES, index=meal_idx)
        edit_description = st.text_area("原始描述", value=meal.get("description") or "", height=68)
        edit_notes       = st.text_area("备注", value=meal.get("notes") or "", height=60)

        st.caption("食物清单（可编辑、增删行）")
        foods_df  = pd.DataFrame(meal["foods"] or [{"food_name": "", "quantity": ""}])
        edited_foods = st.data_editor(
            foods_df,
            num_rows="dynamic",
            column_config={
                "food_name": st.column_config.TextColumn("食物名称", required=True),
                "quantity":  st.column_config.TextColumn("份量"),
            },
            hide_index=True,
            width="stretch",
        )

        c1, c2 = st.columns(2)
        with c1:
            save = st.form_submit_button("保存修改", type="primary", width="stretch")
        with c2:
            cancel_edit = st.form_submit_button("取消", width="stretch")

    if save:
        new_foods = [
            {"food_name": str(row["food_name"]), "quantity": str(row.get("quantity") or "")}
            for _, row in edited_foods.iterrows()
            if pd.notna(row["food_name"]) and str(row["food_name"]).strip()
        ]
        if not new_foods:
            st.error("请至少填写一种食物")
        else:
            update_meal(
                meal_id,
                date=edit_date.strftime("%Y-%m-%d"),
                time=edit_time or None,
                meal_type=edit_meal_type,
                description=edit_description,
                notes=edit_notes or None,
            )
            update_meal_foods(meal_id, new_foods)
            st.session_state.flash = f"✅ 记录 ID {meal_id} 已更新"
            st.rerun()

    if cancel_edit:
        st.rerun()

with tab_delete:
    st.warning("⚠️ 以下记录将被永久删除（含所有食物条目）：")
    col1, col2 = st.columns(2)
    with col1:
        st.metric("日期", meal["date"])
    with col2:
        st.metric("餐顿", meal.get("meal_type") or "未知")
    foods_preview = "、".join(f["food_name"] for f in meal["foods"])
    st.caption(f"食物：{foods_preview}")
    if meal.get("description"):
        st.caption(f"原始描述：{meal['description']}")

    c1, c2 = st.columns(2)
    with c1:
        if st.button("确认删除", type="primary", width="stretch"):
            delete_meal(meal_id)
            st.session_state.flash = f"✅ 记录 ID {meal_id} 已删除"
            st.rerun()
    with c2:
        if st.button("取消", width="stretch"):
            st.rerun()
