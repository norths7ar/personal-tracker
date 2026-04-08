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
            st.dataframe(df, hide_index=True, use_container_width=True)
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
        f"**{form['type']}**　{form['description']}　"
        f"¥{form['amount']:.2f}　{form['date']}"
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
            if st.button("保存", type="primary", use_container_width=True):
                save_and_done(form, category, subcategory)
        with c2:
            if st.button("取消", use_container_width=True):
                cancel()

    # 支出低置信度：从候选中选
    elif result["status"] == "low_confidence":
        st.warning(f"置信度较低（{result['confidence']:.0%}），请确认分类")
        st.caption(f"理由：{result['reasoning']}")

        options = [(result["category"], result["subcategory"], result["confidence"])]
        for c in result["candidates"]:
            pair = (c["category"], c["subcategory"])
            if pair not in [(o[0], o[1]) for o in options]:
                options.append((c["category"], c["subcategory"], c["confidence"]))

        selected = st.radio(
            "选择分类",
            options,
            format_func=lambda o: f"{o[0]} / {o[1]}（{o[2]:.0%}）",
        )
        c1, c2 = st.columns(2)
        with c1:
            if st.button("确认保存", type="primary", use_container_width=True):
                save_and_done(form, selected[0], selected[1], confidence=selected[2])
        with c2:
            if st.button("取消", use_container_width=True):
                cancel()

    # 支出新类别：确认或修改
    elif result["status"] == "new_category":
        st.info(f"识别到新类别：**{result['category']} / {result['subcategory']}**（不在 config.yaml 中）")
        st.caption(f"理由：{result['reasoning']}")
        col1, col2 = st.columns(2)
        with col1:
            category = st.text_input("主类别", value=result["category"])
        with col2:
            subcategory = st.text_input("子类别", value=result["subcategory"])
        c1, c2 = st.columns(2)
        with c1:
            if st.button("确认保存", type="primary", use_container_width=True):
                save_and_done(form, category, subcategory, confidence=result["confidence"])
        with c2:
            if st.button("取消", use_container_width=True):
                cancel()

    # LLM 出错：手动选
    elif result["status"] == "error":
        st.error(f"自动分类失败：{result['reasoning']}")
        cats = load_config().get("支出", {})
        col1, col2 = st.columns(2)
        with col1:
            category = st.selectbox("主类别", list(cats.keys()))
        with col2:
            subcategory = st.selectbox("子类别", cats.get(category, []))
        c1, c2 = st.columns(2)
        with c1:
            if st.button("保存", type="primary", use_container_width=True):
                save_and_done(form, category, subcategory)
        with c2:
            if st.button("取消", use_container_width=True):
                cancel()

    st.stop()


# ── 输入表单 ────────────────────────────────────────────────────────────────
with st.form("entry_form", clear_on_submit=True):
    entry_type = st.radio("类型", ["支出", "收入", "迁移"], horizontal=True)
    description = st.text_input("描述", placeholder="例：中午麦当劳")
    col1, col2 = st.columns(2)
    with col1:
        amount = st.number_input("金额（元）", min_value=0.0, value=0.0, step=1.0, format="%.2f")
    with col2:
        entry_date = st.date_input("日期", value=date.today())
    notes = st.text_area("备注（可选）", height=68)
    submitted = st.form_submit_button("提交", type="primary", use_container_width=True)

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
