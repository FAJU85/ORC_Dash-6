"""
ORC Research Dashboard - Secure Admin Panel
Two-factor authentication with rate limiting and audit logging.
"""

import hmac
import uuid
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
    load_publications, sync_from_openalex, sync_by_display_name, load_researchers,
    flush_audit_log, flush_error_log,
    load_ai_settings, save_ai_settings,
    load_cms_content, save_cms_content,
)
from utils.prompt_builder import preview_integration
from utils.styles import (
    apply_styles, get_theme, hero_html, section_title_html,
    footer_html, render_navbar, DARK, LIGHT
)

apply_styles()
render_navbar()

colors = DARK if get_theme() == "dark" else LIGHT
_cms = st.session_state.get("_cms_override") or load_cms_content()

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
    ("admin_orcid_to_delete_confirm", None), # Added for researcher removal confirmation
    ("confirm_clear_error_log", False),      # Added for error log clear confirmation
]:
    if key not in st.session_state:
        st.session_state[key] = default

# ============================================
# PAGE
# ============================================

_admin_hero = _cms.get("admin_hero", {})
if _admin_hero.get("enabled", True):
    st.markdown(
        hero_html(
            _admin_hero.get("title", "").strip() or "🔐 Administrator Panel",
            _admin_hero.get("subtitle", "").strip() or "Secure system management & audit console",
        ),
        unsafe_allow_html=True,
    )

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

            st.warning(
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

        def _svc(label: str, ok: bool, ok_txt: str, warn_txt: str, is_info: bool = False) -> str:
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
                
                with st.spinner("Adding researcher…"): # Add spinner here
                    if not validate_orcid(orcid_clean):
                        st.error("❌ Invalid ORCID format — expected: 0000-0000-0000-0000")
                    else:
                        ok, err = add_researcher(orcid=orcid_clean, name=new_name, institution=new_inst)
                        if ok:
                            st.success(f"✅ Added: {new_name or orcid_clean}")
                            log_audit("researcher_added", orcid_clean)
                            st.rerun()
                        elif 'conflict' in (err or '').lower():
                            st.warning('⚠️ Another update was in progress. Please try again.')
                        else:
                            st.error(f"❌ {err}")
                            if "HF_REPO_ID" in (err or ""):
                                st.info("Add HF_TOKEN and HF_REPO_ID to your Space secrets to enable data storage.")
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
                            st.session_state.admin_orcid_to_delete_confirm = r.get('orcid')
                            st.rerun() # Trigger rerun to show confirmation dialog
                    st.divider()
            
            # Confirmation dialog for researcher removal
            if st.session_state.get("admin_orcid_to_delete_confirm"):
                orcid_to_delete = st.session_state.admin_orcid_to_delete_confirm
                st.warning(f"Are you sure you want to remove researcher {orcid_to_delete}? This action cannot be undone.")
                col_del_c1, col_del_c2 = st.columns(2)
                with col_del_c1:
                    if st.button("Confirm Remove", key="admin_confirm_remove_researcher_yes", type="secondary", use_container_width=True):
                        with st.spinner(f"Removing {orcid_to_delete}…"):
                            ok, err = remove_researcher(orcid_to_delete)
                            if ok:
                                st.success(f"✅ Removed: {orcid_to_delete}")
                                log_audit("researcher_removed", orcid_to_delete)
                            else:
                                st.error(f"❌ {err}")
                        st.session_state.admin_orcid_to_delete_confirm = None
                        st.rerun()
                with col_del_c2:
                    if st.button("Cancel", key="admin_confirm_remove_researcher_no", use_container_width=True):
                        st.session_state.admin_orcid_to_delete_confirm = None
                        st.rerun()

            # Sync all researchers
            st.markdown("---")
            st.markdown("**Sync All Researchers**")
            if st.button("🔄 Sync All from OpenAlex", key="sync_all_researchers", type="primary"):
                results = []
                progress = st.progress(0)
                status_area = st.empty()
                for i, r in enumerate(researchers):
                    orcid = r.get("orcid", "")
                    name = r.get("name", orcid)
                    if not orcid:
                        continue
                    status_area.info(f"Syncing {name}…")
                    count, err = sync_from_openalex(orcid)
                    if err:
                        results.append(f"❌ {name}: {err}")
                    else:
                        results.append(f"✅ {name}: {count} new publication(s)")
                    progress.progress((i + 1) / len(researchers))
                status_area.empty()
                progress.empty()
                for r in results:
                    st.write(r)
                log_audit("sync_all_researchers")
                st.success("Sync complete.")

            st.markdown("---")
            st.markdown("**Sync by Author Name** (for researchers without ORCID)")
            _name_col1, _name_col2 = st.columns(2)
            _name_input = _name_col1.text_input("Display name", placeholder="AA Alfadda", key="admin_sync_name")
            _name_orcid = _name_col2.text_input("Link to ORCID (optional)", placeholder="0000-0000-0000-0000",
                                                 key="admin_sync_name_orcid")
            if st.button("🔎 Search & Import by Name", key="admin_btn_sync_name", type="primary",
                         disabled=not _name_input.strip()):
                with st.spinner(f"Searching for '{_name_input}'…"):
                    count, err = sync_by_display_name(_name_input.strip(), linked_orcid=_name_orcid.strip())
                if err:
                    st.error(f"❌ {err}")
                else:
                    st.success(f"✅ Imported {count} new publication(s) for '{_name_input}'")
                    log_audit("sync_by_name", f"admin: {_name_input[:30]}")
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
                with st.spinner("Searching for chat ID…"): # Add spinner here
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
                with st.spinner("Testing relay…"): # Add spinner here
                    try:
                        payload = _json.dumps({"otp": "123456", "secret": relay_secret or ""}).encode()
                        req_obj = urllib.request.Request(
                            relay_url, data=payload, method="POST",
                            headers={"Content-Type": "application/json"},
                        )
                        with urllib.request.urlopen(req_obj, timeout=15) as r:  # nosec B310 – HTTPS enforced above
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
                with st.spinner("Clearing cache…"): # Add spinner here
                    st.cache_data.clear()
                    log_audit("cache_cleared")
                st.success("✅ Cache cleared!")
        with mc2:
            if st.button("💾 Flush Audit Log to Storage", use_container_width=True):
                with st.spinner("Flushing audit log…"): # Add spinner here
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
                with st.spinner("Loading audit log..."):
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
                with st.spinner("Loading error log..."):
                    load_error_log_from_hf()
                st.success("Loaded!")
        with action_col2:
            if st.button("🗑️ Clear Error Log"):
                st.session_state.confirm_clear_error_log = True

        if st.session_state.get("confirm_clear_error_log"):
            st.warning("Are you sure you want to clear the error log? This action cannot be undone.")
            col_err_c1, col_err_c2 = st.columns(2)
            with col_err_c1:
                if st.button("Confirm Clear Error Log", key="confirm_clear_error_log_yes", type="secondary", use_container_width=True):
                    with st.spinner("Clearing error log…"): # Add spinner here
                        clear_error_log()
                        flush_error_log()
                        log_audit("error_log_cleared")
                    st.success("✅ Cleared!")
                    st.session_state.confirm_clear_error_log = False
                    st.rerun()
            with col_err_c2:
                if st.button("Cancel Clear Error Log", key="confirm_clear_error_log_no", use_container_width=True):
                    st.session_state.confirm_clear_error_log = False
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
            from html import escape as _esc_h
            for entry in reversed(error_log[-100:]):
                ts         = _esc_h(entry.get('timestamp', '')[:19])
                etype      = _esc_h(entry.get('error_type', 'error'))
                msg        = _esc_h(entry.get('message', ''))
                page       = _esc_h(entry.get('page', ''))
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

# ── AI Assistant Settings ──────────────────────────────────────────────────
if is_admin_authenticated():
    st.markdown(section_title_html("🤖 AI Assistant Settings"), unsafe_allow_html=True)
    st.caption(
        "Add custom instructions for the AI assistant. "
        "They are analyzed and integrated into the assistant's behaviour automatically. "
        "The core system rules remain private and cannot be overridden here."
    )

    current_settings = load_ai_settings()
    current_instructions = current_settings.get("custom_instructions", "")

    ai_custom = st.text_area(
        "Custom instructions",
        value=current_instructions,
        height=160,
        placeholder=(
            "Examples:\n"
            "- Focus primarily on genomics and bioinformatics research.\n"
            "- Always cite publication years when referencing papers.\n"
            "- Use a formal academic tone in all responses.\n"
            "- Avoid providing medical or clinical advice."
        ),
        key="admin_ai_custom_instructions",
        label_visibility="collapsed",
    )

    char_count = len(ai_custom)
    st.caption(f"{char_count:,} / 2,000 characters")

    if char_count > 2000:
        st.warning("⚠️ Instructions exceed 2,000 characters — please shorten them.")

    if ai_custom.strip():
        with st.expander("🔍 Preview how instructions will be integrated", expanded=False):
            st.code(preview_integration(ai_custom), language=None)

    col_ai1, col_ai2 = st.columns([1, 4])
    with col_ai1:
        save_disabled = char_count > 2000
        if st.button("💾 Save", type="primary", key="admin_ai_save",
                     use_container_width=True, disabled=save_disabled):
            new_settings = {**current_settings, "custom_instructions": ai_custom.strip()}
            ok, err = save_ai_settings(new_settings)
            if ok:
                st.success("✅ AI assistant instructions updated.")
                log_audit("ai_settings_updated", f"len={len(ai_custom.strip())}")
            else:
                # HF not configured — store in session so the current run uses it
                st.session_state["_ai_settings_override"] = new_settings
                st.info(f"ℹ️ {err or 'Saved for this session.'}")
    with col_ai2:
        if current_instructions and st.button(
            "🗑️ Clear instructions", key="admin_ai_clear", use_container_width=True
        ):
            ok, err = save_ai_settings({**current_settings, "custom_instructions": ""})
            if ok:
                st.success("✅ Custom instructions cleared.")
                log_audit("ai_settings_cleared", "")
            else:
                st.session_state["_ai_settings_override"] = {
                    **current_settings, "custom_instructions": ""
                }
                st.info(f"ℹ️ {err or 'Cleared for this session.'}")
            st.rerun()

    # ── Model routing overrides ─────────────────────────────────────────────
    st.markdown("<div style='margin-top:1.5rem'></div>", unsafe_allow_html=True)
    with st.expander("🔀 Model Routing Overrides", expanded=False):
        st.caption(
            "Set which model handles each task type. "
            "Leave on **(auto)** to keep the default routing rule."
        )
        from utils.model_router import ROUTING_TABLE, GROQ_MODELS

        current_routing = current_settings.get("model_routing", {})
        model_options   = ["(auto)"] + GROQ_MODELS
        new_routing: dict = {}

        _TASK_LABELS = {
            "quick_lookup":  "Quick factual lookup",
            "free_chat":     "General chat",
            "paper_summary": "Paper summary",
            "deep_analysis": "Deep analysis",
            "reasoning":     "Step-by-step reasoning",
            "methodology":   "Methodology analysis",
            "implications":  "Implications analysis",
        }

        routing_cols = st.columns(2)
        for i, task in enumerate(ROUTING_TABLE):
            if task == "structured_json":
                continue  # always hardcoded; not user-overridable
            col = routing_cols[i % 2]
            current_val = current_routing.get(task) or "(auto)"
            idx = model_options.index(current_val) if current_val in model_options else 0
            with col:
                chosen = st.selectbox(
                    _TASK_LABELS.get(task, task),
                    model_options, index=idx,
                    key=f"admin_routing_{task}",
                )
                new_routing[task] = None if chosen == "(auto)" else chosen

        if st.button("💾 Save Routing Rules", key="admin_routing_save", type="primary"):
            merged = {**current_settings, "model_routing": new_routing}
            ok, err = save_ai_settings(merged)
            if ok:
                st.success("✅ Routing rules saved.")
                log_audit("ai_routing_updated", str(new_routing))
            else:
                st.session_state["_ai_settings_override"] = merged
                st.info(f"ℹ️ {err or 'Saved for this session.'}")

# ── CMS — Content Management ──────────────────────────────────────────────────
if is_admin_authenticated():
    st.markdown(section_title_html("📝 Content Management"), unsafe_allow_html=True)
    st.caption("Customize text and content displayed across every page of the dashboard.")

    cms = st.session_state.get("_cms_override") or load_cms_content()

    def _cms_save(new_cms: dict, label: str) -> None:
        ok, err = save_cms_content(new_cms)
        if ok:
            st.success(f"✅ {label} saved.")
            log_audit("cms_updated", label)
        else:
            st.session_state["_cms_override"] = new_cms
            st.info(f"ℹ️ {err or 'Saved for this session.'}")

    cms_tab_global, cms_tab_home, cms_tab_pages, cms_tab_ai, cms_tab_footer = st.tabs(
        ["🌐 Global", "🏠 Home", "📄 Pages", "🤖 AI Assistant", "🔻 Footer"]
    )

    # ── Global ──────────────────────────────────────────────────────────────
    with cms_tab_global:
        st.caption("Override the site title and tagline shown in the browser and hero areas.")
        g_title    = st.text_input("Site title",   value=cms.get("site_title", ""),
                                   placeholder="ORC Research Dashboard", key="cms_g_title")
        g_tagline  = st.text_input("Site tagline", value=cms.get("site_tagline", ""),
                                   placeholder="Academic Analytics & Publication Intelligence Platform",
                                   key="cms_g_tagline")
        if st.button("💾 Save Global", key="cms_g_save", type="primary"):
            _cms_save({**cms, "site_title": g_title.strip(), "site_tagline": g_tagline.strip()},
                      "Global settings")

    # ── Home ────────────────────────────────────────────────────────────────
    with cms_tab_home:
        with st.expander("🦸 Hero Text", expanded=True):
            h = cms.get("home_hero", {})
            hh_title   = st.text_input("Title",    value=h.get("title", ""),
                                       placeholder="🔬 ORC Research Dashboard", key="cms_hh_title")
            hh_sub     = st.text_input("Subtitle", value=h.get("subtitle", ""),
                                       placeholder="Academic Analytics & Publication Intelligence Platform",
                                       key="cms_hh_sub")
            hh_enabled = st.toggle("Show hero", value=bool(h.get("enabled", False)), key="cms_hh_enabled")
            if st.button("💾 Save Hero", key="cms_hh_save", type="primary"):
                _cms_save({**cms, "home_hero": {
                    "title": hh_title.strip(), "subtitle": hh_sub.strip(), "enabled": hh_enabled}},
                    "Home hero text")

        with st.expander("📢 Announcements", expanded=True):
            st.caption("Add, edit, enable/disable, or delete announcement banners shown on the Home page.")

            _announcements = list(cms.get("announcements", []))

            # ── Existing announcements ────────────────────────────────────
            for _i, _ann in enumerate(_announcements):
                _ann_id = _ann.get("id", str(_i))
                _edit_key = f"_cms_edit_ann_{_ann_id}"
                _del_key  = f"_cms_del_ann_{_ann_id}"
                if _edit_key not in st.session_state:
                    st.session_state[_edit_key] = False
                if _del_key not in st.session_state:
                    st.session_state[_del_key] = False

                _color_badge = {"info": "🔵", "success": "🟢", "warning": "🟡"}.get(_ann.get("color", "info"), "🔵")
                _enabled_icon = "✅" if _ann.get("enabled") else "⏸️"
                _preview = (_ann.get("text", "") or "")[:60] + ("…" if len(_ann.get("text", "")) > 60 else "")

                # Card header row
                _hcols = st.columns([0.05, 0.55, 0.12, 0.12, 0.08, 0.08])
                _hcols[0].write(_color_badge)
                _hcols[1].caption(_preview or "_empty_")
                _hcols[2].write(_enabled_icon)
                if _hcols[3].button("✏️ Edit", key=f"cms_ann_edit_{_ann_id}"):
                    st.session_state[_edit_key] = not st.session_state[_edit_key]
                    st.session_state[_del_key] = False
                if _hcols[4].button("🗑️", key=f"cms_ann_del_{_ann_id}"):
                    st.session_state[_del_key] = not st.session_state[_del_key]
                    st.session_state[_edit_key] = False

                # Delete confirmation
                if st.session_state[_del_key]:
                    st.warning(f"Delete this announcement? \"{_preview}\"")
                    _dc1, _dc2 = st.columns(2)
                    if _dc1.button("Yes, delete", key=f"cms_ann_del_confirm_{_ann_id}", type="primary"):
                        try:
                            _new_anns = [a for a in _announcements if a.get("id") != _ann_id]
                            _cms_save({**cms, "announcements": _new_anns}, "Announcement deleted")
                            st.session_state[_del_key] = False
                            st.rerun()
                        except Exception as _e:
                            st.error(f"Error: {_e}")
                    if _dc2.button("Cancel", key=f"cms_ann_del_cancel_{_ann_id}"):
                        st.session_state[_del_key] = False
                        st.rerun()

                # Edit form
                if st.session_state[_edit_key]:
                    with st.container():
                        _et = st.text_area("Message", value=_ann.get("text", ""), height=80,
                                           key=f"cms_ann_etext_{_ann_id}")
                        _ec1, _ec2 = st.columns(2)
                        _clr_opts = ["info", "success", "warning"]
                        _cur_clr = _ann.get("color", "info")
                        _ec = _ec1.selectbox("Style", _clr_opts,
                                             index=_clr_opts.index(_cur_clr) if _cur_clr in _clr_opts else 0,
                                             key=f"cms_ann_eclr_{_ann_id}")
                        _eon = _ec2.toggle("Enabled", value=bool(_ann.get("enabled", True)),
                                           key=f"cms_ann_een_{_ann_id}")
                        _sb1, _sb2 = st.columns(2)
                        if _sb1.button("💾 Save", key=f"cms_ann_esave_{_ann_id}", type="primary"):
                            try:
                                _new_anns = []
                                for _a in _announcements:
                                    if _a.get("id") == _ann_id:
                                        _new_anns.append({**_a, "text": _et.strip(), "color": _ec, "enabled": _eon})
                                    else:
                                        _new_anns.append(_a)
                                _cms_save({**cms, "announcements": _new_anns}, "Announcement updated")
                                st.session_state[_edit_key] = False
                                st.rerun()
                            except Exception as _e:
                                st.error(f"Error: {_e}")
                        if _sb2.button("Cancel", key=f"cms_ann_ecancel_{_ann_id}"):
                            st.session_state[_edit_key] = False
                            st.rerun()
                st.divider()

            # ── Add new announcement ──────────────────────────────────────
            if "cms_add_ann_open" not in st.session_state:
                st.session_state["cms_add_ann_open"] = False

            if st.button("➕ Add New Announcement", key="cms_ann_add_btn"):
                st.session_state["cms_add_ann_open"] = not st.session_state["cms_add_ann_open"]

            if st.session_state["cms_add_ann_open"]:
                with st.container():
                    st.markdown("**New Announcement**")
                    _new_text  = st.text_area("Message", height=80, key="cms_ann_new_text",
                                              placeholder="e.g. Scheduled maintenance Sunday 2am UTC.")
                    _n1, _n2 = st.columns(2)
                    _new_color = _n1.selectbox("Style", ["info", "success", "warning"], key="cms_ann_new_color")
                    _new_en    = _n2.toggle("Enabled", value=True, key="cms_ann_new_en")
                    _nb1, _nb2 = st.columns(2)
                    if _nb1.button("💾 Add", key="cms_ann_new_save", type="primary"):
                        try:
                            _new_item = {
                                "id":      uuid.uuid4().hex[:8],
                                "text":    _new_text.strip(),
                                "color":   _new_color,
                                "enabled": _new_en,
                            }
                            _cms_save({**cms, "announcements": _announcements + [_new_item]},
                                      "Announcement added")
                            st.session_state["cms_add_ann_open"] = False
                            st.rerun()
                        except Exception as _e:
                            st.error(f"Error: {_e}")
                    if _nb2.button("Cancel", key="cms_ann_new_cancel"):
                        st.session_state["cms_add_ann_open"] = False
                        st.rerun()

    # ── Pages ───────────────────────────────────────────────────────────────
    with cms_tab_pages:
        st.caption("Override the hero title and subtitle on each page. Leave blank to use the default.")
        _PAGE_HEROES = [
            ("publications_hero",   "📚 Publications",    "📚 Publications",
             "Browse, search, and export your research portfolio"),
            ("analytics_hero",      "📊 Analytics",       "📈 Analytics",
             "Research metrics, publication trends, and collaboration insights"),
            ("bioinformatics_hero", "🧬 Bioinformatics",  "🧬 Bioinformatics",
             "Protein structure prediction · Genomic sequence & variant analysis"),
            ("settings_hero",       "⚙️ Settings",         "⚙️ Settings",
             "Customize your dashboard preferences and export publications"),
            ("bug_report_hero",     "🐛 Bug Report",      "🐛 Bug Report",
             "Help us improve by reporting issues you encounter"),
            ("admin_hero",          "🔐 Admin",           "🔐 Administrator Panel",
             "Secure system management & audit console"),
        ]
        for _phkey, _phlabel, _phdef_title, _phdef_sub in _PAGE_HEROES:
            with st.expander(_phlabel, expanded=False):
                _phero = cms.get(_phkey, {})
                _pht = st.text_input("Title",    value=_phero.get("title",    ""),
                                     placeholder=_phdef_title, key=f"cms_{_phkey}_title")
                _phs = st.text_input("Subtitle", value=_phero.get("subtitle", ""),
                                     placeholder=_phdef_sub,   key=f"cms_{_phkey}_sub")
                _phen = st.toggle("Show hero", value=bool(_phero.get("enabled", False)),
                                  key=f"cms_{_phkey}_enabled")
                if st.button("💾 Save", key=f"cms_{_phkey}_save", type="primary"):
                    _cms_save({**cms, _phkey: {
                        "title": _pht.strip(), "subtitle": _phs.strip(), "enabled": _phen}},
                        f"{_phlabel} hero")

    # ── AI Assistant ─────────────────────────────────────────────────────────
    with cms_tab_ai:
        with st.expander("🦸 Hero Text", expanded=True):
            ah = cms.get("ai_assistant_hero", {})
            ah_t   = st.text_input("Title",    value=ah.get("title",    ""),
                                   placeholder="🔬 AI Research Assistant", key="cms_ah_title")
            ah_s   = st.text_input("Subtitle", value=ah.get("subtitle", ""),
                                   placeholder="Structured analysis and Q&A — results remembered within your session",
                                   key="cms_ah_sub")
            ah_en  = st.toggle("Show hero", value=bool(ah.get("enabled", False)), key="cms_ah_enabled")
            if st.button("💾 Save AI Hero", key="cms_ah_save", type="primary"):
                _cms_save({**cms, "ai_assistant_hero": {
                    "title": ah_t.strip(), "subtitle": ah_s.strip(), "enabled": ah_en}},
                    "AI assistant hero")

        with st.expander("💬 Chat Interface", expanded=False):
            _ai_wel_en    = st.toggle("Show welcome message", value=bool(cms.get("ai_welcome_enabled", True)),
                                      key="cms_ai_wel_en")
            ai_welcome    = st.text_area("Welcome message (shown when chat is empty)",
                                         value=cms.get("ai_welcome_message", ""), height=80,
                                         placeholder="Ask me anything about your research publications…",
                                         key="cms_ai_welcome")
            ai_placeholder = st.text_input("Chat input placeholder",
                                           value=cms.get("ai_input_placeholder", ""),
                                           placeholder="Ask about your research papers…",
                                           key="cms_ai_placeholder")
            if st.button("💾 Save Chat Text", key="cms_ai_chat_save", type="primary"):
                _cms_save({**cms,
                           "ai_welcome_message":   ai_welcome.strip(),
                           "ai_welcome_enabled":   _ai_wel_en,
                           "ai_input_placeholder": ai_placeholder.strip()},
                          "AI chat interface text")

        with st.expander("⚡ Quick Action Buttons", expanded=False):
            st.caption("Add, edit, enable/disable, or delete AI quick-action buttons.")

            _quick_btns = list(cms.get("ai_quick_buttons", []))

            # ── Existing buttons ──────────────────────────────────────────
            for _qi, _qb in enumerate(_quick_btns):
                _qid      = _qb.get("id", str(_qi))
                _qedit_k  = f"_cms_edit_qb_{_qid}"
                _qdel_k   = f"_cms_del_qb_{_qid}"
                if _qedit_k not in st.session_state:
                    st.session_state[_qedit_k] = False
                if _qdel_k not in st.session_state:
                    st.session_state[_qdel_k] = False

                _qen_icon = "✅" if _qb.get("enabled", True) else "⏸️"
                _qlbl_pre = (_qb.get("label", "") or "")[:40]
                _qpmt_pre = (_qb.get("prompt", "") or "")[:40]

                _qcols = st.columns([0.30, 0.35, 0.10, 0.12, 0.07, 0.06])
                _qcols[0].caption(f"**{_qlbl_pre}**")
                _qcols[1].caption(_qpmt_pre)
                _qcols[2].write(_qen_icon)
                if _qcols[3].button("✏️ Edit", key=f"cms_qb_edit_{_qid}"):
                    st.session_state[_qedit_k] = not st.session_state[_qedit_k]
                    st.session_state[_qdel_k] = False
                if _qcols[4].button("🗑️", key=f"cms_qb_del_{_qid}"):
                    st.session_state[_qdel_k] = not st.session_state[_qdel_k]
                    st.session_state[_qedit_k] = False

                # Delete confirmation
                if st.session_state[_qdel_k]:
                    st.warning(f"Delete button \"{_qlbl_pre}\"?")
                    _qdc1, _qdc2 = st.columns(2)
                    if _qdc1.button("Yes, delete", key=f"cms_qb_del_confirm_{_qid}", type="primary"):
                        try:
                            _new_qbs = [b for b in _quick_btns if b.get("id") != _qid]
                            _cms_save({**cms, "ai_quick_buttons": _new_qbs}, "Quick button deleted")
                            st.session_state[_qdel_k] = False
                            st.rerun()
                        except Exception as _e:
                            st.error(f"Error: {_e}")
                    if _qdc2.button("Cancel", key=f"cms_qb_del_cancel_{_qid}"):
                        st.session_state[_qdel_k] = False
                        st.rerun()

                # Edit form
                if st.session_state[_qedit_k]:
                    with st.container():
                        _qel  = st.text_input("Label", value=_qb.get("label", ""), key=f"cms_qb_elabel_{_qid}",
                                              placeholder="📝 Summarize")
                        _qep  = st.text_area("Prompt / action", value=_qb.get("prompt", ""), height=60,
                                             key=f"cms_qb_eprompt_{_qid}",
                                             placeholder="summarize  OR  Explain this paper in simple terms")
                        _qeen = st.toggle("Enabled", value=bool(_qb.get("enabled", True)),
                                          key=f"cms_qb_een_{_qid}")
                        _qes1, _qes2 = st.columns(2)
                        if _qes1.button("💾 Save", key=f"cms_qb_esave_{_qid}", type="primary"):
                            try:
                                _new_qbs = []
                                for _b in _quick_btns:
                                    if _b.get("id") == _qid:
                                        _new_qbs.append({**_b, "label": _qel.strip(),
                                                         "prompt": _qep.strip(), "enabled": _qeen})
                                    else:
                                        _new_qbs.append(_b)
                                _cms_save({**cms, "ai_quick_buttons": _new_qbs}, "Quick button updated")
                                st.session_state[_qedit_k] = False
                                st.rerun()
                            except Exception as _e:
                                st.error(f"Error: {_e}")
                        if _qes2.button("Cancel", key=f"cms_qb_ecancel_{_qid}"):
                            st.session_state[_qedit_k] = False
                            st.rerun()
                st.divider()

            # ── Add new quick button ──────────────────────────────────────
            if "cms_add_qb_open" not in st.session_state:
                st.session_state["cms_add_qb_open"] = False

            if st.button("➕ Add New Button", key="cms_qb_add_btn"):
                st.session_state["cms_add_qb_open"] = not st.session_state["cms_add_qb_open"]

            if st.session_state["cms_add_qb_open"]:
                with st.container():
                    st.markdown("**New Quick Action Button**")
                    _qnl  = st.text_input("Label", key="cms_qb_new_label",
                                          placeholder="📝 Summarize")
                    _qnp  = st.text_area("Prompt / action", height=60, key="cms_qb_new_prompt",
                                         placeholder="summarize  OR  Explain this paper in simple terms")
                    _qnen = st.toggle("Enabled", value=True, key="cms_qb_new_en")
                    _qnb1, _qnb2 = st.columns(2)
                    if _qnb1.button("💾 Add", key="cms_qb_new_save", type="primary"):
                        try:
                            _new_qitem = {
                                "id":      uuid.uuid4().hex[:8],
                                "label":   _qnl.strip(),
                                "prompt":  _qnp.strip(),
                                "enabled": _qnen,
                            }
                            _cms_save({**cms, "ai_quick_buttons": _quick_btns + [_new_qitem]},
                                      "Quick button added")
                            st.session_state["cms_add_qb_open"] = False
                            st.rerun()
                        except Exception as _e:
                            st.error(f"Error: {_e}")
                    if _qnb2.button("Cancel", key="cms_qb_new_cancel"):
                        st.session_state["cms_add_qb_open"] = False
                        st.rerun()

    # ── Footer ───────────────────────────────────────────────────────────────
    with cms_tab_footer:
        _fn_en = st.toggle("Show footer note", value=bool(cms.get("footer_note_enabled", True)),
                           key="cms_fn_enabled")
        fn = st.text_area("Footer note (shown on every page below the built-by line)",
                          value=cms.get("footer_note", ""), height=80, key="cms_fn",
                          placeholder="For internal use only · v2.0")
        if st.button("💾 Save Footer", key="cms_fn_save", type="primary"):
            _cms_save({**cms, "footer_note": fn.strip(), "footer_note_enabled": _fn_en}, "Footer note")
        if cms.get("footer_note") and st.button("🗑️ Clear Footer Note", key="cms_fn_clear"):
            _cms_save({**cms, "footer_note": "", "footer_note_enabled": False}, "Footer note cleared")
            st.rerun()

# ── Footer ─────────────────────────────────────────────────────────────────
st.divider()
st.markdown(footer_html("🔒 All admin actions are logged"), unsafe_allow_html=True)
