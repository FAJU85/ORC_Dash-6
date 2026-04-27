"""
ORC Research Dashboard - Export Module
Generates CSV and BibTeX files from publication data.
"""

import io
import csv
import re
from datetime import datetime


# ============================================
# CSV EXPORT
# ============================================

def export_to_csv(publications: list, include_abstracts: bool = True) -> bytes:
    """
    Convert a list of publication dicts to CSV bytes.

    Args:
        publications: List of publication dicts.
        include_abstracts: Whether to include the abstract column.

    Returns:
        UTF-8 encoded CSV bytes with BOM for Excel compatibility.
    """
    if not publications:
        return b""

    fields = ["title", "authors", "journal_name", "publication_year",
              "citation_count", "open_access", "doi"]
    if include_abstracts:
        fields.append("abstract")

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction='ignore',
                            lineterminator="\r\n")
    writer.writeheader()

    for pub in publications:
        row = {f: pub.get(f, "") for f in fields}
        # Flatten authors list to semicolon-separated string
        authors = pub.get("authors", [])
        if isinstance(authors, list):
            row["authors"] = "; ".join(str(a) for a in authors if a)
        row["open_access"] = "Yes" if pub.get("open_access") else "No"
        writer.writerow(row)

    # BOM so Excel opens it correctly
    return ("﻿" + output.getvalue()).encode("utf-8")


# ============================================
# BIBTEX EXPORT
# ============================================

def _bibtex_key(pub: dict) -> str:
    """Generate a unique BibTeX citation key from the publication."""
    title_words = re.sub(r'[^a-zA-Z ]', '', pub.get("title", "untitled")).split()
    first_word = title_words[0].lower() if title_words else "untitled"
    year = pub.get("publication_year", "0000")
    pub_id = (pub.get("id") or "")[-4:].replace("/", "")
    return f"{first_word}{year}{pub_id}"

def _bibtex_authors(pub: dict) -> str:
    """Format authors in BibTeX 'Last, First and ...' style."""
    authors = pub.get("authors", [])
    if isinstance(authors, list) and authors:
        return " and ".join(str(a) for a in authors if a)
    return "Unknown"

def _bibtex_escape(value: str) -> str:
    """Escape special BibTeX characters."""
    if not value:
        return ""
    replacements = {
        '&': r'\&', '%': r'\%', '$': r'\$', '#': r'\#',
        '_': r'\_', '{': r'\{', '}': r'\}', '~': r'\textasciitilde{}',
        '^': r'\textasciicircum{}',
    }
    for char, esc in replacements.items():
        value = value.replace(char, esc)
    return value

def export_to_bibtex(publications: list) -> str:
    """
    Convert a list of publication dicts to a BibTeX string.

    Args:
        publications: List of publication dicts.

    Returns:
        BibTeX-formatted string.
    """
    if not publications:
        return ""

    lines = [f"% ORC Research Dashboard - BibTeX Export",
             f"% Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
             ""]

    for pub in publications:
        key = _bibtex_key(pub)
        title = _bibtex_escape(pub.get("title", "Untitled"))
        authors = _bibtex_escape(_bibtex_authors(pub))
        journal = _bibtex_escape(pub.get("journal_name", ""))
        year = pub.get("publication_year", "")
        doi = pub.get("doi", "")
        abstract = _bibtex_escape(pub.get("abstract", ""))

        entry_lines = [f"@article{{{key},"]
        entry_lines.append(f"  author    = {{{authors}}},")
        entry_lines.append(f"  title     = {{{title}}},")
        if journal:
            entry_lines.append(f"  journal   = {{{journal}}},")
        if year:
            entry_lines.append(f"  year      = {{{year}}},")
        if doi:
            entry_lines.append(f"  doi       = {{{doi}}},")
        if abstract:
            entry_lines.append(f"  abstract  = {{{abstract[:500]}}},")
        entry_lines.append("}")
        lines.extend(entry_lines)
        lines.append("")

    return "\n".join(lines)


# ============================================
# CITATION FORMATTING (APA / MLA / IEEE)
# ============================================

def format_citation(pub: dict, style: str = "APA") -> str:
    """Format a single publication as a citation string."""
    authors = pub.get("authors", [])
    if isinstance(authors, list):
        author_str = "; ".join(str(a) for a in authors[:3] if a)
        if len(authors) > 3:
            author_str += " et al."
    else:
        author_str = str(authors) if authors else "Unknown"

    title = pub.get("title", "Untitled")
    journal = pub.get("journal_name", "")
    year = pub.get("publication_year", "n.d.")
    doi = pub.get("doi", "")
    doi_str = f"https://doi.org/{doi}" if doi else ""

    if style == "APA":
        citation = f"{author_str} ({year}). {title}."
        if journal:
            citation += f" *{journal}*."
        if doi_str:
            citation += f" {doi_str}"

    elif style == "MLA":
        citation = f'{author_str}. "{title}."'
        if journal:
            citation += f" *{journal}*"
        if year:
            citation += f", {year}."
        if doi_str:
            citation += f" {doi_str}."

    elif style == "IEEE":
        citation = f'{author_str}, "{title},"'
        if journal:
            citation += f" *{journal}*,"
        if year:
            citation += f" {year}."
        if doi_str:
            citation += f" doi: {doi}."

    elif style == "Chicago":
        citation = f'{author_str}. "{title}."'
        if journal:
            citation += f" *{journal}*"
        if year:
            citation += f" ({year})."
        if doi_str:
            citation += f" {doi_str}."

    elif style == "Harvard":
        citation = f"{author_str} ({year}) '{title}',"
        if journal:
            citation += f" *{journal}*."
        if doi_str:
            citation += f" Available at: {doi_str}."

    else:
        citation = f"{author_str} ({year}). {title}. {journal}."

    return citation
