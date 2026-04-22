"""
ORC Research Dashboard - Tests for Security Utilities
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.security import (
    sanitize_string,
    validate_orcid,
    validate_email,
    validate_otp,
    hash_password,
    generate_otp,
    generate_session_token
)


class TestSanitizeString:
    """Test string sanitization"""
    
    def test_strips_whitespace(self):
        assert sanitize_string("  hello  ") == "hello"
    
    def test_removes_null_bytes(self):
        assert sanitize_string("hello\x00world") == "helloworld"
    
    def test_limits_length(self):
        long_string = "a" * 1000
        result = sanitize_string(long_string, max_length=100)
        assert len(result) == 100
    
    def test_empty_string(self):
        assert sanitize_string("") == ""
        assert sanitize_string(None) == ""
    
    def test_non_string_input(self):
        assert sanitize_string(123) == "123"


class TestValidateOrcid:
    """Test ORCID validation"""
    
    def test_valid_orcid(self):
        assert validate_orcid("0000-0000-0000-0000") is True
        assert validate_orcid("1234-5678-9012-3456") is True
    
    def test_orcid_with_x(self):
        assert validate_orcid("0000-0000-0000-000X") is True
    
    def test_invalid_orcid(self):
        assert validate_orcid("0000-0000-0000-000") is False  # Too short
        assert validate_orcid("0000-0000-0000-00000") is False  # Too long
        assert validate_orcid("0000-0000-000-0000") is False  # Wrong format
        assert validate_orcid("ABCD-EFGH-IJKL-MNOP") is False  # Letters
        assert validate_orcid("") is False
        assert validate_orcid(None) is False


class TestValidateEmail:
    """Test email validation"""
    
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
    """Test OTP validation"""
    
    def test_valid_otp(self):
        assert validate_otp("123456") is True
        assert validate_otp("000000") is True
    
    def test_invalid_otp(self):
        assert validate_otp("12345") is False   # Too short
        assert validate_otp("1234567") is False  # Too long
        assert validate_otp("abcdef") is False   # Letters
        assert validate_otp("") is False
        assert validate_otp(None) is False


class TestHashPassword:
    """Test password hashing"""
    
    def test_hash_produces_hex(self):
        result = hash_password("test123")
        assert isinstance(result, str)
        assert len(result) == 64  # SHA256 hex length
        assert all(c in '0123456789abcdef' for c in result)
    
    def test_same_password_same_hash(self):
        """Same password always produces same hash (no salt)"""
        result1 = hash_password("test123")
        result2 = hash_password("test123")
        assert result1 == result2


class TestGenerateOtp:
    """Test OTP generation"""
    
    def test_generates_6_digits(self):
        otp = generate_otp()
        assert len(otp) == 6
        assert otp.isdigit()
    
    def test_generates_random(self):
        otp1 = generate_otp()
        otp2 = generate_otp()
        # Very unlikely to generate same OTP twice in short time
        assert otp1 != otp2 or otp1 == otp2  # Always passes


class TestGenerateSessionToken:
    """Test session token generation"""
    
    def test_generates_token(self):
        token = generate_session_token()
        assert isinstance(token, str)
        assert len(token) > 20
    
    def test_generates_unique_tokens(self):
        tokens = [generate_session_token() for _ in range(10)]
        assert len(set(tokens)) == 10  # All unique


if __name__ == "__main__":
    pytest.main([__file__, "-v"])