"""
Compatibility bridge: delegates to utils/styles.py (enterprise design system).
Any page that imports from utils.ui automatically gets the full enterprise CSS.
"""

import streamlit as st
import requests

from utils.styles import (
    apply_styles, get_theme, theme_toggle_html,
    footer_html, DARK, LIGHT,
    chart_layout, chart_colors,
)


def apply_theme() -> None:
    """Alias for apply_styles() — honours ?theme= query param and injects CSS."""
    apply_styles()


def theme_toggle_button() -> None:
    """Render a light/dark mode toggle button."""
    label = theme_toggle_html()
    if st.button(label, use_container_width=True):
        new_theme = "light" if get_theme() == "dark" else "dark"
        st.query_params["theme"] = new_theme
        st.rerun()


def get_chart_theme() -> dict:
    """Return Plotly layout kwargs matching the active UI theme."""
    return chart_layout()


@st.cache_data(ttl=120)
def check_openalex_status() -> bool:
    """Cached OpenAlex connectivity check (at most once every 2 minutes)."""
    try:
        r = requests.get("https://api.openalex.org/works?per_page=1", timeout=5)
        return r.status_code == 200
    except Exception:
        return False


def render_system_status(show_email: bool = False, show_telegram: bool = False) -> None:
    """Render service-status cards with enterprise styling."""
    from utils.security import is_db_configured, get_secret, get_nested_secret

    colors = DARK if get_theme() == "dark" else LIGHT

    def _card(label, ok, ok_txt, warn_txt, is_info=False):
        c = colors["success"] if ok else (colors["muted"] if is_info else colors["warning"])
        txt = ok_txt if ok else warn_txt
        return (
            f'<div class="orc-card" style="padding:0.9rem 1.25rem">'
            f'<div style="font-weight:600;font-size:0.85rem;margin-bottom:0.2rem">{label}</div>'
            f'<div style="font-size:0.78rem;color:{c}">{txt}</div>'
            f'</div>'
        )

    num_cols = 3 + int(show_email) + int(show_telegram)
    cols = st.columns(num_cols)

    db_ok = is_db_configured()
    ai_ok = bool(
        get_secret("AI_API_KEY") or get_secret("GROQ_API_KEY")
        or get_secret("GROQ_API") or get_secret("GROQ_TOKEN")
    )
    oa_ok = check_openalex_status()

    cols[0].markdown(_card("Database",    db_ok, "Connected",  "Not configured"), unsafe_allow_html=True)
    cols[1].markdown(_card("AI Service",  ai_ok, "Ready",      "Not configured"), unsafe_allow_html=True)
    cols[2].markdown(_card("Data Source", oa_ok, "Online",     "Unavailable"),    unsafe_allow_html=True)

    if show_email:
        email_ok = bool(get_nested_secret("smtp", "user"))
        cols[3].markdown(_card("Email",   email_ok, "Configured", "Demo mode"), unsafe_allow_html=True)

    if show_telegram:
        tg_ok = bool(get_nested_secret("telegram", "bot_token"))
        cols[4].markdown(_card("Notifications", tg_ok, "Configured", "Optional", is_info=True), unsafe_allow_html=True)


def render_empty_state(
    title: str,
    message: str,
    cta_label: str = "",
    cta_page: str = "",
) -> None:
    """Render a centred empty-state card with an optional call-to-action link."""
    colors = DARK if get_theme() == "dark" else LIGHT
    st.markdown(
        f'<div class="orc-card" style="text-align:center;padding:2.5rem;">'
        f'<div style="font-size:2.5rem;margin-bottom:0.75rem">📭</div>'
        f'<div style="font-weight:600;font-size:1rem;margin-bottom:0.25rem">{title}</div>'
        f'<div style="font-size:0.85rem;color:{colors["text2"]}">{message}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )
    if cta_label and cta_page:
        _, btn_col, _ = st.columns([2, 1, 2])
        with btn_col:
            st.page_link(cta_page, label=cta_label, use_container_width=True)


def render_footer(note: str = "") -> None:
    """Render the standard page footer."""
    st.divider()
    st.markdown(footer_html(note), unsafe_allow_html=True)
