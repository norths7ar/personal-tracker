import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import date, timedelta

from core.expense.db import (
    get_period_data,
    get_active_weeks, get_active_months, get_active_years,
)

st.title("报表")

# ── 工具函数 ────────────────────────────────────────────────────────────────

def metrics_row(cur: dict, prev: dict, n_days: int):
    """顶部四格指标：本期总额 / 日均 / 与上期对比 / 收支结余。"""
    col1, col2, col3, col4 = st.columns(4)
    for col, label, cur_val, prev_val in [
        (col1, "支出", cur["expense"], prev["expense"]),
        (col2, "收入", cur["income"],  prev["income"]),
    ]:
        delta = cur_val - prev_val
        col.metric(label, f"¥{cur_val:,.2f}",
                   delta=f"¥{delta:+,.2f}" if prev_val else None,
                   delta_color="inverse" if label == "支出" else "normal")

    col3.metric("日均支出", f"¥{cur['expense']/n_days:,.2f}" if n_days else "—")
    balance = cur["balance"]
    col4.metric("收支结余", f"¥{balance:,.2f}",
                delta=f"¥{balance:,.2f}", delta_color="normal")


def daily_bar(daily: list, all_dates: list):
    """期内每日收支柱状图，所有日期都显示（无数据为 0）。"""
    date_map = {r["date"]: r for r in daily}
    dates, incomes, expenses = [], [], []
    for d in all_dates:
        r = date_map.get(d, {})
        dates.append(d)
        incomes.append(r.get("收入", 0))
        expenses.append(r.get("支出", 0))

    fig = go.Figure()
    fig.add_bar(x=dates, y=expenses, name="支出", marker_color="#5B9BD5")
    fig.add_bar(x=dates, y=incomes,  name="收入", marker_color="#70AD47")
    fig.update_layout(
        barmode="group", height=240,
        margin=dict(t=8, b=8, l=0, r=0),
        legend=dict(orientation="h", y=1.1),
        xaxis=dict(tickangle=-45),
    )
    st.plotly_chart(fig, width="stretch")


def period_compare_bar(periods: list):
    """多期汇总对比柱状图。periods: [{label, income, expense}]"""
    labels   = [p["label"]   for p in periods]
    expenses = [p["expense"] for p in periods]
    incomes  = [p["income"]  for p in periods]

    fig = go.Figure()
    fig.add_bar(x=labels, y=expenses, name="支出", marker_color="#5B9BD5")
    fig.add_bar(x=labels, y=incomes,  name="收入", marker_color="#70AD47")
    fig.update_layout(
        barmode="group", height=240,
        margin=dict(t=8, b=8, l=0, r=0),
        legend=dict(orientation="h", y=1.1),
    )
    st.plotly_chart(fig, width="stretch")


def breakdown_table(breakdown: list, label: str):
    if not breakdown:
        st.caption(f"本期无{label}记录")
        return
    df = pd.DataFrame(breakdown)
    df.columns = ["主类别", "子类别", "合计（元）", "笔数"]
    df["合计（元）"] = df["合计（元）"].apply(lambda x: f"¥{x:,.2f}")
    st.dataframe(df, hide_index=True, width="stretch")


# ── 页面主体 ────────────────────────────────────────────────────────────────
tab_week, tab_month, tab_year = st.tabs(["周", "月", "年"])


# ════════════════════════════════════════════════════════════════════════════
# 周视图
# ════════════════════════════════════════════════════════════════════════════
with tab_week:
    weeks = get_active_weeks()   # 每周的周一日期字符串
    if not weeks:
        st.info("暂无数据")
    else:
        # 格式化标签：W14（03/30–04/05）
        def week_label(mon: str) -> str:
            d = date.fromisoformat(mon)
            sun = d + timedelta(days=6)
            wn = d.isocalendar()[1]
            return f"W{wn:02d}（{d.month:02d}/{d.day:02d}–{sun.month:02d}/{sun.day:02d}）"

        options = {week_label(w): w for w in weeks}
        # 默认选当前自然周
        today = date.today()
        cur_mon = (today - timedelta(days=today.weekday())).isoformat()
        default_label = next(
            (lbl for lbl, w in options.items() if w == cur_mon),
            list(options.keys())[0]
        )
        selected_label = st.selectbox("选择周", list(options.keys()),
                                      index=list(options.keys()).index(default_label),
                                      key="week_sel")
        mon = options[selected_label]
        start = mon
        end   = (date.fromisoformat(mon) + timedelta(days=6)).isoformat()
        all_dates = [(date.fromisoformat(mon) + timedelta(days=i)).isoformat() for i in range(7)]

        cur  = get_period_data(start, end)
        # 上一周
        prev_mon = (date.fromisoformat(mon) - timedelta(weeks=1)).isoformat()
        prev_end = (date.fromisoformat(mon) - timedelta(days=1)).isoformat()
        prev = get_period_data(prev_mon, prev_end)

        metrics_row(cur, prev, n_days=7)
        st.caption("本周每日收支")
        daily_bar(cur["daily"], all_dates)

        # 最近 8 周对比
        st.caption("最近 8 周对比")
        recent_weeks = weeks[:8][::-1]
        period_bars = []
        for w in recent_weeks:
            w_end = (date.fromisoformat(w) + timedelta(days=6)).isoformat()
            d = get_period_data(w, w_end)
            period_bars.append({"label": week_label(w), "income": d["income"], "expense": d["expense"]})
        period_compare_bar(period_bars)

        st.subheader("支出明细")
        breakdown_table(cur["expense_breakdown"], "支出")
        st.subheader("收入明细")
        breakdown_table(cur["income_breakdown"], "收入")


