"""
ORC Research Dashboard - Security Utilities
Provides secure database access, input validation, and rate limiting.
"""

import streamlit as st
import os
import hashlib
import secrets
import re
import time
import threading
from datetime import datetime, timedelta
from functools import wraps

# ============================================
# MODULE-LEVEL STORES (shared across all sessions)
# ============================================

_rate_limit_lock = threading.Lock()
_rate_limit_store: dict = {}   # key -> {attempts: [...], blocked_until: float}

_audit_lock = threading.Lock()
_audit_log: list = []           # in-memory audit log (all sessions)

_error_lock = threading.Lock()
_error_log: list = []           # in-memory error log (all sessions)

# ============================================
# SECURE SECRET ACCESS
# ============================================

def get_secret(key: str, default: str = "") -> str:
    """Safely get a secret value - works with both local st.secrets and HF Spaces env vars"""
    try:
        val = os.environ.get(key, None)
        if val:
            return val
        try:
            val = st.secrets.get(key, None)
            return val if val else default
        except Exception:
            return default
    except Exception:
        return default

def get_nested_secret(section: str, key: str, default: str = "") -> str:
    """Safely get nested secret like [researcher].name"""
    try:
        env_key = f"{section}_{key}".upper()
        val = os.environ.get(env_key, None)
        if val:
            return val
        section_data = st.secrets.get(section, {})
        if hasattr(section_data, 'get'):
            return section_data.get(key, default) or default
        return default
    except Exception:
        return default

# ============================================
# INPUT VALIDATION
# ============================================

from typing import Any # Added for execute_query and sanitize_string

def sanitize_string(value: Any, max_length: int = 500) -> str:
    """Sanitize string input to prevent injection"""
    if not value:
        return ""
    value = str(value).strip()
    value = value.replace('\x00', '')
    value = value[:max_length]
    return value

def validate_orcid(orcid: str | None) -> bool:
    """Validate ORCID format (0000-0000-0000-0000)"""
    if not orcid:
        return False
    pattern = r'^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$'
    return bool(re.match(pattern, orcid))

def validate_email(email: str | None) -> bool:
    """Validate email format"""
    if not email:
        return False
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))

def validate_otp(otp: Any) -> bool:
    """Validate OTP format (6 digits)"""
    if not otp:
        return False
    return bool(re.match(r'^\d{6}$', str(otp)))

# ============================================
# PASSWORD SECURITY
# ============================================

def hash_password(password: str) -> str:
    """Hash password using bcrypt with random salt"""
    try:
        import bcrypt
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt(12)).decode()
    except ImportError:
        import warnings
        warnings.warn('bcrypt not installed — falling back to SHA-256. Install bcrypt for production use.', RuntimeWarning, stacklevel=2)
        return hashlib.sha256(password.encode()).hexdigest()

def verify_password(password: str, stored_hash: str) -> bool:
    """
    Verify password against stored hash.
    Supports both bcrypt (new) and SHA-256 (legacy) hashes.
    """
    if not password or not stored_hash:
        return False
    try:
        import bcrypt
        if stored_hash.startswith(('$2b$', '$2a$', '$2y$')):
            return bcrypt.checkpw(password.encode(), stored_hash.encode())
    except (ImportError, ValueError):
        pass
    # Legacy SHA-256 fallback
    return hashlib.sha256(password.encode()).hexdigest() == stored_hash

def generate_otp() -> str:
    """Generate secure 6-digit OTP"""
    return ''.join([str(secrets.randbelow(10)) for _ in range(6)])

def generate_session_token() -> str:
    """Generate secure session token"""
    return secrets.token_urlsafe(32)

# ============================================
# RATE LIMITING (module-level, shared across sessions)
# ============================================

class RateLimiter:
    """
    Rate limiter backed by a module-level dict so limits are enforced
    across all user sessions within the same server process.
    """

    def is_allowed(self, key: str, max_attempts: int = 5, window_seconds: int = 300) -> tuple[bool, int]:
        """Check if action is allowed within rate limit"""
        now = time.time()
        with _rate_limit_lock:
            data = _rate_limit_store.get(key, {'attempts': [], 'blocked_until': 0})

            if now < data.get('blocked_until', 0):
                return False, int(data['blocked_until'] - now)

            data['attempts'] = [t for t in data.get('attempts', []) if now - t < window_seconds]

            if len(data['attempts']) >= max_attempts:
                data['blocked_until'] = now + window_seconds
                _rate_limit_store[key] = data
                return False, window_seconds

            _rate_limit_store[key] = data
            return True, 0

    def record_attempt(self, key: str) -> None:
        """Record an attempt"""
        now = time.time()
        with _rate_limit_lock:
            if key not in _rate_limit_store:
                _rate_limit_store[key] = {'attempts': [], 'blocked_until': 0}
            _rate_limit_store[key]['attempts'].append(now)

    def reset(self, key: str) -> None:
        """Reset rate limit for a key"""
        with _rate_limit_lock:
            _rate_limit_store.pop(key, None)

# ============================================
# AUDIT LOGGING (module-level, shared across sessions)
# ============================================

