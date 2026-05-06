"""
ORC Research Dashboard - SPA Router
Registers all pages with st.navigation(); each page handles its own layout.
"""

import streamlit as st
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.security import init_session

st.set_page_config(
    page_title="ORC Research Dashboard",
    page_icon="https://i.ibb.co/C3m0Gs0p/ORC-LOGO2-page-0001-1.jpg",
    layout="wide",
    initial_sidebar_state="collapsed",
)

init_session()

pg = st.navigation(
    [
        st.Page("pages/0_Home.py",         title="Home",         icon="🏠", default=True),
        st.Page("pages/1_Publications.py", title="Publications", icon="📚"),
        st.Page("pages/2_AI_Assistant.py", title="AI Assistant", icon="🤖"),
        st.Page("pages/4_Analytics.py",    title="Analytics",    icon="📊"),
        st.Page("pages/6_Settings.py",     title="Settings",     icon="⚙️"),
        st.Page("pages/7_Bioinformatics.py", title="Bioinformatics", icon="🧬"),
        st.Page("pages/5_Bug_Report.py",   title="Bug Report",   icon="🐛"),
        st.Page("pages/3_Admin.py",        title="Admin",        icon="🔐"),
    ],
    position="hidden",
)
pg.run()
