"""
ORC Research Dashboard - Tests for Security Utilities
"""

import pytest
import sys
import os
import unittest.mock as mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Patch streamlit before importing security
with mock.patch.dict('sys.modules', {'streamlit': mock.MagicMock()}):
    from utils.security import (
        sanitize_string,
        validate_orcid,
        validate_email,
        validate_otp,
        hash_password,
        verify_password,
        generate_otp,
        generate_session_token,
    )


class TestSanitizeString:

    def test_strips_whitespace(self):
        assert sanitize_string("  hello  ") == "hello"

    def test_removes_null_bytes(self):
        assert sanitize_string("hello\x00world") == "helloworld"

    def test_limits_length(self):
        result = sanitize_string("a" * 1000, max_length=100)
        assert len(result) == 100

    def test_empty_string(self):
        assert sanitize_string("") == ""
        assert sanitize_string(None) == ""

    def test_non_string_input(self):
        assert sanitize_string(123) == "123"

    def test_max_length_default(self):
        long_str = "x" * 600
        result = sanitize_string(long_str)
        assert len(result) == 500


class TestValidateOrcid:

    def test_valid_orcid(self):
        assert validate_orcid("0000-0000-0000-0000") is True
        assert validate_orcid("1234-5678-9012-3456") is True

    def test_orcid_with_x(self):
        assert validate_orcid("0000-0000-0000-000X") is True

    def test_invalid_orcid_short(self):
        assert validate_orcid("0000-0000-0000-000") is False

    def test_invalid_orcid_long(self):
        assert validate_orcid("0000-0000-0000-00000") is False

    def test_invalid_orcid_format(self):
        assert validate_orcid("0000-0000-000-0000") is False

    def test_invalid_orcid_letters(self):
        assert validate_orcid("ABCD-EFGH-IJKL-MNOP") is False

    def test_empty_and_none(self):
        assert validate_orcid("") is False
        assert validate_orcid(None) is False


class TestValidateEmail:

    def test_valid_email(self):
        assert validate_email("test@example.com") is True
        assert validate_email("user.name@domain.co.uk") is True
        assert validate_email("user+tag@gmail.com") is True

    def test_invalid_email(self):
        assert validate_email("notanemail") is False
        assert validate_email("missing@domain") is False
        assert validate_email("@nodomain.com") is False
        assert validate_email("") is False
        assert validate_email(None) is False


class TestValidateOtp:

    def test_valid_otp(self):
        assert validate_otp("123456") is True
        assert validate_otp("000000") is True

    def test_too_short(self):
        assert validate_otp("12345") is False

    def test_too_long(self):
        assert validate_otp("1234567") is False

    def test_non_digits(self):
        assert validate_otp("abcdef") is False

    def test_empty_and_none(self):
        assert validate_otp("") is False
        assert validate_otp(None) is False


class TestHashPassword:

    def test_produces_string(self):
        result = hash_password("test123")
        assert isinstance(result, str)
        assert len(result) > 20

    def test_different_passwords_different_hashes(self):
        h1 = hash_password("password1")
        h2 = hash_password("password2")
        assert h1 != h2


class TestVerifyPassword:

    def test_verify_correct_password(self):
        """verify_password accepts the correct password"""
        hashed = hash_password("secret")
        assert verify_password("secret", hashed) is True

    def test_reject_wrong_password(self):
        hashed = hash_password("secret")
        assert verify_password("wrong", hashed) is False

    def test_legacy_sha256_hash(self):
        """verify_password still works with old SHA-256 hashes"""
        import hashlib
        sha256_hash = hashlib.sha256(b"admin123").hexdigest()
        assert verify_password("admin123", sha256_hash) is True

    def test_legacy_sha256_wrong_password(self):
        import hashlib
        sha256_hash = hashlib.sha256(b"admin123").hexdigest()
        assert verify_password("wrong", sha256_hash) is False

    def test_demo_admin_credentials(self):
        """The template SHA-256 hash for admin123 must verify correctly"""
        demo_hash = "240be518fabd2724ddb6f04eeb1da5967448d7e831c08c8fa822809f74c720a9"
        assert verify_password("admin123", demo_hash) is True

    def test_empty_password_rejected(self):
        hashed = hash_password("something")
        assert verify_password("", hashed) is False

    def test_empty_hash_rejected(self):
        assert verify_password("password", "") is False


class TestGenerateOtp:

    def test_generates_6_digits(self):
        otp = generate_otp()
        assert len(otp) == 6
        assert otp.isdigit()

    def test_generates_unique_otps(self):
        otps = {generate_otp() for _ in range(50)}
        # With 10^6 possible values, 50 samples should be unique
        assert len(otps) > 1


class TestGenerateSessionToken:

    def test_generates_long_token(self):
        token = generate_session_token()
        assert isinstance(token, str)
        assert len(token) > 20

    def test_generates_unique_tokens(self):
        tokens = [generate_session_token() for _ in range(10)]
        assert len(set(tokens)) == 10


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
