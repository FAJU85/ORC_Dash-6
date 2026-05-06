"""
ORC Research Dashboard - User Settings & Export
"""

import streamlit as st
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.security import get_secret, get_nested_secret, execute_query, is_db_configured
from utils.hf_data import load_publications, get_active_researchers
from utils.export import export_to_csv, export_to_bibtex, format_citation
from utils.styles import apply_styles, get_theme, hero_html, section_title_html, footer_html, render_navbar, DARK, LIGHT
from utils.ui import check_openalex_status

apply_styles()
render_navbar()

colors = DARK if get_theme() == "dark" else LIGHT

# ============================================
# SESSION STATE
# ============================================

if "user_preferences" not in st.session_state:
    st.session_state.user_preferences = {
        'items_per_page': 10,
        'show_abstracts': True,
        'citation_style': 'APA',
        'auto_expand': False,
    }
if "confirm_reset_settings" not in st.session_state:
    st.session_state.confirm_reset_settings = False

# ============================================
# PAGE
# ============================================

st.markdown(hero_html("⚙️ Settings", "Customize your dashboard preferences and export publications"), unsafe_allow_html=True)

# Load a small sample for the inline citation preview (cheap, cached by Streamlit)
from utils.security import execute_query as _eq
_preview_pubs, _ = _eq("SELECT * FROM publications ORDER BY citation_count DESC LIMIT 3")
_preview_pubs = _preview_pubs or []

# ── Display Preferences ─────────────────────────────────────────────────────
st.markdown(section_title_html("Display Preferences"), unsafe_allow_html=True)

col1, col2 = st.columns(2)

with col1:
    items_per_page = st.select_slider(
        "Items per page",
        options=[5, 10, 15, 20, 25],
        value=st.session_state.user_preferences.get('items_per_page', 10),
        help="Number of publications per page",
    )
    citation_style = st.selectbox(
        "Citation Format",
        ["APA", "MLA", "Chicago", "Harvard", "IEEE"],
        index=["APA", "MLA", "Chicago", "Harvard", "IEEE"].index(
            st.session_state.user_preferences.get('citation_style', 'APA')
        ),
        help="Default format for citation display and exports",
    )
    if _preview_pubs:
        with st.expander("📖 Citation Preview"):
            for pub in _preview_pubs:
                st.markdown(f"• {format_citation(pub, citation_style)}")

with col2:
    show_abstracts = st.toggle(
        "Show abstracts by default",
        value=st.session_state.user_preferences.get('show_abstracts', True),
        help="Expand abstracts in publication list",
    )
    auto_expand = st.toggle(
        "Auto-expand paper details",
        value=st.session_state.user_preferences.get('auto_expand', False),
        help="Automatically show full details",
    )

# Save / Reset
sc1, sc2 = st.columns([1, 3])
with sc1:
    if st.button("💾 Save Settings", type="primary", use_container_width=True):
        st.session_state.user_preferences = {
            'items_per_page': items_per_page,
            'show_abstracts': show_abstracts,
            'citation_style': citation_style,
            'auto_expand': auto_expand,
        }
        st.success("✅ Settings saved!")
with sc2:
    if st.button("↩️ Reset to Defaults"):
        st.session_state.confirm_reset_settings = True
    
    if st.session_state.get("confirm_reset_settings"):
        st.warning("Are you sure you want to reset all preferences to their default values? This action cannot be undone.")
        col_reset_c1, col_reset_c2 = st.columns(2)
        with col_reset_c1:
            if st.button("Confirm Reset", key="confirm_reset_settings_yes", type="secondary", use_container_width=True):
                st.session_state.user_preferences = {
                    'items_per_page': 10,
                    'show_abstracts': True,
                    'citation_style': 'APA',
                    'auto_expand': False,
                }
                st.success("✅ Reset to defaults!")
                st.session_state.confirm_reset_settings = False
                st.rerun()
        with col_reset_c2:
            if st.button("Cancel Reset", key="confirm_reset_settings_no", use_container_width=True):
                st.session_state.confirm_reset_settings = False
                st.rerun()


# ── Export ──────────────────────────────────────────────────────────────────
st.markdown(section_title_html("Export Publications"), unsafe_allow_html=True)

researchers = get_active_researchers()
researcher_map = {r.get('name', r.get('orcid', '')): r.get('orcid') for r in researchers if r.get('orcid')}

ecol1, ecol2 = st.columns(2)

with ecol1:
    export_researcher = st.selectbox(
        "Researcher",
        ["All Researchers"] + list(researcher_map.keys()),
        help="Filter export by researcher",
    )
    export_format = st.selectbox(
        "Export format",
        ["CSV", "BibTeX", "JSON"],
        help="Choose the download format",
    )

with ecol2:
    include_abs_export = st.toggle("Include abstracts", value=True,
                                   help="Add abstracts to the exported file")

