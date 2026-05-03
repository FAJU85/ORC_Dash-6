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
from utils.styles import (
    apply_styles, get_theme, hero_html, section_title_html,
    footer_html, DARK, LIGHT
)

st.set_page_config(page_title="Admin", page_icon="🔐", layout="wide")

apply_styles()

colors = DARK if get_theme() == "dark" else LIGHT

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

st.markdown(hero_html("🔐 Administrator Panel", "Secure system management & audit console"), unsafe_allow_html=True)

# Support both flat env vars (ADMIN_EMAIL / ADMIN_PASSWORD) and nested secrets
admin_email    = get_secret("ADMIN_EMAIL")    or get_nested_secret("admin", "email", "")
admin_password = get_secret("ADMIN_PASSWORD") or get_nested_secret("admin", "password", "")
admin_hash     = get_nested_secret("admin", "password_hash", "")

# If a plain-text password is provided, hash it on the fly
if admin_password and not admin_hash:
    admin_hash = hash_password(admin_password)

if not admin_email or not admin_hash:
    st.markdown(
        f'<div class="orc-card" style="border-left:3px solid {colors["warning"]};max-width:640px">'
        f'<div style="font-weight:600;font-size:0.95rem;margin-bottom:0.5rem">⚠️ Administrator account not configured</div>'
        f'<div style="font-size:0.85rem;color:{colors["text2"]}">Add <code>ADMIN_EMAIL</code> and <code>ADMIN_PASSWORD</code> (or <code>admin.password_hash</code>) to your secrets. See <code>SECRETS_TEMPLATE.toml</code> for instructions.</div>'
        f'</div>',
        unsafe_allow_html=True,
    )
    st.stop()

# ============================================
# AUTHENTICATION
# ============================================

if not st.session_state.admin_authenticated:

    if not st.session_state.otp_sent:
        # ── Step 1: Email + Password ─────────────────────────────────────
        st.markdown(section_title_html("Administrator Login"), unsafe_allow_html=True)

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

        st.markdown(
            f'<div style="text-align:center;color:{colors["muted"]};font-size:0.82rem;margin-top:1rem">'
            f'🔒 Two-factor authentication required · A verification code will be sent to your email'
            f'</div>',
            unsafe_allow_html=True,
        )

    else:
        # ── Step 2: OTP Verification ──────────────────────────────────────
        st.markdown(section_title_html("Verification Code"), unsafe_allow_html=True)
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

    top_c1, top_c2 = st.columns([5, 1])
    with top_c1:
        st.markdown(
            f'<div style="font-size:0.85rem;color:{colors["success"]};font-weight:500">✓ Authenticated as Administrator</div>',
            unsafe_allow_html=True,
        )
    with top_c2:
        if st.button("Logout", use_container_width=True):
            admin_logout()
            st.rerun()

    st.divider()

    tab1, tab2, tab3, tab4 = st.tabs(["Dashboard", "Researchers", "Settings", "Audit Log"])

    # ── Tab 1: Dashboard ───────────────────────────────────────────────────
    with tab1:
        st.markdown(section_title_html("Service Status"), unsafe_allow_html=True)

        def _svc(label, ok, ok_txt, warn_txt, is_info=False):
            """
            Render an HTML status card for a service with a color-coded message.
            
            Parameters:
                label (str): Visible title for the status card.
                ok (bool): Whether the service is considered healthy; controls color and message choice.
                ok_txt (str): Message shown when `ok` is True.
                warn_txt (str): Message shown when `ok` is False.
                is_info (bool, optional): If True and `ok` is False, use a muted/info color instead of a warning color. Defaults to False.
            
            Returns:
                str: An HTML string for a compact, styled status card suitable for embedding in the dashboard.
            """
            c = colors["success"] if ok else (colors["muted"] if is_info else colors["warning"])
            txt = ok_txt if ok else warn_txt
            return (
                f'<div class="orc-card" style="padding:0.9rem 1.25rem">'
                f'  <div style="font-weight:600;font-size:0.85rem;margin-bottom:0.2rem">{label}</div>'
                f'  <div style="font-size:0.78rem;color:{c}">{txt}</div>'
                f'</div>'
            )

        c1, c2, c3, c4 = st.columns(4)
        c1.markdown(_svc("Database",      is_db_configured(),                                    "Connected",   "Not configured"),  unsafe_allow_html=True)
        c2.markdown(_svc("AI Service",    bool(get_secret("AI_API_KEY") or get_secret("GROQ_API_KEY")), "Configured", "Not set"),    unsafe_allow_html=True)
        c3.markdown(_svc("Email (SMTP)",  bool(get_nested_secret("smtp", "user")),               "Configured",  "Demo mode"),       unsafe_allow_html=True)
        c4.markdown(_svc("Telegram",      bool(get_nested_secret("telegram", "bot_token")),      "Configured",  "Optional",  True), unsafe_allow_html=True)

        st.markdown(section_title_html("Statistics"), unsafe_allow_html=True)

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
        st.markdown(section_title_html("Add Researcher"), unsafe_allow_html=True)

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

        st.markdown(section_title_html("Current Researchers"), unsafe_allow_html=True)

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
        st.markdown(section_title_html("AI Configuration"), unsafe_allow_html=True)
        current_model = get_secret("AI_MODEL") or "llama-3.3-70b-versatile"
        st.markdown(
            f'<div class="orc-card" style="padding:0.9rem 1.25rem">'
            f'<div style="font-size:0.8rem;color:{colors["text2"]}">Active model</div>'
            f'<div style="font-weight:600;font-family:monospace;font-size:0.9rem;margin-top:0.2rem">{current_model}</div>'
            f'<div style="font-size:0.78rem;color:{colors["muted"]};margin-top:0.25rem">Set <code>AI_MODEL</code> in your secrets to override.</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

        st.markdown(section_title_html("Maintenance"), unsafe_allow_html=True)
        mc1, mc2 = st.columns(2)
        with mc1:
            if st.button("🗑️ Clear Application Cache", use_container_width=True):
                st.cache_data.clear()
                log_audit("cache_cleared")
                st.success("✅ Cache cleared!")
        with mc2:
            if st.button("💾 Flush Audit Log to Storage", use_container_width=True):
                flush_audit_log()
                st.success("✅ Audit log flushed!")

        st.markdown(section_title_html("Security"), unsafe_allow_html=True)
        st.markdown(
            f'<div class="orc-card" style="padding:0.9rem 1.25rem">'
            f'<div style="font-size:0.8rem;color:{colors["text2"]}">Admin email</div>'
            f'<div style="font-weight:600;font-size:0.9rem;margin-top:0.2rem">{admin_email}</div>'
            f'<div style="font-size:0.78rem;color:{colors["muted"]};margin-top:0.25rem">Update credentials via the <code>[admin]</code> section in your secrets.</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    # ── Tab 4: Audit Log ───────────────────────────────────────────────────
    with tab4:
        st.markdown(section_title_html("Security Audit Log"), unsafe_allow_html=True)

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
st.markdown(footer_html("🔒 All admin actions are logged"), unsafe_allow_html=True)
