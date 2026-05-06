"""
ORC Research Dashboard - Secure Admin Panel
Two-factor authentication with rate limiting and audit logging.
"""

import hmac
import streamlit as st
import sys
import os
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.security import (
    get_secret, get_nested_secret, hash_password, verify_password,
    generate_otp, validate_email, validate_otp, validate_orcid, sanitize_string,
    log_audit, get_audit_log, load_audit_log_from_hf,
    log_error, get_error_log, clear_error_log, load_error_log_from_hf,
    RateLimiter, is_admin_authenticated, admin_logout,
    execute_query, is_db_configured
)
from utils.email_service import send_otp_email
from utils.hf_data import (
    get_active_researchers, add_researcher, remove_researcher,
    load_publications, sync_from_openalex, load_researchers,
    flush_audit_log, flush_error_log
)
from utils.styles import (
    apply_styles, get_theme, hero_html, section_title_html,
    footer_html, render_navbar, DARK, LIGHT
)

apply_styles()
render_navbar()

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
    ("otp_via_telegram", False),
    ("otp_tg_error", ""),
]:
    if key not in st.session_state:
        st.session_state[key] = default

# ============================================
# PAGE
# ============================================

st.markdown(hero_html("🔐 Administrator Panel", "Secure system management & audit console"), unsafe_allow_html=True)

