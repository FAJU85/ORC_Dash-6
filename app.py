"""
ORC Research Dashboard - Main Application
Secure, production-ready academic analytics platform
Powered by Hugging Face Datasets
"""

import streamlit as st
import sys
import os

# Add utils to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.security import (
    get_nested_secret, execute_query, init_session, log_audit
)
from utils.hf_data import load_publications, get_active_researchers
from utils.ui import apply_theme, theme_toggle_button, render_system_status

# Page configuration - use sidebar for proper page navigation
st.set_page_config(
    page_title="ORC Research Dashboard",
    page_icon="https://i.ibb.co/C3m0Gs0p/ORC-LOGO2-page-0001-1.jpg",
    layout="wide",
    initial_sidebar_state="auto"
)

# Initialize session state
init_session()

# Apply shared theme (handles session state, query params, and CSS injection)
apply_theme()

# ============================================
# HEADER WITH THEME TOGGLE
# ============================================

col1, col2 = st.columns([6, 1])

with col1:
    st.title("🔬 ORC Research Dashboard")
    st.markdown("**Academic Analytics & Publication Intelligence Platform**")

with col2:
    st.write("")
    st.write("")
    theme_toggle_button()

st.divider()

# ============================================
# MAIN PAGE CONTENT
# ============================================

# ============================================
# SYSTEM STATUS
# ============================================

st.header("🔌 System Status")
render_system_status()

st.divider()

# ============================================
# RESEARCH METRICS
# ============================================

st.header("📊 Research Metrics")

metrics, err = execute_query("""
    SELECT 
        COUNT(*) as total_pubs,
        COALESCE(SUM(citation_count), 0) as total_citations,
        COALESCE(AVG(citation_count), 0) as avg_citations,
        SUM(CASE WHEN open_access = 1 THEN 1 ELSE 0 END) as oa_count
    FROM publications
""")

if metrics and len(metrics) > 0:
    m = metrics[0]
    
    # Calculate h-index
    h_data, _ = execute_query("SELECT citation_count FROM publications ORDER BY citation_count DESC")
    h_index = 0
    if h_data:
        citations = [r.get('citation_count', 0) or 0 for r in h_data]
        for i, c in enumerate(citations, 1):
            if c >= i:
                h_index = i
            else:
                break
    
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        st.metric("📄 Publications", m.get("total_pubs", 0))
    with col2:
        st.metric("📈 Citations", f"{m.get('total_citations', 0):,}")
    with col3:
        st.metric("🎯 h-index", h_index)
    with col4:
        avg = m.get("avg_citations", 0) or 0
        st.metric("📊 Avg Citations", f"{avg:.1f}")
    with col5:
        st.metric("🔓 Open Access", m.get("oa_count", 0) or 0)
else:
    st.info("📭 No publications data. Use **Publications** page to sync from OpenAlex.")

st.divider()

# ============================================
# RECENT PUBLICATIONS
# ============================================

st.header("📚 Recent Publications")

pubs, err = execute_query("""
    SELECT title, journal_name, publication_year, citation_count
    FROM publications
    ORDER BY publication_year DESC, citation_count DESC
    LIMIT 5
""")

if pubs and len(pubs) > 0:
    for pub in pubs:
        raw_title = pub.get('title', 'Untitled')
        title = raw_title[:100] + ("…" if len(raw_title) > 100 else "")
        journal = pub.get('journal_name', 'Unknown')
        year = pub.get('publication_year', '')
        citations = pub.get('citation_count', 0) or 0
        
        st.markdown(f"""
        <div class="pub-item">
            <strong>{title}</strong><br>
            <span style="color: #94a3b8;">📰 {journal} • {year} • {citations} citations</span>
        </div>
        """, unsafe_allow_html=True)
else:
    st.info("No publications yet. Use the **Publications** page to sync from OpenAlex.")

st.divider()

# ============================================
# RESEARCHER INFO
# ============================================

st.header("👤 Researcher")

name = get_nested_secret("researcher", "name", "Not configured")
orcid = get_nested_secret("researcher", "orcid", "Not configured")
institution = get_nested_secret("researcher", "institution", "Not configured")

col1, col2, col3 = st.columns(3)
with col1:
    st.markdown(f"**Name:** {name}")
with col2:
    st.markdown(f"**ORCID:** {orcid}")
with col3:
    st.markdown(f"**Institution:** {institution}")

# ============================================
# FOOTER
# ============================================

st.divider()

st.markdown("""
<div style="text-align: center; color: #64748b; font-size: 0.85rem;">
    <p>ORC Research Dashboard v1.0</p>
    <p>
        Powered by 
        <a href="https://www.linkedin.com/in/fahad-al-jubalie-55973926/" target="_blank" class="footer-link">
            Fahad Al-Jubalie
        </a>
    </p>
</div>
""", unsafe_allow_html=True)
