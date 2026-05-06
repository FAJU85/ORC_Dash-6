"""
ORC Research Dashboard - Tests for Hugging Face Data Module
Tests that do not require actual HF credentials.
"""

import pytest
import sys
import os
import json
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.security import sanitize_string, validate_orcid
from utils.hf_data import SCHEMA_VERSION


class TestSchemaVersion:

    def test_schema_version_is_integer(self):
        assert isinstance(SCHEMA_VERSION, int)

    def test_schema_version_positive(self):
        assert SCHEMA_VERSION >= 1


class TestMockDataFunctions:

    def test_sanitize_string(self):
        assert sanitize_string("  test  ") == "test"
        assert sanitize_string("test\x00data") == "testdata"
        assert sanitize_string("a" * 1000, max_length=100) == "a" * 100

    def test_validate_orcid(self):
        assert validate_orcid("0000-0000-0000-0000") is True
        assert validate_orcid("0000-0000-0000-000X") is True
        assert validate_orcid("invalid") is False


class TestPublicationSchema:

    def test_required_fields_present(self, sample_publication):
        required = ["id", "title", "publication_year", "journal_name", "citation_count"]
        for field in required:
            assert field in sample_publication, f"Missing required field: {field}"

    def test_citation_count_integer(self, sample_publication):
        assert isinstance(sample_publication["citation_count"], int)

    def test_open_access_binary(self, sample_publication):
        assert sample_publication["open_access"] in [0, 1]

    def test_authors_is_list(self, sample_publication):
        assert isinstance(sample_publication["authors"], list)

    def test_doi_format(self, sample_publication):
        doi = sample_publication.get("doi", "")
        if doi:
            assert "https://doi.org" not in doi  # stored without prefix

    def test_publication_serialisable(self, sample_publication):
        """Publication must round-trip through JSON without error"""
        serialised = json.dumps(sample_publication, default=str)
        restored = json.loads(serialised)
        assert restored["id"] == sample_publication["id"]


class TestDuplicateDetection:
    """Unit-test the duplicate-detection logic used in sync_from_openalex"""

    def _simulate_dedup(self, existing, candidates):
        """Mirrors the dedup logic in hf_data.sync_from_openalex"""
        existing_ids  = {p.get('id')  for p in existing}
        existing_dois = {p.get('doi') for p in existing if p.get('doi')}
        new = []
        for c in candidates:
            if c.get('id')  in existing_ids:
                continue
            if c.get('doi') and c.get('doi') in existing_dois:
                continue
            new.append(c)
        return new

    def test_skips_duplicate_id(self):
        existing    = [{"id": "W1", "doi": "10.0/a"}]
        candidates  = [{"id": "W1", "doi": "10.0/b"}]
        result = self._simulate_dedup(existing, candidates)
        assert result == []

    def test_skips_duplicate_doi(self):
        existing   = [{"id": "W1", "doi": "10.0/a"}]
        candidates = [{"id": "W2", "doi": "10.0/a"}]
        result = self._simulate_dedup(existing, candidates)
        assert result == []

    def test_accepts_unique_entry(self):
        existing   = [{"id": "W1", "doi": "10.0/a"}]
        candidates = [{"id": "W2", "doi": "10.0/b"}]
        result = self._simulate_dedup(existing, candidates)
        assert len(result) == 1

    def test_no_doi_accepted(self):
        existing   = [{"id": "W1", "doi": "10.0/a"}]
        candidates = [{"id": "W2", "doi": None}]
        result = self._simulate_dedup(existing, candidates)
        assert len(result) == 1


class TestMetricsCalculation:

    def test_h_index(self):
        citations = [10, 8, 5, 4, 3, 2, 1]
        h = 0
        for i, c in enumerate(citations, 1):
            if c >= i:
                h = i
            else:
                break
        assert h == 4

    def test_h_index_empty(self):
        h = 0
        for i, c in enumerate([], 1):
            if c >= i:
                h = i
        assert h == 0

    def test_total_citations(self, sample_publications):
        total = sum(p["citation_count"] for p in sample_publications)
        assert total == 28   # 15 + 8 + 5

    def test_average_citations(self, sample_publications):
        total = sum(p["citation_count"] for p in sample_publications)
        avg = total / len(sample_publications)
        assert abs(avg - (28 / 3)) < 0.01

    def test_open_access_count(self, sample_publications):
        oa = sum(1 for p in sample_publications if p.get("open_access") == 1)
        assert oa == 2


class TestWrappedJsonSchema:
    """Test that the new schema-versioned JSON wrapper is handled correctly"""

    def _parse(self, raw):
        if isinstance(raw, list):
            return raw
        if isinstance(raw, dict):
            return raw.get("data", [])
        return []

    def test_bare_list_parsed(self):
        raw = [{"id": "W1"}, {"id": "W2"}]
        assert len(self._parse(raw)) == 2

    def test_wrapped_object_parsed(self):
        raw = {"schema_version": 1, "data": [{"id": "W1"}], "updated_at": "2025-01-01"}
        result = self._parse(raw)
        assert len(result) == 1
        assert result[0]["id"] == "W1"

    def test_empty_data_key(self):
        raw = {"schema_version": 1, "data": []}
        assert self._parse(raw) == []


class TestQueryHelpers:
    """Tests for the explicit query helpers that replaced the SQL shim."""

    def _patch_load(self, pubs):
        """Return a context manager that patches load_publications to return pubs."""
        return mock.patch("utils.hf_data.load_publications", return_value=pubs)

    def test_get_publication_metrics_empty(self):
        from utils.hf_data import get_publication_metrics
        with self._patch_load([]):
            m = get_publication_metrics()
        assert m["total_pubs"] == 0
        assert m["total_citations"] == 0

    def test_get_publication_metrics_counts(self, sample_publications):
        from utils.hf_data import get_publication_metrics
        with self._patch_load(sample_publications):
            m = get_publication_metrics()
        assert m["total_pubs"] == 3
        assert m["total_citations"] == 28
        assert m["oa_count"] == 2
        assert abs(m["avg_citations"] - 28 / 3) < 0.01

    def test_get_publications_sorted_by_year(self, sample_publications):
        from utils.hf_data import get_publications_sorted
        with self._patch_load(sample_publications):
            result = get_publications_sorted("year")
        years = [r["publication_year"] for r in result]
        assert years == sorted(years, reverse=True)

    def test_get_publications_sorted_by_citations(self, sample_publications):
        from utils.hf_data import get_publications_sorted
        with self._patch_load(sample_publications):
            result = get_publications_sorted("citations")
        citations = [r["citation_count"] for r in result]
        assert citations == sorted(citations, reverse=True)

    def test_get_publications_sorted_limit(self, sample_publications):
        from utils.hf_data import get_publications_sorted
        with self._patch_load(sample_publications):
            result = get_publications_sorted("year", limit=2)
        assert len(result) == 2

    def test_get_publications_sorted_empty(self):
        from utils.hf_data import get_publications_sorted
        with self._patch_load([]):
            assert get_publications_sorted("year") == []

    def test_get_citation_sorted_counts(self, sample_publications):
        from utils.hf_data import get_citation_sorted_counts
        with self._patch_load(sample_publications):
            counts = get_citation_sorted_counts()
        assert counts == sorted(counts, reverse=True)
        assert counts == [15, 8, 5]

    def test_get_citation_sorted_counts_empty(self):
        from utils.hf_data import get_citation_sorted_counts
        with self._patch_load([]):
            assert get_citation_sorted_counts() == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