# Support both flat env vars (ADMIN_EMAIL / ADMIN_PASSWORD) and nested secrets
admin_email    = (get_secret("ADMIN_EMAIL")    or get_nested_secret("admin", "email",    "")).lower().strip()
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

    client_key = "admin_login"

    if not st.session_state.otp_sent:
        # ── Step 1: Email + Password ─────────────────────────────────────
        st.markdown(section_title_html("Administrator Login"), unsafe_allow_html=True)

        allowed, wait_time = rate_limiter.is_allowed(client_key, max_attempts=5, window_seconds=300)
        if not allowed:
            st.error(f"⚠️ Too many login attempts. Please wait {wait_time} seconds.")
            log_audit("login_rate_limited")
            st.stop()

        with st.form("login_form"):
            email_input    = st.text_input("Email", placeholder="admin@example.com")
            password_input = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Continue", type="primary", use_container_width=True)

        # ── Process outside the form so st.rerun() works reliably ──────────
        if submitted:
            rate_limiter.record_attempt(client_key)
            email = sanitize_string(email_input, 100).lower().strip()

            if not validate_email(email):
                st.error("❌ Invalid email format")
                log_audit("login_invalid_email", email[:20])
            elif email != admin_email:
                st.error("❌ Invalid credentials")
                log_audit("login_wrong_email", email[:20])
            elif not verify_password(password_input, admin_hash):
                st.error("❌ Invalid credentials")
                log_audit("login_wrong_password", email[:20])
            else:
                import threading
                otp = generate_otp()
                st.session_state.otp_code    = otp
                st.session_state.otp_expiry  = datetime.now() + timedelta(minutes=5)
                st.session_state.login_email = email

                # Try Telegram first; wait up to 10 s
                tg_result = {"ok": False, "err": ""}
                def _tg_send():
                    ok, err = send_otp_email(email, otp)
                    tg_result["ok"] = ok
                    tg_result["err"] = err or ""

                t = threading.Thread(target=_tg_send, daemon=True)
                t.start()
                with st.spinner("Sending verification code to Telegram…"):
                    t.join(timeout=10)

                st.session_state.otp_sent         = True
                st.session_state.otp_via_telegram = tg_result["ok"]
                st.session_state.otp_tg_error     = tg_result["err"]
                if tg_result["ok"]:
                    log_audit("otp_telegram_sent", email[:20])
                else:
                    log_audit("otp_fallback_screen", email[:20])
                st.rerun()

        st.markdown(
            f'<div style="text-align:center;color:{colors["muted"]};font-size:0.82rem;margin-top:1rem">'
            f'🔒 Two-factor authentication required · A verification code will be sent to your Telegram'
            f'</div>',
            unsafe_allow_html=True,
        )

    else:
        # ── Step 2: OTP Verification ──────────────────────────────────────
        st.markdown(section_title_html("Verification Code"), unsafe_allow_html=True)

        if st.session_state.get("otp_via_telegram"):
            st.success("✅ Verification code sent to your Telegram bot.")
        else:
            _has_token = bool(
                get_secret("TELEGRAM_BOT_TOKEN")
                or get_nested_secret("telegram", "bot_token", "")
            )
            tg_err = st.session_state.get("otp_tg_error", "")

            if _has_token and tg_err:
                if "CHAT_ID_NOT_CONFIGURED" in tg_err:
                    st.warning(
                        "⚠️ Bot token found but no Chat ID yet — "
                        "send any message to the bot in Telegram, then retry login."
                    )
                else:
                    st.warning(f"⚠️ Telegram unavailable (`{tg_err[:80]}`). Using on-screen code.")
            elif not _has_token:
                st.info("ℹ️ Telegram not configured — using on-screen code (demo mode).")
            else:
                st.warning("⚠️ Telegram delivery failed — using on-screen code as fallback.")

            st.error(
                "🔓 **Security notice:** This code is visible to anyone who can access "
                "this URL. Configure SMTP or Telegram in the Admin → Integrations panel "
                "for secure OTP delivery before using this in production."
            )
            st.markdown(
                f'<div class="orc-card" style="text-align:center;padding:1.5rem;'
                f'border:2px solid {colors["warning"]};margin-top:0.5rem">'
                f'<div style="font-size:0.75rem;font-weight:600;text-transform:uppercase;'
                f'letter-spacing:0.08em;color:{colors["warning"]};margin-bottom:0.5rem">'
                f'Verification Code</div>'
                f'<div style="font-size:2.2rem;font-weight:700;font-family:monospace;'
                f'letter-spacing:0.3em;color:{colors["text"]}">'
                f'{st.session_state.otp_code}</div>'
                f'<div style="font-size:0.75rem;color:{colors["muted"]};margin-top:0.4rem">'
                f'Expires in 5 minutes</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

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
                elif not hmac.compare_digest(str(otp_input), str(st.session_state.otp_code)):
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

    tab1, tab2, tab3, tab4, tab5 = st.tabs(["Dashboard", "Researchers", "Settings", "Audit Log", "Error Log"])

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
        c1.markdown(_svc("Database",      is_db_configured(),                                          "Connected",  "Not configured"),  unsafe_allow_html=True)
        c2.markdown(_svc("AI Service",    bool(get_secret("AI_API_KEY") or get_secret("GROQ_API_KEY")), "Configured", "Not set"),         unsafe_allow_html=True)
        c3.markdown(_svc("Email (SMTP)",  bool(get_nested_secret("smtp", "user")),                      "Configured", "Demo mode"),        unsafe_allow_html=True)
        c4.markdown(_svc("Telegram",      bool(get_nested_secret("telegram", "bot_token")),             "Configured", "Optional", True),   unsafe_allow_html=True)

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
                orcid_clean = new_orcid.strip()
                for prefix in ("https://orcid.org/", "http://orcid.org/"):
                    if orcid_clean.startswith(prefix):
                        orcid_clean = orcid_clean[len(prefix):]

                if not validate_orcid(orcid_clean):
                    st.error("❌ Invalid ORCID format — expected: 0000-0000-0000-0000")
                else:
                    ok, err = add_researcher(orcid=orcid_clean, name=new_name, institution=new_inst)
                    if ok:
                        st.success(f"✅ Added: {new_name or orcid_clean}")
                        log_audit("researcher_added", orcid_clean)
                        st.rerun()
                    else:
                        st.error(f"❌ {err}")
                        if "HF_REPO_ID" in (err or ""):
                            st.info("Add **HF_TOKEN** and **HF_REPO_ID** to your Space secrets to enable data storage.")
            else:
                st.warning("Please enter an ORCID")

        st.markdown(section_title_html("Current Researchers"), unsafe_allow_html=True)

        researchers = get_active_researchers()
        if researchers:
            hc1, hc2, hc3, hc4, hc5 = st.columns([3, 2, 1, 1, 1])
            with hc1:
                st.caption("**Researcher**")
            with hc2:
                st.caption("**Institution**")
            with hc3:
                st.caption("**Pubs**")
            with hc4:
                st.caption("**Sync**")
            with hc5:
                st.caption("**Remove**")
            st.divider()

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
                        if st.button("🔄 Sync", key=f"sync_{r.get('orcid')}", help="Sync publications"):
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

        st.markdown(section_title_html("Telegram Notifications"), unsafe_allow_html=True)
        from utils.email_service import test_telegram_connection, get_telegram_chat_id
        relay_url    = get_secret("TELEGRAM_RELAY_URL")
        relay_secret = get_secret("TELEGRAM_RELAY_SECRET")
        tg_token     = get_secret("TELEGRAM_BOT_TOKEN") or get_nested_secret("telegram", "bot_token", "")
        tg_chat_id   = get_secret("TELEGRAM_CHAT_ID") or get_nested_secret("telegram", "admin_chat_id", "")

        # Status cards
        sc1, sc2, sc3 = st.columns(3)
        sc1.markdown(
            f'<div class="orc-card" style="padding:0.75rem 1rem">'
            f'<div style="font-size:0.75rem;color:{colors["text2"]}">BOT TOKEN</div>'
            f'<div style="font-weight:600;font-size:0.82rem;color:{colors["success"] if tg_token else colors["warning"]}">'
            f'{"✅ Configured" if tg_token else "⚠️ Missing"}</div>'
            f'<div style="font-size:0.72rem;color:{colors["muted"]};margin-top:0.2rem">Secret: TELEGRAM_BOT_TOKEN</div>'
            f'</div>', unsafe_allow_html=True)
        sc2.markdown(
            f'<div class="orc-card" style="padding:0.75rem 1rem">'
            f'<div style="font-size:0.75rem;color:{colors["text2"]}">CHAT ID</div>'
            f'<div style="font-weight:600;font-size:0.82rem;color:{colors["success"] if tg_chat_id else colors["warning"]}">'
            f'{"✅ Configured" if tg_chat_id else "⚠️ Missing"}</div>'
            f'<div style="font-size:0.72rem;color:{colors["muted"]};margin-top:0.2rem">Secret: TELEGRAM_CHAT_ID</div>'
            f'</div>', unsafe_allow_html=True)
        sc3.markdown(
            f'<div class="orc-card" style="padding:0.75rem 1rem">'
            f'<div style="font-size:0.75rem;color:{colors["text2"]}">RELAY</div>'
            f'<div style="font-weight:600;font-size:0.82rem;color:{colors["success"] if relay_url else colors["muted"]}">'
            f'{"✅ Active" if relay_url else "— Not used"}</div>'
            f'<div style="font-size:0.72rem;color:{colors["muted"]};margin-top:0.2rem">Secret: TELEGRAM_RELAY_URL</div>'
            f'</div>', unsafe_allow_html=True)

        ta1, ta2 = st.columns(2)
        with ta1:
            if tg_token and st.button("🔍 Get My Chat ID", key="tg_get_chat_id",
                                      help="Finds your Telegram chat ID automatically — send any message to the bot first",
                                      use_container_width=True):
                discovered = get_telegram_chat_id()
                if discovered:
                    st.success(f"✅ Chat ID found: **`{discovered}`**")
                    st.info("Add this as `TELEGRAM_CHAT_ID` in your HF Space secrets.")
                else:
                    st.error("❌ No messages found. Send any message to the bot in Telegram, then try again.")
        with ta2:
            if tg_token and st.button("📨 Send Test Message", key="test_tg_direct",
                                      help="Sends a test message to verify everything works",
                                      use_container_width=True):
                with st.spinner("Testing…"):
                    res = test_telegram_connection()
                if res["ok"]:
                    st.success(f"✅ Message sent! Bot: @{res['bot_name']} · Chat: {res['chat_id']}")
                else:
                    st.error(f"❌ {res['error']}")

        if not tg_token:
            st.info(
                "**To set up Telegram notifications:**\n"
                "1. Create a bot via [@BotFather](https://t.me/botfather) on Telegram\n"
                "2. Add the bot token as `TELEGRAM_BOT_TOKEN` in your HF Space secrets\n"
                "3. Send any message to your bot\n"
                "4. Click **Get My Chat ID** above and add the result as `TELEGRAM_CHAT_ID`"
            )

        if relay_url and st.button("📡 Test Relay Connection", key="test_tg_relay"):
            import json as _json
            import urllib.request
            import urllib.parse
            if urllib.parse.urlparse(relay_url).scheme != "https":
                st.error("❌ TELEGRAM_RELAY_URL must use HTTPS")
            else:
                try:
                    payload = _json.dumps({"otp": "123456", "secret": relay_secret or ""}).encode()
                    req_obj = urllib.request.Request(
                        relay_url, data=payload, method="POST",
                        headers={"Content-Type": "application/json"},
                    )
                    with urllib.request.urlopen(req_obj, timeout=15) as r:
                        body = r.read().decode()
                    result = _json.loads(body)
                    if result.get("ok"):
                        st.success("✅ Relay test delivered! Check your Telegram.")
                    else:
                        st.error(f"❌ Relay error: {body}")
                except Exception as e:
                    st.error(f"❌ {type(e).__name__}: {e}")

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
            if st.button("🔄 Load from Storage", key="load_audit"):
                load_audit_log_from_hf()
                st.success("Loaded!")

        audit_log = get_audit_log()
        if audit_log:
            _DANGER  = {"login_wrong_email", "login_wrong_password", "login_rate_limited",
                        "otp_wrong_code", "otp_expired", "otp_rate_limited", "otp_invalid_format"}
            _WARNING = {"otp_sent", "otp_demo_mode", "sync_error", "ai_error",
                        "bug_report_submitted"}
            _SUCCESS = {"admin_login_success", "sync_complete", "researcher_added",
                        "researcher_removed", "researcher_sync", "cache_cleared"}

            from html import escape as _esc_h
            for entry in reversed(audit_log[-50:]):
                ts     = _esc_h(entry.get('timestamp', '')[:19])
                action = _esc_h(entry.get('action', 'unknown'))
                detail = _esc_h(entry.get('details', ''))

                if action in _DANGER:
                    icon, color = "🔴", "#ef4444"
                elif action in _WARNING:
                    icon, color = "🟡", "#f59e0b"
                elif action in _SUCCESS:
                    icon, color = "🟢", "#22c55e"
                else:
                    icon, color = "⚪", colors["muted"]

                st.markdown(
                    f"<div style='padding:0.25rem 0;border-left:3px solid {color};padding-left:0.6rem;margin-bottom:0.2rem'>"
                    f"<span style='font-size:0.8rem;color:{colors['text2']}'>{ts}</span> "
                    f"{icon} <strong>{action}</strong>"
                    + (f" <span style='color:{colors['text2']}'>{detail}</span>" if detail else "")
                    + "</div>",
                    unsafe_allow_html=True,
                )
        else:
            st.info("No audit events recorded yet.")

    # ── Tab 5: Error Log ───────────────────────────────────────────────────
    with tab5:
        st.markdown(section_title_html("Application Error Log"), unsafe_allow_html=True)
        st.markdown(
            f'<div style="font-size:0.82rem;color:{colors["text2"]};margin-bottom:0.75rem">'
            f'Exceptions and failures captured across all pages</div>',
            unsafe_allow_html=True,
        )

        action_col1, action_col2, _ = st.columns([1, 1, 3])
        with action_col1:
            if st.button("🔄 Load from Storage", key="load_errors"):
                load_error_log_from_hf()
                st.success("Loaded!")
        with action_col2:
            if st.button("🗑️ Clear Error Log"):
                clear_error_log()
                flush_error_log()
                log_audit("error_log_cleared")
                st.success("Cleared!")
                st.rerun()

        error_log = get_error_log()
        if error_log:
            st.caption(f"{len(error_log)} error(s) recorded")
            _TYPE_COLOURS = {
                "sync_error":       "#ef4444",
                "ai_service_error": "#f97316",
                "ai_import_error":  "#f97316",
                "db_query_error":   "#a855f7",
            }
            for entry in reversed(error_log[-100:]):
                ts         = entry.get('timestamp', '')[:19]
                etype      = entry.get('error_type', 'error')
                msg        = entry.get('message', '')
                page       = entry.get('page', '')
                color      = _TYPE_COLOURS.get(etype, "#ef4444")
                page_badge = (
                    f"<span style='background:{color}20;color:{color};"
                    f"padding:0.1rem 0.4rem;border-radius:4px;font-size:0.75rem;"
                    f"margin-left:0.5rem'>{page}</span>"
                    if page else ""
                )
                st.markdown(
                    f"<div style='padding:0.4rem 0;border-left:3px solid {color};"
                    f"padding-left:0.6rem;margin-bottom:0.3rem'>"
                    f"<span style='font-size:0.8rem;color:{colors['text2']}'>{ts}</span>"
                    f"{page_badge} "
                    f"<strong style='color:{color}'>{etype}</strong><br>"
                    f"<span style='font-size:0.9rem'>{msg}</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
        else:
            st.info("No errors recorded yet.")

# ── Footer ─────────────────────────────────────────────────────────────────
st.divider()
st.markdown(footer_html("🔒 All admin actions are logged"), unsafe_allow_html=True)
