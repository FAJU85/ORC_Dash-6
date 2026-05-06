"""
RAG Phase 2 — Feedback loop.

Flow:
  1. User clicks 👍 / 👎 on any AI response.
  2. record() buffers the entry {query, pub_ids, rating, timestamp}.
  3. Buffer is flushed to HF Dataset (rag_feedback.json) after every
     5 ratings, or on demand via flush_now().
  4. boost_scores() reads the persisted history and returns a per-paper
     multiplier ∈ [0.75, 1.25] that is applied to cosine similarity
     scores inside rag.retrieve(), so well-rated papers rank higher.
"""

import streamlit as st
from datetime import datetime
from collections import defaultdict

FEEDBACK_FILE = "rag_feedback.json"
_MAX_STORED   = 2000          # keep only the most recent N entries on disk
_FLUSH_AT     = 5             # buffer size before auto-flush


# ── Persistence helpers ───────────────────────────────────────────────────────

def _load_raw() -> list:
    """Download rag_feedback.json from HF Dataset. Returns [] on any error."""
    try:
        from utils.hf_data import _hf_download_json
        data, _ = _hf_download_json(FEEDBACK_FILE)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _persist(entries: list) -> None:
    """Merge *entries* into the stored file and trim to _MAX_STORED."""
    try:
        from utils.hf_data import _hf_download_json, _hf_upload_json
        existing, _ = _hf_download_json(FEEDBACK_FILE)
        if not isinstance(existing, list):
            existing = []
        existing.extend(entries)
        if len(existing) > _MAX_STORED:
            existing = existing[-_MAX_STORED:]
        _hf_upload_json(FEEDBACK_FILE, existing, "Append RAG feedback")
    except Exception:
        pass


# ── Public API ────────────────────────────────────────────────────────────────

def record(query: str, pub_ids: list, rating: int,
           session_id: str = "") -> None:
    """
    Buffer one feedback entry.
    rating: +1 = helpful, -1 = not helpful.
    Auto-flushes to HF Dataset when the buffer hits _FLUSH_AT entries.
    """
    entry = {
        "query":      query[:300],
        "pub_ids":    pub_ids[:10],
        "rating":     int(rating),
        "session_id": session_id[:64],
        "ts":         datetime.now().isoformat(),
    }
    buf = st.session_state.setdefault("_fb_buffer", [])
    buf.append(entry)
    if len(buf) >= _FLUSH_AT:
        _persist(buf.copy())
        st.session_state["_fb_buffer"] = []
        invalidate_boost_cache()


def flush_now() -> None:
    """Force-flush all buffered entries — call on export or page close."""
    buf = st.session_state.get("_fb_buffer", [])
    if buf:
        _persist(buf.copy())
        st.session_state["_fb_buffer"] = []
        invalidate_boost_cache()


def boost_scores(publications: list) -> dict:
    """
    Return {pub_id: multiplier} where multiplier ∈ [0.75, 1.25].
    Papers appearing in positively-rated responses get multiplier > 1.0;
    those in negatively-rated responses get multiplier < 1.0.
    Result is cached in session_state until invalidated.
    """
    cached = st.session_state.get("_fb_boost_cache")
    if cached is not None:
        return cached

    all_fb = _load_raw() + st.session_state.get("_fb_buffer", [])
    if not all_fb:
        st.session_state["_fb_boost_cache"] = {}
        return {}

    totals: dict = defaultdict(float)
    counts: dict = defaultdict(int)
    for entry in all_fb:
        r = entry.get("rating", 0)
        for pid in entry.get("pub_ids", []):
            totals[pid] += r
            counts[pid] += 1

    scores = {
        pid: round(1.0 + (totals[pid] / counts[pid]) * 0.25, 4)
        for pid in totals
    }
    st.session_state["_fb_boost_cache"] = scores
    return scores


def invalidate_boost_cache() -> None:
    """Drop the cached boost scores so the next retrieval recomputes them."""
    st.session_state.pop("_fb_boost_cache", None)


def stats() -> dict:
    """Return summary statistics for display in the UI."""
    all_fb  = _load_raw() + st.session_state.get("_fb_buffer", [])
    total   = len(all_fb)
    pos     = sum(1 for f in all_fb if f.get("rating", 0) > 0)
    neg     = sum(1 for f in all_fb if f.get("rating", 0) < 0)
    ratio   = round(pos / total * 100) if total else 0

    # Top boosted paper IDs (for informational display)
    bs      = boost_scores([])   # pass empty list — uses cached scores
    top     = sorted(bs.items(), key=lambda x: x[1], reverse=True)[:3]

    return {
        "total":     total,
        "positive":  pos,
        "negative":  neg,
        "ratio":     ratio,
        "top_pubs":  [pid for pid, _ in top],
    }
