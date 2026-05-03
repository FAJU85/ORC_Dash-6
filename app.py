"""
ORC Research Dashboard - Main Application
Secure, production-ready academic analytics platform
"""

import streamlit as st
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import requests

from utils.security import (
    get_secret, get_nested_secret, execute_query,
    is_db_configured, init_session, log_audit
)
from utils.hf_data import load_publications, get_active_researchers
from utils.styles import (
    apply_styles, get_theme, theme_toggle_html,
    metric_card_html, pub_card_html, section_title_html,
    hero_html, footer_html, DARK, LIGHT
)

st.set_page_config(
    page_title="ORC Research Dashboard",
    page_icon="https://i.ibb.co/C3m0Gs0p/ORC-LOGO2-page-0001-1.jpg",
    layout="wide",
    initial_sidebar_state="auto",
)

init_session()
apply_styles()

colors = DARK if get_theme() == "dark" else LIGHT

# ── Header ────────────────────────────────────────────────────────────────────
col_title, col_toggle = st.columns([8, 1])
with col_title:
    st.markdown(
        hero_html("🔬 ORC Research Dashboard",
                  "Academic Analytics & Publication Intelligence Platform"),
        unsafe_allow_html=True,
    )
with col_toggle:
    st.write("")
    st.write("")
    st.write("")
    if st.button(theme_toggle_html(), use_container_width=True):
        new_theme = "light" if get_theme() == "dark" else "dark"
        st.query_params["theme"] = new_theme
        st.rerun()

# ── Research Metrics ─────────────────────────────────────────────────────────
st.markdown(section_title_html("Research Metrics"), unsafe_allow_html=True)

metrics, _ = execute_query("""
    SELECT
        COUNT(*) as total_pubs,
        COALESCE(SUM(citation_count), 0) as total_citations,
        COALESCE(AVG(citation_count), 0) as avg_citations,
        SUM(CASE WHEN open_access = 1 THEN 1 ELSE 0 END) as oa_count
    FROM publications
""")

h_index = 0
h_data, _ = execute_query("SELECT citation_count FROM publications ORDER BY citation_count DESC")
if h_data:
    for i, row in enumerate(h_data, 1):
        if (row.get("citation_count") or 0) >= i:
            h_index = i
        else:
            break

if metrics and metrics[0].get("total_pubs", 0):
    m = metrics[0]
    total_pubs  = m.get("total_pubs", 0)
    total_cit   = m.get("total_citations", 0)
    avg_cit     = m.get("avg_citations", 0) or 0
    oa_count    = m.get("oa_count", 0) or 0

    c1, c2, c3, c4, c5 = st.columns(5)
    for col, icon, val, lbl in [
        (c1, "📄", f"{total_pubs:,}",    "Publications"),
        (c2, "📈", f"{total_cit:,}",     "Citations"),
        (c3, "🎯", str(h_index),         "h-index"),
        (c4, "📊", f"{avg_cit:.1f}",     "Avg Citations"),
        (c5, "🔓", str(int(oa_count)),   "Open Access"),
    ]:
        col.markdown(metric_card_html(icon, val, lbl), unsafe_allow_html=True)
