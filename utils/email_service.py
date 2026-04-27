"""
ORC Research Dashboard - Email Utilities
Secure OTP delivery via email
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from utils.security import get_nested_secret, log_audit

def send_otp_email(recipient_email, otp_code):
    """
    Send OTP code via email
    Returns (success, error_message)
    """
    try:
        # Get SMTP settings from secrets
        smtp_host = get_nested_secret("smtp", "host", "smtp.gmail.com")
        smtp_port = int(get_nested_secret("smtp", "port", "587"))
        smtp_user = get_nested_secret("smtp", "user", "")
        smtp_password = get_nested_secret("smtp", "password", "")
        
        if not smtp_user or not smtp_password:
            log_audit("otp_email_no_smtp", "SMTP not configured")
            # In production without SMTP, we cannot send OTP
            # Return special code to indicate demo mode
            return False, "SMTP_NOT_CONFIGURED"
        
        # Create message
        msg = MIMEMultipart()
        msg['From'] = smtp_user
        msg['To'] = recipient_email
        msg['Subject'] = "ORC Dashboard - Login Verification Code"
        
        body = f"""
Your verification code for ORC Research Dashboard is:

{otp_code}

This code will expire in 5 minutes.

If you did not request this code, please ignore this email.

---
ORC Research Dashboard
        """
        
        msg.attach(MIMEText(body, 'plain'))
        
        # Send email
        server = smtplib.SMTP(smtp_host, smtp_port)
        server.starttls()
        server.login(smtp_user, smtp_password)
        server.send_message(msg)
        server.quit()
        
        log_audit("otp_email_sent", f"To: {recipient_email[:3]}***")
        return True, None
        
    except smtplib.SMTPAuthenticationError:
        log_audit("otp_email_auth_error")
        return False, "Email authentication failed"
    except Exception as e:
        log_audit("otp_email_error", str(type(e).__name__))
        return False, "Email delivery failed"

def send_bug_report_notification(summary, full_description, user_contact, github_url=None):
    """Send bug report notification via Telegram"""
    import requests
    
    try:
        bot_token = get_nested_secret("telegram", "bot_token", "")
        chat_id = get_nested_secret("telegram", "admin_chat_id", "")
        
        if not bot_token or not chat_id:
            return False, "Telegram not configured"
        
        # Truncate description to 200 chars for Telegram message
        desc_truncated = full_description[:200] if len(full_description) > 200 else full_description
        ellipsis = '...' if len(full_description) > 200 else ''
        
        message = f"""🐞 *NEW BUG REPORT*

*Summary:* {summary[:100]}

*From:* {user_contact or 'Anonymous'}

*Description:*
{desc_truncated}{ellipsis}"""
        
        if github_url:
            message += f"\n\n🔗 [View on GitHub]({github_url})"
        
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "Markdown"
        }
        
        response = requests.post(url, json=payload, timeout=10)
        
        if response.status_code == 200:
            log_audit("telegram_notification_sent")
            return True, None
        
        return False, "Telegram API error"
        
    except Exception as e:
        log_audit("telegram_error", str(type(e).__name__))
        return False, "Notification failed"

def create_github_issue(summary, description, steps, expected_actual, user_contact):
    """Create GitHub issue for bug report"""
    import requests
    
    try:
        github_token = get_nested_secret("github", "token", "")
        repo_owner = get_nested_secret("github", "owner", "")
        repo_name = get_nested_secret("github", "repo", "")
        
        if not all([github_token, repo_owner, repo_name]):
            return None, "GitHub not configured"
        
        body = f"""## Bug Report

### Description
{description}

### Steps to Reproduce
{steps or 'Not provided'}

### Expected vs Actual
{expected_actual or 'Not provided'}

---
**Reporter:** {user_contact or 'Anonymous'}
**Source:** ORC Research Dashboard
"""
        
        url = f"https://api.github.com/repos/{repo_owner}/{repo_name}/issues"
        headers = {
            "Authorization": f"Bearer {github_token}",
            "Accept": "application/vnd.github.v3+json"
        }
        payload = {
            "title": f"[Bug] {summary[:100]}",
            "body": body,
            "labels": ["bug", "from-dashboard"]
        }
        
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        
        if response.status_code == 201:
            data = response.json()
            log_audit("github_issue_created", data.get('html_url', ''))
            return data.get('html_url'), None
        
        return None, "GitHub API error"
        
    except Exception as e:
        log_audit("github_error", str(type(e).__name__))
        return None, "Issue creation failed"
