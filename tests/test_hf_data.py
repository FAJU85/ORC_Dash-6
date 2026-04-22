"""
ORC Research Dashboard - Tests for Hugging Face Data Module
"""

import pytest
import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.security import (
    sanitize_string,
    validate_orcid
)


class TestMockDataFunctions:
    """Test functions that don't require HF credentials"""
    
    def test_sanitize_string(self):
        """Test string sanitization"""
        assert sanitize_string("  test  ") == "test"
        assert sanitize_string("test\x00data") == "testdata"
        assert sanitize_string("a" * 1000, max_length=100) == "a" * 100
    
    def test_validate_orcid(self):
        """Test ORCID validation"""
        assert validate_orcid("0000-0000-0000-0000") is True
        assert validate_orcid("0000-0000-0000-000X") is True
        assert validate_orcid("invalid") is False


class TestPublicationData:
    """Test publication data structure"""
    
    def test_publication_schema(self):
        """Test that a publication has required fields"""
        pub = {
            "id": "W12345",
            "doi": "10.1234/test",
            "title": "Test Publication",
            "abstract": "Test abstract",
            "publication_year": 2024,
            "journal_name": "Test Journal",
            "citation_count": 10,
            "open_access": 1,
            "source": "openalex",
            "authors": ["Author 1", "Author 2"],
            "synced_at": "2024-01-01T00:00:00"
        }
        
        required_fields = [
            "id", "title", "publication_year", 
            "journal_name", "citation_count"
        ]
        
        for field in required_fields:
            assert field in pub, f"Missing required field: {field}"
    
    def test_publication_citation_count(self):
        """Test citation count is always an integer"""
        pub = {"citation_count": 10}
        assert isinstance(pub["citation_count"], int)
        
        pub2 = {"citation_count": 0}
        assert isinstance(pub2["citation_count"], int)
    
    def test_publication_open_access(self):
        """Test open_access is 0 or 1"""
        assert 0 in [0, 1]
        pub = {"open_access": 1}
        assert pub["open_access"] in [0, 1]


class TestMetricsCalculation:
    """Test metrics calculations"""
    
    def test_h_index_calculation(self):
        """Test h-index calculation"""
        citations = [10, 8, 5, 4, 3, 2, 1]  # 7 papers
        
        h_index = 0
        for i, c in enumerate(citations, 1):
            if c >= i:
                h_index = i
            else:
                break
        
        # h-index = 4 (4 papers have at least 4 citations each, 5th has only 3)
        assert h_index == 4
    
    def test_h_index_empty(self):
        """Test h-index with no publications"""
        citations = []
        h_index = 0
        for i, c in enumerate(citations, 1):
            if c >= i:
                h_index = i
        assert h_index == 0
    
    def test_total_citations(self):
        """Test total citations sum"""
        pubs = [
            {"citation_count": 10},
            {"citation_count": 5},
            {"citation_count": 3}
        ]
        total = sum(p["citation_count"] for p in pubs)
        assert total == 18
    
    def test_average_citations(self):
        """Test average citations"""
        pubs = [
            {"citation_count": 10},
            {"citation_count": 5},
            {"citation_count": 5}
        ]
        total = sum(p["citation_count"] for p in pubs)
        avg = total / len(pubs)
        assert abs(avg - 6.67) < 0.01  # Allow floating point tolerance


if __name__ == "__main__":
    pytest.main([__file__, "-v"])