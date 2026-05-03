"""
ORC Research Dashboard - Bug Report
Submit bugs → Telegram alert → GitHub Issue
"""

import streamlit as st
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.security import sanitize_string, validate_email, log_audit, RateLimiter
from utils.email_service import send_bug_report_notification, create_github_issue
from utils.styles import apply_styles, get_theme, hero_html, section_title_html, footer_html, DARK, LIGHT

st.set_page_config(page_title="Bug Report", page_icon="🐛", layout="wide")

apply_styles()

colors = DARK if get_theme() == "dark" else LIGHT

# Initialize rate limiter
rate_limiter = RateLimiter()

# Session state
if "bug_submitted" not in st.session_state:
    st.session_state.bug_submitted = False
if "github_url" not in st.session_state:
    st.session_state.github_url = None

# ============================================
# PAGE
# ============================================

st.markdown(hero_html("🐛 Bug Report", "Help us improve by reporting issues you encounter"), unsafe_allow_html=True)


if st.session_state.bug_submitted:
    # Success state
    st.success("✅ Bug report submitted successfully!")
    st.markdown("Thank you for helping us improve the dashboard.")
    
    if st.session_state.github_url:
        st.markdown(f"🔗 **Issue created:** [{st.session_state.github_url}]({st.session_state.github_url})")
    
    st.info("The administrator has been notified and will review your report.")
    
    if st.button("📝 Submit Another Report", use_container_width=True):
        st.session_state.bug_submitted = False
        st.session_state.github_url = None
        st.rerun()

else:
    # Check rate limit
    session_id = st.session_state.get('session_token', 'default')
    allowed, wait_time = rate_limiter.is_allowed(f"bug_{session_id}", max_attempts=5, window_seconds=600)
    
    if not allowed:
        st.error(f"⚠️ Too many reports submitted. Please wait {wait_time} seconds.")
        st.stop()
    
    # Bug report form
    with st.form("bug_form"):
        st.markdown(section_title_html("What went wrong?"), unsafe_allow_html=True)
        
        summary = st.text_input(
            "Summary *",
            placeholder="Brief description of the issue",
            help="A short, clear summary of the bug"
        )
        
        description = st.text_area(
            "Description *",
            placeholder="Describe what happened in detail...",
            height=100,
            help="Explain the bug in detail"
        )
        
        steps = st.text_area(
            "Steps to Reproduce",
            placeholder="1. Go to...\n2. Click on...\n3. See error...",
            height=80,
            help="How can we reproduce this issue?"
        )
        
        expected_actual = st.text_area(
            "Expected vs Actual",
            placeholder="Expected: ...\nActual: ...",
            height=60,
            help="What did you expect vs what happened?"
        )
        
        user_contact = st.text_input(
            "Your Email (optional)",
            placeholder="your@email.com",
            help="We may contact you for more details"
        )
        
        st.divider()
        
        col1, col2 = st.columns(2)
        
        with col1:
            severity = st.selectbox("Severity", [
                "Low - Minor issue",
                "Medium - Affects usability",
                "High - Major feature broken",
                "Critical - App unusable"
            ])
        
        with col2:
            category = st.selectbox("Category", [
                "UI/Display Issue",
                "Data Problem",
                "AI Assistant",
                "Publications",
                "Analytics",
                "Performance",
                "Other"
            ])
        
        submitted = st.form_submit_button("🚀 Submit Report", type="primary", use_container_width=True)
        
        if submitted:
            # Validate required fields
            if not summary or not description:
                st.error("❌ Summary and Description are required")
            else:
                rate_limiter.record_attempt(f"bug_{session_id}")
                
                # Sanitize inputs
                summary = sanitize_string(summary, 200)
                description = sanitize_string(description, 2000)
                steps = sanitize_string(steps, 1000)
                expected_actual = sanitize_string(expected_actual, 500)
                user_contact = sanitize_string(user_contact, 100)
                
                # Validate email if provided
                if user_contact and not validate_email(user_contact):
                    st.error("❌ Invalid email format")
                else:
                    with st.spinner("Submitting report..."):
                        # Add metadata to description
                        full_description = f"**Category:** {category}\n**Severity:** {severity}\n\n{description}"
                        
                        # Create GitHub issue (if configured)
                        github_url, github_error = create_github_issue(
                            summary, full_description, steps, expected_actual, user_contact
                        )
                        
                        if github_url:
                            st.session_state.github_url = github_url
                            log_audit("bug_report_github", github_url)
                        
                        # Send Telegram notification (if configured)
                        telegram_success, _ = send_bug_report_notification(
                            summary, full_description, user_contact, github_url
                        )
                        
                        if telegram_success:
                            log_audit("bug_report_telegram")
                        
                        # Mark as submitted (even if notifications fail)
                        st.session_state.bug_submitted = True
                        log_audit("bug_report_submitted", summary[:50])
                        st.rerun()
    
    st.markdown(
        f'<div class="orc-card" style="padding:0.9rem 1.25rem;margin-top:0.5rem">'
        f'<div style="font-weight:600;font-size:0.82rem;margin-bottom:0.35rem;color:{colors["text2"]}">TIPS FOR A GOOD REPORT</div>'
        f'<div style="font-size:0.82rem;color:{colors["text2"]};line-height:1.7">'
        f'· Be specific about what happened<br>'
        f'· Include the steps that triggered the issue<br>'
        f'· Mention which page or feature was affected<br>'
        f'· Copy any error messages you saw'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

# ── Footer ───────────────────────────────────────────────────────────────────
st.divider()
st.markdown(footer_html("Your feedback helps improve the dashboard for everyone"), unsafe_allow_html=True)
