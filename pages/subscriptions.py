from datetime import date, timedelta

import pandas as pd
import streamlit as st

from core.config import load_config
from core.constants import (
    RECURRING_PAYMENT_PREPAID,
    RECURRING_PAYMENT_SUBSCRIPTION,
    SUBSCRIPTION_CYCLE_CUSTOM,
    SUBSCRIPTION_CYCLE_MONTHLY,
    SUBSCRIPTION_CYCLE_ONE_TIME,
    SUBSCRIPTION_CYCLE_QUARTERLY,
    SUBSCRIPTION_CYCLE_YEARLY,
    SUBSCRIPTION_CYCLES,
    SUBSCRIPTION_STATUS_ACTIVE,
    SUBSCRIPTION_STATUSES,
    TYPE_EXPENSE,
)
from core.expense.db import add_transaction
from core.subscription.db import (
    add_subscription,
    delete_subscription,
    get_subscriptions,
    get_upcoming_subscriptions,
    update_subscription,
)
from core.text import display_text, optional_text

st.title("跨期费用")

if "recurring_delete_candidate" not in st.session_state:
    st.session_state.recurring_delete_candidate = None

config = load_config()
expense_categories = config.get(TYPE_EXPENSE, {})
today = date.today()

all_active = get_subscriptions(include_inactive=False)
subscriptions = [r for r in all_active if r["payment_type"] == RECURRING_PAYMENT_SUBSCRIPTION]
prepaid = [r for r in all_active if r["payment_type"] == RECURRING_PAYMENT_PREPAID]
upcoming = get_upcoming_subscriptions(
    today.isoformat(), (today + timedelta(days=31)).isoformat()
)

monthly_sub = sum(r["monthly_equivalent"] for r in subscriptions)
monthly_pre = sum(r["monthly_equivalent"] for r in prepaid)

# ── 顶部指标 ──────────────────────────────────────────────────────────────────

cols = st.columns(4)
cols[0].metric("订阅月成本", f"¥{monthly_sub:,.2f}", delta=f"{len(subscriptions)} 项")
cols[1].metric("预付月均摊销", f"¥{monthly_pre:,.2f}", delta=f"{len(prepaid)} 项")
cols[2].metric("合计月固定成本", f"¥{monthly_sub + monthly_pre:,.2f}")
cols[3].metric("31天内续费", f"¥{sum(r['amount'] for r in upcoming):,.2f}",
               delta=f"{len(upcoming)} 项")


# ── 辅助函数 ──────────────────────────────────────────────────────────────────

def _subcategory_options(category: str) -> list[str]:
    values = expense_categories.get(category) or []
    return values if values else [""]


def _date_or_none(value) -> date | None:
    text = display_text(value)
    return date.fromisoformat(text) if text else None


def _optional_date_input(label: str, value, key: str):
    enabled = st.checkbox(label, value=_date_or_none(value) is not None, key=f"{key}_enabled")
    if not enabled:
        return None
    return st.date_input(f"{label}日期", value=_date_or_none(value) or today, key=key)


def _category_widgets(key_prefix: str, cur_cat: str = "", cur_sub: str = ""):
    category_options = list(expense_categories.keys())
    default_cat = "通讯" if "通讯" in category_options else category_options[0]
    cat_idx = category_options.index(cur_cat) if cur_cat in category_options else category_options.index(default_cat)
    col1, col2 = st.columns(2)
    with col1:
        category = st.selectbox("主类别", category_options, index=cat_idx, key=f"{key_prefix}_cat")
    with col2:
        subs = _subcategory_options(category)
        default_sub = "平台会员" if "平台会员" in subs else subs[0]
        sub_idx = subs.index(cur_sub) if cur_sub in subs else (subs.index(default_sub) if default_sub in subs else 0)
        subcategory = st.selectbox("子类别", subs, index=sub_idx, key=f"{key_prefix}_sub")
    return category, subcategory


# ── 新增表单 ──────────────────────────────────────────────────────────────────

SUBSCRIPTION_CYCLES_ACTIVE = (
    SUBSCRIPTION_CYCLE_MONTHLY,
    SUBSCRIPTION_CYCLE_YEARLY,
    SUBSCRIPTION_CYCLE_QUARTERLY,
    SUBSCRIPTION_CYCLE_CUSTOM,
)

