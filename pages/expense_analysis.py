import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import date, timedelta

from core.expense.db import (
    get_period_data,
    get_active_months,
    get_active_years,
)
from core.budget.db import get_month_budget, save_month_budget

st.title("开销分析")

analysis_basis = st.radio(
    "统计口径",
    ["现金流", "摊销后"],
    horizontal=True,
    help="现金流按实际付款日期统计；摊销后会把设置了摊销月数的支出分摊到对应月份。",
)
basis_key = "amortized" if analysis_basis == "摊销后" else "cash"

# ── 工具函数 ────────────────────────────────────────────────────────────────


def metrics_row(cur: dict, prev: dict, n_days: int):
    """顶部四格指标：本期总额 / 日均 / 与上期对比 / 收支结余。"""
    col1, col2, col3, col4 = st.columns(4)
    for col, label, cur_val, prev_val in [
        (col1, "支出", cur["expense"], prev["expense"]),
        (col2, "收入", cur["income"], prev["income"]),
    ]:
        delta = cur_val - prev_val
        col.metric(
            label,
            f"¥{cur_val:,.2f}",
            delta=f"¥{delta:+,.2f}" if prev_val else None,
            delta_color="inverse" if label == "支出" else "normal",
        )

    col3.metric("日均支出", f"¥{cur['expense'] / n_days:,.2f}" if n_days else "—")
    balance = cur["balance"]
    col4.metric(
        "收支结余", f"¥{balance:,.2f}", delta=f"¥{balance:,.2f}", delta_color="normal"
    )


def daily_line(daily: list, all_dates: list):
    """期内每日收支走势；离群值保留为尖峰而不主导整个画面。"""
    date_map = {r["date"]: r for r in daily}
    dates, incomes, expenses = [], [], []
    for d in all_dates:
        r = date_map.get(d, {})
        dates.append(d)
        incomes.append(r.get("收入", 0))
        expenses.append(r.get("支出", 0))

    fig = go.Figure()
    fig.add_scatter(
        x=dates,
        y=expenses,
        name="支出",
        mode="lines+markers",
        line=dict(color="#D9534F", width=2),
        marker=dict(size=5),
    )
    fig.add_scatter(
        x=dates,
        y=incomes,
        name="收入",
        mode="lines+markers",
        line=dict(color="#4C9F70", width=2),
        marker=dict(size=5),
    )
    fig.update_layout(
        height=240,
        margin=dict(t=8, b=8, l=0, r=0),
        legend=dict(orientation="h", y=1.1),
        xaxis=dict(tickangle=-45, type="category"),
    )
    st.plotly_chart(fig, width="stretch")


def period_compare_bar(periods: list):
    """多期汇总对比柱状图。periods: [{label, income, expense}]"""
    labels = [p["label"] for p in periods]
    expenses = [p["expense"] for p in periods]
    incomes = [p["income"] for p in periods]

    fig = go.Figure()
    fig.add_bar(x=labels, y=expenses, name="支出", marker_color="#5B9BD5")
    fig.add_bar(x=labels, y=incomes, name="收入", marker_color="#70AD47")
    fig.update_layout(
        barmode="group",
        height=240,
        margin=dict(t=8, b=8, l=0, r=0),
        legend=dict(orientation="h", y=1.1),
    )
    st.plotly_chart(fig, width="stretch")


def breakdown_table(breakdown: list, label: str, level: str):
    if not breakdown:
        st.caption(f"本期无{label}记录")
        return
    df = pd.DataFrame(breakdown)
    if level == "一级分类":
        df = df[["category", "total", "count"]]
        df.columns = ["主类别", "合计（元）", "笔数"]
    else:
        df.columns = ["主类别", "子类别", "合计（元）", "笔数"]
    df["合计（元）"] = df["合计（元）"].apply(lambda x: f"¥{x:,.2f}")
    st.dataframe(df, hide_index=True, width="stretch")


def breakdown_chart(breakdown: list, level: str):
    if not breakdown:
        st.caption("本期无支出记录")
        return
    rows = breakdown[:8][::-1]
    labels = [
        row["category"] if level == "一级分类" else f"{row['category']} / {row['subcategory']}"
        for row in rows
    ]
    fig = go.Figure(
        go.Bar(
            x=[row["total"] for row in rows],
            y=labels,
            orientation="h",
            marker_color="#5B9BD5",
            text=[f"¥{row['total']:,.0f}" for row in rows],
            textposition="outside",
        )
    )
    fig.update_layout(
        height=max(220, len(rows) * 34),
        margin=dict(t=8, b=8, l=0, r=44),
        xaxis=dict(title=None),
        yaxis=dict(title=None),
    )
    st.plotly_chart(fig, width="stretch")
    with st.expander("查看完整支出明细"):
        breakdown_table(breakdown, "支出", level)


