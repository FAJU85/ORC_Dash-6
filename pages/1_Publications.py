"""
ORC Research Dashboard - Publications Page
"""

import streamlit as st
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.security import (
    get_secret, get_nested_secret, execute_query,
    sanitize_string, validate_orcid, log_audit, log_error, RateLimiter,
    can_sync_publications, is_admin
)
from utils.hf_data import (
    sync_from_openalex as hf_sync, get_active_researchers,
    sync_all_sources, start_auto_sync, stop_auto_sync, is_auto_sync_running,
)
from utils.export import export_to_csv, export_to_bibtex
from utils.ui import apply_theme, render_footer, render_empty_state

st.set_page_config(page_title="Publications", page_icon="📚", layout="wide")
apply_theme()

# Initialize rate limiter
rate_limiter = RateLimiter()

# ============================================
# SYNC FUNCTION
# ============================================

def sync_publications(orcid, all_sources=False):
    """Sync publications for the given ORCID from OpenAlex (or all sources)."""
    if not validate_orcid(orcid):
        return {}, "Invalid ORCID format. Use: 0000-0000-0000-0000"

    allowed, wait_time = rate_limiter.is_allowed(f"sync_{orcid}", max_attempts=3, window_seconds=300)
    if not allowed:
        return {}, f"Too many sync attempts. Please wait {wait_time} seconds."

    rate_limiter.record_attempt(f"sync_{orcid}")
    log_audit("sync_start", f"ORCID: {orcid[:8]}***")

    if all_sources:
        results = sync_all_sources(orcid)
        total = sum(c for c, _ in results.values())
        errors = {src: e for src, (c, e) in results.items() if e and c == 0}
        log_audit("sync_complete", f"Total: {total}")
        return results, None
    else:
        count, error = hf_sync(orcid)
        if error:
            log_audit("sync_error", error)
            log_error("sync_error", error, page="Publications")
            return {"openalex": (0, error)}, error
        log_audit("sync_complete", f"Inserted: {count}")
        return {"openalex": (count, None)}, None

# ============================================
# SESSION STATE
# ============================================

if "selected_paper" not in st.session_state:
    st.session_state.selected_paper = None
if "current_page" not in st.session_state:
    st.session_state.current_page = 1

# ============================================
# PAGE
# ============================================

st.title("📚 Publications")

# ── Sync Section ────────────────────────────────────────────────────────────
st.header("🔄 Sync Publications")

if can_sync_publications():
    default_orcid = get_nested_secret("researcher", "orcid", "")
    col1, col2, col3, col4 = st.columns([3, 1, 1, 1])
    with col1:
        orcid = st.text_input("ORCID ID", value=default_orcid, placeholder="0000-0000-0000-0000")
    with col2:
        st.write("")
        if st.button("🔄 OpenAlex", type="primary", use_container_width=True):
            with st.spinner("Syncing…"):
                results, error = sync_publications(orcid, all_sources=False)
            if error:
                st.error(f"❌ {error}")
            else:
                cnt = results.get("openalex", (0, None))[0]
                st.success(f"✅ +{cnt}")
                st.rerun()
    with col3:
        st.write("")
        if st.button("🌐 All Sources", use_container_width=True,
                     help="Sync from OpenAlex, CrossRef, and PubMed"):
            with st.spinner("Syncing all sources…"):
                results, error = sync_publications(orcid, all_sources=True)
            if error:
                st.error(f"❌ {error}")
            else:
                total = sum(c for c, _ in results.values())
                oa = results.get("openalex", (0, None))[0]
                cr = results.get("crossref", (0, None))[0]
                pm = results.get("pubmed",   (0, None))[0]
                st.success(f"✅ +{total} total (OA:{oa} CR:{cr} PM:{pm})")
                st.rerun()
    with col4:
        st.write("")
        auto_on = is_auto_sync_running()
        if auto_on:
            if st.button("⏹ Auto-Sync", use_container_width=True,
                         help="Stop background auto-sync"):
                stop_auto_sync()
                st.rerun()
            st.caption("⏱ Active")
        else:
            if st.button("⏱ Auto-Sync", use_container_width=True,
                         help="Sync all researchers every 24 h in the background"):
                start_auto_sync(interval_hours=24)
                st.success("✅ Auto-sync enabled")
