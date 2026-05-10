"""
ORC Research Dashboard - Publications Page
"""

import streamlit as st
import json
import sys
import os
import html # Added for escaping DOI in links

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.security import (
    get_secret, get_nested_secret, execute_query,
    sanitize_string, validate_orcid, log_audit, log_error, RateLimiter,
    can_sync_publications, is_admin
)
from utils.hf_data import sync_from_openalex as hf_sync, get_active_researchers, load_cms_content
from utils.export import export_to_csv, export_to_bibtex
from utils.styles import (
    apply_styles, get_theme, hero_html, section_title_html,
    pub_card_html, footer_html, render_navbar, DARK, LIGHT
)

apply_styles()
render_navbar()

colors = DARK if get_theme() == "dark" else LIGHT
_cms = st.session_state.get("_cms_override") or load_cms_content()

# Initialize rate limiter
rate_limiter = RateLimiter()

# ============================================
# SYNC FUNCTION
# ============================================

def sync_publications(orcid: str) -> tuple[int, str | None]:
    """
    Synchronize a researcher's publications from OpenAlex using their ORCID.
    
    Parameters:
        orcid (str): ORCID identifier in the format `0000-0000-0000-0000`.
    
    Returns:
        tuple: `(inserted_count, error_message)` where `inserted_count` is the number of publications added (0 on failure), and `error_message` is a string describing the failure or `None` on success. Possible error messages include an invalid ORCID format message and a rate-limit message indicating how many seconds to wait.
    """
    if not validate_orcid(orcid):
        return 0, "Invalid ORCID format. Use: 0000-0000-0000-0000"

    allowed, wait_time = rate_limiter.is_allowed(f"sync_{orcid}", max_attempts=3, window_seconds=300)
    if not allowed:
        return 0, f"Too many sync attempts. Please wait {wait_time} seconds."

    rate_limiter.record_attempt(f"sync_{orcid}")
    log_audit("sync_start", f"ORCID: {orcid[:8]}***")

    count, error = hf_sync(orcid)
    if error:
        log_audit("sync_error", error)
        log_error("sync_error", error, page="Publications")
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
# PAGE
# ============================================

_pub_hero = _cms.get("publications_hero", {})
if _pub_hero.get("enabled", True):
    st.markdown(
        hero_html(
            _pub_hero.get("title", "").strip() or "📚 Publications",
            _pub_hero.get("subtitle", "").strip() or "Browse, search, and export your research portfolio",
        ),
        unsafe_allow_html=True,
    )

# ── Sync Section ────────────────────────────────────────────────────────────
st.markdown(section_title_html("Sync Publications"), unsafe_allow_html=True)

if can_sync_publications():
    col1, col2 = st.columns([3, 1])
    with col1:
        default_orcid = get_nested_secret("researcher", "orcid", "")
        orcid = st.text_input("ORCID ID", value=default_orcid, placeholder="0000-0000-0000-0000", label_visibility="collapsed")
    with col2:
        if st.button("🔄 Sync Now", type="primary", use_container_width=True):
            with st.spinner("Syncing publications…"):
                count, error = sync_publications(orcid)
            if error:
                st.error(f"❌ {error}")
            else:
                st.success(f"✅ Synced {count} new publications!")
                st.rerun()
else:
    st.markdown(
        f'<div class="orc-card" style="border-left:4px solid {colors["warning"]};padding:0.75rem 1rem;">'
        f'🔒 Sync is restricted to administrators only.'
        f'</div>',
        unsafe_allow_html=True,
    )

if can_sync_publications():
    with st.expander("🔍 Search by Author Name", expanded=False):
        st.caption("Find publications for authors without an ORCID by searching OpenAlex by display name.")
        name_input = st.text_input("Author display name", placeholder="AA Alfadda", key="sync_name_input")
        link_orcid_input = st.text_input("Link to researcher ORCID (optional)", placeholder="0000-0000-0000-0000",
                                          key="sync_name_link_orcid")
        if st.button("🔎 Search & Import", type="primary", key="btn_sync_name",
                     disabled=not name_input.strip()):
            allowed, wait_time = rate_limiter.is_allowed(f"sync_name_{name_input[:20]}", max_attempts=3, window_seconds=300)
            if not allowed:
                st.error(f"⚠️ Rate limited. Wait {wait_time}s.")
            else:
                rate_limiter.record_attempt(f"sync_name_{name_input[:20]}")
                with st.spinner(f"Searching OpenAlex for '{name_input}'…"):
                    from utils.hf_data import sync_by_display_name
                    count, err = sync_by_display_name(name_input.strip(), linked_orcid=link_orcid_input.strip())
                if err:
                    st.error(f"❌ {err}")
                else:
                    st.success(f"✅ Imported {count} new publication(s) for '{name_input}'")
                    log_audit("sync_by_name", f"name:{name_input[:30]}, count:{count}")

# ── Load all publications ───────────────────────────────────────────────────
pubs, error = execute_query(
    "SELECT * FROM publications ORDER BY publication_year DESC, citation_count DESC"
)