with st.expander("新增跨期费用", expanded=not all_active):
    payment_type = st.radio(
        "类型",
        [RECURRING_PAYMENT_SUBSCRIPTION, RECURRING_PAYMENT_PREPAID],
        format_func=lambda x: "订阅（周期自动续费）" if x == RECURRING_PAYMENT_SUBSCRIPTION else "预付（一次付清，按月摊销）",
        horizontal=True,
        key="add_payment_type",
    )

    with st.form("recurring_add_form", clear_on_submit=True):
        name = st.text_input("名称")
        vendor = st.text_input("商户 / 平台")
        amount = st.number_input("金额（元）", min_value=0.0, value=0.0, format="%.2f")

        if payment_type == RECURRING_PAYMENT_SUBSCRIPTION:
            col1, col2, col3 = st.columns(3)
            with col1:
                billing_cycle = st.selectbox("付费周期", list(SUBSCRIPTION_CYCLES_ACTIVE))
            with col2:
                custom_months = st.number_input(
                    "自定义月数", min_value=1, max_value=120, value=1, step=1,
                    disabled=billing_cycle != SUBSCRIPTION_CYCLE_CUSTOM,
                )
            with col3:
                auto_renew = st.checkbox("自动续费", value=True)

            col4, col5 = st.columns(2)
            with col4:
                start_date = st.date_input("开始日期", value=today)
            with col5:
                next_renewal_date = st.date_input("下次续费日期", value=today)

            payment_method = st.text_input("支付方式")
            category, subcategory = _category_widgets("add_sub")
            notes = st.text_area("备注", height=68)

            submitted = st.form_submit_button("保存订阅", type="primary", width="stretch")
            if submitted:
                if not name.strip():
                    st.error("名称不能为空。")
                elif amount <= 0:
                    st.error("金额必须大于 0。")
                else:
                    add_subscription(
                        name=name.strip(), vendor=optional_text(vendor), amount=amount,
                        billing_cycle=billing_cycle,
                        billing_interval_months=custom_months if billing_cycle == SUBSCRIPTION_CYCLE_CUSTOM else None,
                        start_date=start_date.isoformat(),
                        next_renewal_date=next_renewal_date.isoformat(),
                        category=category, subcategory=optional_text(subcategory),
                        payment_method=optional_text(payment_method),
                        auto_renew=auto_renew, notes=optional_text(notes),
                        payment_type=RECURRING_PAYMENT_SUBSCRIPTION,
                    )
                    st.success("订阅已保存。")
                    st.rerun()

        else:  # prepaid
            col1, col2 = st.columns(2)
            with col1:
                payment_date = st.date_input("付款日期", value=today)
            with col2:
                total_months = st.number_input("摊销月数", min_value=1, max_value=120, value=12, step=1)

            start_month = st.text_input(
                "摊销开始月份", value=today.strftime("%Y-%m"),
                placeholder="YYYY-MM",
                help="从哪个月开始分摊，默认为付款当月",
            )
            category, subcategory = _category_widgets("add_pre")
            notes = st.text_area("备注", height=68)

            submitted = st.form_submit_button("保存预付项目", type="primary", width="stretch")
            if submitted:
                if not name.strip():
                    st.error("名称不能为空。")
                elif amount <= 0:
                    st.error("金额必须大于 0。")
                else:
                    try:
                        amort_start = date.fromisoformat(f"{start_month.strip()}-01").isoformat()
                    except ValueError:
                        st.error("摊销开始月份格式必须是 YYYY-MM。")
                        st.stop()

                    tx_id = add_transaction(
                        TYPE_EXPENSE, name.strip(), amount, payment_date.isoformat(),
                        category=category, subcategory=optional_text(subcategory),
                        notes=optional_text(notes),
                        amortization_months=int(total_months),
                        amortization_start=amort_start,
                    )
                    add_subscription(
                        name=name.strip(), vendor=optional_text(vendor), amount=amount,
                        billing_cycle=SUBSCRIPTION_CYCLE_ONE_TIME,
                        billing_interval_months=int(total_months),
                        start_date=amort_start,
                        category=category, subcategory=optional_text(subcategory),
                        auto_renew=False, notes=optional_text(notes),
                        payment_type=RECURRING_PAYMENT_PREPAID,
                        transaction_id=tx_id,
                    )
                    st.success(f"预付项目已保存，同时已在账目中录入 ¥{amount:.2f} 支出（ID {tx_id}）。")
                    st.rerun()

# ── 列表 ──────────────────────────────────────────────────────────────────────

include_inactive = st.checkbox("显示暂停/取消", value=False)
rows = get_subscriptions(include_inactive=include_inactive)

if not rows:
    st.info("暂无记录。")
    st.stop()

df = pd.DataFrame(rows)

type_label = {
    RECURRING_PAYMENT_SUBSCRIPTION: "订阅",
    RECURRING_PAYMENT_PREPAID: "预付",
}

