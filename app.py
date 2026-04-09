import streamlit as st
from core.db import init_db

init_db()

pages = [
    st.Page("pages/expense_entry.py",    title="开销记录", icon="✏️"),
    st.Page("pages/expense_ledger.py",   title="开销流水", icon="📋"),
    st.Page("pages/expense_analysis.py", title="开销分析", icon="📊"),
    st.Page("pages/diet_entry.py",       title="饮食记录", icon="🍽️"),
    st.Page("pages/diet_ledger.py",      title="饮食查看", icon="📋"),
    st.Page("pages/diet_analysis.py",    title="饮食分析", icon="📊"),
]
pg = st.navigation(pages)
pg.run()