if error:
    st.error("❌ Could not load publications")
    st.stop()

if not pubs:
    st.markdown(
        f'<div class="orc-card" style="text-align:center;padding:2.5rem;">'
        f'<div style="font-size:2.5rem;margin-bottom:0.75rem">📭</div>'
        f'<div style="font-weight:600;font-size:1rem;margin-bottom:0.25rem">No publications yet</div>'
        f'<div style="font-size:0.85rem;color:{colors["text2"]}">Use Sync Now to fetch your publications</div>'
        f'</div>',
        unsafe_allow_html=True,
    )
    st.stop()

# Ensure authors are always a list, even if stored as JSON string
for p in pubs:
    authors_data = p.get("authors")
    if isinstance(authors_data, str):
        try:
            p["authors"] = json.loads(authors_data)
        except json.JSONDecodeError:
            p["authors"] = []
    elif not isinstance(authors_data, list):
        p["authors"] = []

# ── Filters ─────────────────────────────────────────────────────────────────
st.markdown(section_title_html("Publication List"), unsafe_allow_html=True)

researchers = get_active_researchers()
researcher_map = {r.get('name', r.get('orcid', '')): r.get('orcid') for r in researchers if r.get('orcid')}

filter_cols = st.columns([2, 2, 1, 1])

with filter_cols[0]:
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

if selected_researcher != "All Researchers" and selected_researcher in researcher_map:
    filter_orcid = researcher_map[selected_researcher]
    filtered = [p for p in filtered if p.get('orcid') == filter_orcid]

if search:
    q = sanitize_string(search, 100).lower()
    def _matches(p: dict) -> bool:
        """
        Check whether the current query string `q` appears in key text fields of a publication record.
        
        Parameters:
            p (Mapping): A publication-like mapping with optional keys `"title"`, `"abstract"`, `"journal_name"`, and `"authors"`. `"authors"` may be a list of author strings.
        
        Returns:
            bool: `True` if `q` is a substring of the title, abstract, journal name, or any author entry (case-insensitive); `False` otherwise.
        """
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

if year_filter != "All":
    filtered = [p for p in filtered if str(p.get("publication_year")) == year_filter]

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

# ── Pagination ──────────────────────────────────────────────────────────────
prefs = st.session_state.get("user_preferences", {})
PER_PAGE = prefs.get("items_per_page", 10)
total_pages = max(1, (len(filtered) + PER_PAGE - 1) // PER_PAGE)
st.session_state.current_page = min(max(1, st.session_state.current_page), total_pages)

start = (st.session_state.current_page - 1) * PER_PAGE
page_items = filtered[start:start + PER_PAGE]

if filtered:
    st.markdown(
        f'<p style="font-size:0.82rem;opacity:0.6;margin:0.5rem 0 0.75rem">'
        f'Showing {start + 1}–{min(start + PER_PAGE, len(filtered))} of {len(filtered)} publications</p>',
        unsafe_allow_html=True,
    )
else:
    st.markdown(
        f'<p style="font-size:0.82rem;color:{colors["text2"]};margin:0.5rem 0 0.75rem">'
        f'No publications match the current filters</p>',
        unsafe_allow_html=True,
    )

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

    pub_id = pub.get('id', title[:20])

    # Card — full width
    st.markdown(
        pub_card_html(
            title    = title[:160],
            authors  = authors,
            journal  = journal,
            year     = year,
            citations= citations,
            is_oa    = bool(is_oa),
            abstract = abstract if show_abstracts else "",
        ),
        unsafe_allow_html=True,
    )

    # Action buttons — compact row beneath the card
    btn_cols = st.columns([2, 2, 6]) if doi else st.columns([2, 8])
    with btn_cols[0]:
        if st.button("🔬 Analyze", key=f"a_{pub_id}", help="Analyze with AI Assistant"):
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
        with btn_cols[1]:
            st.markdown(
                f'<a href="https://doi.org/{html.escape(doi)}" target="_blank" '
                f'style="display:inline-flex;align-items:center;gap:0.3rem;'
                f'background:{colors["surface2"]};color:{colors["text"]};'
                f'border:1px solid {colors["border"]};border-radius:6px;'
                f'padding:0.35rem 0.75rem;text-decoration:none;'
                f'font-size:0.82rem;font-weight:500;white-space:nowrap">'
                f'🔗 View</a>',
                unsafe_allow_html=True,
            )

    st.markdown('<div style="margin-bottom:0.5rem"></div>', unsafe_allow_html=True)

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
            f"<div style='text-align:center;font-size:0.85rem;opacity:0.7'>Page {st.session_state.current_page} / {total_pages}</div>",
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

# ── Sidebar ─────────────────────────────────────────────────────────────────
if st.session_state.get("selected_paper"):
    st.sidebar.success(f"📄 Selected: {st.session_state.selected_paper['title'][:30]}…")
    st.sidebar.info("Go to **AI Assistant** to analyze")

# ── Footer ───────────────────────────────────────────────────────────────────
st.divider()
st.markdown(footer_html(), unsafe_allow_html=True)
