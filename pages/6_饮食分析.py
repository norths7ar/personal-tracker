import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import date, timedelta

from core.db import init_db
from core.diet.db import get_diet_stats

init_db()

st.title("📊 饮食分析")

MAIN_MEAL_TYPES = ["早餐", "午餐", "晚餐"]


# ── 工具函数 ────────────────────────────────────────────────────────────────

def date_range_days(start_str: str, end_str: str) -> list[str]:
    start = date.fromisoformat(start_str)
    end   = date.fromisoformat(end_str)
    days  = (end - start).days + 1
    return [(start + timedelta(days=i)).isoformat() for i in range(days)]


def coverage_heatmap(daily_coverage: list, all_dates: list):
    """三餐覆盖热力图：横轴日期，纵轴早/午/晚，有记录=绿，无=灰。"""
    covered = {(r["date"], r["meal_type"]) for r in daily_coverage}
    z = [
        [1 if (d, mt) in covered else 0 for d in all_dates]
        for mt in MAIN_MEAL_TYPES
    ]
    # Shorten x labels to MM-DD when range > 14 days
    x_labels = [d[5:] for d in all_dates]
    fig = go.Figure(go.Heatmap(
        x=x_labels,
        y=MAIN_MEAL_TYPES,
        z=z,
        colorscale=[[0, "#eeeeee"], [1, "#2ecc71"]],
        showscale=False,
        xgap=3,
        ygap=3,
        hovertemplate="%{y} %{x}: %{z}<extra></extra>",
    ))
    fig.update_layout(
        height=160,
        margin=dict(t=8, b=8, l=0, r=0),
        xaxis=dict(tickangle=-45, tickfont=dict(size=10)),
    )
    return fig


def meal_type_bar(meal_type_dist: list):
    if not meal_type_dist:
        return None
    labels = [r["meal_type"] for r in meal_type_dist]
    counts = [r["count"] for r in meal_type_dist]
    fig = go.Figure(go.Bar(
        x=labels, y=counts,
        marker_color="#5B9BD5",
        text=counts, textposition="outside",
    ))
    fig.update_layout(
        height=240,
        margin=dict(t=8, b=8, l=0, r=0),
        yaxis=dict(title="次数"),
    )
    return fig


def food_freq_bar(food_freq: list):
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


def daily_meals_line(daily_meals: list, all_dates: list):
    count_map = {r["date"]: r["count"] for r in daily_meals}
    counts = [count_map.get(d, 0) for d in all_dates]
    x_labels = [d[5:] for d in all_dates]
    fig = go.Figure(go.Scatter(
        x=x_labels, y=counts,
        mode="lines+markers",
        line=dict(color="#E67E22", width=2),
        marker=dict(size=5),
        fill="tozeroy",
        fillcolor="rgba(230,126,34,0.1)",
    ))
    fig.update_layout(
        height=200,
        margin=dict(t=8, b=8, l=0, r=0),
        xaxis=dict(tickangle=-45, tickfont=dict(size=10)),
        yaxis=dict(title="餐次数", dtick=1),
    )
    return fig


def metrics_row(stats: dict, all_dates: list):
    total_meals  = sum(r["count"] for r in stats["daily_meals"])
    days_with    = len(stats["daily_meals"])
    days_total   = len(all_dates)
    coverage_pct = days_with / days_total if days_total else 0

    # Count days with all three main meals recorded
    covered = {(r["date"], r["meal_type"]) for r in stats["daily_coverage"]}
    full_days = sum(
        1 for d in all_dates
        if all((d, mt) in covered for mt in MAIN_MEAL_TYPES)
    )

    top_food = stats["food_freq"][0]["food_name"] if stats["food_freq"] else "—"

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("记录天数", f"{days_with} / {days_total} 天",
                delta=f"{coverage_pct:.0%} 覆盖率")
    col2.metric("总餐次", total_meals)
    col3.metric("三餐齐全的天数", full_days)
    col4.metric("最高频食物", top_food)


def render_tab(start_date: str, end_date: str, key_prefix: str):
    all_dates = date_range_days(start_date, end_date)
    stats = get_diet_stats(start_date, end_date)

    if not stats["daily_meals"]:
        st.info("该时间段内没有饮食记录")
        return

    metrics_row(stats, all_dates)

    st.caption("三餐覆盖情况")
    st.plotly_chart(coverage_heatmap(stats["daily_coverage"], all_dates),
                    width="stretch", key=f"{key_prefix}_heatmap")

    col1, col2 = st.columns(2)
    with col1:
        st.caption("餐顿类型分布")
        fig = meal_type_bar(stats["meal_type_dist"])
        if fig:
            st.plotly_chart(fig, width="stretch", key=f"{key_prefix}_meal_type")

    with col2:
        st.caption("每日餐次趋势")
        st.plotly_chart(daily_meals_line(stats["daily_meals"], all_dates),
                        width="stretch", key=f"{key_prefix}_daily")

    st.caption("高频食物 Top 15")
    fig = food_freq_bar(stats["food_freq"])
    if fig:
        st.plotly_chart(fig, width="stretch", key=f"{key_prefix}_foods")
    else:
        st.info("暂无食物数据")


# ── 页面主体：周 / 月 tabs ───────────────────────────────────────────────────
tab_week, tab_month = st.tabs(["周", "月"])

today = date.today()

with tab_week:
    mon = today - timedelta(days=today.weekday())  # 本周一
    week_options = {
        f"本周（{mon.strftime('%m/%d')}–{(mon+timedelta(days=6)).strftime('%m/%d')}）": mon,
    }
    for i in range(1, 5):
        w = mon - timedelta(weeks=i)
        label = f"第{i}周前（{w.strftime('%m/%d')}–{(w+timedelta(days=6)).strftime('%m/%d')}）"
        week_options[label] = w

    selected_label = st.selectbox("选择周", list(week_options.keys()), key="week_sel")
    w_start = week_options[selected_label]
    w_end   = w_start + timedelta(days=6)
    render_tab(w_start.isoformat(), min(w_end, today).isoformat(), key_prefix="week")

with tab_month:
    # Build last 12 months
    month_options = {}
    y, m = today.year, today.month
    for _ in range(12):
        label = f"{y}-{m:02d}"
        month_options[label] = (y, m)
        m -= 1
        if m == 0:
            m = 12
            y -= 1

    selected_ym = st.selectbox("选择月份", list(month_options.keys()), key="month_sel")
    yy, mm = month_options[selected_ym]
    m_start = date(yy, mm, 1)
    if mm == 12:
        m_end = date(yy + 1, 1, 1) - timedelta(days=1)
    else:
        m_end = date(yy, mm + 1, 1) - timedelta(days=1)
    render_tab(m_start.isoformat(), min(m_end, today).isoformat(), key_prefix="month")
