from datetime import date, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core.config import load_config
from core.constants import DEFAULT_MEAL_TYPES
from core.diet.db import (
    delete_meal,
    get_diet_stats,
    get_meals,
    update_meal_with_foods,
)
from core.text import display_text, optional_text

st.title("饮食")

MEAL_TYPES = (
    load_config().get("diet", {}).get("meal_types", list(DEFAULT_MEAL_TYPES))
)
MAIN_MEAL_TYPES = list(DEFAULT_MEAL_TYPES[:3])

# ── session state ─────────────────────────────────────────────────────────────

if "diet_ledger_flash" not in st.session_state:
    st.session_state.diet_ledger_flash = None

if st.session_state.diet_ledger_flash:
    st.success(st.session_state.diet_ledger_flash)
    st.session_state.diet_ledger_flash = None


# ── 分析辅助函数 ──────────────────────────────────────────────────────────────

def _date_range_days(start_str: str, end_str: str) -> list[str]:
    start = date.fromisoformat(start_str)
    end = date.fromisoformat(end_str)
    return [(start + timedelta(days=i)).isoformat() for i in range((end - start).days + 1)]


def _coverage_heatmap(daily_coverage: list, all_dates: list):
    covered = {(r["date"], r["meal_type"]) for r in daily_coverage}
    z = [[1 if (d, mt) in covered else 0 for d in all_dates] for mt in MAIN_MEAL_TYPES]
    x_labels = [d[5:] for d in all_dates]
    fig = go.Figure(go.Heatmap(
        x=x_labels, y=MAIN_MEAL_TYPES, z=z,
        colorscale=[[0, "#eeeeee"], [1, "#2ecc71"]],
        showscale=False, xgap=3, ygap=3,
        hovertemplate="%{y} %{x}: %{z}<extra></extra>",
    ))
    fig.update_layout(height=160, margin=dict(t=8, b=8, l=0, r=0),
                      xaxis=dict(tickangle=-45, tickfont=dict(size=10)))
    return fig


def _meal_type_bar(meal_type_dist: list):
    if not meal_type_dist:
        return None
    fig = go.Figure(go.Bar(
        x=[r["meal_type"] for r in meal_type_dist],
        y=[r["count"] for r in meal_type_dist],
        marker_color="#5B9BD5",
        text=[r["count"] for r in meal_type_dist],
        textposition="outside",
    ))
    fig.update_layout(height=240, margin=dict(t=8, b=8, l=0, r=0), yaxis=dict(title="次数"))
    return fig


def _food_freq_bar(food_freq: list):
    if not food_freq:
        return None
    top = food_freq[:15][::-1]
    fig = go.Figure(go.Bar(
        y=[r["food_name"] for r in top],
        x=[r["count"] for r in top],
        orientation="h",
        marker_color="#70AD47",
        text=[r["count"] for r in top],
        textposition="outside",
    ))
    fig.update_layout(
        height=max(200, len(top) * 28),
        margin=dict(t=8, b=8, l=0, r=0),
        xaxis=dict(title="出现次数"),
    )
    return fig


def _daily_meals_line(daily_meals: list, all_dates: list):
    count_map = {r["date"]: r["count"] for r in daily_meals}
    counts = [count_map.get(d, 0) for d in all_dates]
    fig = go.Figure(go.Scatter(
        x=all_dates, y=counts, mode="lines+markers",
        line=dict(color="#E67E22", width=2), marker=dict(size=5),
        fill="tozeroy", fillcolor="rgba(230,126,34,0.1)",
    ))
    fig.update_layout(height=200, margin=dict(t=8, b=8, l=0, r=0),
                      xaxis=dict(tickangle=-45, tickfont=dict(size=10), type="category"),
                      yaxis=dict(title="餐次数", dtick=1))
    return fig


def _metrics_row(stats: dict, all_dates: list):
    total_meals = sum(r["count"] for r in stats["daily_meals"])
    days_with = len(stats["daily_meals"])
    days_total = len(all_dates)
    coverage_pct = days_with / days_total if days_total else 0
    covered = {(r["date"], r["meal_type"]) for r in stats["daily_coverage"]}
    full_days = sum(1 for d in all_dates if all((d, mt) in covered for mt in MAIN_MEAL_TYPES))
    top_food = stats["food_freq"][0]["food_name"] if stats["food_freq"] else "—"

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("记录天数", f"{days_with} / {days_total} 天", delta=f"{coverage_pct:.0%} 覆盖率")
    col2.metric("总餐次", total_meals)
    col3.metric("三餐齐全", full_days)
    col4.metric("最高频食物", top_food)