def log_audit(action: str, details: str = "", user: str = "anonymous") -> None:
    """Log security-relevant actions to the module-level audit log"""
    entry = {
        'timestamp': datetime.now().isoformat(),
        'action': action,
        'details': sanitize_string(details, 200),
        'user': sanitize_string(user, 100)
    }
    with _audit_lock:
        _audit_log.append(entry)
        if len(_audit_log) > 500:
            _audit_log[:] = _audit_log[-500:]

    # Best-effort persistence to HF
    try:
        from utils.hf_data import append_audit_entry
        append_audit_entry(entry)
    except Exception:
        pass

def get_audit_log() -> list[dict]:
    """Return the current in-memory audit log (newest last)"""
    with _audit_lock:
        return list(_audit_log)

def load_audit_log_from_hf() -> None:
    """Load persisted audit log from HF Dataset into the module-level list"""
    try:
        from utils.hf_data import load_audit_log as hf_load
        entries = hf_load()
        if entries:
            with _audit_lock:
                existing_ts = {e['timestamp'] for e in _audit_log}
                for e in entries:
                    if e.get('timestamp') not in existing_ts:
                        _audit_log.append(e)
                _audit_log.sort(key=lambda x: x.get('timestamp', ''))
                _audit_log[:] = _audit_log[-500:]
    except Exception:
        pass

# ============================================
# ERROR LOGGING (module-level, shared across sessions)
# ============================================

def log_error(error_type: str, message: str, page: str = "") -> None:
    """Persist an application error to the in-memory log and HF storage."""
    entry = {
        'timestamp': datetime.now().isoformat(),
        'error_type': sanitize_string(error_type, 100),
        'message': sanitize_string(message, 500),
        'page': sanitize_string(page, 100),
    }
    with _error_lock:
        _error_log.append(entry)
        if len(_error_log) > 500:
            _error_log[:] = _error_log[-500:]

    try:
        from utils.hf_data import append_error_entry
        append_error_entry(entry)
    except Exception:
        pass


def get_error_log() -> list[dict]:
    """Return the current in-memory error log."""
    with _error_lock:
        return list(_error_log)


def clear_error_log() -> None:
    """Clear the in-memory error log."""
    global _error_log
    with _error_lock:
        _error_log.clear()


def load_error_log_from_hf() -> None:
    """Load persisted error log from HF Dataset into the module-level list."""
    try:
        from utils.hf_data import load_error_log as hf_load
        entries = hf_load()
        if entries:
            with _error_lock:
                existing_ts = {e['timestamp'] for e in _error_log}
                for e in entries:
                    if e.get('timestamp') not in existing_ts:
                        _error_log.append(e)
                _error_log.sort(key=lambda x: x.get('timestamp', ''))
                _error_log[:] = _error_log[-500:]
    except Exception:
        pass


# ============================================
# DATABASE ACCESS (Hugging Face Datasets)
# ============================================

def is_db_configured() -> bool:
    """Check if Hugging Face is properly configured"""
    try:
        from utils.hf_data import is_hf_configured
        return is_hf_configured()
    except Exception:
        return False

def execute_query(sql: str, params: Any | None = None) -> tuple[list[dict] | None, str | None]:
    """Execute a query using Hugging Face Datasets"""
    try:
        from utils.hf_data import execute_query as hf_execute_query
        return hf_execute_query(sql, params)
    except Exception as e:
        log_error("db_query_error", str(e), page="execute_query")
        return None, str(e)

# ============================================
# SESSION SECURITY
# ============================================

def init_session() -> None:
    """Initialize secure session state"""
    if 'session_initialized' not in st.session_state:
        st.session_state.session_initialized = True
        st.session_state.session_token = generate_session_token()
        st.session_state.session_start = datetime.now().isoformat()

def is_admin_authenticated() -> bool:
    """Check if admin is authenticated in this session"""
    return st.session_state.get('admin_authenticated', False)

def admin_logout() -> None:
    """Securely logout admin"""
    log_audit("admin_logout")
    st.session_state.admin_authenticated = False
    st.session_state.otp_sent = False
    st.session_state.otp_code = None
    st.session_state.otp_expiry = None
    st.session_state.admin_email = None

# ============================================
# USER ROLES AND PERMISSIONS
# ============================================

def is_admin(orcid: str = None) -> bool:
    """Check if current user is admin"""
    if st.session_state.get('admin_authenticated', False):
        return True
    admin_orcids = get_secret("ADMIN_ORCIDS", "").split(",")
    admin_orcids = [o.strip() for o in admin_orcids if o.strip()]
    current_orcid = orcid or st.session_state.get('orcid', '')
    return current_orcid in admin_orcids

def can_sync_publications() -> bool:
    """Check if current user can sync publications from OpenAlex"""
    return is_admin()

def can_access_admin_panel() -> bool:
    """Check if current user can access admin panel"""
    return is_admin()

def get_user_role(orcid: str = None) -> str:
    """Get user's role ('admin' or 'user')"""
    return 'admin' if is_admin(orcid) else 'user'
