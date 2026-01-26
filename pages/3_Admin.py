"""
ORC Research Dashboard - Secure Admin Panel
With rate limiting, audit logging, and secure OTP
"""

import streamlit as st
import sys
import os
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.security import (
    get_secret, get_nested_secret, hash_password, generate_otp,
    validate_email, validate_otp, sanitize_string, log_audit,
    get_audit_log, RateLimiter, is_admin_authenticated, admin_logout,
    execute_query, is_db_configured
)
from utils.email_service import send_otp_email

st.set_page_config(page_title="Admin", page_icon="🔐", layout="wide")

# Initialize rate limiter
rate_limiter = RateLimiter()

# ============================================
# SESSION STATE
# ============================================

if "admin_authenticated" not in st.session_state:
    st.session_state.admin_authenticated = False
if "otp_sent" not in st.session_state:
    st.session_state.otp_sent = False
if "otp_code" not in st.session_state:
    st.session_state.otp_code = None
if "otp_expiry" not in st.session_state:
    st.session_state.otp_expiry = None
if "login_email" not in st.session_state:
    st.session_state.login_email = None
if "smtp_not_configured" not in st.session_state:
    st.session_state.smtp_not_configured = False

# ============================================
# PAGE
# ============================================

st.title("🔐 Administrator Panel")

# Check if admin is configured
admin_email = get_nested_secret("admin", "email")
admin_hash = get_nested_secret("admin", "password_hash")

if not admin_email or not admin_hash:
    st.warning("⚠️ Administrator account not configured")
    st.info("Contact system administrator to set up admin access")
    st.stop()

# ============================================
# AUTHENTICATION
# ============================================

if not st.session_state.admin_authenticated:
    
    if not st.session_state.otp_sent:
        # Step 1: Email + Password Login
        st.header("🔑 Administrator Login")
        
        # Check rate limit
        client_key = "admin_login"
        allowed, wait_time = rate_limiter.is_allowed(client_key, max_attempts=5, window_seconds=300)
        
        if not allowed:
            st.error(f"⚠️ Too many login attempts. Please wait {wait_time} seconds.")
            log_audit("login_rate_limited")
            st.stop()
        
        with st.form("login_form"):
            email = st.text_input("Email", placeholder="admin@example.com")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Continue", type="primary", use_container_width=True)
            
            if submitted:
                rate_limiter.record_attempt(client_key)
                
                # Sanitize inputs
                email = sanitize_string(email, 100).lower().strip()
                
                # Validate email format
                if not validate_email(email):
                    st.error("❌ Invalid email format")
                    log_audit("login_invalid_email", email[:20])
                elif email != admin_email:
                    st.error("❌ Invalid credentials")
                    log_audit("login_wrong_email", email[:20])
                elif hash_password(password) != admin_hash:
                    st.error("❌ Invalid credentials")
                    log_audit("login_wrong_password", email[:20])
                else:
                    # Generate OTP
                    otp = generate_otp()
                    st.session_state.otp_code = otp
                    st.session_state.otp_expiry = datetime.now() + timedelta(minutes=5)
                    st.session_state.login_email = email
                    
                    # Try to send OTP via email
                    success, error = send_otp_email(email, otp)
                    
                    if success:
                        st.session_state.otp_sent = True
                        st.session_state.smtp_not_configured = False
                        log_audit("otp_sent", email[:20])
                        st.rerun()
                    elif error == "SMTP_NOT_CONFIGURED":
                        # SMTP not configured - show OTP for demo
                        st.session_state.otp_sent = True
                        st.session_state.smtp_not_configured = True
                        log_audit("otp_demo_mode", email[:20])
                        st.rerun()
                    else:
                        st.error("❌ Could not send verification code")
                        log_audit("otp_send_failed", error)
        
        st.divider()
        st.markdown("""
        <div style="text-align: center; color: #64748b; font-size: 0.85rem;">
            🔒 Two-factor authentication required<br>
            A verification code will be sent to your email
        </div>
        """, unsafe_allow_html=True)
    
    else:
        # Step 2: OTP Verification
        st.header("📱 Enter Verification Code")
        
        st.markdown(f"A 6-digit code has been sent to **{st.session_state.login_email[:3]}***")
        
        # Show demo mode warning if SMTP not configured
        if st.session_state.smtp_not_configured:
            st.warning("⚠️ Email service not configured. Demo mode active.")
            st.info(f"🔐 **Demo OTP:** {st.session_state.otp_code}")
        
        # Check OTP rate limit
        otp_key = f"otp_{st.session_state.login_email}"
        allowed, wait_time = rate_limiter.is_allowed(otp_key, max_attempts=5, window_seconds=300)
        
        if not allowed:
            st.error(f"⚠️ Too many attempts. Please wait {wait_time} seconds.")
            st.session_state.otp_sent = False
            st.session_state.otp_code = None
            log_audit("otp_rate_limited")
            st.rerun()
        
        with st.form("otp_form"):
            otp_input = st.text_input("Verification Code", max_chars=6, placeholder="123456")
            
            col1, col2 = st.columns(2)
            with col1:
                verify = st.form_submit_button("✅ Verify", type="primary", use_container_width=True)
            with col2:
                cancel = st.form_submit_button("← Back", use_container_width=True)
            
            if verify:
                rate_limiter.record_attempt(otp_key)
                
                if not validate_otp(otp_input):
                    st.error("❌ Invalid code format")
                    log_audit("otp_invalid_format")
                elif datetime.now() > st.session_state.otp_expiry:
                    st.error("❌ Code expired. Please try again.")
                    st.session_state.otp_sent = False
                    st.session_state.otp_code = None
                    log_audit("otp_expired")
                    st.rerun()
                elif otp_input != st.session_state.otp_code:
                    st.error("❌ Invalid code")
                    log_audit("otp_wrong_code")
                else:
                    # Success!
                    st.session_state.admin_authenticated = True
                    st.session_state.otp_sent = False
                    st.session_state.otp_code = None
                    st.session_state.otp_expiry = None
                    rate_limiter.reset(client_key)
                    rate_limiter.reset(otp_key)
                    log_audit("admin_login_success", st.session_state.login_email[:20])
                    st.success("✅ Authentication successful!")
                    st.rerun()
            
            if cancel:
                st.session_state.otp_sent = False
                st.session_state.otp_code = None
                st.rerun()