def render_analysis_period(start_date: str, end_date: str, key_prefix: str):
    all_dates = _date_range_days(start_date, end_date)
    stats = get_diet_stats(start_date, end_date)

    if not stats["daily_meals"]:
        st.info("该时间段内没有饮食记录")
        return

    _metrics_row(stats, all_dates)

    st.caption("三餐覆盖情况")
    st.plotly_chart(_coverage_heatmap(stats["daily_coverage"], all_dates),
                    width="stretch", key=f"{key_prefix}_heatmap")

    col1, col2 = st.columns(2)
    with col1:
        st.caption("餐顿类型分布")
        fig = _meal_type_bar(stats["meal_type_dist"])
        if fig:
            st.plotly_chart(fig, width="stretch", key=f"{key_prefix}_meal_type")
    with col2:
        st.caption("每日餐次趋势")
        st.plotly_chart(_daily_meals_line(stats["daily_meals"], all_dates),
                        width="stretch", key=f"{key_prefix}_daily")

    st.caption("高频食物 Top 15")
    fig = _food_freq_bar(stats["food_freq"])
    if fig:
        st.plotly_chart(fig, width="stretch", key=f"{key_prefix}_foods")
    else:
        st.info("暂无食物数据")


# ── Tab 渲染函数 ──────────────────────────────────────────────────────────────

