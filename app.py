import streamlit as st

from core import db as core_db
from core.auth import require_login
from core.ui import apply_app_style

st.set_page_config(layout="wide")
apply_app_style()

require_login()


@st.cache_resource(show_spinner=False)
def initialize_database(cache_key: str) -> None:
    core_db.init_db()


backend = core_db.get_backend()
database_location = (
    str(core_db.DB_PATH.resolve()) if backend == "sqlite" else "configured"
)
initialize_database(f"{backend}:{database_location}")

pages = [
    st.Page("pages/batch_entry.py", title="记录", icon="✏️"),
    st.Page("pages/expense_pending.py", title="待处理", icon="✅"),
    st.Page("pages/expense_ledger.py", title="账目", icon="📋"),
    st.Page("pages/expense_analysis.py", title="开销分析", icon="📊"),
    st.Page("pages/subscriptions.py", title="跨期费用", icon="🔄"),
    st.Page("pages/diet_ledger.py", title="饮食", icon="🍽️"),
]
pg = st.navigation(pages)
pg.run()