else:
    # ============================================
    # ADMIN DASHBOARD
    # ============================================
    
    st.success("✅ Logged in as Administrator")
    
    if st.button("🚪 Logout"):
        admin_logout()
        st.rerun()
    
    st.divider()
    
    # Tabs
    tab1, tab2, tab3, tab4 = st.tabs(["📊 Dashboard", "👥 Researchers", "⚙️ Settings", "📋 Audit Log"])
    
    with tab1:
        st.header("System Overview")
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.subheader("Database")
            if is_db_configured():
                result, _ = execute_query("SELECT 1")
                if result is not None:
                    st.success("✅ Connected")
                else:
                    st.error("❌ Error")
            else:
                st.error("❌ Not configured")
        
        with col2:
            st.subheader("AI Service")
            if get_secret("AI_API_KEY") or get_secret("GROQ_API_KEY"):
                st.success("✅ Configured")
            else:
                st.warning("⚠️ Not set")
        
        with col3:
            st.subheader("Email (SMTP)")
            if get_nested_secret("smtp", "user"):
                st.success("✅ Configured")
            else:
                st.warning("⚠️ Demo mode")
        
        with col4:
            st.subheader("Telegram")
            if get_nested_secret("telegram", "bot_token"):
                st.success("✅ Configured")
            else:
                st.info("ℹ️ Optional")
        
        st.divider()
        
        # Quick stats
        st.header("📊 Statistics")
        
        stats, _ = execute_query("""
            SELECT COUNT(*) as count, 
                   COALESCE(SUM(citation_count), 0) as citations,
                   MAX(publication_year) as latest_year
            FROM publications
        """)
        
        if stats and len(stats) > 0:
            s = stats[0]
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Publications", s.get("count", 0))
            with col2:
                st.metric("Total Citations", f"{s.get('citations', 0):,}")
            with col3:
                st.metric("Latest Year", s.get("latest_year", "N/A"))
    
    with tab2:
        st.header("Manage Researchers")
        
        st.subheader("Primary Researcher")
        
        col1, col2 = st.columns(2)
        with col1:
            st.text_input("Name", value=get_nested_secret("researcher", "name", "Not set"), disabled=True)
            st.text_input("Institution", value=get_nested_secret("researcher", "institution", "Not set"), disabled=True)
        with col2:
            st.text_input("ORCID", value=get_nested_secret("researcher", "orcid", "Not set"), disabled=True)
        
        st.info("📝 To edit researcher info, update the `[researcher]` section in Streamlit Secrets")
        
        st.divider()
        
        st.subheader("Add Additional Researchers")
        st.info("🚧 Feature coming soon: Multi-author support")
    
    with tab3:
        st.header("System Settings")
        
        st.subheader("AI Configuration")
        st.selectbox("Default Model", ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768"], disabled=True)
        st.info("Model settings are configured in Streamlit Secrets")
        
        st.divider()
        
        st.subheader("Cache Management")
        if st.button("🗑️ Clear Application Cache"):
            st.cache_data.clear()
            log_audit("cache_cleared")
            st.success("✅ Cache cleared!")
        
        st.divider()
        
        st.subheader("Security")
        st.info(f"**Admin Email:** {admin_email}")
        st.info("To change admin credentials, update the `[admin]` section in Streamlit Secrets")
    
    with tab4:
        st.header("Security Audit Log")
        st.markdown("*Recent security-relevant events*")
        
        audit_log = get_audit_log()
        
        if audit_log:
            # Show in reverse chronological order
            for entry in reversed(audit_log[-50:]):
                timestamp = entry.get('timestamp', '')[:19]
                action = entry.get('action', 'unknown')
                details = entry.get('details', '')
                
                st.markdown(f"`{timestamp}` **{action}** {details}")
        else:
            st.info("No audit events recorded yet")

# Footer
st.divider()
st.markdown("""
<div style="text-align: center; color: #64748b; font-size: 0.8rem;">
    🔒 Secure Admin Panel • All actions are logged
</div>
""", unsafe_allow_html=True)
