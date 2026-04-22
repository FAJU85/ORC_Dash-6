"""
ORC Research Dashboard - Pytest Configuration
"""

import pytest
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def sample_publication():
    """Sample publication data for testing"""
    return {
        "id": "W12345",
        "doi": "10.1234/test",
        "title": "Test Publication About Machine Learning",
        "abstract": "This is a test abstract for a machine learning paper.",
        "publication_year": 2024,
        "journal_name": "Test Journal",
        "citation_count": 10,
        "open_access": 1,
        "source": "openalex",
        "authors": ["Author 1", "Author 2", "Author 3"],
        "synced_at": "2024-01-01T00:00:00"
    }


@pytest.fixture
def sample_publications():
    """Multiple sample publications for testing"""
    return [
        {
            "id": "W1",
            "title": "Paper 1",
            "publication_year": 2024,
            "journal_name": "Journal A",
            "citation_count": 15,
            "open_access": 1,
        },
        {
            "id": "W2",
            "title": "Paper 2",
            "publication_year": 2023,
            "journal_name": "Journal B",
            "citation_count": 8,
            "open_access": 0,
        },
        {
            "id": "W3",
            "title": "Paper 3",
            "publication_year": 2024,
            "journal_name": "Journal A",
            "citation_count": 5,
            "open_access": 1,
        },
    ]


@pytest.fixture
def mock_orcid():
    """Valid ORCID for testing"""
    return "0000-0002-1825-0097"


@pytest.fixture
def mock_email():
    """Valid email for testing"""
    return "test@example.com"