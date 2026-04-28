"""
Shared UI utilities: theme injection, chart theming, theme toggle button,
and system status panel.
Call apply_theme() on every page immediately after st.set_page_config().
"""

import streamlit as st
import requests

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
    .pub-card-wrap { margin-bottom: 1.25rem; }
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


@st.cache_data(ttl=300)
def _check_openalex() -> bool:
    """Cached OpenAlex connectivity check — fires at most once every 5 minutes."""
    try:
        r = requests.get("https://api.openalex.org/works?per_page=1", timeout=5)
        return r.status_code == 200
    except Exception:
        return False


def render_system_status(show_email: bool = False, show_telegram: bool = False) -> None:
    """Render service status cards — no vendor names exposed in the UI.

    Args:
        show_email: also show the email service status column (Admin page).
        show_telegram: also show the notifications status column (Admin page).
    """
    from utils.security import is_db_configured, get_secret, get_nested_secret

    num_cols = 3 + int(show_email) + int(show_telegram)
    cols = st.columns(num_cols)

    with cols[0]:
        st.subheader("Database")
        if is_db_configured():
            st.success("✅ Connected")
        else:
            st.warning("⚠️ Not configured")

    with cols[1]:
        st.subheader("AI Service")
        ai_key = get_secret("AI_API_KEY") or get_secret("GROQ_API_KEY") or get_secret("GROQ_API")
        if ai_key and len(ai_key) > 5:
            st.success("✅ Ready")
        else:
            st.warning("⚠️ Not configured")

    with cols[2]:
        st.subheader("Data Source")
        if _check_openalex():
            st.success("✅ Online")
        else:
            st.warning("⚠️ Unavailable")

    if show_email:
        with cols[3]:
            st.subheader("Email Service")
            if get_nested_secret("smtp", "user"):
                st.success("✅ Configured")
            else:
                st.warning("⚠️ Demo mode")

    if show_telegram:
        with cols[4]:
            st.subheader("Notifications")
            if get_nested_secret("telegram", "bot_token"):
                st.success("✅ Configured")
            else:
                st.info("ℹ️ Optional")


def render_empty_state(
    title: str,
    message: str,
    cta_label: str = "",
    cta_page: str = "",
) -> None:
    """Render a centred empty-state card with an optional call-to-action link.

    Args:
        title:     Short headline (e.g. "No publications yet").
        message:   One-sentence explanation of what to do next.
        cta_label: Button / link label text. Omit to show no CTA.
        cta_page:  Streamlit page path for st.page_link (e.g. "pages/1_Publications.py").
    """
    st.markdown(
        f"<div style='text-align:center;padding:2.5rem 1rem;'>"
        f"<div style='font-size:2.5rem;margin-bottom:0.5rem'>📭</div>"
        f"<p style='font-size:1.1rem;font-weight:600;margin-bottom:0.25rem'>{title}</p>"
        f"<p class='text-muted' style='margin-bottom:1rem'>{message}</p>"
        f"</div>",
        unsafe_allow_html=True,
    )
    if cta_label and cta_page:
        _, btn_col, _ = st.columns([2, 1, 2])
        with btn_col:
            st.page_link(cta_page, label=cta_label, use_container_width=True)


def render_footer(note: str = "") -> None:
    """Render the standard page footer with an optional page-specific note above it.

    Args:
        note: Short contextual sentence shown as a caption above the divider.
    """
    if note:
        st.caption(note)
    st.divider()
    st.markdown(
        "<div style='text-align:center;font-size:0.85rem;line-height:1.8;'>"
        "<span class='text-muted'>Powered by "
        "<a href='https://www.linkedin.com/in/fahad-al-jubalie-55973926/' "
        "target='_blank' style='color:#06b6d4;text-decoration:none;'>Fahad Al-Jubalie</a>"
        "<br>All rights reserved to the "
        "<a href='https://obesitycenter.ksu.edu.sa/ar' "
        "target='_blank' style='color:#06b6d4;text-decoration:none;'>Obesity Research Center (ORC)</a>"
        "</span></div>",
        unsafe_allow_html=True,
    )
