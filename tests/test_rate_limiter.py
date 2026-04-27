"""
ORC Research Dashboard - Tests for RateLimiter
Verifies module-level (cross-session) rate limiting behaviour.
"""

import pytest
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Patch streamlit before importing security
import unittest.mock as mock
with mock.patch.dict('sys.modules', {'streamlit': mock.MagicMock()}):
    from utils import security as sec


class TestRateLimiterBasic:
    """Basic allow / deny behaviour"""

    def setup_method(self):
        """Reset the shared rate-limit store before each test"""
        with sec._rate_limit_lock:
            sec._rate_limit_store.clear()

    def test_allows_first_attempt(self):
        rl = sec.RateLimiter()
        allowed, wait = rl.is_allowed("test_key", max_attempts=3, window_seconds=60)
        assert allowed is True
        assert wait == 0

    def test_blocks_after_max_attempts(self):
        rl = sec.RateLimiter()
        key = "block_key"
        for _ in range(3):
            rl.record_attempt(key)
        allowed, wait = rl.is_allowed(key, max_attempts=3, window_seconds=60)
        assert allowed is False
        assert wait > 0

    def test_allows_after_reset(self):
        rl = sec.RateLimiter()
        key = "reset_key"
        for _ in range(5):
            rl.record_attempt(key)
        rl.reset(key)
        allowed, wait = rl.is_allowed(key, max_attempts=5, window_seconds=60)
        assert allowed is True

    def test_shared_across_instances(self):
        """Two RateLimiter instances share the same module-level store"""
        rl1 = sec.RateLimiter()
        rl2 = sec.RateLimiter()
        key = "shared_key"
        for _ in range(3):
            rl1.record_attempt(key)
        # rl2 should see those attempts
        allowed, _ = rl2.is_allowed(key, max_attempts=3, window_seconds=60)
        assert allowed is False

    def test_different_keys_independent(self):
        rl = sec.RateLimiter()
        for _ in range(5):
            rl.record_attempt("key_a")
        # key_b should still be allowed
        allowed, _ = rl.is_allowed("key_b", max_attempts=5, window_seconds=60)
        assert allowed is True

    def test_old_attempts_expire(self):
        """Attempts older than the window should not count"""
        rl = sec.RateLimiter()
        key = "expire_key"
        now = time.time()
        with sec._rate_limit_lock:
            sec._rate_limit_store[key] = {
                'attempts': [now - 400],  # older than 300-s window
                'blocked_until': 0,
            }
        allowed, _ = rl.is_allowed(key, max_attempts=1, window_seconds=300)
        assert allowed is True  # expired attempt doesn't count


class TestRateLimiterEdgeCases:

    def setup_method(self):
        with sec._rate_limit_lock:
            sec._rate_limit_store.clear()

    def test_zero_max_attempts(self):
        """max_attempts=0 should always block (no allowed attempts)"""
        rl = sec.RateLimiter()
        allowed, _ = rl.is_allowed("zero_key", max_attempts=0, window_seconds=60)
        assert allowed is False

    def test_blocked_until_respected(self):
        rl = sec.RateLimiter()
        key = "blocked_key"
        with sec._rate_limit_lock:
            sec._rate_limit_store[key] = {
                'attempts': [],
                'blocked_until': time.time() + 9999,
            }
        allowed, wait = rl.is_allowed(key, max_attempts=5, window_seconds=60)
        assert allowed is False
        assert wait > 0