# ════════════════════════════════════════════════════════════════════════════
# 月视图
# ════════════════════════════════════════════════════════════════════════════
with tab_month:
    months = get_active_months()
    if not months:
        st.info("暂无数据")
    else:
        today = date.today()
        cur_ym = today.strftime("%Y-%m")
        default_idx = months.index(cur_ym) if cur_ym in months else 0
        selected_ym = st.selectbox("选择月份", months, index=default_idx, key="month_sel")

        y, m = int(selected_ym[:4]), int(selected_ym[5:])
        start = f"{y:04d}-{m:02d}-01"
        if m == 12:
            next_first = date(y + 1, 1, 1)
        else:
            next_first = date(y, m + 1, 1)
        end = (next_first - timedelta(days=1)).isoformat()
        n_days = (next_first - date(y, m, 1)).days

        all_dates = [(date(y, m, 1) + timedelta(days=i)).isoformat() for i in range(n_days)]

        cur = get_period_data(start, end)

        # 上个月
        if m == 1:
            prev_start = f"{y-1:04d}-12-01"
            prev_end   = f"{y:04d}-01-01"
            prev_end   = (date(y, 1, 1) - timedelta(days=1)).isoformat()
        else:
            prev_start = f"{y:04d}-{m-1:02d}-01"
            prev_end   = (date(y, m, 1) - timedelta(days=1)).isoformat()
        prev = get_period_data(prev_start, prev_end)

        metrics_row(cur, prev, n_days=n_days)
        st.caption("本月每日收支")
        daily_bar(cur["daily"], all_dates)

        # 最近 12 个月对比
        st.caption("最近 12 个月对比")
        recent_months = months[:12][::-1]
        period_bars = []
        for ym in recent_months:
            yy, mm = int(ym[:4]), int(ym[5:])
            ms = f"{yy:04d}-{mm:02d}-01"
            if mm == 12:
                me = (date(yy+1,1,1) - timedelta(days=1)).isoformat()
            else:
                me = (date(yy, mm+1, 1) - timedelta(days=1)).isoformat()
            d = get_period_data(ms, me)
            period_bars.append({"label": ym, "income": d["income"], "expense": d["expense"]})
        period_compare_bar(period_bars)

        st.subheader("支出明细")
        breakdown_table(cur["expense_breakdown"], "支出")
        st.subheader("收入明细")
        breakdown_table(cur["income_breakdown"], "收入")


# ════════════════════════════════════════════════════════════════════════════
# 年视图
# ════════════════════════════════════════════════════════════════════════════
with tab_year:
    years = get_active_years()
    if not years:
        st.info("暂无数据")
    else:
        cur_year = str(date.today().year)
        default_idx = years.index(cur_year) if cur_year in years else 0
        selected_year = st.selectbox("选择年份", years, index=default_idx, key="year_sel")

        start = f"{selected_year}-01-01"
        end   = f"{selected_year}-12-31"

        # 按月生成 all_dates（用月份标签，不是每天）
        all_months = [f"{selected_year}-{m:02d}" for m in range(1, 13)]
        # 年视图的 daily_bar 改为按月聚合
        cur = get_period_data(start, end)

        # 上一年
        prev_year = str(int(selected_year) - 1)
        prev = get_period_data(f"{prev_year}-01-01", f"{prev_year}-12-31")
        n_days = 366 if int(selected_year) % 4 == 0 else 365

        metrics_row(cur, prev, n_days=n_days)

        # 年视图：按月聚合柱状图
        st.caption("本年各月收支")
        month_bars = []
        for ym in all_months:
            yy, mm = int(ym[:4]), int(ym[5:])
            ms = f"{yy:04d}-{mm:02d}-01"
            me = (date(yy, mm+1, 1) - timedelta(days=1)).isoformat() if mm < 12 else f"{yy}-12-31"
            d = get_period_data(ms, me)
            month_bars.append({"label": f"{mm}月", "income": d["income"], "expense": d["expense"]})
        period_compare_bar(month_bars)

        # 历年对比
        st.caption("历年对比")
        year_bars = []
        for yr in years[::-1]:
            d = get_period_data(f"{yr}-01-01", f"{yr}-12-31")
            year_bars.append({"label": yr, "income": d["income"], "expense": d["expense"]})
        period_compare_bar(year_bars)

        st.subheader("支出明细")
        breakdown_table(cur["expense_breakdown"], "支出")
        st.subheader("收入明细")
        breakdown_table(cur["income_breakdown"], "收入")
