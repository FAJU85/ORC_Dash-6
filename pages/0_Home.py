"""
ORC Research Dashboard - Home Page
Displays research metrics, system status, researchers, and recent publications.
"""

import streamlit as st
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.security import (
    get_secret, get_nested_secret,
    is_db_configured,
)
from utils.hf_data import (
    load_publications, get_active_researchers,
    get_publication_metrics, get_citation_sorted_counts, get_publications_sorted,
    load_cms_content,
)
from utils.styles import (
    apply_styles, get_theme, render_navbar,
    metric_card_html, pub_card_html, section_title_html,
    hero_html, footer_html, DARK, LIGHT,
)
from utils.ui import check_openalex_status

apply_styles()
render_navbar()

colors = DARK if get_theme() == "dark" else LIGHT

# ── CMS content ───────────────────────────────────────────────────────────────
_cms = st.session_state.get("_cms_override") or load_cms_content()

# ── Header ────────────────────────────────────────────────────────────────────
_hero = _cms.get("home_hero", {})
_hero_title    = _hero.get("title",    "").strip() or "🔬 ORC Research Dashboard"
_hero_subtitle = _hero.get("subtitle", "").strip() or "Academic Analytics & Publication Intelligence Platform"
st.markdown(hero_html(_hero_title, _hero_subtitle), unsafe_allow_html=True)

# ── Announcement banner ───────────────────────────────────────────────────────
_ann = _cms.get("home_announcement", {})
if _ann.get("enabled") and _ann.get("text", "").strip():
    _ann_color = _ann.get("color", "info")
    _ann_fn    = {"info": st.info, "success": st.success, "warning": st.warning}.get(_ann_color, st.info)
    _ann_fn(_ann.get("text", ""))

# ── Research Metrics ─────────────────────────────────────────────────────────
st.markdown(section_title_html("Research Metrics"), unsafe_allow_html=True)

m = get_publication_metrics()
h_index = sum(1 for i, c in enumerate(get_citation_sorted_counts(), 1) if c >= i)

if m.get("total_pubs", 0):
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
        f'<div style="font-size:0.85rem;color:{colors["text2"]}">Use the <strong>Publications</strong> page to sync your research data</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

# ── System Status ─────────────────────────────────────────────────────────────
st.markdown(section_title_html("System Status"), unsafe_allow_html=True)


def _dot(ok: bool) -> str:
    color = "#22c55e" if ok else "#ef4444"
    return (
        f'<span style="display:inline-block;width:7px;height:7px;'
        f'border-radius:50%;background:{color};margin-right:4px;'
        f'vertical-align:middle"></span>'
    )


def _status_block(icon: str, label: str, ok: bool, detail: str) -> str:
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
oa_ok = check_openalex_status()

c1, c2, c3 = st.columns(3)
c1.markdown(_status_block("🗄️", "Data Storage",  db_ok, "Not configured"), unsafe_allow_html=True)
c2.markdown(_status_block("🤖", "AI Service",     ai_ok, "Not configured"), unsafe_allow_html=True)
c3.markdown(_status_block("🔗", "Data Source",    oa_ok, "Unavailable"),    unsafe_allow_html=True)

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
pubs = get_publications_sorted("year", limit=5)

st.markdown(section_title_html("Recent Publications"), unsafe_allow_html=True)
if pubs:
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
else:
    st.caption("No recent publications yet.")

# ── Footer ────────────────────────────────────────────────────────────────────
st.divider()
st.markdown(footer_html(), unsafe_allow_html=True)
