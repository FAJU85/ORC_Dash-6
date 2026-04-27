"""
ORC Research Dashboard - Secure Admin Panel
Two-factor authentication with rate limiting and audit logging.
"""

import streamlit as st
import sys
import os
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.security import (
    get_secret, get_nested_secret, hash_password, verify_password,
    generate_otp, validate_email, validate_otp, sanitize_string,
    log_audit, get_audit_log, load_audit_log_from_hf,
    RateLimiter, is_admin_authenticated, admin_logout,
    execute_query, is_db_configured
)
from utils.email_service import send_otp_email
from utils.hf_data import (
    get_active_researchers, add_researcher, remove_researcher,
    load_publications, sync_from_openalex, load_researchers,
    flush_audit_log
)

st.set_page_config(page_title="Admin", page_icon="🔐", layout="wide")

rate_limiter = RateLimiter()

# ============================================
# SESSION STATE
# ============================================

for key, default in [
    ("admin_authenticated", False),
    ("otp_sent", False),
    ("otp_code", None),
    ("otp_expiry", None),
    ("login_email", None),
    ("smtp_not_configured", False),
]:
    if key not in st.session_state:
        st.session_state[key] = default

# ============================================
# PAGE
# ============================================

st.title("🔐 Administrator Panel")

admin_email = get_nested_secret("admin", "email")
admin_hash  = get_nested_secret("admin", "password_hash")

if not admin_email or not admin_hash:
    st.warning("⚠️ Administrator account not configured")
    st.info("Contact system administrator to set up admin access.")
    st.stop()

# ============================================
# AUTHENTICATION
# ============================================

