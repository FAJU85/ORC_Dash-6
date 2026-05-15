"""
RAG Phase 1 — Semantic retrieval from the publication database.

Architecture:
  1. Split each publication into semantic chunks (title_meta + abstract_body).
  2. Embed all chunks with sentence-transformers.
  3. Cache the index in st.session_state; rebuild only when publication
     count changes.
  4. At chat time: embed the query, compute cosine similarity over chunks,
     deduplicate by pub_id, and return the top-k unique publications.
  5. Inject the retrieved papers into the AI system prompt.

Falls back to TF-IDF keyword search (sklearn, already a dependency) when
the sentence-transformers model is unavailable.
"""

import numpy as np
import streamlit as st
from typing import Any

try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    SentenceTransformer = None  # type: ignore

# ── Model loading ─────────────────────────────────────────────────────────────

@st.cache_resource(show_spinner=False)
def _load_neural_model() -> "SentenceTransformer | None":
    """Load SentenceTransformer once per server process (cached globally)."""
    if SentenceTransformer is None:
        st.warning(
            "RAG neural model unavailable: sentence-transformers not installed."
            " Falling back to TF-IDF."
        )
        return None
    try:
        model = SentenceTransformer("all-MiniLM-L6-v2")
        return model
    except Exception as e:
        st.warning(
            f"RAG neural model unavailable: {type(e).__name__}. Falling back to TF-IDF."
        )
        return None


# ── Chunking ──────────────────────────────────────────────────────────────────

def _chunk_pub(pub: dict) -> list[dict]:
    """
    Split a single publication into semantic chunks.

    Returns a list of chunk dicts, each with:
      - pub_id:  the publication's id field
      - section: "title_meta" | "abstract_body"
      - text:    the chunk text string

    Every publication always produces at least the title_meta chunk.
    The abstract_body chunk is only added when the abstract is longer than
    50 characters so we don't embed meaningless empty strings.
    """
    pub_id  = pub.get("id", "")
    title   = (pub.get("title")            or "").strip()
    journal = (pub.get("journal_name")     or "").strip()
    year    = str(pub.get("publication_year") or "").strip()
    authors = pub.get("authors") or []

    # Build a compact authors string (last names only, max 3)
    if isinstance(authors, list):
        author_names = [
            (a.get("family") or a.get("name") or "").strip()
            for a in authors
            if isinstance(a, dict)
        ]
        author_names = [n for n in author_names if n]
    else:
        author_names = []
    authors_str = ", ".join(author_names[:3])
    if len(author_names) > 3:
        authors_str += " et al."

    # Chunk 1 — always present
    title_meta_text = f"{title} | {journal} {year} | {authors_str}".strip()
    chunks = [
        {"pub_id": pub_id, "section": "title_meta", "text": title_meta_text}
    ]

    # Chunk 2 — abstract body (only when there is meaningful content)
    abstract = (pub.get("abstract") or "").strip()
    if len(abstract) > 50:
        chunks.append(
            {"pub_id": pub_id, "section": "abstract_body", "text": abstract[:800]}
        )

    return chunks


# ── Index building ────────────────────────────────────────────────────────────

def _collect_chunks(publications: list[dict]) -> tuple[list[dict], list[str]]:
    """
    Build the flat list of chunks and their text strings from all publications.

    Returns:
        chunks: list of chunk dicts (pub_id, section, text)
        texts:  list of text strings, parallel to chunks
    """
    chunks: list[dict] = []
    for pub in publications:
        for chunk in _chunk_pub(pub):
            if chunk["text"]:
                chunks.append(chunk)
    texts = [c["text"] for c in chunks]
    return chunks, texts


def _build_neural_index(chunks: list[dict], texts: list[str]) -> "np.ndarray | None":
    model = _load_neural_model()
    if not model:
        return None
    emb = model.encode(
        texts,
        normalize_embeddings=True,
        show_progress_bar=False,
        batch_size=32,
    )
    return emb.astype("float32")


def _build_tfidf_index(texts: list[str]) -> "dict[str, Any] | None":
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        vec = TfidfVectorizer(
            max_features=8000, stop_words="english", ngram_range=(1, 2)
        )
        mat = vec.fit_transform(texts)
        return {"vec": vec, "mat": mat}
    except Exception:
        return None


def _build_index(publications: list[dict]) -> dict[str, Any]:
    """Build the best available chunk index from the publication list."""
    chunks, texts = _collect_chunks(publications)
    if not texts:
        return {"kind": "empty", "chunks": [], "pubs": {}}

    # Build a pub_id → pub dict for fast lookup during retrieval
    pub_lookup = {pub.get("id", ""): pub for pub in publications}

    # Try neural first
    emb = _build_neural_index(chunks, texts)
    if emb is not None:
        return {
            "kind": "neural",
            "chunks": chunks,
            "embeddings": emb,
            "pub_lookup": pub_lookup,
        }

    # TF-IDF fallback
    idx = _build_tfidf_index(texts)
    if idx:
        return {
            "kind": "tfidf",
            "chunks": chunks,
            "pub_lookup": pub_lookup,
            **idx,
        }

    return {"kind": "empty", "chunks": [], "pubs": {}}


