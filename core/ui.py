import streamlit as st


def apply_app_style() -> None:
    """Keep utility pages readable on wide screens without constraining mobile."""
    st.markdown(
        """
        <style>
        .block-container {
            max-width: 1280px;
            padding-top: 1.75rem;
            padding-bottom: 3rem;
        }
        [data-testid="stDataFrame"] {
            border: 1px solid rgba(49, 51, 63, 0.16);
            border-radius: 6px;
        }
        @media (max-width: 768px) {
            .block-container {
                padding-left: 1rem;
                padding-right: 1rem;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )
