"""
ORC Research Dashboard - Tests for Export module
"""

import pytest
import sys
import os
import csv
import io

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.export import export_to_csv, export_to_bibtex, format_citation


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def pubs():
    return [
        {
            "id": "W001",
            "doi": "10.1234/test.001",
            "title": "Deep Learning for Medical Imaging",
            "abstract": "We propose a novel deep learning framework for medical imaging tasks.",
            "authors": ["Alice Smith", "Bob Jones"],
            "journal_name": "Nature Medicine",
            "publication_year": 2023,
            "citation_count": 42,
            "open_access": 1,
        },
        {
            "id": "W002",
            "doi": "10.5678/test.002",
            "title": "Graph Neural Networks: A Survey",
            "abstract": "A comprehensive survey of graph neural network architectures.",
            "authors": ["Carol White", "Dan Brown", "Eve Black"],
            "journal_name": "IEEE Transactions",
            "publication_year": 2022,
            "citation_count": 150,
            "open_access": 0,
        },
    ]

@pytest.fixture
def single_pub(pubs):
    return [pubs[0]]


# ── CSV Tests ─────────────────────────────────────────────────────────────────

class TestExportCSV:

    def test_returns_bytes(self, pubs):
        result = export_to_csv(pubs)
        assert isinstance(result, bytes)

    def test_empty_returns_empty_bytes(self):
        assert export_to_csv([]) == b""

    def test_has_header_row(self, pubs):
        data = export_to_csv(pubs).decode("utf-8-sig")
        reader = csv.reader(io.StringIO(data))
        header = next(reader)
        assert "title" in header
        assert "citation_count" in header
        assert "doi" in header

    def test_correct_row_count(self, pubs):
        data = export_to_csv(pubs).decode("utf-8-sig")
        rows = list(csv.reader(io.StringIO(data)))
        assert len(rows) == 3  # header + 2 data rows

    def test_authors_semicolon_separated(self, pubs):
        data = export_to_csv(pubs).decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(data))
        rows = list(reader)
        assert "Alice Smith; Bob Jones" in rows[0]["authors"]

    def test_open_access_yes_no(self, pubs):
        data = export_to_csv(pubs).decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(data))
        rows = list(reader)
        assert rows[0]["open_access"] == "Yes"
        assert rows[1]["open_access"] == "No"

    def test_without_abstracts(self, pubs):
        data = export_to_csv(pubs, include_abstracts=False).decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(data))
        header = reader.fieldnames or []
        assert "abstract" not in header

    def test_with_abstracts(self, pubs):
        data = export_to_csv(pubs, include_abstracts=True).decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(data))
        rows = list(reader)
        assert "framework" in rows[0].get("abstract", "")


# ── BibTeX Tests ──────────────────────────────────────────────────────────────

class TestExportBibTeX:

    def test_returns_string(self, pubs):
        result = export_to_bibtex(pubs)
        assert isinstance(result, str)

    def test_empty_returns_empty(self):
        assert export_to_bibtex([]) == ""

    def test_contains_article_entry(self, pubs):
        bib = export_to_bibtex(pubs)
        assert "@article{" in bib

    def test_contains_title(self, pubs):
        bib = export_to_bibtex(pubs)
        assert "Deep Learning for Medical Imaging" in bib

    def test_contains_doi(self, pubs):
        bib = export_to_bibtex(pubs)
        assert "10.1234/test.001" in bib

    def test_contains_year(self, pubs):
        bib = export_to_bibtex(pubs)
        assert "2023" in bib

    def test_contains_author(self, pubs):
        bib = export_to_bibtex(pubs)
        assert "Alice Smith" in bib

    def test_multiple_entries(self, pubs):
        bib = export_to_bibtex(pubs)
        count = bib.count("@article{")
        assert count == 2

    def test_no_doi_skips_doi_field(self):
        pub = [{"id": "W003", "title": "No DOI Paper", "authors": ["Anon"],
                "publication_year": 2021, "journal_name": "Unknown"}]
        bib = export_to_bibtex(pub)
        assert "doi" not in bib


# ── Citation Formatting Tests ─────────────────────────────────────────────────

class TestFormatCitation:

    def test_apa_contains_year_and_title(self, single_pub):
        citation = format_citation(single_pub[0], style="APA")
        assert "2023" in citation
        assert "Deep Learning" in citation

    def test_mla_style(self, single_pub):
        citation = format_citation(single_pub[0], style="MLA")
        assert "Deep Learning" in citation

    def test_ieee_style(self, single_pub):
        citation = format_citation(single_pub[0], style="IEEE")
        assert "Deep Learning" in citation

    def test_chicago_style(self, single_pub):
        citation = format_citation(single_pub[0], style="Chicago")
        assert "2023" in citation

    def test_harvard_style(self, single_pub):
        citation = format_citation(single_pub[0], style="Harvard")
        assert "2023" in citation

    def test_unknown_style_fallback(self, single_pub):
        citation = format_citation(single_pub[0], style="XYZ")
        assert "Deep Learning" in citation

    def test_missing_fields_graceful(self):
        pub = {"title": "Minimal Paper"}
        citation = format_citation(pub, style="APA")
        assert "Minimal Paper" in citation


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