def render_ledger_tab():
    col1, col2, col3 = st.columns(3)
    with col1:
        date_range = st.selectbox(
            "时间范围",
            ["今日", "最近7天", "最近30天", "本月", "上月", "全部", "自定义"],
            index=1,
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
        end_date = today.strftime("%Y-%m-%d")
    elif date_range == "最近30天":
        start_date = (today - timedelta(days=29)).strftime("%Y-%m-%d")
        end_date = today.strftime("%Y-%m-%d")
    elif date_range == "本月":
        start_date = today.replace(day=1).strftime("%Y-%m-%d")
        end_date = today.strftime("%Y-%m-%d")
    elif date_range == "上月":
        first_this = today.replace(day=1)
        last_prev = first_this - timedelta(days=1)
        start_date = last_prev.replace(day=1).strftime("%Y-%m-%d")
        end_date = last_prev.strftime("%Y-%m-%d")
    elif date_range == "自定义" and custom_start and custom_end:
        start_date = custom_start.strftime("%Y-%m-%d")
        end_date = custom_end.strftime("%Y-%m-%d")
    else:
        start_date = end_date = None

    try:
        meals = get_meals(
            start_date=start_date, end_date=end_date,
            meal_type=meal_type_filter if meal_type_filter != "全部" else None,
            limit=int(limit),
        )
    except Exception as e:
        st.error(f"加载数据时出错：{e}")
        return

    if not meals:
        st.info("该时间段内没有饮食记录")
        return

    def _meals_to_df(meals_list):
        return pd.DataFrame([{
            "id": m["id"],
            "date": m["date"],
            "time": display_text(m.get("time")),
            "meal_type": display_text(m.get("meal_type")),
            "foods": "、".join(
                f"{f['food_name']}{'×' + f['quantity'] if f.get('quantity') else ''}"
                for f in m["foods"]
            ),
            "notes": display_text(m.get("notes")),
        } for m in meals_list])

    def _meals_to_export_df(meals_list):
        return pd.DataFrame([{
            "id": m["id"],
            "date": m["date"],
            "time": display_text(m.get("time")),
            "meal_type": display_text(m.get("meal_type")),
            "foods": "、".join(
                f"{f['food_name']}{'×' + f['quantity'] if f.get('quantity') else ''}"
                for f in m["foods"]
            ),
            "description": display_text(m.get("description")),
            "notes": display_text(m.get("notes")),
            "confidence": m.get("confidence"),
            "created_at": m.get("created_at") or "",
        } for m in meals_list])

    col_export, col_count = st.columns([1, 3])
    with col_export:
        csv = _meals_to_export_df(meals).to_csv(index=False, encoding="utf-8-sig")
        st.download_button(
            "导出为CSV", data=csv,
            file_name=f"饮食记录_{today.strftime('%Y%m%d')}.csv",
            mime="text/csv",
        )
    with col_count:
        st.caption(f"共 {len(meals)} 餐")

    event = st.dataframe(
        _meals_to_df(meals),
        hide_index=True, width="stretch",
        selection_mode="single-row", on_select="rerun",
        column_config={
            "id": st.column_config.NumberColumn("ID", width="small"),
            "date": st.column_config.TextColumn("日期"),
            "time": st.column_config.TextColumn("时间"),
            "meal_type": st.column_config.TextColumn("餐顿"),
            "foods": st.column_config.TextColumn("食物"),
            "notes": st.column_config.TextColumn("备注"),
        },
    )

    selected_rows = event.selection.rows
    if not selected_rows:
        st.caption("点击一行可编辑或删除。")
        return

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
                edit_time = st.text_input("时间", value=display_text(meal.get("time")))
            cur_meal = meal.get("meal_type") or MEAL_TYPES[-1]
            meal_idx = MEAL_TYPES.index(cur_meal) if cur_meal in MEAL_TYPES else len(MEAL_TYPES) - 1
            edit_meal_type = st.selectbox("餐顿类型", MEAL_TYPES, index=meal_idx)
            edit_description = st.text_area("原始描述", value=display_text(meal.get("description")), height=68)
            edit_notes = st.text_area("备注", value=display_text(meal.get("notes")), height=60)
            st.caption("食物清单（可编辑、增删行）")
            foods_df = pd.DataFrame(meal["foods"] or [{"food_name": "", "quantity": ""}])
            edited_foods = st.data_editor(
                foods_df, num_rows="dynamic",
                column_config={
                    "food_name": st.column_config.TextColumn("食物名称", required=True),
                    "quantity": st.column_config.TextColumn("份量"),
                },
                hide_index=True, width="stretch",
            )
            c1, c2 = st.columns(2)
            with c1:
                save = st.form_submit_button("保存修改", type="primary", width="stretch")
            with c2:
                st.form_submit_button("取消", width="stretch")

        if save:
            new_foods = [
                {"food_name": str(row["food_name"]), "quantity": display_text(row.get("quantity"))}
                for _, row in edited_foods.iterrows()
                if pd.notna(row["food_name"]) and str(row["food_name"]).strip()
            ]
            if not new_foods:
                st.error("请至少填写一种食物")
            else:
                update_meal_with_foods(
                    meal_id, new_foods,
                    date=edit_date.strftime("%Y-%m-%d"),
                    time=optional_text(edit_time),
                    meal_type=edit_meal_type,
                    description=edit_description,
                    notes=optional_text(edit_notes),
                )
                st.session_state.diet_ledger_flash = f"✅ 记录 ID {meal_id} 已更新"
                st.rerun()

    with tab_delete:
        st.warning("⚠️ 以下记录将被永久删除（含所有食物条目）：")
        col1, col2 = st.columns(2)
        with col1:
            st.metric("日期", meal["date"])
        with col2:
            st.metric("餐顿", meal.get("meal_type") or "未知")
        st.caption(f"食物：{'、'.join(f['food_name'] for f in meal['foods'])}")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("确认删除", type="primary", width="stretch"):
                delete_meal(meal_id)
                st.session_state.diet_ledger_flash = f"✅ 记录 ID {meal_id} 已删除"
                st.rerun()
        with c2:
            if st.button("取消", width="stretch"):
                st.rerun()


def render_analysis_tab():
    today = date.today()
    month_options = {}
    y, m = today.year, today.month
    for _ in range(12):
        label = f"{y}-{m:02d}"
        month_options[label] = (y, m)
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    selected_ym = st.selectbox("选择月份", list(month_options.keys()), key="diet_month_sel")
    yy, mm = month_options[selected_ym]
    m_start = date(yy, mm, 1)
    m_end = (date(yy + 1, 1, 1) - timedelta(days=1)) if mm == 12 else (date(yy, mm + 1, 1) - timedelta(days=1))
    render_analysis_period(m_start.isoformat(), min(m_end, today).isoformat(), key_prefix="month")


# ── 主体 ──────────────────────────────────────────────────────────────────────

tab_ledger, tab_analysis = st.tabs(["查看", "分析"])

with tab_ledger:
    render_ledger_tab()

with tab_analysis:
    render_analysis_tab()
