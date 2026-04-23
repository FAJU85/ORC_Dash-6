"""
ORC Research Dashboard - Publications Page
Secure data fetching with input validation
Using Hugging Face Datasets for storage
"""

import streamlit as st
import requests
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.security import (
    get_secret, get_nested_secret, execute_query,
    sanitize_string, validate_orcid, log_audit, RateLimiter,
    can_sync_publications, is_admin
)
from utils.hf_data import sync_from_openalex as hf_sync_from_openalex

st.set_page_config(page_title="Publications", page_icon="📚", layout="wide")

# Initialize rate limiter
rate_limiter = RateLimiter()

# ============================================
# SYNC FUNCTION (Using Hugging Face Datasets)
# ============================================

def sync_from_openalex(orcid):
    """Sync publications from OpenAlex using Hugging Face Datasets"""
    
    # Validate ORCID format
    if not validate_orcid(orcid):
        return 0, "Invalid ORCID format. Use: 0000-0000-0000-0000"
    
    # Rate limit sync operations
    allowed, wait_time = rate_limiter.is_allowed(f"sync_{orcid}", max_attempts=3, window_seconds=300)
    if not allowed:
        return 0, f"Too many sync attempts. Please wait {wait_time} seconds."
    
    rate_limiter.record_attempt(f"sync_{orcid}")
    log_audit("sync_start", f"ORCID: {orcid[:8]}***")
    
    # Use HF Data module for syncing
    count, error = hf_sync_from_openalex(orcid)
    
    if error:
        log_audit("sync_error", error)
        return 0, error
    
    log_audit("sync_complete", f"Inserted: {count}")
    return count, None

# ============================================
# SESSION STATE
# ============================================

if "selected_paper" not in st.session_state:
    st.session_state.selected_paper = None
if "current_page" not in st.session_state:
    st.session_state.current_page = 1

# ============================================
# PAGE CONTENT
# ============================================

st.title("📚 Publications")

# SYNC SECTION
st.header("🔄 Sync from OpenAlex")

# Check if user can sync
if can_sync_publications():
    col1, col2 = st.columns([3, 1])

    with col1:
        default_orcid = get_nested_secret("researcher", "orcid", "")
        orcid = st.text_input("ORCID ID", value=default_orcid, placeholder="0000-0000-0000-0000")

    with col2:
        st.write("")
        if st.button("🔄 Sync Now", type="primary", use_container_width=True):
            with st.spinner("Syncing publications..."):
                count, error = sync_from_openalex(orcid)
                if error:
                    st.error(f"❌ {error}")
                else:
                    st.success(f"✅ Synced {count} publications!")
                    st.cache_data.clear()
                    st.rerun()
else:
    st.info("🔒 **Sync functionality is restricted to administrators only.**")
    st.markdown("*Only admins can sync publications from OpenAlex.*")

st.divider()

# PUBLICATIONS LIST
st.header("📄 Publication List")

# Use parameterized query (no user input in this query, but still safe)
pubs, error = execute_query(
    "SELECT * FROM publications ORDER BY publication_year DESC, citation_count DESC"
)

if error:
    st.error("❌ Could not load publications")
    st.stop()

if not pubs:
    st.info("📭 No publications in database. Click **Sync Now** to fetch from OpenAlex.")
    st.stop()

# Filters
col1, col2, col3 = st.columns([2, 1, 1])

with col1:
    search = st.text_input("🔍 Search", placeholder="Search title or journal...")

with col2:
    years = sorted(set(p.get("publication_year", 0) for p in pubs if p.get("publication_year")), reverse=True)
    year_filter = st.selectbox("Year", ["All"] + [str(y) for y in years])

with col3:
    sort_opt = st.selectbox("Sort", ["Newest", "Most Cited", "A-Z"])

# Filter (in Python, not SQL, to avoid injection)
filtered = pubs.copy()