def aggregate_breakdown(breakdown: list, level: str) -> list:
    if level == "二级分类" or not breakdown:
        return breakdown
    grouped = {}
    for row in breakdown:
        category = row.get("category") or "未分类"
        current = grouped.setdefault(
            category,
            {"category": category, "subcategory": "全部", "total": 0, "count": 0},
        )
        current["total"] += row.get("total") or 0
        current["count"] += row.get("count") or 0
    return sorted(grouped.values(), key=lambda row: row["total"], reverse=True)


def category_totals(breakdown: list) -> dict[str, float]:
    totals: dict[str, float] = {}
    for row in breakdown:
        category = row.get("category") or "未分类"
        totals[category] = totals.get(category, 0) + float(row.get("total") or 0)
    return totals


def trend_summary(current: dict, previous: dict, basis_label: str) -> str:
    """Produce a traceable explanation from the same numbers shown on the page."""
    delta = current["expense"] - previous["expense"]
    if abs(delta) < 0.005:
        return f"按{basis_label}口径，本期支出与上期基本持平。"

    direction = "增加" if delta > 0 else "减少"
    current_categories = category_totals(current["expense_breakdown"])
    previous_categories = category_totals(previous["expense_breakdown"])
    changes = [
        (category, current_categories.get(category, 0) - previous_categories.get(category, 0))
        for category in set(current_categories) | set(previous_categories)
    ]
    if not changes:
        return f"按{basis_label}口径，本期支出较上期{direction} ¥{abs(delta):,.2f}，主要受退款影响。"
    largest_category, largest_change = max(changes, key=lambda item: abs(item[1]))
    category_direction = "增加" if largest_change > 0 else "减少"
    return (
        f"按{basis_label}口径，本期支出较上期{direction} ¥{abs(delta):,.2f}；"
        f"变化最大的是{largest_category}，{category_direction} ¥{abs(largest_change):,.2f}。"
    )


def render_budget_status(
    label: str,
    actual: float,
    budget: float | None,
    projected: float | None = None,
):
    if budget is None:
        st.caption(f"{label}尚未设置上限")
        return

    ratio = actual / budget if budget else 0
    st.progress(
        max(0.0, min(ratio, 1.0)),
        text=f"{label}：¥{actual:,.2f} / ¥{budget:,.2f}（{ratio:.0%}）",
    )
    if ratio >= 1:
        st.error(f"{label}已超出 ¥{actual - budget:,.2f}。")
    elif projected is not None and projected > budget:
        st.warning(f"按当前日均速度，月底预计 ¥{projected:,.2f}，可能超出 ¥{projected - budget:,.2f}。")
    elif ratio >= 0.8:
        st.warning(f"{label}已达到 80%，剩余 ¥{budget - actual:,.2f}。")
    else:
        st.caption(f"{label}剩余 ¥{budget - actual:,.2f}")


