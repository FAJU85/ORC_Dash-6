"""
ORC Research Dashboard - Notification Utilities
OTP delivery (email → Telegram fallback) and bug-report notifications.
"""

import smtplib
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from utils.security import get_nested_secret, log_audit


# ── OTP delivery ────────────────────────────────────────────────────────────

def _send_otp_via_email(recipient_email: str, otp_code: str):
    """Try SMTP delivery. Returns (success, error_str)."""
    smtp_host     = get_nested_secret("smtp", "host", "smtp.gmail.com")
    smtp_port     = int(get_nested_secret("smtp", "port", "587"))
    smtp_user     = get_nested_secret("smtp", "user", "")
    smtp_password = get_nested_secret("smtp", "password", "")

    if not smtp_user or not smtp_password:
        return False, "SMTP_NOT_CONFIGURED"

    msg = MIMEMultipart()
    msg["From"]    = smtp_user
    msg["To"]      = recipient_email
    msg["Subject"] = "ORC Dashboard – Login Verification Code"
    msg.attach(MIMEText(
        f"Your verification code is:\n\n{otp_code}\n\n"
        "This code expires in 5 minutes.\n\n— ORC Research Dashboard",
        "plain",
    ))

    try:
        server = smtplib.SMTP(smtp_host, smtp_port, timeout=10)
        server.starttls()
        server.login(smtp_user, smtp_password)
        server.send_message(msg)
        server.quit()
        log_audit("otp_email_sent", f"To:{recipient_email[:3]}***")
        return True, None
    except smtplib.SMTPAuthenticationError:
        log_audit("otp_email_auth_error")
        return False, "SMTP authentication failed"
    except Exception as e:
        log_audit("otp_email_error", type(e).__name__)
        return False, f"SMTP error: {type(e).__name__}"


def _send_otp_via_telegram(otp_code: str):
    """Try Telegram delivery. Returns (success, error_str)."""
    bot_token = get_nested_secret("telegram", "bot_token", "")
    chat_id   = get_nested_secret("telegram", "admin_chat_id", "")

    if not bot_token or not chat_id:
        return False, "TELEGRAM_NOT_CONFIGURED"

    text = (
        f"🔐 *ORC Dashboard – Login Code*\n\n"
        f"Your verification code is:\n\n"
        f"`{otp_code}`\n\n"
        f"This code expires in 5 minutes."
    )
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
            timeout=10,
        )
        if resp.status_code == 200:
            log_audit("otp_telegram_sent")
            return True, None
        return False, f"Telegram API {resp.status_code}"
    except Exception as e:
        log_audit("otp_telegram_error", type(e).__name__)
        return False, f"Telegram error: {type(e).__name__}"


def send_otp_email(recipient_email: str, otp_code: str):
    """
    Deliver OTP to the admin.
    Tries email first; falls back to Telegram if email fails.
    Returns (success, error_or_None).
    """
    # 1. Try email
    ok, err = _send_otp_via_email(recipient_email, otp_code)
    if ok:
        return True, None

    log_audit("otp_email_failed_trying_telegram", err)

    # 2. Fall back to Telegram
    ok, err = _send_otp_via_telegram(otp_code)
    if ok:
        return True, None

    # 3. Both failed
    return False, "SMTP_NOT_CONFIGURED"


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
