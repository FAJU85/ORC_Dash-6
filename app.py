"""
ORC Research Dashboard - Main Application
Secure, production-ready academic analytics platform
"""

import streamlit as st
import requests
import sys
import os

# Add utils to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.security import (
    get_secret, get_nested_secret, execute_query, 
    is_db_configured, init_session, log_audit
)

# Page configuration
st.set_page_config(
    page_title="ORC Research Dashboard",
    page_icon="🔬",
    layout="wide"
)

# Initialize secure session
init_session()

# ============================================
# CUSTOM STYLING
# ============================================

st.markdown("""
<style>
    /* Material Design Dark Theme */
    .stApp {
        background-color: #0f172a;
    }
    
    .metric-card {
        background: linear-gradient(135deg, #1e3a5f, #0f172a);
        border-radius: 12px;
        padding: 1.5rem;
        text-align: center;
        border: 1px solid #334155;
    }
    
    .status-ok { color: #22c55e; }
    .status-error { color: #ef4444; }
    .status-warn { color: #fbbf24; }
    
    .pub-item {
        background: #1e293b;
        border-radius: 8px;
        padding: 1rem;
        margin-bottom: 0.75rem;
        border-left: 3px solid #06b6d4;
    }
    
    .footer-link {
        color: #94a3b8;
        text-decoration: none;
    }
    
    .footer-link:hover {
        color: #06b6d4;
    }
</style>
""", unsafe_allow_html=True)

# ============================================
# MAIN PAGE
# ============================================

st.title("🔬 ORC Research Dashboard")
st.markdown("**AI-Powered Academic Analytics Platform**")

st.divider()

# ============================================
# SYSTEM STATUS
# ============================================

st.header("🔌 System Status")

col1, col2, col3 = st.columns(3)

with col1:
    st.subheader("Database")
    if is_db_configured():
        result, error = execute_query("SELECT 1 as test")
        if result is not None:
            st.success("✅ Connected")
        else:
            st.error("❌ Connection failed")
    else:
        st.error("❌ Not configured")

with col2:
    st.subheader("AI Service")
    ai_key = get_secret("AI_API_KEY") or get_secret("GROQ_API_KEY")
    if ai_key and len(ai_key) > 5:
        st.success("✅ Ready")
    else:
        st.warning("⚠️ Not configured")

with col3:
    st.subheader("OpenAlex")
    try:
        r = requests.get("https://api.openalex.org/works?per_page=1", timeout=5)
        if r.status_code == 200:
            st.success("✅ Online")
        else:
            st.warning("⚠️ Unavailable")
    except:
        st.warning("⚠️ Unavailable")

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
        title = pub.get('title', 'Untitled')[:100]
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
