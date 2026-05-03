"""
ORC Research Dashboard - Hugging Face Data Storage
Stores publications and researchers using Hugging Face Datasets.
Supports multiple researchers, caching, schema versioning, and concurrent-write safety.
"""

import os
import io
import json
import time
import threading
import pandas as pd
from datetime import datetime

try:
    from huggingface_hub import HfApi, hf_hub_download
    HF_AVAILABLE = True
except ImportError:
    HF_AVAILABLE = False

from utils.cache import get_cached_works, set_cached_works

# ============================================
# SCHEMA VERSION
# ============================================

SCHEMA_VERSION = 1

# Write lock — prevents concurrent HF uploads corrupting data
_write_lock = threading.Lock()

# ============================================
# HF DATASET CONFIGURATION
# ============================================

def get_repo_id():
    """Get the Hugging Face repo ID for data storage"""
    return os.environ.get("HF_REPO_ID") or None

def get_hf_token():
    """Get Hugging Face token from environment"""
    return os.environ.get("HF_TOKEN") or None

def is_hf_configured():
    """Check if Hugging Face is properly configured"""
    return HF_AVAILABLE and bool(get_hf_token()) and bool(get_repo_id())

# ============================================
# LOW-LEVEL HF HELPERS
# ============================================

def _hf_download_json(filename):
    """Download and parse a JSON file from HF Dataset. Returns (data, error)."""
    try:
        local_path = hf_hub_download(
            repo_id=get_repo_id(),
            filename=filename,
            repo_type="dataset",
            force_download=True,   # always get fresh copy
        )
        with open(local_path, 'r') as f:
            return json.load(f), None
    except Exception as e:
        return None, str(e)

def _hf_upload_json(filename, data, commit_message):
    """Upload a Python object as a JSON file to HF Dataset. Returns (success, error)."""
    repo_id = get_repo_id()
    if not repo_id:
        return False, "HF_REPO_ID not configured"
    try:
        api = HfApi(token=get_hf_token())
        payload = json.dumps(data, indent=2, default=str).encode("utf-8")
        api.upload_file(
            path_or_fileobj=io.BytesIO(payload),
            path_in_repo=filename,
            repo_id=repo_id,
            repo_type="dataset",
            commit_message=commit_message,
        )
        return True, None
    except Exception as e:
        return False, str(e)

def _retry(fn, attempts=3, base_delay=2):
    """Call fn() with exponential backoff on failure. Returns last result."""
    last_err = None
    for attempt in range(attempts):
        result = fn()
        if result[0]:           # first element is truthy = success
            return result
        last_err = result
        if attempt < attempts - 1:
            time.sleep(base_delay * (2 ** attempt))
    return last_err

# ============================================
# RESEARCHERS MANAGEMENT
# ============================================

def load_researchers():
    """Load researchers list from HF Dataset"""
    if not is_hf_configured():
        return []
    data, err = _hf_download_json("researchers.json")
    if err or data is None:
        return []
    # Handle both schema versions: bare list or wrapped object
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return data.get("data", [])
    return []

def save_researchers(researchers):
    """Save researchers list to HF Dataset (thread-safe)"""
    wrapped = {
        "schema_version": SCHEMA_VERSION,
        "data": researchers,
        "updated_at": datetime.now().isoformat(),
    }
    with _write_lock:
        return _retry(
            lambda: _hf_upload_json("researchers.json", wrapped, "Update researchers list"),
            attempts=3, base_delay=2,
        )

def add_researcher(orcid, name="", institution="", email=""):
    """Add a new researcher"""
    researchers = load_researchers()
    for r in researchers:
        if r.get('orcid') == orcid:
            return False, "Researcher with this ORCID already exists"
    researcher = {
        'orcid': orcid,
        'name': name or f"Researcher {orcid[-4:]}",
        'institution': institution,
        'email': email,
        'added_at': datetime.now().isoformat(),
        'active': True,
        'schema_version': SCHEMA_VERSION,
    }
    researchers.append(researcher)
    success, error = save_researchers(researchers)
    return (True, None) if success else (False, error)

def remove_researcher(orcid):
    """Soft-delete a researcher (keeps their publications)"""
    researchers = load_researchers()
    for r in researchers:
        if r.get('orcid') == orcid:
            r['active'] = False
    return save_researchers(researchers)

def get_active_researchers():
    """Get list of active researchers"""
    return [r for r in load_researchers() if r.get('active', True)]

# ============================================
# PUBLICATIONS STORAGE
# ============================================

