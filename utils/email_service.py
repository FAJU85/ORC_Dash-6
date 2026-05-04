"""
ORC Research Dashboard - Notification Utilities
OTP delivery via Telegram and bug-report notifications.
"""

import json
import urllib.request
import urllib.parse
import requests
from utils.security import get_secret, get_nested_secret, log_audit


# ── Internal helpers ──────────────────────────────────────────────────────────

def _get_bot_token() -> str:
    return (
        get_secret("TELEGRAM_BOT_TOKEN")
        or get_nested_secret("telegram", "bot_token", "")
    )


def _get_chat_id() -> str:
    return (
        get_secret("TELEGRAM_CHAT_ID")
        or get_nested_secret("telegram", "admin_chat_id", "")
    )


def _discover_chat_id(bot_token: str) -> str:
    """
    Call getUpdates and return the chat_id of the most recent message sender.
    Returns empty string if no updates are found or on error.
    """
    try:
        url = f"https://api.telegram.org/bot{bot_token}/getUpdates?limit=10&timeout=0"
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            if not data.get("ok"):
                return ""
            updates = data.get("result", [])
            if not updates:
                return ""
            # Use the most recent update's chat id
            last = updates[-1]
            msg = last.get("message") or last.get("edited_message") or {}
            chat = msg.get("chat", {})
            return str(chat.get("id", ""))
    except Exception:
        return ""


def _telegram_send(bot_token: str, chat_id: str, text: str, parse_mode: str = "") -> tuple:
    """Send a message via the Telegram Bot API. Returns (ok, error_str)."""
    params: dict = {"chat_id": chat_id, "text": text}
    if parse_mode:
        params["parse_mode"] = parse_mode
    data = urllib.parse.urlencode(params).encode()
    try:
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            data=data, method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            result = json.loads(resp.read())
            if result.get("ok"):
                return True, None
            err = result.get("description", "unknown error")
            return False, f"Telegram: {err}"
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


# ── OTP delivery ─────────────────────────────────────────────────────────────

def _send_otp_via_relay(otp_code: str, relay_url: str, relay_secret: str) -> tuple:
    """Send OTP through a Cloudflare Worker relay. Returns (ok, error_str)."""
    import urllib.parse as _up
    parsed = _up.urlparse(relay_url)
    if parsed.scheme != "https":
        return False, "Relay URL must use HTTPS"
    try:
        payload = json.dumps({"otp": otp_code, "secret": relay_secret or ""}).encode()
        req = urllib.request.Request(
            relay_url, data=payload, method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
            if result.get("ok"):
                log_audit("otp_telegram_sent", "via_relay")
                return True, None
            err = result.get("description", str(result))
            log_audit("otp_telegram_relay_error", err)
            return False, f"Relay error: {err}"
    except Exception as e:
        log_audit("otp_telegram_relay_error", f"{type(e).__name__}: {e}")
        return False, f"Relay: {type(e).__name__}: {e}"


def send_otp_email(recipient_email: str, otp_code: str) -> tuple:
    """
    Deliver OTP via Telegram. Tries relay → direct API → auto-discover chat_id.
    Returns (success, error_or_None).
    """
    text = (
        f"ORC Dashboard — Login Code\n\n"
        f"Verification code: {otp_code}\n\n"
        f"This code expires in 5 minutes. Do not share it."
    )

    # ── Path A: Cloudflare relay (preferred for HF Spaces) ───────────────
    relay_url = get_secret("TELEGRAM_RELAY_URL")
    if relay_url:
        ok, err = _send_otp_via_relay(otp_code, relay_url, get_secret("TELEGRAM_RELAY_SECRET") or "")
        if ok:
            return True, None
        log_audit("otp_relay_failed", err)
        # fall through to direct API

    # ── Path B: Direct Telegram Bot API ──────────────────────────────────
    bot_token = _get_bot_token()
    if not bot_token:
        log_audit("otp_telegram_not_configured")
        return False, "TELEGRAM_NOT_CONFIGURED"

    chat_id = _get_chat_id()

    # ── Path C: Auto-discover chat_id from getUpdates ─────────────────────
    if not chat_id:
        log_audit("otp_chat_id_missing", "attempting getUpdates")
        chat_id = _discover_chat_id(bot_token)
        if chat_id:
            log_audit("otp_chat_id_discovered", chat_id[:6] + "***")
        else:
            log_audit("otp_no_updates_found")
            return False, "CHAT_ID_NOT_CONFIGURED — send any message to the bot first, then try again"

    ok, err = _telegram_send(bot_token, chat_id, text)
    if ok:
        log_audit("otp_telegram_sent", "direct")
        return True, None
    log_audit("otp_telegram_api_error", err)
    return False, err


# ── Telegram utility: test connection ────────────────────────────────────────

def test_telegram_connection() -> dict:
    """
    Test the Telegram bot configuration.
    Returns a dict with keys: ok, bot_name, chat_id, error.
    """
    result = {"ok": False, "bot_name": "", "chat_id": "", "error": ""}

    bot_token = _get_bot_token()
    if not bot_token:
        result["error"] = "No bot token configured (TELEGRAM_BOT_TOKEN secret)"
        return result

    # Validate token via getMe
    try:
        url = f"https://api.telegram.org/bot{bot_token}/getMe"
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
            if not data.get("ok"):
                result["error"] = data.get("description", "Invalid token")
                return result
            result["bot_name"] = data["result"].get("username", "")
    except Exception as e:
        result["error"] = f"Cannot reach Telegram API: {type(e).__name__}: {e}"
        return result

    # Get or discover chat_id
    chat_id = _get_chat_id()
    if not chat_id:
        chat_id = _discover_chat_id(bot_token)

    if not chat_id:
        result["error"] = (
            "Bot token is valid but no chat ID found. "
            "Send any message to @" + result["bot_name"] + " first."
        )
        return result

    result["chat_id"] = chat_id

    # Send test message
    ok, err = _telegram_send(bot_token, chat_id, "✅ ORC Dashboard — Telegram connection test successful.")
    if ok:
        result["ok"] = True
    else:
        result["error"] = err
    return result


def get_telegram_chat_id() -> str:
    """Return the configured or auto-discovered admin chat ID, empty string if none."""
    bot_token = _get_bot_token()
    if not bot_token:
        return ""
    chat_id = _get_chat_id()
    if chat_id:
        return chat_id
    return _discover_chat_id(bot_token)


# ── SMTP email ───────────────────────────────────────────────────────────────

def send_smtp_email(subject: str, body: str, to_email: str = "") -> tuple:
    """
    Send a plain-text email via SMTP (Gmail-compatible).
    Reads SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD from secrets.
    Returns (success, error_or_None).
    """
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    smtp_host = get_secret("SMTP_HOST") or get_nested_secret("smtp", "host", "smtp.gmail.com")
    smtp_port = int(get_secret("SMTP_PORT") or get_nested_secret("smtp", "port", "587") or 587)
    smtp_user = get_secret("SMTP_USER") or get_nested_secret("smtp", "user", "")
    smtp_pass = get_secret("SMTP_PASSWORD") or get_nested_secret("smtp", "password", "")

    if not smtp_user or not smtp_pass:
        return False, "SMTP_NOT_CONFIGURED"

    if not to_email:
        to_email = (
            get_secret("ADMIN_EMAIL")
            or get_nested_secret("admin", "email", "")
        )
    if not to_email:
        return False, "No recipient email configured"

    try:
        msg = MIMEMultipart("alternative")
        msg["From"]    = smtp_user
        msg["To"]      = to_email
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain", "utf-8"))

        with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as server:
            server.ehlo()
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)

        log_audit("smtp_email_sent", to_email[:20])
        return True, None
    except Exception as e:
        log_audit("smtp_error", str(e)[:60])
        return False, str(e)


