"""
ORC Research Dashboard - Security Utilities
Provides secure database access, input validation, and rate limiting
"""

import streamlit as st
import os
import hashlib
import secrets
import re
import time
from datetime import datetime, timedelta
from functools import wraps

# ============================================
# SECURE SECRET ACCESS
# ============================================

def get_secret(key, default=""):
    """Safely get a secret value - works with both local st.secrets and HF Spaces env vars"""
    try:
        # First try environment variables (for Hugging Face Spaces)
        val = os.environ.get(key, None)
        if val:
            return val
        
        # Fall back to st.secrets (for local development)
        try:
            val = st.secrets.get(key, None)
            return val if val else default
        except Exception:
            return default
    except Exception:
        return default

def get_nested_secret(section, key, default=""):
    """Safely get nested secret like [researcher].name - works with both local and HF Spaces"""
    try:
        # Try environment variables first (for Hugging Face Spaces)
        # HF secrets are prefixed with the section name
        env_key = f"{section}_{key}".upper()
        val = os.environ.get(env_key, None)
        if val:
            return val
        
        # Fall back to st.secrets (for local development)
        section_data = st.secrets.get(section, {})
        if hasattr(section_data, 'get'):
            return section_data.get(key, default) or default
        return default
    except Exception:
        return default

# ============================================
# INPUT VALIDATION
# ============================================

def sanitize_string(value, max_length=500):
    """Sanitize string input to prevent injection"""
    if not value:
        return ""
    # Convert to string and strip
    value = str(value).strip()
    # Remove null bytes
    value = value.replace('\x00', '')
    # Limit length
    value = value[:max_length]
    return value

def validate_orcid(orcid):
    """Validate ORCID format (0000-0000-0000-0000)"""
    if not orcid:
        return False
    pattern = r'^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$'
    return bool(re.match(pattern, orcid))

def validate_email(email):
    """Validate email format"""
    if not email:
        return False
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))

def validate_otp(otp):
    """Validate OTP format (6 digits)"""
    if not otp:
        return False
    return bool(re.match(r'^\d{6}$', str(otp)))

# ============================================
# PASSWORD SECURITY
# ============================================

def hash_password(password):
    """Hash password with salt"""
    return hashlib.sha256(password.encode()).hexdigest()

def generate_otp():
    """Generate secure 6-digit OTP"""
    return ''.join([str(secrets.randbelow(10)) for _ in range(6)])

def generate_session_token():
    """Generate secure session token"""
    return secrets.token_urlsafe(32)

# ============================================
# RATE LIMITING
# ============================================

class RateLimiter:
    """Simple in-memory rate limiter"""
    
    def __init__(self):
        if 'rate_limit_data' not in st.session_state:
            st.session_state.rate_limit_data = {}
    
    def is_allowed(self, key, max_attempts=5, window_seconds=300):
        """Check if action is allowed within rate limit"""
        now = time.time()
        data = st.session_state.rate_limit_data.get(key, {'attempts': [], 'blocked_until': 0})
        
        # Check if currently blocked
        if now < data.get('blocked_until', 0):
            return False, int(data['blocked_until'] - now)
        
        # Clean old attempts
        data['attempts'] = [t for t in data.get('attempts', []) if now - t < window_seconds]
        
        # Check if over limit
        if len(data['attempts']) >= max_attempts:
            data['blocked_until'] = now + window_seconds
            st.session_state.rate_limit_data[key] = data
            return False, window_seconds
        
        return True, 0
    
    def record_attempt(self, key):
        """Record an attempt"""
        now = time.time()
        if key not in st.session_state.rate_limit_data:
            st.session_state.rate_limit_data[key] = {'attempts': [], 'blocked_until': 0}
        st.session_state.rate_limit_data[key]['attempts'].append(now)
    
    def reset(self, key):
        """Reset rate limit for a key"""
        if key in st.session_state.rate_limit_data:
            del st.session_state.rate_limit_data[key]

# ============================================
# AUDIT LOGGING
# ============================================

def log_audit(action, details="", user="anonymous"):
    """Log security-relevant actions"""
    if 'audit_log' not in st.session_state:
        st.session_state.audit_log = []
    
    entry = {
        'timestamp': datetime.now().isoformat(),
        'action': action,
        'details': sanitize_string(details, 200),
        'user': sanitize_string(user, 100)
    }
    
    st.session_state.audit_log.append(entry)
    
    # Keep only last 100 entries
    if len(st.session_state.audit_log) > 100:
        st.session_state.audit_log = st.session_state.audit_log[-100:]

def get_audit_log():
    """Get audit log (admin only)"""
    return st.session_state.get('audit_log', [])

# ============================================
# SECURE DATABASE ACCESS
# ============================================

def get_db_config():
    """Get database configuration securely"""
    return {
        'account_id': get_secret("CLOUDFLARE_ACCOUNT_ID"),
        'api_token': get_secret("CLOUDFLARE_API_TOKEN"),
        'database_id': get_secret("CLOUDFLARE_D1_DATABASE_ID")
    }

def is_db_configured():
    """Check if database is properly configured"""
    config = get_db_config()
    return all([config['account_id'], config['api_token'], config['database_id']])

def execute_query(sql, params=None):
    """
    Execute a parameterized query against Cloudflare D1
    ALWAYS use parameterized queries to prevent SQL injection
    """
    import requests
    
    config = get_db_config()
    
    if not all([config['account_id'], config['api_token'], config['database_id']]):
        return None, "Database not configured"
    
    try:
        url = f"https://api.cloudflare.com/client/v4/accounts/{config['account_id']}/d1/database/{config['database_id']}/query"
        headers = {
            "Authorization": f"Bearer {config['api_token']}",
            "Content-Type": "application/json"
        }
        
        payload = {"sql": sql}
        if params:
            # Ensure params are properly sanitized
            safe_params = []
            for p in params:
                if p is None:
                    safe_params.append(None)
                elif isinstance(p, (int, float)):
                    safe_params.append(p)
                else:
                    safe_params.append(sanitize_string(str(p), 2000))
            payload["params"] = safe_params
        
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            if data.get("success") and data.get("result"):
                return data["result"][0].get("results", []), None
            return [], None
        
        # Don't expose detailed error info
        log_audit("db_error", f"Status: {response.status_code}")
        return None, "Database query failed"
        
    except requests.exceptions.Timeout:
        log_audit("db_timeout")
        return None, "Database timeout"
    except Exception as e:
        log_audit("db_exception", str(type(e).__name__))
        return None, "Database error"

# ============================================
# SESSION SECURITY
# ============================================

def init_session():
    """Initialize secure session state"""
    if 'session_initialized' not in st.session_state:
        st.session_state.session_initialized = True
        st.session_state.session_token = generate_session_token()
        st.session_state.session_start = datetime.now().isoformat()

def is_admin_authenticated():
    """Check if admin is authenticated"""
    return st.session_state.get('admin_authenticated', False)

def admin_logout():
    """Securely logout admin"""
    log_audit("admin_logout")
    st.session_state.admin_authenticated = False
    st.session_state.otp_sent = False
    st.session_state.otp_code = None
    st.session_state.otp_expiry = None
    st.session_state.admin_email = None