# Load publications for export
if export_researcher != "All Researchers" and export_researcher in researcher_map:
    export_pubs = load_publications(orcid=researcher_map[export_researcher])
else:
    result, _ = execute_query("SELECT * FROM publications ORDER BY publication_year DESC")
    export_pubs = result or []

st.markdown(
    f'<p style="font-size:0.82rem;color:{colors["text2"]};margin:0.25rem 0 0.75rem">'
    f'{len(export_pubs)} publication(s) ready for export.</p>',
    unsafe_allow_html=True,
)

if export_pubs:
    if export_format == "CSV":
        data   = export_to_csv(export_pubs, include_abstracts=include_abs_export)
        fname  = "publications.csv"
        mime   = "text/csv"
    elif export_format == "BibTeX":
        data   = export_to_bibtex(export_pubs).encode("utf-8")
        fname  = "publications.bib"
        mime   = "text/plain"
    else:
        # json is already imported at the top, no need for alias
        data   = json.dumps(export_pubs, indent=2, default=str).encode("utf-8")
        fname  = "publications.json"
        mime   = "application/json"

    st.download_button(
        label=f"⬇️ Download {export_format}",
        data=data,
        file_name=fname,
        mime=mime,
        type="primary",
        use_container_width=True,
    )

else:
    st.markdown(
        f'<div class="orc-card" style="padding:0.9rem 1.25rem">'
        f'<div style="font-size:0.85rem;color:{colors["text2"]}">No publications found. Sync from the <strong>Publications</strong> page first.</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

# ── Connection Status ───────────────────────────────────────────────────────
st.markdown(section_title_html("Connection Status"), unsafe_allow_html=True)


def _conn_card(label: str, ok: bool, ok_txt: str, fail_txt: str, optional: bool = False) -> str:
    """
    Builds an HTML status card for a connection check.
    
    Parameters:
        label (str): Title displayed on the card.
        ok (bool): Health flag; selects the success or warning style and message.
        ok_txt (str): Message displayed when `ok` is True.
        fail_txt (str): Message displayed when `ok` is False.
        optional (bool): If True, uses 'muted' color for fail state instead of 'warning'.
    
    Returns:
        html (str): An HTML fragment representing a themed status card containing the label and the selected message colored according to status.
    """
    if not ok and optional:
        status_color = colors["muted"]
    else:
        status_color = colors["success"] if ok else colors["warning"]
    txt = ok_txt if ok else fail_txt
    return (
        f'<div style="background:{colors["surface"]};border-radius:6px;'
        f'padding:0.9rem 1.25rem;margin-bottom:0.65rem;color:{colors["text"]}">'
        f'<div style="font-weight:600;font-size:0.85rem;margin-bottom:0.2rem;'
        f'color:{colors["text"]}">{label}</div>'
        f'<div style="font-size:0.78rem;color:{status_color}">{txt}</div>'
        f'</div>'
    )


oa_ok = check_openalex_status()

cc1, cc2, cc3 = st.columns(3)
_ai_key = bool(
    get_secret("AI_API_KEY") or get_secret("GROQ_API_KEY")
    or get_secret("GROQ_API") or get_secret("GROQ_TOKEN")
)
cc1.markdown(_conn_card("Database",    is_db_configured(), "Connected",  "Not configured"), unsafe_allow_html=True)
cc2.markdown(_conn_card("AI Service",  _ai_key,            "Available",  "Not configured — add AI_API_KEY or GROQ_API_KEY secret", optional=True), unsafe_allow_html=True)
cc3.markdown(_conn_card("Data Source", oa_ok,              "Online",     "Unavailable"),    unsafe_allow_html=True)

# ── About ───────────────────────────────────────────────────────────────────
st.markdown(section_title_html("About"), unsafe_allow_html=True)
st.markdown(
    f'<div class="orc-card" style="padding:1rem 1.5rem">'
    f'<div style="font-weight:700;font-size:0.95rem;margin-bottom:0.5rem">ORC Research Dashboard · v1.0</div>'
    f'<div style="font-size:0.83rem;color:{colors["text2"]};line-height:1.75">'
    f'📚 Automated publication tracking<br>'
    f'🔬 AI-powered research assistant<br>'
    f'📊 Interactive analytics &amp; visualizations<br>'
    f'📥 Export to CSV, BibTeX, JSON<br>'
    f'🔐 Secure admin panel with two-factor authentication'
    f'</div>'
    f'<div style="margin-top:0.75rem;font-size:0.8rem;color:{colors["muted"]}">'
    f'Need help? <a href="/Bug_Report" style="color:{colors["accent"]};text-decoration:none">Report a bug</a>'
    f'</div>'
    f'</div>',
    unsafe_allow_html=True,
)

# ── Footer ───────────────────────────────────────────────────────────────────
st.divider()
st.markdown(footer_html(), unsafe_allow_html=True)
