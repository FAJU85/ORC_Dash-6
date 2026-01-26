"""
ORC Research Dashboard - User Settings
User preferences (separate from Admin settings)
"""

import streamlit as st
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.security import get_secret, get_nested_secret, is_db_configured
import requests

st.set_page_config(page_title="Settings", page_icon="⚙️", layout="wide")

# ============================================
# SESSION STATE
# ============================================

if "user_preferences" not in st.session_state:
    st.session_state.user_preferences = {
        'items_per_page': 10,
        'show_abstracts': True,
        'citation_style': 'APA',
        'auto_expand': False
    }

# ============================================
# PAGE
# ============================================

st.title("⚙️ Settings")
st.markdown("Customize your dashboard experience")

st.divider()

# ============================================
# DISPLAY PREFERENCES
# ============================================

st.header("🎨 Display Preferences")

col1, col2 = st.columns(2)

with col1:
    items_per_page = st.select_slider(
        "Items per page",
        options=[5, 10, 15, 20, 25],
        value=st.session_state.user_preferences.get('items_per_page', 10),
        help="Number of publications per page"
    )
    
    citation_style = st.selectbox(
        "Citation Format",
        ["APA", "MLA", "Chicago", "Harvard", "IEEE"],
        help="Default format for exports"
    )

with col2:
    show_abstracts = st.toggle(
        "Show abstracts by default",
        value=st.session_state.user_preferences.get('show_abstracts', True),
        help="Expand abstracts in publication list"
    )
    
    auto_expand = st.toggle(
        "Auto-expand paper details",
        value=st.session_state.user_preferences.get('auto_expand', False),
        help="Automatically show full details"
    )

st.divider()

# ============================================
# EXPORT PREFERENCES
# ============================================

st.header("📥 Export Preferences")

col1, col2 = st.columns(2)

with col1:
    export_format = st.selectbox(
        "Default export format",
        ["CSV", "BibTeX", "JSON"],
        help="Default format when exporting"
    )

with col2:
    include_abstracts = st.toggle(
        "Include abstracts in exports",
        value=True,
        help="Add abstracts to exported files"
    )

st.divider()

# ============================================
# SAVE SETTINGS
# ============================================

col1, col2 = st.columns([1, 3])

with col1:
    if st.button("💾 Save Settings", type="primary", use_container_width=True):
        st.session_state.user_preferences = {
            'items_per_page': items_per_page,
            'show_abstracts': show_abstracts,
            'citation_style': citation_style,
            'auto_expand': auto_expand
        }
        st.success("✅ Settings saved!")

with col2:
    if st.button("↩️ Reset to Defaults"):
        st.session_state.user_preferences = {
            'items_per_page': 10,
            'show_abstracts': True,
            'citation_style': 'APA',
            'auto_expand': False
        }
        st.success("✅ Reset to defaults!")
        st.rerun()

st.divider()

# ============================================
# CONNECTION STATUS
# ============================================

st.header("🔌 Connection Status")

col1, col2, col3 = st.columns(3)

with col1:
    st.subheader("Database")
    if is_db_configured():
        st.success("✅ Connected")
    else:
        st.error("❌ Not configured")

with col2:
    st.subheader("AI Service")
    if get_secret("AI_API_KEY") or get_secret("GROQ_API_KEY"):
        st.success("✅ Available")
    else:
        st.warning("⚠️ Not available")

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
# ABOUT
# ============================================

st.header("ℹ️ About")

st.markdown("""
**ORC Research Dashboard** v1.0

An AI-powered academic research analytics platform.

**Features:**
- 📚 Publication tracking from OpenAlex
- 🤖 AI-powered research assistant
- 📊 Interactive analytics & visualizations
- 📥 Export to CSV, BibTeX, JSON

**Need help?**
- 🐛 [Report a Bug](/Bug_Report)
- 🔐 [Admin Panel](/Admin) (administrators only)
""")

st.divider()

st.markdown("""
<div style="text-align: center; color: #64748b; font-size: 0.85rem;">
    Powered by <a href="https://www.linkedin.com/in/fahad-al-jubalie-55973926/" target="_blank">Fahad Al-Jubalie</a>
</div>
""", unsafe_allow_html=True)