display_df = pd.DataFrame({
    "ID": df["id"],
    "类型": df["payment_type"].map(type_label).fillna("订阅"),
    "名称": df["name"],
    "商户": df["vendor"].apply(display_text),
    "金额": df["amount"].apply(lambda v: f"¥{float(v or 0):.2f}"),
    "周期/月数": df.apply(
        lambda r: f"{int(float(r.get('billing_interval_months') or 1))}个月"
        if r.get("payment_type") == RECURRING_PAYMENT_PREPAID
        else display_text(r.get("billing_cycle")),
        axis=1,
    ),
    "月均": df["monthly_equivalent"].apply(lambda v: f"¥{float(v or 0):.2f}"),
    "下次续费": df["next_renewal_date"].apply(display_text),
    "状态": df["status"],
    "主类别": df["category"].apply(display_text),
})

event = st.dataframe(
    display_df, hide_index=True, width="stretch",
    selection_mode="single-row", on_select="rerun",
    column_config={
        "ID": st.column_config.NumberColumn("ID", width="small"),
        "类型": st.column_config.TextColumn("类型", width="small"),
        "名称": st.column_config.TextColumn("名称"),
        "商户": st.column_config.TextColumn("商户"),
        "金额": st.column_config.TextColumn("金额"),
        "周期/月数": st.column_config.TextColumn("周期/月数"),
        "月均": st.column_config.TextColumn("月均"),
        "下次续费": st.column_config.TextColumn("下次续费"),
        "状态": st.column_config.TextColumn("状态"),
        "主类别": st.column_config.TextColumn("主类别"),
    },
)

if not event.selection.rows:
    st.caption("点击一行可编辑。")
    st.stop()

# ── 编辑面板 ──────────────────────────────────────────────────────────────────

record = df.iloc[event.selection.rows[0]].to_dict()
record_id = int(record["id"])
rec_payment_type = record.get("payment_type") or RECURRING_PAYMENT_SUBSCRIPTION

st.divider()
st.subheader(f"编辑 #{record_id}  ({'订阅' if rec_payment_type == RECURRING_PAYMENT_SUBSCRIPTION else '预付'})")

name = st.text_input("名称", value=display_text(record.get("name")), key=f"name_{record_id}")
vendor = st.text_input("商户 / 平台", value=display_text(record.get("vendor")), key=f"vendor_{record_id}")
amount = st.number_input("金额（元）", min_value=0.0, value=float(record.get("amount") or 0),
                         format="%.2f", key=f"amount_{record_id}")

cur_cat = display_text(record.get("category"))
cur_sub = display_text(record.get("subcategory"))
cat_options = list(expense_categories.keys())
cat_idx = cat_options.index(cur_cat) if cur_cat in cat_options else 0
col1, col2 = st.columns(2)
with col1:
    category = st.selectbox("主类别", cat_options, index=cat_idx, key=f"cat_{record_id}")
with col2:
    subs = _subcategory_options(category)
    sub_idx = subs.index(cur_sub) if cur_sub in subs else 0
    subcategory = st.selectbox("子类别", subs, index=sub_idx, key=f"sub_{record_id}_{category}")

