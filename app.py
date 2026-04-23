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
from utils.hf_data import load_publications, get_active_researchers

# Page configuration - use sidebar for proper page navigation
st.set_page_config(
    page_title="ORC Research Dashboard",
    page_icon="https://i.ibb.co/C3m0Gs0p/ORC-LOGO2-page-0001-1.jpg",
    layout="wide",
    initial_sidebar_state="auto"
)

# Initialize session state
init_session()

# Theme toggle via query params
if 'theme_mode' not in st.session_state:
    st.session_state.theme_mode = "dark"

# ============================================
# RESPONSIVE STYLES
# ============================================

st.markdown("""
<style>
    /* Hide Streamlit menu and footer */
    #MainMenu {visibility: hidden !important;}
    footer {visibility: hidden !important;}
    .stDeployButton {display: none !important;}
    
    /* Responsive Design */
    @media (max-width: 768px) {
        .metric-row {
            flex-direction: column !important;
        }
        .metric-col {
            min-width: 100% !important;
            margin-bottom: 0.5rem;
        }
        .nav-links {
            flex-wrap: wrap !important;
            justify-content: center !important;
        }
        .nav-btn {
            font-size: 0.75rem !important;
            padding: 0.4rem 0.6rem !important;
        }
    }
    
    /* Responsive columns */
    .stColumn {
        min-width: 150px;
    }
    
    /* Better mobile layout */
    .element-container {
        width: 100% !important;
    }
    
    /* Metric cards responsive */
    .metric-card {
        padding: 1rem;
        border-radius: 8px;
        text-align: center;
    }
    
    /* Footer responsive */
    .footer-divider {
        margin: 1rem 0;
    }
</style>
""", unsafe_allow_html=True)

# ============================================
# THEME SYSTEM (via query params)
# ============================================

# Check for theme toggle
params = st.query_params
if "theme" in params:
    if params["theme"] == "light":
        st.session_state.theme_mode = "light"
    else:
        st.session_state.theme_mode = "dark"

# Theme styles
DARK_THEME = """
<style>
    .stApp { background-color: #0f172a; }
    h1, h2, h3, h4, h5, h6, p, span { color: white !important; }
    .stMetric label { color: #94a3b8 !important; }
    .metric-card { background: #1e293b; border: 1px solid #334155; }
    .pub-item { background: #1e293b; border-left: 3px solid #06b6d4; }
    .status-card { background: #1e293b; }
</style>
"""

LIGHT_THEME = """
<style>
    .stApp { background-color: #f8fafc; }
    h1, h2, h3, h4, h5, h6, p, span { color: #1e293b !important; }
    .stMetric label { color: #475569 !important; }
    .stMetric [data-testid="stMetricValue"] { color: #1e293b !important; }
    .metric-card { background: #ffffff; border: 1px solid #e2e8f0; }
    .pub-item { background: #ffffff; border-left: 3px solid #0ea5e9; }
    .status-card { background: #ffffff; border: 1px solid #e2e8f0; }
</style>
"""

if st.session_state.theme_mode == "light":
    st.markdown(LIGHT_THEME, unsafe_allow_html=True)
else:
    st.markdown(DARK_THEME, unsafe_allow_html=True)

# ============================================
# HEADER WITH THEME TOGGLE
# ============================================

col1, col2 = st.columns([6, 1])

with col1:
    st.title("🔬 ORC Research Dashboard")
    st.markdown("**AI-Powered Academic Analytics Platform**")

with col2:
    st.write("")
    st.write("")
    # Theme toggle button
    if st.session_state.theme_mode == "dark":
        if st.button("☀️ Light Mode", use_container_width=True):
            st.query_params["theme"] = "light"
            st.rerun()
    else:
        if st.button("🌙 Dark Mode", use_container_width=True):
            st.query_params["theme"] = "dark"
            st.rerun()

st.divider()

# ============================================
# MAIN PAGE CONTENT
# ============================================

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