else:
    st.info("🔒 **Sync functionality is restricted to administrators only.**")

st.divider()

# ── Load all publications ───────────────────────────────────────────────────
pubs, error = execute_query(
    "SELECT * FROM publications ORDER BY publication_year DESC, citation_count DESC"
)

if error:
    st.error("❌ Could not load publications")
    st.stop()

if not pubs:
    render_empty_state(
        "No publications yet",
        "Use the Sync section above to import your publications.",
    )
    st.stop()

# ── Researcher Filter ───────────────────────────────────────────────────────
st.header("📄 Publication List")

researchers = get_active_researchers()
researcher_map = {r.get('name', r.get('orcid', '')): r.get('orcid') for r in researchers if r.get('orcid')}

filter_cols = st.columns([2, 2, 1, 1])

with filter_cols[0]:
    # Full-text search (title + abstract + journal + authors)
    search = st.text_input("🔍 Search", placeholder="Search title, abstract, journal, authors…")

with filter_cols[1]:
    researcher_options = ["All Researchers"] + list(researcher_map.keys())
    selected_researcher = st.selectbox("👤 Researcher", researcher_options)

with filter_cols[2]:
    years = sorted({p.get("publication_year") for p in pubs if p.get("publication_year")}, reverse=True)
    year_filter = st.selectbox("Year", ["All"] + [str(y) for y in years])

with filter_cols[3]:
    sort_opt = st.selectbox("Sort", ["Newest", "Most Cited", "A-Z"])

# ── Apply Filters ───────────────────────────────────────────────────────────
filtered = list(pubs)

# Researcher filter
if selected_researcher != "All Researchers" and selected_researcher in researcher_map:
    filter_orcid = researcher_map[selected_researcher]
    filtered = [p for p in filtered if p.get('orcid') == filter_orcid]

# Full-text search across title, abstract, journal, and authors
if search:
    q = sanitize_string(search, 100).lower()
    def _matches(p):
        if q in (p.get("title") or "").lower():
            return True
        if q in (p.get("abstract") or "").lower():
            return True
        if q in (p.get("journal_name") or "").lower():
            return True
        authors = p.get("authors", [])
        if isinstance(authors, list):
            return any(q in (a or "").lower() for a in authors)
        return False
    filtered = [p for p in filtered if _matches(p)]

# Year filter
if year_filter != "All":
    filtered = [p for p in filtered if str(p.get("publication_year")) == year_filter]

# Sort
if sort_opt == "Newest":
    filtered.sort(key=lambda x: x.get("publication_year") or 0, reverse=True)
elif sort_opt == "Most Cited":
    filtered.sort(key=lambda x: x.get("citation_count") or 0, reverse=True)
else:
    filtered.sort(key=lambda x: (x.get("title") or "").lower())

# ── Export Section ──────────────────────────────────────────────────────────
if filtered:
    with st.expander("📥 Export Publications", expanded=False):
        prefs = st.session_state.get("user_preferences", {})
        include_abs = prefs.get("show_abstracts", True)

        ecol1, ecol2, ecol3 = st.columns(3)

        with ecol1:
            csv_bytes = export_to_csv(filtered, include_abstracts=include_abs)
            st.download_button(
                label="⬇️ Download CSV",
                data=csv_bytes,
                file_name="publications.csv",
                mime="text/csv",
                use_container_width=True,
            )

        with ecol2:
            bib_text = export_to_bibtex(filtered)
            st.download_button(
                label="⬇️ Download BibTeX",
                data=bib_text.encode("utf-8"),
                file_name="publications.bib",
                mime="text/plain",
                use_container_width=True,
            )

        with ecol3:
            import json as _json
            json_bytes = _json.dumps(filtered, indent=2, default=str).encode("utf-8")
            st.download_button(
                label="⬇️ Download JSON",
                data=json_bytes,
                file_name="publications.json",
                mime="application/json",
                use_container_width=True,
            )

        st.caption(f"Exporting {len(filtered)} publication(s) currently shown.")

