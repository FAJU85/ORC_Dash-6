"""
ORC Research Dashboard - User Settings & Export
"""

import streamlit as st
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.security import get_secret, get_nested_secret, is_db_configured
from utils.hf_data import load_publications, get_active_researchers
from utils.export import export_to_csv, export_to_bibtex, format_citation
from utils.ui import apply_theme
import requests

st.set_page_config(page_title="Settings", page_icon="⚙️", layout="wide")
apply_theme()

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

# ============================================
# PAGE
# ============================================

st.title("⚙️ Settings")
st.markdown("Customize your dashboard experience")
st.divider()

# ── Display Preferences ─────────────────────────────────────────────────────
st.header("🎨 Display Preferences")

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
        st.session_state.user_preferences = {
            'items_per_page': 10,
            'show_abstracts': True,
            'citation_style': 'APA',
            'auto_expand': False,
        }
        st.success("✅ Reset to defaults!")
        st.rerun()

st.divider()

# ── Export ──────────────────────────────────────────────────────────────────
st.header("📥 Export Publications")

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
    from utils.security import execute_query
    result, _ = execute_query("SELECT * FROM publications ORDER BY publication_year DESC")
    export_pubs = result or []

st.markdown(f"**{len(export_pubs)} publication(s)** ready for export.")

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
        import json as _json
        data   = _json.dumps(export_pubs, indent=2, default=str).encode("utf-8")
        fname  = "publications.json"
        mime   = "application/json"

    st.download_button(
        label=f"⬇️ Download {export_format}",
        data=data,
        file_name=fname,
        mime=mime,
        type="primary",
        use_container_width=False,
    )

    # Citation preview
    if export_pubs:
        with st.expander("📖 Citation Preview (first 3 papers)"):
            style = citation_style
            for pub in export_pubs[:3]:
                st.markdown(f"• {format_citation(pub, style)}")

else:
    st.info("No publications found. Sync publications from the Publications page first.")

st.divider()

# ── Connection Status ───────────────────────────────────────────────────────
st.header("🔌 Connection Status")

c1, c2, c3 = st.columns(3)
with c1:
    st.subheader("Database")
    if is_db_configured():
        st.success("✅ Connected")
    else:
        st.error("❌ Not configured")
with c2:
    st.subheader("AI Service")
    if get_secret("AI_API_KEY") or get_secret("GROQ_API_KEY"):
        st.success("✅ Available")
    else:
        st.warning("⚠️ Not available")
with c3:
    st.subheader("OpenAlex")
    try:
        r = requests.get("https://api.openalex.org/works?per_page=1", timeout=5)
        if r.status_code == 200:
            st.success("✅ Online")
        else:
            st.warning("⚠️ Unavailable")
    except Exception:
        st.warning("⚠️ Unavailable")

st.divider()

# ── About ───────────────────────────────────────────────────────────────────
st.header("ℹ️ About")
st.markdown("""
**ORC Research Dashboard** v1.0

An AI-powered academic research analytics platform.

**Features:**
- 📚 Publication tracking via OpenAlex
- 🔬 AI-powered research assistant
- 📊 Interactive analytics & visualizations
- 📥 Export to CSV, BibTeX, JSON
- 🔐 Secure admin panel with two-factor authentication

**Need help?**
- 🐛 [Report a Bug](/Bug_Report)
- 🔐 [Admin Panel](/Admin) (administrators only)
""")

st.divider()
st.markdown(
    "<div style='text-align:center;color:#64748b;font-size:0.85rem;'>"
    "Powered by <a href='https://www.linkedin.com/in/fahad-al-jubalie-55973926/' target='_blank'>Fahad Al-Jubalie</a>"
    "</div>",
    unsafe_allow_html=True,
)
