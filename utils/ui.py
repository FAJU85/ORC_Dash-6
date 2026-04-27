"""
Shared UI utilities: theme injection, chart theming, and theme toggle button.
Call apply_theme() on every page immediately after st.set_page_config().
"""

import streamlit as st

# ---------------------------------------------------------------------------
# CSS blocks
# ---------------------------------------------------------------------------

_COMMON_CSS = """
<style>
    #MainMenu {visibility: hidden !important;}
    footer {visibility: hidden !important;}
    .stDeployButton {display: none !important;}

    @media (max-width: 768px) {
        .metric-row { flex-direction: column !important; }
        .metric-col { min-width: 100% !important; margin-bottom: 0.5rem; }
        .nav-links { flex-wrap: wrap !important; justify-content: center !important; }
        .nav-btn { font-size: 0.75rem !important; padding: 0.4rem 0.6rem !important; }
    }

    .stColumn { min-width: 150px; }
    .metric-card { padding: 1rem; border-radius: 8px; text-align: center; }
    .footer-divider { margin: 1rem 0; }
</style>
"""

_DARK_CSS = """
<style>
    .stApp { background-color: #0f172a; }
    h1, h2, h3, h4, h5, h6, p, span { color: white !important; }
    .stMetric label { color: #94a3b8 !important; }
    .metric-card { background: #1e293b; border: 1px solid #334155; }
    .pub-item {
        background: #1e293b;
        border-left: 3px solid #06b6d4;
        padding: 0.75rem 1rem;
        border-radius: 4px;
        margin-bottom: 0.5rem;
    }
    .status-card { background: #1e293b; border: 1px solid #334155; }
    .text-muted { color: #94a3b8; }
</style>
"""

_LIGHT_CSS = """
<style>
    .stApp { background-color: #f8fafc; }
    h1, h2, h3, h4, h5, h6, p, span { color: #1e293b !important; }
    .stMetric label { color: #475569 !important; }
    .stMetric [data-testid="stMetricValue"] { color: #1e293b !important; }
    .metric-card { background: #ffffff; border: 1px solid #e2e8f0; }
    .pub-item {
        background: #ffffff;
        border-left: 3px solid #0ea5e9;
        padding: 0.75rem 1rem;
        border-radius: 4px;
        margin-bottom: 0.5rem;
    }
    .status-card { background: #ffffff; border: 1px solid #e2e8f0; }
    .text-muted { color: #475569; }
</style>
"""

# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def apply_theme() -> None:
    """Initialise session theme state, honour query-param overrides, inject CSS.

    Must be called on every page after st.set_page_config().
    """
    if "theme_mode" not in st.session_state:
        st.session_state.theme_mode = "dark"

    # Allow ?theme=light / ?theme=dark in the URL to override session state.
    params = st.query_params
    if "theme" in params and params["theme"] in ("light", "dark"):
        st.session_state.theme_mode = params["theme"]

    st.markdown(_COMMON_CSS, unsafe_allow_html=True)

    if st.session_state.theme_mode == "light":
        st.markdown(_LIGHT_CSS, unsafe_allow_html=True)
    else:
        st.markdown(_DARK_CSS, unsafe_allow_html=True)


def theme_toggle_button() -> None:
    """Render a light/dark mode toggle button."""
    if st.session_state.get("theme_mode", "dark") == "dark":
        if st.button("☀️ Light Mode", use_container_width=True):
            st.query_params["theme"] = "light"
            st.rerun()
    else:
        if st.button("🌙 Dark Mode", use_container_width=True):
            st.query_params["theme"] = "dark"
            st.rerun()


def get_chart_theme() -> dict:
    """Return Plotly layout kwargs that match the active UI theme."""
    if st.session_state.get("theme_mode", "dark") == "light":
        font_color = "#1e293b"
    else:
        font_color = "#94a3b8"
    return {
        "font_color": font_color,
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor": "rgba(0,0,0,0)",
    }