if rec_payment_type == RECURRING_PAYMENT_SUBSCRIPTION:
    edit_col1, edit_col2, edit_col3 = st.columns(3)
    with edit_col1:
        cycle = display_text(record.get("billing_cycle"))
        billing_cycle = st.selectbox(
            "付费周期", list(SUBSCRIPTION_CYCLES),
            index=list(SUBSCRIPTION_CYCLES).index(cycle) if cycle in SUBSCRIPTION_CYCLES else 0,
            key=f"cycle_{record_id}",
        )
    with edit_col2:
        billing_interval_months = st.number_input(
            "自定义月数", min_value=1, max_value=120,
            value=max(1, int(record.get("billing_interval_months") or 1)),
            step=1, disabled=billing_cycle != SUBSCRIPTION_CYCLE_CUSTOM,
            key=f"interval_{record_id}",
        )
    with edit_col3:
        auto_renew = st.checkbox("自动续费", value=bool(record.get("auto_renew")), key=f"auto_renew_{record_id}")

    date_col1, date_col2, date_col3 = st.columns(3)
    with date_col1:
        start_date = _optional_date_input("开始", record.get("start_date"), f"start_{record_id}")
    with date_col2:
        next_renewal_date = _optional_date_input("下次续费", record.get("next_renewal_date"), f"next_{record_id}")
    with date_col3:
        end_date = _optional_date_input("结束", record.get("end_date"), f"end_{record_id}")

    payment_method = st.text_input("支付方式", value=display_text(record.get("payment_method")),
                                   key=f"payment_{record_id}")
    status = display_text(record.get("status")) or SUBSCRIPTION_STATUS_ACTIVE
    status = st.selectbox(
        "状态", list(SUBSCRIPTION_STATUSES),
        index=list(SUBSCRIPTION_STATUSES).index(status) if status in SUBSCRIPTION_STATUSES else 0,
        key=f"status_{record_id}",
    )
    notes = st.text_area("备注", value=display_text(record.get("notes")), height=68,
                         key=f"notes_{record_id}")

    btn1, btn2, btn3 = st.columns([2, 2, 1])
    with btn1:
        save = st.button("保存修改", type="primary", width="stretch")
    with btn2:
        cancel = st.button("取消", width="stretch")
    with btn3:
        delete_btn = st.button("删除", width="stretch")

    if save:
        if not name.strip():
            st.error("名称不能为空。")
            st.stop()
        update_subscription(
            record_id, name=name.strip(), vendor=optional_text(vendor), amount=amount,
            billing_cycle=billing_cycle,
            billing_interval_months=billing_interval_months if billing_cycle == SUBSCRIPTION_CYCLE_CUSTOM else None,
            start_date=start_date.isoformat() if start_date else None,
            next_renewal_date=next_renewal_date.isoformat() if next_renewal_date else None,
            end_date=end_date.isoformat() if end_date else None,
            category=category, subcategory=optional_text(subcategory),
            payment_method=optional_text(payment_method),
            auto_renew=auto_renew, status=status,
            notes=optional_text(notes),
        )
        st.success("已保存。")
        st.rerun()

    if cancel:
        st.rerun()

    if delete_btn:
        st.session_state.recurring_delete_candidate = record_id
        st.rerun()

else:  # prepaid — 编辑摊销信息（不能改已有流水，只改归类/备注/月数）
    total_months = st.number_input(
        "摊销月数", min_value=1, max_value=120,
        value=max(1, int(record.get("billing_interval_months") or 1)),
        step=1, key=f"months_{record_id}",
    )
    start_raw = display_text(record.get("start_date"))
    start_default = start_raw[:7] if start_raw else today.strftime("%Y-%m")
    start_month = st.text_input("摊销开始月份", value=start_default,
                                placeholder="YYYY-MM", key=f"start_month_{record_id}")
    notes = st.text_area("备注", value=display_text(record.get("notes")), height=68,
                         key=f"notes_{record_id}")

    tx_id = record.get("transaction_id")
    if tx_id:
        st.caption(f"关联流水 ID：{int(tx_id)}（金额和付款日期请到账目页修改）")

    btn1, btn2, btn3 = st.columns([2, 2, 1])
    with btn1:
        save = st.button("保存修改", type="primary", width="stretch")
    with btn2:
        cancel = st.button("取消", width="stretch")
    with btn3:
        delete_btn = st.button("删除", width="stretch")

    if save:
        if not name.strip():
            st.error("名称不能为空。")
            st.stop()
        try:
            amort_start = date.fromisoformat(f"{start_month.strip()}-01").isoformat()
        except ValueError:
            st.error("摊销开始月份格式必须是 YYYY-MM。")
            st.stop()
        update_subscription(
            record_id, name=name.strip(), vendor=optional_text(vendor), amount=amount,
            billing_interval_months=int(total_months),
            start_date=amort_start,
            category=category, subcategory=optional_text(subcategory),
            notes=optional_text(notes),
        )
        st.success("已保存。")
        st.rerun()

    if cancel:
        st.rerun()

    if delete_btn:
        st.session_state.recurring_delete_candidate = record_id
        st.rerun()

# ── 删除确认 ──────────────────────────────────────────────────────────────────

if st.session_state.recurring_delete_candidate == record_id:
    if rec_payment_type == RECURRING_PAYMENT_PREPAID and record.get("transaction_id"):
        st.warning(f"确认删除 #{record_id}？关联的流水记录（账目）不会被删除，仅移除跨期归属。")
    else:
        st.warning(f"确认删除 #{record_id}？")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("确认删除", type="primary", width="stretch", key=f"confirm_del_{record_id}"):
            delete_subscription(record_id)
            st.session_state.recurring_delete_candidate = None
            st.rerun()
    with c2:
        if st.button("取消删除", width="stretch", key=f"cancel_del_{record_id}"):
            st.session_state.recurring_delete_candidate = None
            st.rerun()