# ── 页面主体 ────────────────────────────────────────────────────────────────
tab_month, tab_year = st.tabs(["月", "年"])


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
        selected_ym = st.selectbox(
            "选择月份", months, index=default_idx, key="month_sel"
        )

        y, m = int(selected_ym[:4]), int(selected_ym[5:])
        start = f"{y:04d}-{m:02d}-01"
        if m == 12:
            next_first = date(y + 1, 1, 1)
        else:
            next_first = date(y, m + 1, 1)
        end = (next_first - timedelta(days=1)).isoformat()
        n_days = (next_first - date(y, m, 1)).days

        all_dates = [
            (date(y, m, 1) + timedelta(days=i)).isoformat() for i in range(n_days)
        ]

        cur = get_period_data(start, end, basis=basis_key)

        # 上个月
        if m == 1:
            prev_start = f"{y - 1:04d}-12-01"
            prev_end = f"{y:04d}-01-01"
            prev_end = (date(y, 1, 1) - timedelta(days=1)).isoformat()
        else:
            prev_start = f"{y:04d}-{m - 1:02d}-01"
            prev_end = (date(y, m, 1) - timedelta(days=1)).isoformat()
        prev = get_period_data(prev_start, prev_end, basis=basis_key)

        metrics_row(cur, prev, n_days=n_days)
        budget = get_month_budget(selected_ym)
        cash_data = cur if basis_key == "cash" else get_period_data(start, end, "cash")
        amortized_data = (
            cur if basis_key == "amortized" else get_period_data(start, end, "amortized")
        )
        elapsed_days = today.day if selected_ym == cur_ym else None
        cash_projection = (
            cash_data["expense"] / elapsed_days * n_days if elapsed_days else None
        )
        amortized_projection = (
            amortized_data["expense"] / elapsed_days * n_days if elapsed_days else None
        )
        budget_col, cash_col = st.columns(2)
        with budget_col:
            render_budget_status(
                "摊销后成本上限",
                amortized_data["expense"],
                budget["amortized_total"],
                amortized_projection,
            )
        with cash_col:
            render_budget_status(
                "现金流上限",
                cash_data["expense"],
                budget["cash_total"],
                cash_projection,
            )
        with st.expander("设置本月预算"):
            with st.form("month_budget_form"):
                budget_col, cash_col = st.columns(2)
                with budget_col:
                    amortized_total = st.number_input(
                        "摊销后成本上限（元）",
                        min_value=0.0,
                        value=float(budget["amortized_total"] or 0),
                        format="%.2f",
                        help="0 表示不设置该上限。",
                    )
                with cash_col:
                    cash_total = st.number_input(
                        "现金流上限（元）",
                        min_value=0.0,
                        value=float(budget["cash_total"] or 0),
                        format="%.2f",
                        help="0 表示不设置该上限。",
                    )
                if st.form_submit_button("保存预算", type="primary"):
                    save_month_budget(
                        selected_ym,
                        amortized_total=amortized_total if amortized_total > 0 else None,
                        cash_total=cash_total if cash_total > 0 else None,
                    )
                    st.rerun()
        st.info(trend_summary(cur, prev, analysis_basis))
        st.caption("本月每日收支")
        daily_line(cur["daily"], all_dates)

        # 最近 12 个月对比
        st.caption("最近 12 个月对比")
        recent_months = months[:12][::-1]
        period_bars = []
        for ym in recent_months:
            yy, mm = int(ym[:4]), int(ym[5:])
            ms = f"{yy:04d}-{mm:02d}-01"
            if mm == 12:
                me = (date(yy + 1, 1, 1) - timedelta(days=1)).isoformat()
            else:
                me = (date(yy, mm + 1, 1) - timedelta(days=1)).isoformat()
            d = get_period_data(ms, me, basis=basis_key)
            period_bars.append(
                {"label": ym, "income": d["income"], "expense": d["expense"]}
            )
        period_compare_bar(period_bars)

        breakdown_level = st.radio(
            "明细聚合",
            ["一级分类", "二级分类"],
            horizontal=True,
            key="month_breakdown_level",
        )
        st.subheader("支出明细")
        expense_breakdown = aggregate_breakdown(cur["expense_breakdown"], breakdown_level)
        breakdown_chart(expense_breakdown, breakdown_level)
        with st.expander("查看收入明细"):
            breakdown_table(
                aggregate_breakdown(cur["income_breakdown"], breakdown_level),
                "收入",
                breakdown_level,
            )

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
        selected_year = st.selectbox(
            "选择年份", years, index=default_idx, key="year_sel"
        )

        start = f"{selected_year}-01-01"
        end = f"{selected_year}-12-31"

        # 按月生成 all_dates（用月份标签，不是每天）
        all_months = [f"{selected_year}-{m:02d}" for m in range(1, 13)]
        # 年视图按月聚合。
        cur = get_period_data(start, end, basis=basis_key)

        # 上一年
        prev_year = str(int(selected_year) - 1)
        prev = get_period_data(
            f"{prev_year}-01-01", f"{prev_year}-12-31", basis=basis_key
        )
        n_days = 366 if int(selected_year) % 4 == 0 else 365

        metrics_row(cur, prev, n_days=n_days)

        # 年视图：按月聚合柱状图
        st.caption("本年各月收支")
        month_bars = []
        for ym in all_months:
            yy, mm = int(ym[:4]), int(ym[5:])
            ms = f"{yy:04d}-{mm:02d}-01"
            me = (
                (date(yy, mm + 1, 1) - timedelta(days=1)).isoformat()
                if mm < 12
                else f"{yy}-12-31"
            )
            d = get_period_data(ms, me, basis=basis_key)
            month_bars.append(
                {"label": f"{mm}月", "income": d["income"], "expense": d["expense"]}
            )
        period_compare_bar(month_bars)

        # 历年对比
        st.caption("历年对比")
        year_bars = []
        for yr in years[::-1]:
            d = get_period_data(f"{yr}-01-01", f"{yr}-12-31", basis=basis_key)
            year_bars.append(
                {"label": yr, "income": d["income"], "expense": d["expense"]}
            )
        period_compare_bar(year_bars)

        breakdown_level = st.radio(
            "明细聚合",
            ["一级分类", "二级分类"],
            horizontal=True,
            key="year_breakdown_level",
        )
        st.subheader("支出明细")
        expense_breakdown = aggregate_breakdown(cur["expense_breakdown"], breakdown_level)
        breakdown_chart(expense_breakdown, breakdown_level)
        with st.expander("查看收入明细"):
            breakdown_table(
                aggregate_breakdown(cur["income_breakdown"], breakdown_level),
                "收入",
                breakdown_level,
            )
