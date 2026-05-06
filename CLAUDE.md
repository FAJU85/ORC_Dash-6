# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run the app locally
streamlit run app.py

# Run all tests
pytest tests/ -v

# Run a single test file
pytest tests/test_security.py -v

# Run a single test by name
pytest tests/test_security.py::TestSanitizeString::test_strips_whitespace -v

# Install dependencies
pip install -r requirements.txt
```

No build step, no linter configured.

## Architecture

**Entry point:** `app.py` — a thin SPA router using `st.navigation(position="hidden")`. It calls `init_session()` once, then hands off to whichever registered page the user navigates to. All `st.set_page_config()` must live here only.

**Page files** (`pages/0_Home.py` … `pages/6_Settings.py`) each start with `apply_styles()` + `render_navbar()`. They must NOT call `st.set_page_config()`.

**Data layer — `utils/hf_data.py`** is the single source of truth for all persistence. There is no SQL database. Publications and researchers are stored as JSON files in a Hugging Face Dataset repo and downloaded/uploaded via `huggingface_hub`. Key functions:
- `load_publications(orcid=None)` — cached with `@st.cache_data(ttl=300)`; call `load_publications.clear()` after any write
- `save_publications(publications)` — thread-safe with `_write_lock`, optimistic concurrency via SHA check, auto-clears cache
- `get_publication_metrics()`, `get_publications_sorted()`, `get_citation_sorted_counts()` — prefer these over `execute_query()`
- `execute_query(sql)` — backwards-compat shim; routes to the explicit helpers above; avoid adding new SQL strings

**Secret access** — always use `get_secret(key)` and `get_nested_secret(section, key, default)` from `utils/security.py`. These read from `st.secrets` (`.streamlit/secrets.toml` locally, HF Space secrets in production). Never read `os.environ` directly for app secrets. Template is in `SECRETS_TEMPLATE.toml`.

**AI layer** (`pages/2_AI_Assistant.py` + `utils/ai_schemas.py`):
- LLM: Groq API, key read as `AI_API_KEY` or `GROQ_API_KEY`, default model `llama-3.3-70b-versatile` (override with `AI_MODEL` secret)
- RAG: `utils/rag.py` embeds publications with `sentence-transformers/all-MiniLM-L6-v2`, falls back to TF-IDF. Index cached in `st.session_state["_rag_index_cache"]` keyed by count + first/last pub ID.
- Feedback loop: `utils/rag_feedback.py` persists 👍/👎 ratings to `rag_feedback.json` in HF Dataset; boosts retrieval scores by ±25% for well/poorly-rated papers.

**Styling** (`utils/styles.py`):
- Theme is stored in `st.session_state.theme_mode` ("dark" default) and synced to `st.query_params["theme"]`
- `apply_styles()` must be called at the top of every page — injects all CSS including dark/light overrides
- `render_navbar()` renders the top nav using `st.page_link()` (SPA, no full reload) and includes the theme toggle button — do not add a separate theme toggle in page files
- CSS strings use Python `.format(**colors)` so curly braces inside CSS must be doubled `{{}}`

**Auth flow** (Admin page):
1. Email input → OTP generated → sent via Telegram bot or SMTP; shown on-screen only as fallback (demo mode)
2. OTP verified → `st.session_state.admin_authenticated = True`
3. `is_admin_authenticated()` from `utils/security.py` guards all admin actions

**Notifications** (`utils/email_service.py`): Telegram bot for OTP + bug report alerts; SMTP for email OTP. GitHub Issues for bug reports. All three are optional; missing config degrades gracefully.

## Key Constraints

- `execute_query()` is a routing shim, not real SQL — do not add complex WHERE clauses or JOINs; add an explicit helper function in `hf_data.py` instead.
- `load_publications()` is cached for 5 min. After any write call `load_publications.clear()` explicitly.
- `render_navbar()` already contains the theme toggle — adding another one in a page causes duplicates.
- All page files need `sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))` since they live in `pages/`.
- HF Dataset uploads are rate-limited; `save_publications()` retries with exponential backoff and conflict detection.
- The CI workflow (`.github/workflows/ci.yml`) runs `pytest tests/` on push to `main` and `claude/**` branches and on PRs to `main`.
