import streamlit as st
from core.db import init_db

init_db()

pages = [
    st.Page("pages/1_记账.py",  title="记一笔", icon="✏️"),
    st.Page("pages/2_分析.py",  title="报表",   icon="📊"),
    st.Page("pages/3_记录.py",  title="流水",   icon="📋"),
    st.Page("pages/4_饮食记录.py", title="饮食记录", icon="🍽️"),
    st.Page("pages/5_饮食查看.py", title="饮食查看", icon="📋"),
]
pg = st.navigation(pages)
pg.run()