def load_publications(orcid=None):
    """
    Load publications from HF Dataset.
    If orcid is provided, filter by researcher ORCID.
    Returns list (empty on error).
    """
    if not is_hf_configured():
        return []
    data, err = _hf_download_json("publications.json")
    if err or data is None:
        return []
    if isinstance(data, list):
        all_publications = data
    elif isinstance(data, dict):
        all_publications = data.get("data", [])
    else:
        return []

    if orcid:
        return [p for p in all_publications if p.get('orcid') == orcid]
    return all_publications

def save_publications(publications):
    """Save publications to HF Dataset (thread-safe)"""
    wrapped = {
        "schema_version": SCHEMA_VERSION,
        "data": publications,
        "updated_at": datetime.now().isoformat(),
    }
    with _write_lock:
        return _retry(
            lambda: _hf_upload_json("publications.json", wrapped, "Update publications data"),
            attempts=3, base_delay=2,
        )

def add_publication(pub_data):
    """Add or update a single publication"""
    publications = load_publications()
    for i, p in enumerate(publications):
        if p.get('id') == pub_data.get('id'):
            publications[i] = pub_data
            return save_publications(publications)
    publications.append(pub_data)
    return save_publications(publications)

# ============================================
# OPENALEX SYNC (with caching, dedup, backoff)
# ============================================

def sync_from_openalex(orcid, force=False):
    """
    Sync publications from OpenAlex API for a given ORCID.
    Uses cache (1-hour TTL) unless force=True.
    Detects duplicates by both OpenAlex ID and DOI.
    Returns (new_count, error_message).
    """
    import requests

    # Normalize ORCID — strip full URL prefix if user pasted it
    orcid = orcid.strip()
    if orcid.startswith("https://orcid.org/"):
        orcid = orcid[len("https://orcid.org/"):]
    if orcid.startswith("http://orcid.org/"):
        orcid = orcid[len("http://orcid.org/"):]

    try:
        # --- Cache check (only use cache when it has results) ---
        works = None
        if not force:
            cached = get_cached_works(orcid)
            if cached:           # ignore cached empty lists
                works = cached

        if works is None:
            url = (
                f"https://api.openalex.org/works"
                f"?filter=authorships.author.orcid:{orcid}"
                f"&per-page=200&sort=publication_year:desc"
            )
            # Add polite-pool email to User-Agent if configured
            polite_email = os.environ.get("OPEN_ALEX", "")
            user_agent = (
                f"ORC-Dashboard/1.0 (mailto:{polite_email})" if polite_email
                else "ORC-Dashboard/1.0"
            )
            # Retry with backoff
            resp = None
            for attempt in range(3):
                try:
                    resp = requests.get(
                        url,
                        headers={"User-Agent": user_agent},
                        timeout=30,
                    )
                    if resp.status_code == 200:
                        break
                    resp = None
                except requests.RequestException:
                    pass
                if attempt < 2:
                    time.sleep(2 ** attempt)

            if resp is None or resp.status_code != 200:
                return 0, "Could not fetch from OpenAlex after retries"

            works = resp.json().get("results", [])
            if works:            # only cache non-empty results
                set_cached_works(orcid, works, ttl=3600)

        if not works:
            return 0, "No publications found for this ORCID"

        publications = load_publications()
        existing_ids = {p.get('id') for p in publications}
        existing_dois = {p.get('doi') for p in publications if p.get('doi')}

        new_count = 0
        for work in works:
            work_id = work.get("id", "").replace("https://openalex.org/", "")
            doi = (work.get("doi") or "").replace("https://doi.org/", "") or None

            # Skip duplicates by OpenAlex ID or DOI
            if work_id in existing_ids:
                continue
            if doi and doi in existing_dois:
                continue

            pub = {
                "id": work_id,
                "doi": doi,
                "title": work.get("title") or "Untitled",
                "abstract": work.get("abstract") or "",
                "publication_year": work.get("publication_year"),
                "journal_name": (
                    (work.get("primary_location") or {})
                    .get("source") or {}
                ).get("display_name", "") or "Unknown",
                "citation_count": work.get("cited_by_count", 0) or 0,
                "open_access": 1 if (work.get("open_access") or {}).get("is_oa") else 0,
                "source": "openalex",
                "authors": [
                    a.get("author", {}).get("display_name", "")
                    for a in work.get("authorships", [])[:10]
                ],
                "orcid": orcid,
                "synced_at": datetime.now().isoformat(),
                "schema_version": SCHEMA_VERSION,
            }
            publications.append(pub)
            existing_ids.add(work_id)
            if doi:
                existing_dois.add(doi)
            new_count += 1

        if new_count > 0:
            success, error = save_publications(publications)
            if error:
                return 0, error

        return new_count, None

    except Exception as e:
        return 0, str(e)

