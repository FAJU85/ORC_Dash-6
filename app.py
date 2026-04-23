"""
ORC Research Dashboard - Main Application
Secure, production-ready academic analytics platform
Powered by Hugging Face Datasets
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
from utils.hf_data import load_publications

# Page configuration
st.set_page_config(
    page_title="ORC Research Dashboard",
    page_icon="https://i.ibb.co/C3m0Gs0p/ORC-LOGO2-page-0001-1.jpg",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Initialize session state for theme
if 'theme' not in st.session_state:
    st.session_state.theme = "dark"

# ============================================
# THEME TOGGLE
# ============================================

def toggle_theme():
    st.session_state.theme = "light" if st.session_state.theme == "dark" else "dark"

# ============================================
# LIGHT THEME STYLES
# ============================================

LIGHT_THEME_STYLES = """
<style>
    /* Light Theme */
    [data-theme="light"] .stApp {
        background-color: #f8fafc;
    }
    
    [data-theme="light"] .metric-card {
        background: linear-gradient(135deg, #ffffff, #f1f5f9);
        border: 1px solid #e2e8f0;
        color: #1e293b;
    }
    
    [data-theme="light"] .pub-item {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        color: #1e293b;
    }
    
    [data-theme="light"] .stMetric label,
    [data-theme="light"] .stMetric [data-testid="stMetricValue"] {
        color: #1e293b !important;
    }
    
    [data-theme="light"] h1, [data-theme="light"] h2, [data-theme="light"] h3 {
        color: #1e293b !important;
    }
    
    [data-theme="light"] .footer-link {
        color: #475569;
    }
</style>
"""

# ============================================
# NAVIGATION STYLES
# ============================================

NAV_STYLES = """
<style>
    /* Hide default sidebar */
    [data-testid="stSidebar"] {
        display: none;
    }
    
    /* Top Navigation Bar */
    .main-nav {
        background: linear-gradient(90deg, #0f172a 0%, #1e3a5f 100%);
        padding: 0.75rem 1.5rem;
        border-radius: 0;
        margin: -1rem -1rem 1rem -1rem;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }
    
    .nav-logo {
        display: flex;
        align-items: center;
        gap: 0.75rem;
    }
    
    .nav-logo img {
        width: 40px;
        height: 40px;
        border-radius: 8px;
    }
    
    .nav-title {
        color: white;
        font-size: 1.25rem;
        font-weight: 600;
    }
    
    .nav-links {
        display: flex;
        gap: 0.5rem;
        align-items: center;
    }
    
    .nav-btn {
        background: rgba(255,255,255,0.1);
        border: 1px solid rgba(255,255,255,0.2);
        color: white;
        padding: 0.5rem 1rem;
        border-radius: 8px;
        cursor: pointer;
        text-decoration: none;
        font-size: 0.9rem;
        transition: all 0.2s;
    }
    
    .nav-btn:hover {
        background: rgba(255,255,255,0.2);
    }
    
    .nav-btn.active {
        background: #06b6d4;
        border-color: #06b6d4;
    }
    
    .theme-toggle {
        background: rgba(255,255,255,0.1);
        border: 1px solid rgba(255,255,255,0.2);
        color: white;
        padding: 0.5rem 1rem;
        border-radius: 8px;
        cursor: pointer;
        font-size: 1.2rem;
        transition: all 0.2s;
    }
    
    .theme-toggle:hover {
        background: rgba(255,255,255,0.2);
    }
    
    /* Light theme adjustments */
    [data-theme="light"] .main-nav {
        background: linear-gradient(90deg, #ffffff 0%, #f1f5f9 100%);
        border-bottom: 1px solid #e2e8f0;
    }
    
    [data-theme="light"] .nav-title {
        color: #1e293b;
    }
    
    [data-theme="light"] .nav-btn {
        background: #f1f5f9;
        border: 1px solid #e2e8f0;
        color: #1e293b;
    }
    
    [data-theme="light"] .nav-btn:hover {
        background: #e2e8f0;
    }
    
    [data-theme="light"] .nav-btn.active {
        background: #0ea5e9;
        border-color: #0ea5e9;
        color: white;
    }
    
    [data-theme="light"] .theme-toggle {
        background: #f1f5f9;
        border: 1px solid #e2e8f0;
        color: #1e293b;
    }
    
    /* Card Grid for Home */
    .card-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
        gap: 1rem;
        padding: 1rem 0;
    }
    
    .nav-card {
        background: rgba(255,255,255,0.05);
        border: 1px solid rgba(255,255,255,0.1);
        border-radius: 12px;
        padding: 1.5rem;
        text-align: center;
        cursor: pointer;
        transition: all 0.2s;
    }
    
    .nav-card:hover {
        background: rgba(255,255,255,0.1);
        transform: translateY(-2px);
    }
    
    .nav-card-icon {
        font-size: 2.5rem;
        margin-bottom: 0.5rem;
    }
    
    .nav-card-title {
        color: white;
        font-size: 1.1rem;
        font-weight: 600;
        margin-bottom: 0.25rem;
    }
    
    .nav-card-desc {
        color: rgba(255,255,255,0.6);
        font-size: 0.85rem;
    }
    
    [data-theme="light"] .nav-card {
        background: #ffffff;
        border: 1px solid #e2e8f0;
    }
    
    [data-theme="light"] .nav-card:hover {
        background: #f8fafc;
    }
    
    [data-theme="light"] .nav-card-title {
        color: #1e293b;
    }
    
    [data-theme="light"] .nav-card-desc {
        color: #64748b;
    }
</style>
"""

# Apply theme-specific styles
if st.session_state.theme == "light":
    st.markdown(f'<html data-theme="light">{LIGHT_THEME_STYLES}</html>', unsafe_allow_html=True)
st.markdown(NAV_STYLES, unsafe_allow_html=True)

# ============================================
# TOP NAVIGATION BAR
# ============================================

# Get current page
current_page = st.query_params.get("page", "Home")

# Navigation items
nav_pages = {
    "Home": "🏠",
    "Publications": "📄",
    "AI Assistant": "🤖",
    "Analytics": "📊",
    "Bug Report": "🐛",
    "Settings": "⚙️",
    "Admin": "🔐"
}

# Render top navigation
st.markdown(f'''
<div class="main-nav">
    <div class="nav-logo">
        <img src="https://i.ibb.co/C3m0Gs0p/ORC-LOGO2-page-0001-1.jpg" alt="ORC">
        <span class="nav-title">ORC Dashboard</span>
    </div>
    <div class="nav-links">
        {''.join([f'<a href="?page={name}" class="nav-btn {"active" if current_page == name else ""}">{icon} {name}</a>' for name, icon in nav_pages.items()])}
        <button class="theme-toggle" onclick="toggle_theme()" title="Toggle Theme">{"☀️" if st.session_state.theme == "dark" else "🌙"}</button>
    </div>
</div>
''', unsafe_allow_html=True)

# Theme toggle JavaScript
st.markdown('''
<script>
function toggle_theme() {
    const current = document.documentElement.getAttribute('data-theme');
    const next = current === 'light' ? 'dark' : 'light';
    document.documentElement.setAttribute('data-theme', next);
    // Store preference
    localStorage.setItem('orc_theme', next);
    // Reload to apply
    window.location.reload();
}
</script>
''', unsafe_allow_html=True)

# Restore theme from localStorage on load
st.markdown('''
<script>
// Restore theme from localStorage
const savedTheme = localStorage.getItem('orc_theme');
if (savedTheme) {
    document.documentElement.setAttribute('data-theme', savedTheme);
}
</script>
''', unsafe_allow_html=True)

# Initialize secure session
init_session()

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
        st.success("✅ HF Connected")
    else:
        st.warning("⚠️ HF Not configured")

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