st.divider()

# ── Pagination ──────────────────────────────────────────────────────────────
prefs = st.session_state.get("user_preferences", {})
PER_PAGE = prefs.get("items_per_page", 10)
total_pages = max(1, (len(filtered) + PER_PAGE - 1) // PER_PAGE)
st.session_state.current_page = min(max(1, st.session_state.current_page), total_pages)

start = (st.session_state.current_page - 1) * PER_PAGE
page_items = filtered[start:start + PER_PAGE]

st.markdown(f"**Showing {start + 1}–{min(start + PER_PAGE, len(filtered))} of {len(filtered)} publications**")

# ── Publication Cards ───────────────────────────────────────────────────────
show_abstracts = prefs.get("show_abstracts", True)

for pub in page_items:
    title    = pub.get("title") or "Untitled"
    journal  = pub.get("journal_name") or "Unknown"
    year     = pub.get("publication_year") or ""
    citations = pub.get("citation_count") or 0
    doi      = pub.get("doi")
    abstract = pub.get("abstract") or ""
    is_oa    = pub.get("open_access")
    authors  = pub.get("authors", [])
    if not isinstance(authors, list):
        authors = []

    col1, col2 = st.columns([5, 1])

    with col1:
        st.markdown(f"**{title}**")
        if authors:
            auth_str = ", ".join(str(a) for a in authors[:3] if a)
            if len(authors) > 3:
                with st.expander(f"👥 {auth_str} +{len(authors) - 3} more"):
                    st.write(", ".join(str(a) for a in authors if a))
            else:
                st.markdown(f"👥 {auth_str}")
        oa_badge = " • 🔓 OA" if is_oa else ""
        st.markdown(f"📰 **{journal}** • {year} • 📈 {citations} citations{oa_badge}")

        if abstract and show_abstracts:
            with st.expander("📝 Abstract"):
                st.write(abstract[:500] + ("…" if len(abstract) > 500 else ""))

    with col2:
        pub_id = pub.get('id', title[:20])
        if st.button("🔬 Analyze", key=f"a_{pub_id}", use_container_width=True):
            st.session_state.selected_paper = {
                "id": pub_id,
                "title": title,
                "journal_name": journal,
                "publication_year": year,
                "citation_count": citations,
                "abstract": abstract,
            }
            log_audit("paper_selected", title[:50])
            st.switch_page("pages/2_AI_Assistant.py")

        if doi:
            st.link_button("🔗 DOI", f"https://doi.org/{doi}", use_container_width=True)

    st.markdown("<div class='pub-card-wrap'></div>", unsafe_allow_html=True)

# ── Pagination Controls ─────────────────────────────────────────────────────
if total_pages > 1:
    c1, c2, c3, c4, c5 = st.columns([1, 1, 2, 1, 1])
    with c1:
        if st.button("⏮ First", disabled=st.session_state.current_page == 1, use_container_width=True):
            st.session_state.current_page = 1
            st.rerun()
    with c2:
        if st.button("◀ Prev", disabled=st.session_state.current_page == 1, use_container_width=True):
            st.session_state.current_page -= 1
            st.rerun()
    with c3:
        st.markdown(
            f"<div style='text-align:center'>Page {st.session_state.current_page} / {total_pages}</div>",
            unsafe_allow_html=True,
        )
    with c4:
        if st.button("Next ▶", disabled=st.session_state.current_page == total_pages, use_container_width=True):
            st.session_state.current_page += 1
            st.rerun()
    with c5:
        if st.button("Last ⏭", disabled=st.session_state.current_page == total_pages, use_container_width=True):
            st.session_state.current_page = total_pages
            st.rerun()

render_footer()

# ── Sidebar ─────────────────────────────────────────────────────────────────
if st.session_state.get("selected_paper"):
    st.sidebar.success(f"📄 Selected: {st.session_state.selected_paper['title'][:30]}…")
    st.sidebar.info("Go to **AI Assistant** to analyze")
