"""
ORC Research Dashboard - Notification Utilities
OTP delivery via Telegram (through Cloudflare Worker relay) and bug-report notifications.
"""

import json
import urllib.request
import urllib.parse
import requests
from utils.security import get_secret, get_nested_secret, log_audit


# ── OTP delivery ─────────────────────────────────────────────────────────────

def _send_otp_via_telegram(otp_code: str):
    """
    Send OTP via Telegram.
    Tries the Cloudflare Worker relay first (bypasses HF Spaces network block).
    Falls back to direct Telegram API if no relay is configured.
    """
    relay_url    = get_secret("TELEGRAM_RELAY_URL")
    relay_secret = get_secret("TELEGRAM_RELAY_SECRET")

    # ── Path A: relay (recommended for HF Spaces) ────────────────────────
    if relay_url:
        try:
            payload = json.dumps({
                "otp": otp_code,
                "secret": relay_secret or "",
            }).encode()
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
                return False, f"Relay→Telegram: {err}"
        except Exception as e:
            log_audit("otp_telegram_relay_error", f"{type(e).__name__}: {e}")
            return False, f"Relay error: {type(e).__name__}: {e}"

    # ── Path B: direct API (works outside HF Spaces) ─────────────────────
    bot_token = get_nested_secret("telegram", "bot_token", "")
    chat_id   = get_nested_secret("telegram", "admin_chat_id", "")

    if not bot_token or not chat_id:
        log_audit("otp_telegram_not_configured")
        return False, "TELEGRAM_NOT_CONFIGURED"

    text = (
        f"ORC Dashboard - Login Code\n\n"
        f"Your verification code is:\n\n{otp_code}\n\n"
        f"This code expires in 5 minutes."
    )
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode()
    try:
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            data=data, method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            result = json.loads(resp.read())
            if result.get("ok"):
                log_audit("otp_telegram_sent", "direct")
                return True, None
            err = result.get("description", "unknown")
            log_audit("otp_telegram_api_error", err)
            return False, f"Telegram: {err}"
    except Exception as e:
        log_audit("otp_telegram_error", f"{type(e).__name__}: {e}")
        return False, f"{type(e).__name__}: {e}"


def send_otp_email(recipient_email: str, otp_code: str):
    """Deliver OTP via Telegram relay. Returns (success, error_or_None)."""
    return _send_otp_via_telegram(otp_code)


def send_otp_email(recipient_email: str, otp_code: str):
    """
    Deliver OTP via Telegram. Falls back to demo mode (on-screen) if Telegram fails.
    Returns (success, error_or_None).
    """
    return _send_otp_via_telegram(otp_code)


# ── Bug-report notifications ─────────────────────────────────────────────────

def send_bug_report_notification(summary, full_description, user_contact, github_url=None):
    """Send bug report notification via Telegram."""
    try:
        bot_token = get_nested_secret("telegram", "bot_token", "")
        chat_id   = get_nested_secret("telegram", "admin_chat_id", "")

        if not bot_token or not chat_id:
            return False, "Telegram not configured"

        desc_truncated = full_description[:200]
        ellipsis = "…" if len(full_description) > 200 else ""

        message = (
            f"🐞 *NEW BUG REPORT*\n\n"
            f"*Summary:* {summary[:100]}\n\n"
            f"*From:* {user_contact or 'Anonymous'}\n\n"
            f"*Description:*\n{desc_truncated}{ellipsis}"
        )
        if github_url:
            message += f"\n\n🔗 [View on GitHub]({github_url})"

        resp = requests.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"},
            timeout=10,
        )
        if resp.status_code == 200:
            log_audit("telegram_notification_sent")
            return True, None
        return False, "Telegram API error"
    except Exception as e:
        log_audit("telegram_error", type(e).__name__)
        return False, "Notification failed"


# ── GitHub issue creation ────────────────────────────────────────────────────

def create_github_issue(summary, description, steps, expected_actual, user_contact):
    """Create a GitHub issue for a bug report."""
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
            f"**Source:** ORC Research Dashboard\n"
        )
        resp = requests.post(
            f"https://api.github.com/repos/{repo_owner}/{repo_name}/issues",
            headers={
                "Authorization": f"Bearer {github_token}",
                "Accept": "application/vnd.github.v3+json",
            },
            json={"title": f"[Bug] {summary[:100]}", "body": body, "labels": ["bug", "from-dashboard"]},
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
