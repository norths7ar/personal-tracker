import hmac

import streamlit as st

from core.secrets import get_secret


def _auth_enabled() -> bool:
    value = (get_secret("AUTH_ENABLED", "false") or "false").strip().lower()
    return value in {"1", "true", "yes", "on"}


def require_login():
    if not _auth_enabled():
        return

    password = get_secret("APP_PASSWORD")
    if not password:
        st.error("AUTH_ENABLED is true, but APP_PASSWORD is not configured.")
        st.stop()

    if st.session_state.get("authenticated"):
        with st.sidebar:
            if st.button("退出登录"):
                st.session_state.authenticated = False
                st.rerun()
        return

    st.title("personal-tracker")
    st.caption("请输入访问密码。")
    submitted_password = st.text_input("密码", type="password")

    if submitted_password:
        if hmac.compare_digest(submitted_password, password):
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("密码不正确。")

    st.stop()