def _get_cached_index(publications: list[dict]) -> dict[str, Any]:
    """Return a cached index, rebuilding when publications change."""
    n = len(publications)
    # count + first/last pub IDs + "chunked" tag = cheap content fingerprint
    fingerprint = (
        n,
        publications[0].get("id", "") if n > 0 else "",
        publications[-1].get("id", "") if n > 0 else "",
        "chunked",
    )
    cache = st.session_state.get("_rag_index_cache", {})
    if cache.get("fingerprint") == fingerprint and "index" in cache:
        return cache["index"]
    index = _build_index(publications)
    st.session_state["_rag_index_cache"] = {"fingerprint": fingerprint, "index": index}
    return index


# ── Retrieval ─────────────────────────────────────────────────────────────────

def retrieve(
    query: str,
    publications: list[dict],
    top_k: int = 3,
    feedback_scores: "dict | None" = None,
) -> list[dict]:
    """
    Return the top_k publications most semantically relevant to *query*.

    Internally operates on per-chunk embeddings, then deduplicates by pub_id
    so each publication appears at most once in the result.  The chunk with
    the highest similarity score represents the publication.

    feedback_scores: optional {pub_id: boost_factor} dict that multiplies
    each chunk's raw score before ranking (supports the rag_feedback loop).

    Returns a list of publication dicts (same type as the input list).
    Returns an empty list if RAG is unavailable or no publications exist.
    """
    if not query or not publications:
        return []

    index = _get_cached_index(publications)
    kind = index.get("kind", "empty")
    if kind == "empty":
        return []

    chunks: list[dict] = index.get("chunks", [])
    pub_lookup: dict = index.get("pub_lookup", {})
    if not chunks:
        return []

    # Load feedback boost scores (non-critical — silently ignored on error)
    boosts: dict = {}
    if feedback_scores is not None:
        boosts = feedback_scores
    else:
        try:
            from utils.rag_feedback import boost_scores
            boosts = boost_scores(list(pub_lookup.values()))
        except Exception:
            pass

    def _score_with_boosts(raw_scores: np.ndarray) -> np.ndarray:
        if not boosts:
            return raw_scores
        out = raw_scores.copy()
        for i, chunk in enumerate(chunks):
            pid = chunk.get("pub_id", "")
            if pid in boosts:
                out[i] *= boosts[pid]
        return out

    # Compute raw similarity scores over all chunks
    if kind == "neural":
        model = _load_neural_model()
        if not model:
            return []
        q_emb = model.encode([query], normalize_embeddings=True).astype("float32")
        raw = (index["embeddings"] @ q_emb.T).squeeze()
        if raw.ndim == 0:
            raw = np.array([raw.item()])
    elif kind == "tfidf":
        from sklearn.metrics.pairwise import cosine_similarity
        q_vec = index["vec"].transform([query])
        raw = cosine_similarity(index["mat"], q_vec).squeeze()
    else:
        return []

    scores = _score_with_boosts(raw)

    # Get top_k * 3 chunk candidates, then deduplicate by pub_id
    candidate_count = min(top_k * 3, len(chunks))
    top_chunk_idx = np.argsort(scores)[::-1][:candidate_count].tolist()

    seen_pub_ids: set = set()
    best_chunks: list[tuple[float, dict]] = []  # (score, chunk)
    for idx in top_chunk_idx:
        chunk = chunks[idx]
        pid = chunk.get("pub_id", "")
        if pid not in seen_pub_ids:
            seen_pub_ids.add(pid)
            best_chunks.append((float(scores[idx]), chunk))

    # Sort by score descending and take top_k unique pubs
    best_chunks.sort(key=lambda x: x[0], reverse=True)
    best_chunks = best_chunks[:top_k]

    # Resolve pub dicts and attach the winning section label for format_context
    result: list[dict] = []
    for score, chunk in best_chunks:
        pid = chunk.get("pub_id", "")
        pub = pub_lookup.get(pid)
        if pub is None:
            continue
        # Attach retrieval metadata without mutating the original dict
        enriched = dict(pub)
        enriched["_rag_section"] = chunk.get("section", "")
        enriched["_rag_score"]   = score
        result.append(enriched)

    return result


# ── Context formatting ────────────────────────────────────────────────────────

def format_context(retrieved: list[dict]) -> str:
    """Format retrieved publications as a context block for the AI system prompt."""
    if not retrieved:
        return ""
    lines = [
        "\n\n--- RELEVANT PUBLICATIONS FROM THE RESEARCHER'S DATABASE ---",
    ]
    for i, pub in enumerate(retrieved, 1):
        title     = pub.get("title")            or "Untitled"
        journal   = pub.get("journal_name")     or ""
        year      = pub.get("publication_year") or ""
        citations = pub.get("citation_count")   or 0
        abstract  = (pub.get("abstract") or "").strip()
        snippet   = abstract[:400] + ("…" if len(abstract) > 400 else "")
        section   = pub.get("_rag_section", "")

        section_label = {
            "title_meta":    "Title / metadata",
            "abstract_body": "Abstract",
        }.get(section, section.replace("_", " ").title() if section else "")

        lines.append(f"\n[{i}] \"{title}\" ({year}) — {journal}")
        lines.append(f"    Citations: {citations:,}")
        if section_label:
            lines.append(f"    Relevance: {section_label}")
        if snippet:
            lines.append(f"    {snippet}")
    lines.append("\n--- Ground your answers in the above publications when relevant. ---")
    return "\n".join(lines)


# ── Index kind helper (for UI display) ───────────────────────────────────────

def index_kind(publications: list[dict]) -> str:
    """Return 'neural', 'tfidf', or 'empty' — useful for status display."""
    index = _get_cached_index(publications)
    return index.get("kind", "empty")
