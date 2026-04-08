import streamlit as st
import pandas as pd
from datetime import date, timedelta

from core.db import init_db
from core.diet.db import (
    get_diet_entries, update_diet_entry, delete_diet_entry, get_diet_summary
)
from core.config import load_config

init_db()

st.title("📋 饮食查看")

MEAL_TYPES = load_config().get("diet", {}).get("meal_types", ["早餐", "午餐", "晚餐", "零食", "其他"])

# ── session state 初始化 ────────────────────────────────────────────────────
for key, default in [("flash", None), ("edit_id", None), ("delete_id", None)]:
    if key not in st.session_state:
        st.session_state[key] = default

# ── flash 消息 ──────────────────────────────────────────────────────────────
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

# 自定义日期范围
today = date.today()
custom_start = custom_end = None
if date_range == "自定义":
    col1, col2 = st.columns(2)
    with col1:
        custom_start = st.date_input("开始日期", value=today - timedelta(days=7))
    with col2:
        custom_end = st.date_input("结束日期", value=today)

# 计算 start_date / end_date
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
else:  # 全部
    start_date = end_date = None

# ── 获取数据 ────────────────────────────────────────────────────────────────
try:
    rows = get_diet_entries(
        start_date=start_date,
        end_date=end_date,
        meal_type=meal_type_filter if meal_type_filter != "全部" else None,
        limit=int(limit),
    )
except Exception as e:
    st.error(f"加载数据时出错：{e}")
    st.exception(e)
    st.stop()

if not rows:
    st.info("该时间段内没有饮食记录")
    st.stop()

df = pd.DataFrame(rows)

# ── 侧边栏：统计 ────────────────────────────────────────────────────────────
with st.sidebar:
    st.subheader("📊 统计摘要")
    if start_date and end_date:
        try:
            summary = get_diet_summary(start_date, end_date)
            if summary["meal_stats"]:
                st.caption(f"{start_date} 至 {end_date}")
                st.write("**餐顿类型分布**")
                for stat in summary["meal_stats"]:
                    st.progress(
                        stat["count"] / max(1, len(rows)),
                        text=f"{stat['meal_type']}: {stat['count']} 次",
                    )
                st.write("**最近记录**")
                for i, rec in enumerate(summary["recent"][:5], 1):
                    st.caption(
                        f"{i}. {rec['date']} {rec['meal_type']}: "
                        f"{rec['food_name']} {rec.get('quantity', '')}"
                    )
        except Exception as e:
            st.caption(f"统计加载失败：{e}")

    st.divider()
    st.subheader("导出数据")
    csv = df.to_csv(index=False, encoding="utf-8-sig")
    st.download_button(
        label="导出为CSV",
        data=csv,
        file_name=f"饮食记录_{today.strftime('%Y%m%d')}.csv",
        mime="text/csv",
        use_container_width=True,
    )

# ── 主表格（支持行选择，与流水页对齐）──────────────────────────────────────
display_cols = ["id", "date", "time", "meal_type", "food_name", "quantity", "description", "notes"]
display_df = df[display_cols].copy().fillna("")

st.subheader(f"饮食记录（共 {len(rows)} 条）")
event = st.dataframe(
    display_df,
    hide_index=True,
    use_container_width=True,
    selection_mode="single-row",
    on_select="rerun",
    column_config={
        "id":          st.column_config.NumberColumn("ID", width="small"),
        "date":        st.column_config.TextColumn("日期"),
        "time":        st.column_config.TextColumn("时间"),
        "meal_type":   st.column_config.TextColumn("餐顿"),
        "food_name":   st.column_config.TextColumn("食物"),
        "quantity":    st.column_config.TextColumn("份量"),
        "description": st.column_config.TextColumn("原始描述"),
        "notes":       st.column_config.TextColumn("备注"),
    },
)

selected_rows = event.selection.rows
if not selected_rows:
    st.caption("点击一行可编辑或删除。")
    st.stop()

# ── 编辑 / 删除面板 ─────────────────────────────────────────────────────────
record = df.iloc[selected_rows[0]].to_dict()
record_id = int(record["id"])
st.divider()
st.subheader(f"操作记录 #{record_id}")

tab_edit, tab_delete = st.tabs(["编辑", "删除"])

with tab_edit:
    with st.form("edit_form"):
        col1, col2 = st.columns(2)
        with col1:
            edit_date = st.date_input("日期", value=date.fromisoformat(record["date"]))
        with col2:
            edit_time = st.text_input("时间", value=record.get("time") or "")

        cur_meal = record.get("meal_type") or MEAL_TYPES[-1]
        meal_idx = MEAL_TYPES.index(cur_meal) if cur_meal in MEAL_TYPES else len(MEAL_TYPES) - 1
        edit_meal_type   = st.selectbox("餐顿类型", MEAL_TYPES, index=meal_idx)
        edit_food_name   = st.text_input("食物名称", value=record.get("food_name") or "")
        edit_quantity    = st.text_input("份量", value=record.get("quantity") or "")
        edit_description = st.text_area("原始描述", value=record.get("description") or "", height=80)
        edit_notes       = st.text_area("备注", value=record.get("notes") or "", height=60)

        c1, c2 = st.columns(2)
        with c1:
            save = st.form_submit_button("保存修改", type="primary", use_container_width=True)
        with c2:
            cancel_edit = st.form_submit_button("取消", use_container_width=True)

    if save:
        update_diet_entry(
            record_id,
            date=edit_date.strftime("%Y-%m-%d"),
            time=edit_time or None,
            meal_type=edit_meal_type,
            food_name=edit_food_name,
            quantity=edit_quantity,
            description=edit_description,
            notes=edit_notes or None,
        )
        st.session_state.flash = f"✅ 记录 ID {record_id} 已更新"
        st.rerun()

    if cancel_edit:
        st.rerun()

with tab_delete:
    st.warning("⚠️ 以下记录将被永久删除：")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("日期", record["date"])
    with col2:
        st.metric("餐顿", record.get("meal_type") or "未知")
    with col3:
        st.metric("食物", record.get("food_name") or "未知")
    st.caption(f"原始描述：{record.get('description', '')}")

    c1, c2 = st.columns(2)
    with c1:
        if st.button("确认删除", type="primary", use_container_width=True):
            delete_diet_entry(record_id)
            st.session_state.flash = f"✅ 记录 ID {record_id} 已删除"
            st.rerun()
    with c2:
        if st.button("取消", use_container_width=True):
            st.rerun()