else:
    st.markdown(
        f'<div class="orc-card" style="text-align:center;padding:2rem;">'
        f'<div style="font-size:2rem;margin-bottom:0.5rem">📭</div>'
        f'<div style="font-weight:600;margin-bottom:0.25rem">No publications yet</div>'
        f'<div style="font-size:0.85rem;color:{colors["text2"]}">Use the <strong>Publications</strong> page to sync from OpenAlex</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

# ── System Status ─────────────────────────────────────────────────────────────
st.markdown(section_title_html("System Status"), unsafe_allow_html=True)


@st.cache_data(ttl=120)
def _openalex_status() -> bool:
    try:
        return requests.get("https://api.openalex.org/works?per_page=1", timeout=4).status_code == 200
    except Exception:
        return False


def _dot(ok: bool) -> str:
    """
    Return an HTML span representing a status dot colored for success or warning.
    
    Parameters:
        ok (bool): If True, the dot uses the success color; if False, it uses the warning color.
    
    Returns:
        str: HTML string for a <span> element with class "orc-dot" and an inline background color.
    """
    c = colors["success"] if ok else colors["warning"]
    return f'<span class="orc-dot" style="background:{c}"></span>'


def _status_block(icon, label, ok, detail):
    """
    Render a compact status card HTML snippet for a system component.
    
    Parameters:
        icon (str): HTML or emoji used as the card icon.
        label (str): Human-readable name of the component (displayed prominently).
        ok (bool): Component health flag; when true the card shows the connected state.
        detail (str): Text to display when the component is not connected.
    
    Returns:
        html (str): HTML string for the status card. When `ok` is true the card displays "Connected"; otherwise it displays `detail`. The card includes a colored status dot, the icon, and the label.
    """
    dot = _dot(ok)
    msg = "Connected" if ok else detail
    return (
        f'<div class="orc-card" style="display:flex;align-items:center;gap:0.75rem;padding:0.9rem 1.2rem;">'
        f'  <span style="font-size:1.3rem">{icon}</span>'
        f'  <div>'
        f'    <div style="font-weight:600;font-size:0.88rem">{label}</div>'
        f'    <div style="font-size:0.76rem;color:{colors["text2"]}">{dot}{msg}</div>'
        f'  </div>'
        f'</div>'
    )


db_ok = is_db_configured()
ai_ok = bool(get_secret("AI_API_KEY") or get_secret("GROQ_API_KEY"))
oa_ok = _openalex_status()

c1, c2, c3 = st.columns(3)
c1.markdown(_status_block("🗄️", "Data Storage",  db_ok, "Not configured"), unsafe_allow_html=True)
c2.markdown(_status_block("🤖", "AI Service",     ai_ok, "Not configured"), unsafe_allow_html=True)
c3.markdown(_status_block("🔗", "OpenAlex API",   oa_ok, "Unavailable"),    unsafe_allow_html=True)

# ── Researchers ───────────────────────────────────────────────────────────────
researchers = get_active_researchers()
if researchers:
    st.markdown(section_title_html("Researchers"), unsafe_allow_html=True)
    cols = st.columns(min(len(researchers), 3))
    for col, r in zip(cols, researchers[:3]):
        pubs = load_publications(orcid=r.get("orcid", ""))
        col.markdown(
            f'<div class="orc-card">'
            f'  <div style="font-weight:600;font-size:0.95rem">{r.get("name", "—")}</div>'
            f'  <div style="font-size:0.78rem;color:{colors["text2"]};margin:0.15rem 0">'
            f'    {r.get("institution", "")}</div>'
            f'  <div style="font-size:0.76rem;color:{colors["muted"]};font-family:monospace">'
            f'    {r.get("orcid", "")}</div>'
            f'  <div style="margin-top:0.5rem;font-size:0.8rem;font-weight:600;color:{colors["accent"]}">'
            f'    {len(pubs)} publication{"s" if len(pubs) != 1 else ""}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
else:
    name        = get_nested_secret("researcher", "name", "Not configured")
    orcid       = get_nested_secret("researcher", "orcid", "")
    institution = get_nested_secret("researcher", "institution", "")
    if name != "Not configured":
        st.markdown(section_title_html("Researcher"), unsafe_allow_html=True)
        st.markdown(
            f'<div class="orc-card" style="max-width:420px">'
            f'  <div style="font-weight:600;font-size:1rem">{name}</div>'
            f'  <div style="font-size:0.82rem;color:{colors["text2"]}">{institution}</div>'
            f'  <div style="font-size:0.76rem;color:{colors["muted"]};font-family:monospace;margin-top:0.25rem">{orcid}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

# ── Recent Publications ───────────────────────────────────────────────────────
pubs, _ = execute_query("""
    SELECT title, journal_name, publication_year, citation_count, open_access, authors
    FROM publications
    ORDER BY publication_year DESC, citation_count DESC
    LIMIT 5
""")

if pubs:
    st.markdown(section_title_html("Recent Publications"), unsafe_allow_html=True)
    for pub in pubs:
        authors = pub.get("authors", [])
        if not isinstance(authors, list):
            authors = []
        st.markdown(
            pub_card_html(
                title    = (pub.get("title") or "Untitled")[:120],
                authors  = authors,
                journal  = pub.get("journal_name") or "Unknown",
                year     = pub.get("publication_year"),
                citations= pub.get("citation_count") or 0,
                is_oa    = bool(pub.get("open_access")),
            ),
            unsafe_allow_html=True,
        )

# ── Footer ────────────────────────────────────────────────────────────────────
st.divider()
st.markdown(footer_html(), unsafe_allow_html=True)
