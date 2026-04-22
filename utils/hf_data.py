"""
ORC Research Dashboard - Hugging Face Data Storage
Stores publications using Hugging Face Datasets
"""

import os
import json
import pandas as pd
from datetime import datetime

try:
    from huggingface_hub import HfApi, hf_hub_download
    HF_AVAILABLE = True
except ImportError:
    HF_AVAILABLE = False

# ============================================
# HF DATASET CONFIGURATION
# ============================================

def get_repo_id():
    """Get the Hugging Face repo ID for data storage"""
    # Get from environment variable or use default pattern
    repo_id = os.environ.get("HF_REPO_ID", "")
    if repo_id:
        return repo_id
    return None

def get_hf_token():
    """Get Hugging Face token from secrets/environment"""
    # Try HF_TOKEN first, then fall back to other names
    token = os.environ.get("HF_TOKEN", "")
    if token:
        return token
    return None

def is_hf_configured():
    """Check if Hugging Face is properly configured"""
    return HF_AVAILABLE and get_hf_token() and get_repo_id()

# ============================================
# DATA STORAGE (Using JSON file in HF Dataset)
# ============================================

def load_publications():
    """Load publications from Hugging Face Dataset"""
    try:
        api = HfApi(token=get_hf_token())
        repo_id = get_repo_id()
        
        if not repo_id:
            return []
        
        try:
            # Try to download existing data file
            local_path = hf_hub_download(
                repo_id=repo_id,
                filename="publications.json",
                repo_type="dataset"
            )
            with open(local_path, 'r') as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
        except Exception:
            # File doesn't exist yet, return empty list
            return []
            
    except Exception as e:
        print(f"Error loading publications: {e}")
        return []

def save_publications(publications):
    """Save publications to Hugging Face Dataset"""
    try:
        api = HfApi(token=get_hf_token())
        repo_id = get_repo_id()
        
        if not repo_id:
            return False, "HF_REPO_ID not configured"
        
        # Save to temp file
        temp_path = "/tmp/publications.json"
        with open(temp_path, 'w') as f:
            json.dump(publications, f, indent=2, default=str)
        
        # Upload to HF
        api.upload_file(
            path_or_fileobj=temp_path,
            path_in_repo="publications.json",
            repo_id=repo_id,
            repo_type="dataset",
            commit_message="Update publications data"
        )
        
        return True, None
        
    except Exception as e:
        return False, str(e)

def add_publication(pub_data):
    """Add or update a single publication"""
    publications = load_publications()
    
    # Check if publication already exists
    existing_ids = [p.get('id') for p in publications]
    
    if pub_data.get('id') in existing_ids:
        # Update existing
        for i, p in enumerate(publications):
            if p.get('id') == pub_data.get('id'):
                publications[i] = pub_data
                break
    else:
        # Add new
        publications.append(pub_data)
    
    return save_publications(publications)

def sync_from_openalex(orcid, api_client=None):
    """Sync publications from OpenAlex API"""
    import requests
    
    try:
        url = f"https://api.openalex.org/works?filter=authorships.author.orcid:{orcid}&per-page=200&sort=publication_year:desc"
        resp = requests.get(url, headers={"User-Agent": "ORC-Dashboard/1.0"}, timeout=30)
        
        if resp.status_code != 200:
            return 0, "Could not fetch from OpenAlex"
        
        works = resp.json().get("results", [])
        if not works:
            return 0, "No publications found for this ORCID"
        
        publications = load_publications()
        existing_ids = {p.get('id') for p in publications}
        
        new_count = 0
        for work in works:
            work_id = work.get("id", "").replace("https://openalex.org/", "")
            doi = (work.get("doi") or "").replace("https://doi.org/", "") or None
            
            # Skip if already exists
            if work_id in existing_ids:
                continue
            
            pub = {
                "id": work_id,
                "doi": doi,
                "title": work.get("title") or "Untitled",
                "abstract": work.get("abstract") or "",
                "publication_year": work.get("publication_year"),
                "journal_name": (work.get("primary_location", {}).get("source", {}) or {}).get("display_name", "") or "Unknown",
                "citation_count": work.get("cited_by_count", 0) or 0,
                "open_access": 1 if work.get("open_access", {}).get("is_oa") else 0,
                "source": "openalex",
                "authors": [a.get("author", {}).get("display_name", "") 
                           for a in work.get("authorships", [])[:10]],
                "synced_at": datetime.now().isoformat()
            }
            publications.append(pub)
            new_count += 1
        
        if new_count > 0:
            success, error = save_publications(publications)
            if error:
                return 0, error
        
        return new_count, None
        
    except Exception as e:
        return 0, str(e)

# ============================================
# COMPATIBILITY LAYER (for existing code)
# ============================================

def execute_query(sql, params=None):
    """
    Compatibility layer - converts SQL-like queries to HF Dataset operations
    This provides the same interface as the old D1 execute_query function
    """
    publications = load_publications()
    
    if not publications:
        return [], None
    
    df = pd.DataFrame(publications)
    
    # Handle simple SQL patterns
    sql_lower = sql.lower().strip()
    
    if sql_lower.startswith("select count(*)"):
        # Count query
        result = [{"count": len(df)}]
        return result, None
    
    if sql_lower.startswith("select "):
        # Basic SELECT query
        if "order by" in sql_lower:
            # Handle ORDER BY
            if "publication_year desc" in sql_lower:
                df = df.sort_values("publication_year", ascending=False)
            elif "citation_count desc" in sql_lower:
                df = df.sort_values("citation_count", ascending=False)
        
        if "limit" in sql_lower:
            # Handle LIMIT
            limit_match = sql_lower.split("limit")
            if len(limit_match) > 1:
                try:
                    limit = int(limit_match[1].strip().split()[0])
                    df = df.head(limit)
                except:
                    pass
        
        return df.to_dict('records'), None
    
    return [], None

def is_db_configured():
    """Check if Hugging Face is configured"""
    return is_hf_configured()

def log_audit(action, details="", user="anonymous"):
    """Placeholder audit log"""
    pass