if not st.session_state.admin_authenticated:

    if not st.session_state.otp_sent:
        # ── Step 1: Email + Password ─────────────────────────────────────
        st.header("🔑 Administrator Login")

        client_key = "admin_login"
        allowed, wait_time = rate_limiter.is_allowed(client_key, max_attempts=5, window_seconds=300)
        if not allowed:
            st.error(f"⚠️ Too many login attempts. Please wait {wait_time} seconds.")
            log_audit("login_rate_limited")
            st.stop()

        with st.form("login_form"):
            email    = st.text_input("Email", placeholder="admin@example.com")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Continue", type="primary", use_container_width=True)

            if submitted:
                rate_limiter.record_attempt(client_key)
                email = sanitize_string(email, 100).lower().strip()

                if not validate_email(email):
                    st.error("❌ Invalid email format")
                    log_audit("login_invalid_email", email[:20])
                elif email != admin_email:
                    st.error("❌ Invalid credentials")
                    log_audit("login_wrong_email", email[:20])
                elif not verify_password(password, admin_hash):
                    st.error("❌ Invalid credentials")
                    log_audit("login_wrong_password", email[:20])
                else:
                    otp = generate_otp()
                    st.session_state.otp_code   = otp
                    st.session_state.otp_expiry = datetime.now() + timedelta(minutes=5)
                    st.session_state.login_email = email

                    success, error = send_otp_email(email, otp)
                    if success:
                        st.session_state.otp_sent = True
                        st.session_state.smtp_not_configured = False
                        log_audit("otp_sent", email[:20])
                        st.rerun()
                    elif error == "SMTP_NOT_CONFIGURED":
                        st.session_state.otp_sent = True
                        st.session_state.smtp_not_configured = True
                        log_audit("otp_demo_mode", email[:20])
                        st.rerun()
                    else:
                        st.error("❌ Could not send verification code")
                        log_audit("otp_send_failed", error)

        st.divider()
        st.markdown(
            "<div style='text-align:center;color:#64748b;font-size:0.85rem;'>"
            "🔒 Two-factor authentication required<br>"
            "A verification code will be sent to your email"
            "</div>",
            unsafe_allow_html=True,
        )

    else:
        # ── Step 2: OTP Verification ──────────────────────────────────────
        st.header("📱 Enter Verification Code")
        st.markdown(f"A 6-digit code has been sent to **{st.session_state.login_email[:3]}***")

        if st.session_state.smtp_not_configured:
            st.warning("⚠️ Email service not configured. Demo mode active.")
            st.info(f"🔐 **Demo OTP:** {st.session_state.otp_code}")

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
            c1, c2 = st.columns(2)
            with c1:
                verify = st.form_submit_button("✅ Verify", type="primary", use_container_width=True)
            with c2:
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
                    st.session_state.admin_authenticated = True
                    st.session_state.otp_sent  = False
                    st.session_state.otp_code  = None
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

    tab1, tab2, tab3, tab4 = st.tabs(["📊 Dashboard", "👥 Researchers", "⚙️ Settings", "📋 Audit Log"])

    # ── Tab 1: Dashboard ───────────────────────────────────────────────────
    with tab1:
        st.header("System Overview")

        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.subheader("Database")
            if is_db_configured():
                st.success("✅ Connected")
            else:
                st.error("❌ Not configured")
        with c2:
            st.subheader("AI Service")
            if get_secret("AI_API_KEY") or get_secret("GROQ_API_KEY"):
                st.success("✅ Configured")
            else:
                st.warning("⚠️ Not set")
        with c3:
            st.subheader("Email (SMTP)")
            if get_nested_secret("smtp", "user"):
                st.success("✅ Configured")
            else:
                st.warning("⚠️ Demo mode")
        with c4:
            st.subheader("Notifications")
            if get_nested_secret("telegram", "bot_token"):
                st.success("✅ Configured")
            else:
                st.info("ℹ️ Optional")

        st.divider()
        st.header("📊 Statistics")

        stats, _ = execute_query("""
            SELECT COUNT(*) as count,
                   COALESCE(SUM(citation_count), 0) as citations,
                   MAX(publication_year) as latest_year
            FROM publications
        """)
        if stats:
            s = stats[0]
            c1, c2, c3 = st.columns(3)
            with c1:
                st.metric("Publications", s.get("count", 0))
            with c2:
                st.metric("Total Citations", f"{s.get('citations', 0):,}")
            with c3:
                st.metric("Latest Year", s.get("latest_year", "N/A"))

    # ── Tab 2: Researchers ─────────────────────────────────────────────────
    with tab2:
        st.header("👥 Manage Researchers")
        st.subheader("➕ Add New Researcher")

        c1, c2, c3 = st.columns(3)
        with c1:
            new_orcid = st.text_input("ORCID", placeholder="0000-0000-0000-0000", key="new_orcid")
        with c2:
            new_name  = st.text_input("Name", placeholder="Researcher Name", key="new_name")
        with c3:
            new_inst  = st.text_input("Institution", placeholder="University/Organization", key="new_inst")

        if st.button("Add Researcher", type="primary"):
            if new_orcid:
                ok, err = add_researcher(orcid=new_orcid, name=new_name, institution=new_inst)
                if ok:
                    st.success(f"✅ Added: {new_name or new_orcid}")
                    log_audit("researcher_added", new_orcid)
                    st.rerun()
                else:
                    st.error(f"❌ {err}")
            else:
                st.warning("Please enter an ORCID")

        st.divider()
        st.subheader("📋 Current Researchers")

        researchers = get_active_researchers()
        if researchers:
            for r in researchers:
                with st.container():
                    c1, c2, c3, c4, c5 = st.columns([3, 2, 1, 1, 1])
                    with c1:
                        st.markdown(f"**{r.get('name') or r.get('orcid', '')[:8]}…**")
                        st.caption(f"ORCID: {r.get('orcid', 'N/A')}")
                    with c2:
                        st.caption(f"🏛️ {r.get('institution', 'Not specified')}")
                    with c3:
                        pubs = load_publications(orcid=r.get('orcid'))
                        st.caption(f"📄 {len(pubs)} pubs")
                    with c4:
                        if st.button("🔄 Sync", key=f"sync_{r.get('orcid')}", help="Sync from OpenAlex"):
                            with st.spinner("Syncing…"):
                                cnt, err = sync_from_openalex(r.get('orcid'))
                            if err:
                                st.error(f"❌ {err}")
                            else:
                                st.success(f"✅ +{cnt}")
                                log_audit("researcher_sync", f"{r.get('orcid')}: +{cnt}")
                                st.rerun()
                    with c5:
                        if st.button("🗑️", key=f"del_{r.get('orcid')}", help="Remove researcher"):
                            ok, err = remove_researcher(r.get('orcid'))
                            if ok:
                                st.success("✅ Removed")
                                log_audit("researcher_removed", r.get('orcid'))
                                st.rerun()
                            else:
                                st.error(f"❌ {err}")
                    st.divider()
        else:
            st.info("No researchers added yet.")

    # ── Tab 3: Settings ────────────────────────────────────────────────────
    with tab3:
        st.header("System Settings")

        st.subheader("AI Configuration")
        current_model = get_secret("AI_MODEL") or "llama-3.3-70b-versatile"
        st.info(f"**Active model:** `{current_model}`  \nSet the `AI_MODEL` key in your environment or secrets to change it.")

        st.divider()
        st.subheader("Cache Management")
        if st.button("🗑️ Clear Application Cache"):
            st.cache_data.clear()
            log_audit("cache_cleared")
            st.success("✅ Cache cleared!")

        if st.button("💾 Flush Audit Log to Storage"):
            flush_audit_log()
            st.success("✅ Audit log flushed!")

        st.divider()
        st.subheader("Security")
        st.info(f"**Admin Email:** {admin_email}")
        st.info(
            "To change admin credentials, update the `[admin]` section in your "
            "environment secrets."
        )

    # ── Tab 4: Audit Log ───────────────────────────────────────────────────
    with tab4:
        st.header("Security Audit Log")
        st.markdown("*Recent security-relevant events*")

        col_load, _ = st.columns([1, 3])
        with col_load:
            if st.button("🔄 Load from Storage"):
                load_audit_log_from_hf()
                st.success("Loaded!")

        audit_log = get_audit_log()
        if audit_log:
            for entry in reversed(audit_log[-50:]):
                ts     = entry.get('timestamp', '')[:19]
                action = entry.get('action', 'unknown')
                detail = entry.get('details', '')
                st.markdown(f"`{ts}` **{action}** {detail}")
        else:
            st.info("No audit events recorded yet.")

# ── Footer ─────────────────────────────────────────────────────────────────
st.divider()
st.markdown(
    "<div style='text-align:center;color:#64748b;font-size:0.8rem;'>"
    "🔒 Secure Admin Panel · All actions are logged"
    "</div>",
    unsafe_allow_html=True,
)
