import streamlit as st
from datetime import date

import pandas as pd

from core.config import load_config
from core.db import init_db
from core.expense.classifier import Classifier
from core.expense.db import add_transaction, get_transactions

init_db()

st.title("记一笔")


@st.cache_resource
def get_classifier():
    return Classifier(load_config())


# ── session state 初始化 ────────────────────────────────────────────────────
for key, default in [("pending", None), ("flash", None)]:
    if key not in st.session_state:
        st.session_state[key] = default

# ── flash 消息（跨 rerun 的成功提示）──────────────────────────────────────
if st.session_state.flash:
    st.success(st.session_state.flash)
    st.session_state.flash = None

# ── 侧边栏：最近记录 ────────────────────────────────────────────────────────
with st.sidebar:
    st.subheader("最近记录")
    try:
        rows = get_transactions(limit=10)
        if rows:
            df = pd.DataFrame(rows)[["date", "type", "description", "amount", "category"]]
            df["amount"] = df["amount"].apply(lambda x: f"¥{x:.2f}")
            st.dataframe(df, hide_index=True, width="stretch")
        else:
            st.caption("暂无记录")
    except Exception as e:
        st.caption(f"加载失败：{e}")


# ── 工具函数 ────────────────────────────────────────────────────────────────
def save_and_done(form, category, subcategory, confidence=None):
    record_id = add_transaction(
        form["type"], form["description"], form["amount"], form["date"],
        category=category, subcategory=subcategory,
        notes=form["notes"], confidence=confidence,
    )
    st.session_state.pending = None
    st.session_state.flash = (
        f"已保存（ID {record_id}）：{form['type']} / {form['description']} / ¥{form['amount']:.2f}"
    )
    st.rerun()


# ── 确认界面（有 pending 时替代主表单）──────────────────────────────────────
if st.session_state.pending:
    form = st.session_state.pending["form"]
    result = st.session_state.pending["result"]

    st.caption(
        f"**{form['type']}** {form['description']} "
        f"¥{form['amount']:.2f} {form['date']}"
    )
    st.divider()

    def cancel():
        st.session_state.pending = None
        st.rerun()

    # 收入：从 config 选择分类
    if result is None:
        st.subheader("填写收入分类")
        income_cats = load_config().get("收入", {})
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
                save_and_done(form, category, subcategory)
        with c2:
            if st.button("取消", width="stretch"):
                cancel()

    # 支出需确认：低置信度 / LLM返回未知类别 / 出错，统一用 selectbox 预选
    elif result["status"] in ("low_confidence", "new_category", "error"):
        cats = load_config().get("支出", {})
        cat_keys = list(cats.keys())

        if result["status"] == "low_confidence":
            st.warning(f"置信度较低（{result['confidence']:.0%}），请确认分类")
        elif result["status"] == "new_category":
            st.warning(f"LLM 建议了未知分类（{result['category']} / {result['subcategory']}），请从下方选择")
        else:
            st.error(f"自动分类失败：{result['reasoning']}")

        if result.get("reasoning") and result["status"] != "error":
            st.caption(f"理由：{result['reasoning']}")

        # 预选 LLM 建议，不在列表内则默认第一项
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
                subcategory = category  # 无子类别时与主类别一致
                st.caption("（无子类别）")

        c1, c2 = st.columns(2)
        with c1:
            if st.button("确认保存", type="primary", width="stretch"):
                save_and_done(form, category, subcategory, confidence=result.get("confidence"))
        with c2:
            if st.button("取消", width="stretch"):
                cancel()

    st.stop()


# ── 输入表单 ────────────────────────────────────────────────────────────────
with st.form("entry_form", clear_on_submit=True):
    entry_type = st.radio("类型", ["支出", "收入", "迁移"], horizontal=True)
    description = st.text_input("描述", placeholder="例：中午麦当劳")
    col1, col2 = st.columns(2)
    with col1:
        amount = st.number_input("金额（元）", min_value=0.0, value=0.0, step=0.1, format="%.2f")
    with col2:
        entry_date = st.date_input("日期", value=date.today())
    notes = st.text_area("备注（可选）", height=68)
    submitted = st.form_submit_button("提交", type="primary", width="stretch")

if submitted:
    if not description.strip():
        st.error("请填写描述")
        st.stop()
    if amount <= 0:
        st.error("金额须大于 0")
        st.stop()

    form_data = {
        "type": entry_type,
        "description": description.strip(),
        "amount": amount,
        "date": entry_date.strftime("%Y-%m-%d"),
        "notes": notes.strip() or None,
    }

    if entry_type == "迁移":
        record_id = add_transaction(
            entry_type, description.strip(), amount, entry_date.strftime("%Y-%m-%d"),
            notes=notes.strip() or None,
        )
        st.session_state.flash = f"迁移记录已保存（ID {record_id}）"
        st.rerun()

    elif entry_type == "收入":
        st.session_state.pending = {"form": form_data, "result": None}
        st.rerun()

    else:  # 支出
        with st.spinner("分类中…"):
            result = get_classifier().classify(description.strip())

        if result["status"] == "confirmed":
            record_id = add_transaction(
                entry_type, description.strip(), amount, entry_date.strftime("%Y-%m-%d"),
                category=result["category"], subcategory=result["subcategory"],
                confidence=result["confidence"], notes=notes.strip() or None,
            )
            st.session_state.flash = (
                f"已保存（ID {record_id}）：{result['category']} / {result['subcategory']}"
                f"（{result['confidence']:.0%}）"
            )
            st.rerun()
        else:
            st.session_state.pending = {"form": form_data, "result": result}
            st.rerun()