# ============================================
# AUDIT LOG PERSISTENCE
# ============================================

_audit_buffer: list = []
_audit_buffer_lock = threading.Lock()

def append_audit_entry(entry):
    """Buffer an audit entry; flush to HF when buffer reaches threshold"""
    with _audit_buffer_lock:
        _audit_buffer.append(entry)
        should_flush = len(_audit_buffer) >= 20
    if should_flush:
        flush_audit_log()

def flush_audit_log():
    """Flush buffered audit entries to HF Dataset"""
    with _audit_buffer_lock:
        if not _audit_buffer:
            return
        pending = list(_audit_buffer)
        _audit_buffer.clear()

    if not is_hf_configured():
        return

    existing = load_audit_log()
    existing.extend(pending)
    if len(existing) > 1000:
        existing = existing[-1000:]
    _hf_upload_json("audit_log.json", existing, "Append audit entries")

def load_audit_log():
    """Load persisted audit log from HF Dataset"""
    if not is_hf_configured():
        return []
    data, err = _hf_download_json("audit_log.json")
    if err or not isinstance(data, list):
        return []
    return data

# ============================================
# ERROR LOG PERSISTENCE
# ============================================

_error_buffer: list = []
_error_buffer_lock = threading.Lock()


def append_error_entry(entry):
    """Buffer an error entry; flush to HF when buffer reaches threshold."""
    with _error_buffer_lock:
        _error_buffer.append(entry)
        should_flush = len(_error_buffer) >= 10
    if should_flush:
        flush_error_log()


def flush_error_log():
    """Flush buffered error entries to HF Dataset."""
    with _error_buffer_lock:
        if not _error_buffer:
            return
        pending = list(_error_buffer)
        _error_buffer.clear()

    if not is_hf_configured():
        return

    existing = load_error_log()
    existing.extend(pending)
    if len(existing) > 500:
        existing = existing[-500:]
    _hf_upload_json("error_log.json", existing, "Append error entries")


def load_error_log():
    """Load persisted error log from HF Dataset."""
    if not is_hf_configured():
        return []
    data, err = _hf_download_json("error_log.json")
    if err or not isinstance(data, list):
        return []
    return data


# ============================================
# COMPATIBILITY LAYER (SQL-style queries → HF Dataset)
# ============================================

def execute_query(sql, params=None):
    """
    Compatibility shim — converts SQL-like queries to HF Dataset operations.
    Mirrors the interface previously used for Cloudflare D1.
    """
    publications = load_publications()
    if not publications:
        return [], None

    df = pd.DataFrame(publications)
    sql_lower = sql.lower().strip()

    # Aggregate query used by the dashboard metrics block
    if "coalesce" in sql_lower or "case when" in sql_lower:
        total = len(df)
        total_cit = int(df['citation_count'].sum()) if 'citation_count' in df else 0
        avg_cit = float(df['citation_count'].mean()) if 'citation_count' in df else 0.0
        oa = int(df['open_access'].sum()) if 'open_access' in df else 0
        max_year = df['publication_year'].max() if 'publication_year' in df else None
        result = [{
            "count": total,
            "total_pubs": total,
            "total_citations": total_cit,
            "citations": total_cit,
            "avg_citations": avg_cit,
            "oa_count": oa,
            "latest_year": max_year,
        }]
        return result, None

    if sql_lower.startswith("select count(*)"):
        return [{"count": len(df)}], None

    if sql_lower.startswith("select "):
        if "order by" in sql_lower:
            if "publication_year desc" in sql_lower:
                df = df.sort_values("publication_year", ascending=False, na_position='last')
            elif "citation_count desc" in sql_lower:
                df = df.sort_values("citation_count", ascending=False, na_position='last')
        if "limit" in sql_lower:
            parts = sql_lower.split("limit")
            if len(parts) > 1:
                try:
                    limit = int(parts[1].strip().split()[0])
                    df = df.head(limit)
                except (ValueError, IndexError):
                    pass
        return df.to_dict('records'), None

    return [], None

def is_db_configured():
    """Check if HF is configured"""
    return is_hf_configured()

def log_audit(action, details="", user="anonymous"):
    """No-op stub kept for import compatibility; real logging in security.py"""
    pass