if search:
    search_lower = sanitize_string(search, 100).lower()
    filtered = [p for p in filtered if 
        search_lower in (p.get("title") or "").lower() or 
        search_lower in (p.get("journal_name") or "").lower()]

if year_filter != "All":
    filtered = [p for p in filtered if str(p.get("publication_year")) == year_filter]

# Sort
if sort_opt == "Newest":
    filtered.sort(key=lambda x: x.get("publication_year") or 0, reverse=True)
elif sort_opt == "Most Cited":
    filtered.sort(key=lambda x: x.get("citation_count") or 0, reverse=True)
else:
    filtered.sort(key=lambda x: (x.get("title") or "").lower())

# Pagination
PER_PAGE = 10
total_pages = max(1, (len(filtered) + PER_PAGE - 1) // PER_PAGE)
st.session_state.current_page = min(max(1, st.session_state.current_page), total_pages)

start = (st.session_state.current_page - 1) * PER_PAGE
end = start + PER_PAGE
page_items = filtered[start:end]

st.markdown(f"**Showing {start+1}-{min(end, len(filtered))} of {len(filtered)} publications**")

# Display
for pub in page_items:
    title = pub.get("title") or "Untitled"
    journal = pub.get("journal_name") or "Unknown"
    year = pub.get("publication_year") or ""
    citations = pub.get("citation_count") or 0
    doi = pub.get("doi")
    abstract = pub.get("abstract") or ""
    is_oa = pub.get("open_access")
    
    # Parse authors safely
    try:
        raw = json.loads(pub.get("raw_data") or "{}")
        authors = raw.get("authors", [])
    except:
        authors = []
    
    col1, col2 = st.columns([5, 1])
    
    with col1:
        st.markdown(f"### {title}")
        if authors:
            authors_str = ", ".join(authors[:3])
            if len(authors) > 3:
                authors_str += f" +{len(authors)-3} more"
            st.markdown(f"👥 {authors_str}")
        st.markdown(f"📰 **{journal}** • {year} • 📈 {citations} citations" + (" • 🔓 OA" if is_oa else ""))
        
        if abstract:
            with st.expander("📝 Abstract"):
                st.write(abstract[:500] + ("..." if len(abstract) > 500 else ""))
    
    with col2:
        pub_id = pub.get('id', title[:20])
        if st.button("🤖 Analyze", key=f"a_{pub_id}", use_container_width=True):
            st.session_state.selected_paper = {
                "id": pub_id,
                "title": title,
                "journal_name": journal,
                "publication_year": year,
                "citation_count": citations,
                "abstract": abstract
            }
            log_audit("paper_selected", title[:50])
            st.success("✅ Selected! Go to AI Assistant")
        
        if doi:
            st.link_button("🔗 DOI", f"https://doi.org/{doi}", use_container_width=True)
    
    st.divider()

# Pagination controls
if total_pages > 1:
    col1, col2, col3, col4, col5 = st.columns([1, 1, 2, 1, 1])
    
    with col1:
        if st.button("⏮️", disabled=st.session_state.current_page == 1):
            st.session_state.current_page = 1
            st.rerun()
    with col2:
        if st.button("◀️", disabled=st.session_state.current_page == 1):
            st.session_state.current_page -= 1
            st.rerun()
    with col3:
        st.markdown(f"<div style='text-align:center'>Page {st.session_state.current_page} / {total_pages}</div>", unsafe_allow_html=True)
    with col4:
        if st.button("▶️", disabled=st.session_state.current_page == total_pages):
            st.session_state.current_page += 1
            st.rerun()
    with col5:
        if st.button("⏭️", disabled=st.session_state.current_page == total_pages):
            st.session_state.current_page = total_pages
            st.rerun()

# Sidebar
if st.session_state.get("selected_paper"):
    st.sidebar.success(f"📄 Selected: {st.session_state.selected_paper['title'][:30]}...")
    st.sidebar.info("Go to **AI Assistant** to analyze")
