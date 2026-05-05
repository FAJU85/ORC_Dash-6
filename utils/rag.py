"""
RAG Phase 1 — Semantic retrieval from the publication database.

Architecture:
  1. Embed all publication titles + abstracts with sentence-transformers.
  2. Cache the index in st.session_state; rebuild only when publication
     count changes.
  3. At chat time: embed the query, compute cosine similarity, return top-k.
  4. Inject the retrieved papers into the AI system prompt.

Falls back to TF-IDF keyword search (sklearn, already a dependency) when
the sentence-transformers model is unavailable.
"""

import numpy as np
import streamlit as st


# ── Model loading ─────────────────────────────────────────────────────────────

@st.cache_resource(show_spinner=False)
def _load_neural_model():
    """Load SentenceTransformer once per server process (cached globally)."""
    try:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer("all-MiniLM-L6-v2")
        return model
    except Exception:
        return None


# ── Index building ────────────────────────────────────────────────────────────

def _texts_from_pubs(publications: list) -> tuple[list[str], list[dict]]:
    """Extract embeddable text strings and the matching publication records."""
    texts, valid = [], []
    for pub in publications:
        title    = (pub.get("title")    or "").strip()
        abstract = (pub.get("abstract") or "").strip()
        text = f"{title}. {abstract}"[:800].strip()
        if len(text) > 15:
            texts.append(text)
            valid.append(pub)
    return texts, valid


def _build_neural_index(texts: list) -> np.ndarray | None:
    model = _load_neural_model()
    if not model:
        return None
    emb = model.encode(
        texts, normalize_embeddings=True,
        show_progress_bar=False, batch_size=32,
    )
    return emb.astype("float32")


def _build_tfidf_index(texts: list) -> dict | None:
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        vec = TfidfVectorizer(max_features=8000, stop_words="english", ngram_range=(1, 2))
        mat = vec.fit_transform(texts)
        return {"vec": vec, "mat": mat}
    except Exception:
        return None


def _build_index(publications: list) -> dict:
    """Build the best available index from the publication list."""
    texts, valid = _texts_from_pubs(publications)
    if not texts:
        return {"kind": "empty", "pubs": []}

    # Try neural first
    emb = _build_neural_index(texts)
    if emb is not None:
        return {"kind": "neural", "pubs": valid, "embeddings": emb}

    # TF-IDF fallback
    idx = _build_tfidf_index(texts)
    if idx:
        return {"kind": "tfidf", "pubs": valid, **idx}

    return {"kind": "empty", "pubs": []}


def _get_cached_index(publications: list) -> dict:
    """Return a cached index, rebuilding only when publication count changes."""
    cache = st.session_state.get("_rag_index_cache", {})
    if cache.get("count") == len(publications) and "index" in cache:
        return cache["index"]
    index = _build_index(publications)
    st.session_state["_rag_index_cache"] = {"count": len(publications), "index": index}
    return index


# ── Retrieval ─────────────────────────────────────────────────────────────────

def retrieve(query: str, publications: list, top_k: int = 3) -> list[dict]:
    """
    Return the top_k publications most semantically relevant to *query*.
    Returns an empty list if RAG is unavailable or no publications exist.
    """
    if not query or not publications:
        return []

    index = _get_cached_index(publications)
    kind  = index.get("kind", "empty")
    pubs  = index.get("pubs", [])
    if kind == "empty" or not pubs:
        return []

    k = min(top_k, len(pubs))

    if kind == "neural":
        model = _load_neural_model()
        if not model:
            return []
        q_emb  = model.encode([query], normalize_embeddings=True).astype("float32")
        scores = (index["embeddings"] @ q_emb.T).squeeze()
        if scores.ndim == 0:
            return [pubs[0]]
        top_idx = np.argsort(scores)[::-1][:k].tolist()
        return [pubs[i] for i in top_idx]

    if kind == "tfidf":
        from sklearn.metrics.pairwise import cosine_similarity
        q_vec  = index["vec"].transform([query])
        scores = cosine_similarity(index["mat"], q_vec).squeeze()
        top_idx = np.argsort(scores)[::-1][:k].tolist()
        return [pubs[i] for i in top_idx]

    return []


# ── Context formatting ────────────────────────────────────────────────────────

def format_context(retrieved: list[dict]) -> str:
    """Format retrieved publications as a context block for the AI system prompt."""
    if not retrieved:
        return ""
    lines = [
        "\n\n--- RELEVANT PUBLICATIONS FROM THE RESEARCHER'S DATABASE ---",
    ]
    for i, pub in enumerate(retrieved, 1):
        title    = pub.get("title")           or "Untitled"
        journal  = pub.get("journal_name")    or ""
        year     = pub.get("publication_year") or ""
        citations = pub.get("citation_count") or 0
        abstract = (pub.get("abstract") or "")
        snippet  = abstract[:400] + ("…" if len(abstract) > 400 else "")
        lines.append(f"\n[{i}] {title}")
        lines.append(f"    {journal} · {year} · {citations:,} citations")
        if snippet:
            lines.append(f"    {snippet}")
    lines.append("\n--- Ground your answers in the above publications when relevant. ---")
    return "\n".join(lines)


# ── Index kind helper (for UI display) ───────────────────────────────────────

def index_kind(publications: list) -> str:
    """Return 'neural', 'tfidf', or 'empty' — useful for status display."""
    index = _get_cached_index(publications)
    return index.get("kind", "empty")