# ── Bug-report notifications ─────────────────────────────────────────────────

def send_bug_report_notification(summary, full_description, user_contact, github_url=None) -> tuple:
    """
    Send bug report via Telegram, then email as fallback.
    Returns (success, error_or_None).
    """
    desc_snippet = full_description[:400] + ("…" if len(full_description) > 400 else "")

    # ── Try Telegram ──────────────────────────────────────────────────────
    bot_token = _get_bot_token()
    chat_id   = _get_chat_id() or (bot_token and _discover_chat_id(bot_token)) or ""

    if bot_token and chat_id:
        message = (
            f"🐞 NEW BUG REPORT\n\n"
            f"Summary: {summary[:100]}\n"
            f"From: {user_contact or 'Anonymous'}\n\n"
            f"{desc_snippet}"
        )
        if github_url:
            message += f"\n\nIssue: {github_url}"
        ok, _ = _telegram_send(bot_token, chat_id, message)
        if ok:
            log_audit("bug_report_telegram_sent")
            return True, None
        log_audit("bug_report_telegram_failed")

    # ── Fallback: SMTP email ──────────────────────────────────────────────
    subject = f"[ORC Bug Report] {summary[:80]}"
    body = (
        f"Bug Report\n{'='*40}\n\n"
        f"Summary  : {summary}\n"
        f"Reporter : {user_contact or 'Anonymous'}\n\n"
        f"Description:\n{full_description}\n"
    )
    if github_url:
        body += f"\nGitHub Issue: {github_url}\n"

    email_ok, email_err = send_smtp_email(subject, body)
    if email_ok:
        log_audit("bug_report_email_sent")
        return True, None

    log_audit("bug_report_all_failed", str(email_err)[:40])
    return False, f"Telegram not reachable; email: {email_err}"


# ── GitHub issue creation ────────────────────────────────────────────────────

def create_github_issue(summary, description, steps, expected_actual, user_contact) -> tuple:
    """Create a GitHub issue for a bug report. Returns (url_or_None, error_or_None)."""
    try:
        github_token = get_nested_secret("github", "token", "")
        repo_owner   = get_nested_secret("github", "owner", "")
        repo_name    = get_nested_secret("github", "repo", "")

        if not all([github_token, repo_owner, repo_name]):
            return None, "GitHub not configured"

        body = (
            f"## Bug Report\n\n"
            f"### Description\n{description}\n\n"
            f"### Steps to Reproduce\n{steps or 'Not provided'}\n\n"
            f"### Expected vs Actual\n{expected_actual or 'Not provided'}\n\n"
            f"---\n**Reporter:** {user_contact or 'Anonymous'}\n"
        )
        resp = requests.post(
            f"https://api.github.com/repos/{repo_owner}/{repo_name}/issues",
            headers={
                "Authorization": f"Bearer {github_token}",
                "Accept": "application/vnd.github.v3+json",
            },
            json={"title": f"[Bug] {summary[:100]}", "body": body, "labels": ["bug"]},
            timeout=10,
        )
        if resp.status_code == 201:
            data = resp.json()
            log_audit("github_issue_created", data.get("html_url", ""))
            return data.get("html_url"), None
        return None, "GitHub API error"
    except Exception as e:
        log_audit("github_error", type(e).__name__)
        return None, "Issue creation failed"
