"""
ORC Research Assistant — Paper Analysis & Chat
Includes: structured quick actions, chat, result cache, and session export.
"""

import json
import datetime
import streamlit as st
import pandas as pd
import plotly.express as px
import sys
import os
from html import escape

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pydantic import ValidationError
from utils.security import get_secret, execute_query, log_audit, log_error, RateLimiter
from utils.styles import (
    apply_styles, get_theme, hero_html, section_title_html,
    footer_html, render_navbar, DARK, LIGHT,
    chart_layout, chart_colors, PLOTLY_CONFIG,
)
from utils.ai_schemas import (
    AIRequest, PaperContext, ACTION_PROMPTS, parse_action_response,
    PaperSummary, KeyFindings, Methodology, Implications,
)

apply_styles()
render_navbar()

colors = DARK if get_theme() == "dark" else LIGHT
rate_limiter = RateLimiter()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _card(content: str, border_color: str = "") -> str:
    border = f"border-left:4px solid {border_color};" if border_color else ""
    return (
        f'<div style="background:{colors["surface"]};border-radius:6px;'
        f'padding:1rem 1.25rem;margin-bottom:0.65rem;color:{colors["text"]};'
        f'overflow:hidden;overflow-wrap:break-word;word-wrap:break-word;{border}">'
        f'{content}</div>'
    )


def _tag(text: str) -> str:
    return (
        f'<span style="display:inline-block;background:{colors["surface2"]};'
        f'color:{colors["text"]};border:1px solid {colors["border"]};'
        f'border-radius:4px;padding:0.1rem 0.45rem;font-size:0.8rem;'
        f'margin:0.1rem 0.15rem 0.1rem 0">{escape(text)}</span>'
    )


def _label(text: str):
    st.markdown(
        f'<div style="font-size:0.72rem;font-weight:700;text-transform:uppercase;'
        f'letter-spacing:0.07em;color:{colors["text2"]};margin:0.75rem 0 0.25rem">'
        f'{escape(text)}</div>',
        unsafe_allow_html=True,
    )


# ── Quick chart renderer ───────────────────────────────────────────────────────

def _render_ai_chart(kind: str):
    pubs, _ = execute_query("SELECT * FROM publications ORDER BY publication_year")
    if not pubs:
        st.info("No publication data available. Sync from the Publications page first.")
        return
    df = pd.DataFrame(pubs)
    ccs = chart_colors()

    if kind == "trend" and "publication_year" in df.columns:
        yc = df.groupby("publication_year").size().reset_index(name="count")
        fig = px.bar(yc, x="publication_year", y="count",
                     labels={"publication_year": "Year", "count": "Publications"},
                     color_discrete_sequence=[colors["accent"]])
        fig.update_layout(**chart_layout("Publications by Year"))
        st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)

    elif kind == "citations" and "citation_count" in df.columns:
        df["citation_count"] = pd.to_numeric(df["citation_count"], errors="coerce").fillna(0)
        fig = px.histogram(df, x="citation_count", nbins=20,
                           labels={"citation_count": "Citations", "count": "Papers"},
                           color_discrete_sequence=[colors["accent2"]])
        fig.update_layout(**chart_layout("Citation Distribution"))
        st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)

    elif kind == "journals" and "journal_name" in df.columns:
        jc = df["journal_name"].value_counts().head(8).reset_index()
        jc.columns = ["journal", "count"]
        fig = px.pie(jc, values="count", names="journal",
                     color_discrete_sequence=ccs, hole=0.4)
        fig.update_layout(**chart_layout("Top Journals"))
        st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)

    elif kind == "access" and "open_access" in df.columns:
        df["open_access"] = df["open_access"].astype(str).str.lower().isin({"1", "true", "yes"})
        oa = int(df["open_access"].sum())
        fig = px.pie(values=[oa, len(df) - oa], names=["Open Access", "Subscription"],
                     color_discrete_sequence=[colors["success"], colors["muted"]], hole=0.4)
        fig.update_layout(**chart_layout("Open Access Distribution"))
        st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)

    else:
        st.info("Chart data not available for the current selection.")


def _detect_chart_intent(message: str) -> str | None:
    """Return chart slug if the message is asking for a visualization, else None."""
    msg = message.lower()
    words = set(msg.replace(",", " ").replace(".", " ").split())
    chart_words = {"chart", "graph", "plot", "histogram", "visualize",
                   "visualization", "diagram", "figure", "draw", "show"}
    if not (words & chart_words):
        return None
    if any(w in msg for w in ("year", "trend", "time", "annual", "history", "over")):
        return "trend"
    if any(w in msg for w in ("citation", "cited", "cites", "impact", "h-index")):
        return "citations"
    if any(w in msg for w in ("journal", "venue", "publisher")):
        return "journals"
    if any(w in msg for w in ("open access", "open-access", "access", " oa")):
        return "access"
    return "trend"


def _handle_feedback(msg_idx: int, rating: int) -> None:
    """Save 👍/👎 feedback for the assistant message at msg_idx then rerun."""
    from utils.rag_feedback import record, invalidate_boost_cache
    chat = st.session_state.chat_history

    # Walk backwards to find the user query that preceded this response
    query = ""
    for j in range(msg_idx - 1, -1, -1):
        if chat[j]["role"] == "user":
            query = chat[j]["content"]
            break

    pub_ids = chat[msg_idx].get("rag_pub_ids", [])
    sid     = st.session_state.get("session_token", "anonymous")
    record(query, pub_ids, rating, sid)
    invalidate_boost_cache()
    st.session_state[f"_fb_{msg_idx}"] = rating
    st.rerun()


# ── AI client ─────────────────────────────────────────────────────────────────

def _groq_client():
    api_key = (
        get_secret("AI_API_KEY") or get_secret("GROQ_API_KEY")
        or get_secret("GROQ_API") or get_secret("GROQ_TOKEN")
    )
    if not api_key:
        return None, "AI service not configured"
    try:
        from groq import Groq
        return Groq(api_key=api_key), None
    except ImportError:
        return None, "AI library not available"


def _rate_check(key: str, max_req: int = 20) -> tuple:
    sid = st.session_state.get("session_token", "default")
    allowed, wait = rate_limiter.is_allowed(f"ai_{sid}_{key}", max_req, 60)
    if allowed:
        rate_limiter.record_attempt(f"ai_{sid}_{key}")
    return allowed, wait


def _call_ai(system: str, user: str, json_mode: bool = False,
             temperature: float = 0.5, max_tokens: int = 1800) -> tuple:
    allowed, wait = _rate_check("general")
    if not allowed:
        return None, f"Rate limit exceeded — wait {wait}s"
    client, err = _groq_client()
    if not client:
        return None, err
    model = get_secret("AI_MODEL") or "llama-3.3-70b-versatile"
    kwargs: dict = dict(
        model=model,
        messages=[{"role": "system", "content": system},
                  {"role": "user",   "content": user}],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    try:
        resp = client.chat.completions.create(**kwargs)
        log_audit("ai_request", "ok")
        return resp.choices[0].message.content, None
    except Exception as e:
        log_error("ai_service_error", str(e), page="AI Assistant")
        return None, "AI service temporarily unavailable"


# ── Paper helpers ─────────────────────────────────────────────────────────────

def _paper_context(paper: dict) -> str:
    try:
        ctx = PaperContext.from_dict(paper)
        return (
            f"\n\nCurrently analyzing:\nTitle: {ctx.title}\n"
            f"Journal: {ctx.journal_name}\nYear: {ctx.publication_year or 'N/A'}\n"
            f"Citations: {ctx.citation_count}\nAbstract: {ctx.abstract}\n"
        )
    except Exception:
        return ""


def _paper_cache_key(paper: dict, action: str) -> str:
    paper_id = str(paper.get("id", paper.get("title", "")[:30]))
    return f"{paper_id}__{action}"


def get_ai_response(message: str, paper: dict | None = None,
                    chart_kind: str | None = None) -> tuple:
    try:
        req = AIRequest(message=message)
    except ValidationError as e:
        return None, e.errors()[0]["msg"]
    system = (
        "You are an expert academic research assistant. "
        "Be precise, concise, and professional. "
        "Format answers with clear paragraphs and plain numbered or bulleted lists."
    )

    # ── RAG: inject relevant publications from the database ───────────────────
    try:
        from utils.rag import retrieve, format_context
        all_pubs, _ = execute_query("SELECT * FROM publications")
        if all_pubs:
            retrieved = retrieve(message, all_pubs, top_k=3)
            rag_ctx   = format_context(retrieved)
            if rag_ctx:
                system += rag_ctx
                st.session_state["_rag_retrieved"] = retrieved
        else:
            st.session_state["_rag_retrieved"] = []
    except Exception:
        st.session_state["_rag_retrieved"] = []

    if chart_kind:
        _chart_labels = {
            "trend": "publications by year",
            "citations": "citation count distribution",
            "journals": "top journals breakdown",
            "access": "open access vs subscription ratio",
        }
        system += (
            f"\n\nA visual interactive {_chart_labels.get(chart_kind, 'data chart')} "
            "has been generated and is displayed to the user below your response. "
            "Briefly explain what the chart shows and what key patterns or insights "
            "to look for. Do NOT draw ASCII art, text tables, or any text-based charts."
        )
    if paper:
        system += _paper_context(paper)

    messages = [{"role": "system", "content": system}]
    for m in st.session_state.get("chat_history", [])[-6:]:
        messages.append({"role": m["role"], "content": m["content"]})
    messages.append({"role": "user", "content": req.message})

    allowed, wait = _rate_check("chat")
    if not allowed:
        return None, f"Rate limit exceeded — wait {wait}s"
    client, err = _groq_client()
    if not client:
        return None, err
    try:
        resp = client.chat.completions.create(
            model=get_secret("AI_MODEL") or "llama-3.3-70b-versatile",
            messages=messages, temperature=0.7, max_tokens=1500,
        )
        log_audit("ai_chat", "ok")
        return resp.choices[0].message.content, None
    except Exception:
        return None, "AI service temporarily unavailable"


def get_structured_response(action: str, paper: dict) -> tuple:
    # Return cached result if available
    cache_key = _paper_cache_key(paper, action)
    if cache_key in st.session_state.get("ai_cache", {}):
        cached = st.session_state["ai_cache"][cache_key]
        return cached, None, None

    allowed, wait = _rate_check("structured")
    if not allowed:
        return None, None, f"Rate limit exceeded — wait {wait}s"
    client, err = _groq_client()
    if not client:
        return None, None, err
    json_schema, model_cls = ACTION_PROMPTS[action]
    try:
        PaperContext.from_dict(paper)
    except Exception:
        return None, None, "Invalid paper data"
    system = (
        "You are an expert academic research assistant. "
        "Respond with valid JSON only.\n\n" + json_schema + _paper_context(paper)
    )
    try:
        resp = client.chat.completions.create(
            model=get_secret("AI_MODEL") or "llama-3.3-70b-versatile",
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": "Analyze this paper and return the JSON."}],
            response_format={"type": "json_object"},
            temperature=0.3, max_tokens=1500,
        )
        raw = resp.choices[0].message.content
        validated = parse_action_response(action, raw)
        log_audit("ai_structured", action)
        # Store in cache
        if validated:
            st.session_state["ai_cache"][cache_key] = validated
        return validated, raw, None
    except Exception:
        return None, None, "AI service temporarily unavailable"


# ── Export helpers ────────────────────────────────────────────────────────────

def _result_to_markdown(action: str, result) -> str:
    """Convert a structured result object to plain markdown text."""
    label = {"summarize": "Summary", "findings": "Key Findings",
              "methodology": "Methodology", "implications": "Implications"}.get(action, action.title())
    lines = [f"## {label}", ""]
    if isinstance(result, PaperSummary):
        lines += [result.overview, ""]
        lines += ["**Objectives**"] + [f"- {o}" for o in result.objectives] + [""]
        lines += [f"**Methodology**\n{result.methods}", ""]
        lines += ["**Key Results**"] + [f"- {r}" for r in result.results] + [""]
        lines += [f"**Conclusion**\n{result.conclusion}"]
    elif isinstance(result, KeyFindings):
        for i, f in enumerate(result.findings, 1):
            lines += [f"**Finding {i}:** {f}"]
        lines += ["", f"**Significance:** {result.significance}"]
        if result.limitations:
            lines += ["", "**Limitations**"] + [f"- {l}" for l in result.limitations]
    elif isinstance(result, Methodology):
        lines += [f"**Study Design:** {result.study_design}", ""]
        lines += [f"**Sample:** {result.sample}", ""]
        lines += [f"**Analysis Method:** {result.analysis_method}"]
        if result.tools:
            lines += ["", "**Tools:** " + " · ".join(result.tools)]
    elif isinstance(result, Implications):
        if result.clinical:
            lines += ["**Clinical**"] + [f"- {i}" for i in result.clinical] + [""]
        if result.research:
            lines += ["**Research**"] + [f"- {i}" for i in result.research] + [""]
        if result.policy:
            lines += ["**Policy**"] + [f"- {i}" for i in result.policy] + [""]
        lines += ["", f"**Summary:** {result.summary}"]
    return "\n".join(lines)


def _build_export(paper: dict | None, ai_cache: dict, chat_history: list) -> str:
    lines = ["# ORC Research Assistant — Session Export", ""]
    lines += [f"*Exported: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}*", ""]

    if paper:
        lines += [
            "---", "## Paper",
            f"**Title:** {paper.get('title', '')}",
            f"**Journal:** {paper.get('journal_name', '')}  "
            f"**Year:** {paper.get('publication_year', '')}  "
            f"**Citations:** {paper.get('citation_count', 0):,}",
            "",
        ]
        # Include any cached analyses for this paper
        pid = str(paper.get("id", paper.get("title", "")[:30]))
        for action in ("summarize", "findings", "methodology", "implications"):
            key = f"{pid}__{action}"
            if key in ai_cache:
                lines += [_result_to_markdown(action, ai_cache[key]), ""]

    if chat_history:
        lines += ["---", "## Chat History", ""]
        for msg in chat_history:
            role = "**You**" if msg["role"] == "user" else "**AI Assistant**"
            lines += [f"{role}", msg["content"], ""]

    return "\n".join(lines)


# ── Structured result renderers ───────────────────────────────────────────────

def _bullet(items: list):
    for item in items:
        st.markdown(f"- {item}")


def render_structured(result):
    if isinstance(result, PaperSummary):
        st.markdown(
            _card(
                f'<div style="font-size:0.9rem;line-height:1.7;color:{colors["text"]}">'
                f'{escape(result.overview)}</div>',
                border_color=colors["accent"],
            ),
            unsafe_allow_html=True,
        )
        c1, c2 = st.columns(2)
        with c1:
            _label("Objectives")
            _bullet(result.objectives)
            _label("Methodology")
            st.markdown(
                f'<div style="font-size:0.87rem;color:{colors["text"]};line-height:1.65">'
                f'{escape(result.methods)}</div>',
                unsafe_allow_html=True,
            )
        with c2:
            _label("Key Results")
            _bullet(result.results)
            _label("Conclusion")
            st.markdown(
                _card(
                    f'<div style="font-size:0.87rem;color:{colors["text"]};line-height:1.65">'
                    f'{escape(result.conclusion)}</div>',
                    border_color=colors["success"],
                ),
                unsafe_allow_html=True,
            )

    elif isinstance(result, KeyFindings):
        for i, f in enumerate(result.findings, 1):
            st.markdown(
                _card(
                    f'<div style="font-size:0.8rem;font-weight:700;color:{colors["text2"]};'
                    f'text-transform:uppercase;letter-spacing:0.05em;margin-bottom:0.2rem">'
                    f'Finding {i}</div>'
                    f'<div style="font-size:0.9rem;color:{colors["text"]};line-height:1.65">'
                    f'{escape(f)}</div>',
                ),
                unsafe_allow_html=True,
            )
        st.markdown(
            _card(
                f'<div style="font-size:0.8rem;font-weight:700;color:{colors["text2"]};'
                f'text-transform:uppercase;letter-spacing:0.05em;margin-bottom:0.2rem">'
                f'Significance</div>'
                f'<div style="font-size:0.9rem;color:{colors["text"]};line-height:1.65">'
                f'{escape(result.significance)}</div>',
                border_color=colors["accent"],
            ),
            unsafe_allow_html=True,
        )
        if result.limitations:
            with st.expander("⚠️ Limitations"):
                _bullet(result.limitations)

    elif isinstance(result, Methodology):
        c1, c2 = st.columns(2)
        with c1:
            _label("Study Design")
            st.markdown(
                f'<div style="font-size:0.88rem;color:{colors["text"]};line-height:1.65">'
                f'{escape(result.study_design)}</div>',
                unsafe_allow_html=True,
            )
            _label("Sample")
            st.markdown(
                f'<div style="font-size:0.88rem;color:{colors["text"]};line-height:1.65">'
                f'{escape(result.sample)}</div>',
                unsafe_allow_html=True,
            )
        with c2:
            _label("Analysis Method")
            st.markdown(
                f'<div style="font-size:0.88rem;color:{colors["text"]};line-height:1.65">'
                f'{escape(result.analysis_method)}</div>',
                unsafe_allow_html=True,
            )
            if result.tools:
                _label("Tools & Software")
                st.markdown(
                    f'<div style="margin-top:0.15rem">'
                    + " ".join(_tag(t) for t in result.tools)
                    + '</div>',
                    unsafe_allow_html=True,
                )

    elif isinstance(result, Implications):
        t1, t2, t3 = st.tabs(["🏥 Clinical", "🔬 Research", "📋 Policy"])
        with t1:
            _bullet(result.clinical) if result.clinical else st.caption("None identified")
        with t2:
            _bullet(result.research) if result.research else st.caption("None identified")
        with t3:
            _bullet(result.policy) if result.policy else st.caption("None identified")
        st.markdown(
            _card(
                f'<div style="font-size:0.9rem;color:{colors["text"]};line-height:1.65">'
                f'{escape(result.summary)}</div>',
                border_color=colors["accent2"],
            ),
            unsafe_allow_html=True,
        )


# ── Session state ─────────────────────────────────────────────────────────────

for key, val in [
    ("chat_history", []),
    ("pending_action", None),
    ("ai_cache", {}),
    ("last_action_label", ""),
    ("last_action_result", None),
    ("ai_active_chart", None),
    ("_rag_retrieved", []),
    ("_rag_index_cache", {}),
]:
    if key not in st.session_state:
        st.session_state[key] = val


# ── Page ──────────────────────────────────────────────────────────────────────

st.markdown(
    hero_html("🔬 AI Research Assistant",
              "Structured analysis and Q&A — results are remembered within your session"),
    unsafe_allow_html=True,
)

api_key = (
    get_secret("AI_API_KEY") or get_secret("GROQ_API_KEY")
    or get_secret("GROQ_API") or get_secret("GROQ_TOKEN")
)
_ai_available = bool(api_key)
if not _ai_available:
    st.warning(
        "⚠️ AI service not configured — add an **AI_API_KEY** or **GROQ_API_KEY** secret. "
        "Charts and export still work below."
    )

# RAG + feedback status banner
try:
    from utils.rag import index_kind
    from utils.rag_feedback import stats as _fb_stats
    from utils.security import execute_query as _eq
    _rag_pubs, _ = _eq("SELECT * FROM publications")
    _rag_count   = len(_rag_pubs) if _rag_pubs else 0
    if _rag_count:
        _kind = index_kind(_rag_pubs)
        _kind_label = {
            "neural": "🧠 Neural",
            "tfidf":  "🔤 TF-IDF fallback",
            "empty":  "⚠️ Unavailable",
        }.get(_kind, _kind)
        _fb  = _fb_stats()
        _fb_part = (
            f" · 📊 {_fb['total']} ratings ({_fb['ratio']}% helpful)"
            if _fb["total"] > 0 else ""
        )
        st.markdown(
            f'<div style="background:{colors["surface"]};border-radius:6px;'
            f'padding:0.5rem 1rem;margin-bottom:0.75rem;font-size:0.8rem;'
            f'border-left:3px solid {colors["success"]};color:{colors["text2"]}">'
            f'📚 RAG active — {_rag_count} papers indexed · {_kind_label}{_fb_part}'
            f'</div>',
            unsafe_allow_html=True,
        )
except Exception:
    pass


# ── Paper context card ────────────────────────────────────────────────────────

paper = st.session_state.get("selected_paper")
if paper:
    citations = paper.get("citation_count", 0) or 0
    c1, c2 = st.columns([8, 1])
    with c1:
        st.markdown(
            _card(
                f'<div style="font-weight:600;font-size:0.95rem;color:{colors["text"]}">'
                f'{escape(str(paper.get("title", "Unknown")))}</div>'
                f'<div style="font-size:0.8rem;color:{colors["text2"]};margin-top:0.25rem">'
                f'📰 {escape(str(paper.get("journal_name", "")))} &nbsp;·&nbsp; '
                f'{paper.get("publication_year", "")} &nbsp;·&nbsp; '
                f'{citations:,} citations</div>',
                border_color=colors["accent"],
            ),
            unsafe_allow_html=True,
        )
    with c2:
        st.write("")
        if st.button("✕ Clear", use_container_width=True):
            st.session_state.selected_paper = None
            st.rerun()
else:
    st.markdown(
        f'<div style="background:{colors["surface"]};border-radius:6px;'
        f'padding:0.85rem 1.1rem;margin-bottom:0.75rem;'
        f'border:1px dashed {colors["border"]};color:{colors["text2"]};font-size:0.87rem">'
        f'💡 Go to <b style="color:{colors["text"]}">Publications</b> and click '
        f'<b style="color:{colors["text"]}">Analyze</b> on any paper to set context.</div>',
        unsafe_allow_html=True,
    )


# ── Quick Actions ─────────────────────────────────────────────────────────────

st.markdown(section_title_html("Quick Actions"), unsafe_allow_html=True)

# Show cache status badge when results are already saved
if paper:
    pid = str(paper.get("id", paper.get("title", "")[:30]))
    cached_actions = [a for a in ("summarize", "findings", "methodology", "implications")
                      if f"{pid}__{a}" in st.session_state["ai_cache"]]
    if cached_actions:
        badge_labels = {"summarize": "Summary", "findings": "Findings",
                        "methodology": "Methodology", "implications": "Implications"}
        tags = " ".join(_tag(badge_labels[a]) for a in cached_actions)
        st.markdown(
            f'<div style="font-size:0.78rem;color:{colors["text2"]};margin-bottom:0.5rem">'
            f'✓ Saved in session: {tags}</div>',
            unsafe_allow_html=True,
        )

qa1, qa2, qa3, qa4 = st.columns(4)
for col, label, action in [
    (qa1, "📝 Summarize",    "summarize"),
    (qa2, "🔍 Key Findings", "findings"),
    (qa3, "📊 Methodology",  "methodology"),
    (qa4, "🔗 Implications", "implications"),
]:
    with col:
        if st.button(label, use_container_width=True, disabled=not paper or not _ai_available):
            st.session_state.pending_action = action

if st.session_state.pending_action and paper:
    action = st.session_state.pending_action
    st.session_state.pending_action = None
    labels = {
        "summarize":    "📝 Summary",
        "findings":     "🔍 Key Findings",
        "methodology":  "📊 Methodology",
        "implications": "🔗 Implications",
    }
    label = labels.get(action, action.title())
    st.markdown(section_title_html(label), unsafe_allow_html=True)

    # Check if result is already cached
    cache_key = _paper_cache_key(paper, action)
    is_cached = cache_key in st.session_state["ai_cache"]

    if is_cached:
        st.caption("✓ Loaded from session cache — no API call needed")

    with st.spinner("Analyzing…" if not is_cached else ""):
        validated, raw, error = get_structured_response(action, paper)

    st.session_state.last_action_label = label
    st.session_state.last_action_result = validated

    if error:
        st.warning(f"⚠️ {error}")
    elif validated:
        render_structured(validated)
    elif raw:
        st.markdown(
            _card(
                f'<div style="font-size:0.88rem;line-height:1.7;color:{colors["text"]}">'
                f'{escape(raw)}</div>'
            ),
            unsafe_allow_html=True,
        )


# ── Quick Charts ─────────────────────────────────────────────────────────────

st.markdown(section_title_html("Quick Charts"), unsafe_allow_html=True)

qc1, qc2, qc3, qc4 = st.columns(4)
for _col, _lbl, _knd in [
    (qc1, "📅 By Year",     "trend"),
    (qc2, "📈 Citations",   "citations"),
    (qc3, "📰 Journals",    "journals"),
    (qc4, "🔓 Open Access", "access"),
]:
    with _col:
        if st.button(_lbl, key=f"qc_{_knd}", use_container_width=True):
            if st.session_state["ai_active_chart"] == _knd:
                st.session_state["ai_active_chart"] = None
            else:
                st.session_state["ai_active_chart"] = _knd

if st.session_state["ai_active_chart"]:
    _render_ai_chart(st.session_state["ai_active_chart"])


# ── Chat ──────────────────────────────────────────────────────────────────────

st.markdown(section_title_html("Chat"), unsafe_allow_html=True)

# Row: message count + clear + export
ctrl1, ctrl2, ctrl3 = st.columns([5, 1, 1])
with ctrl1:
    if st.session_state.chat_history:
        st.markdown(
            f'<div style="font-size:0.78rem;color:{colors["text2"]};padding-top:0.4rem">'
            f'{len(st.session_state.chat_history)} messages in this session</div>',
            unsafe_allow_html=True,
        )
with ctrl2:
    if st.session_state.chat_history and st.button("🗑️ Clear", use_container_width=True):
        st.session_state.chat_history = []
        st.rerun()
with ctrl3:
    has_content = bool(st.session_state.chat_history or st.session_state.get("ai_cache"))
    if has_content:
        try:
            from utils.rag_feedback import flush_now as _flush_fb
            _flush_fb()
        except Exception:
            pass
        export_md = _build_export(
            paper,
            st.session_state.get("ai_cache", {}),
            st.session_state.chat_history,
        )
        st.download_button(
            label="📥 Save",
            data=export_md.encode("utf-8"),
            file_name=f"research_session_{datetime.datetime.now().strftime('%Y%m%d_%H%M')}.md",
            mime="text/markdown",
            use_container_width=True,
            help="Download chat + all AI analyses as a Markdown file",
        )

for _i, msg in enumerate(st.session_state.chat_history):
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("chart_kind"):
            _render_ai_chart(msg["chart_kind"])
        if msg.get("rag_count") and msg["role"] == "assistant":
            st.caption(f"📚 {msg['rag_count']} paper(s) retrieved from your database")

    # ── Feedback buttons (assistant messages only) ────────────────────────────
    if msg["role"] == "assistant" and _ai_available:
        _fb_key = f"_fb_{_i}"
        _rating = st.session_state.get(_fb_key)
        if _rating is None:
            _fc1, _fc2, _fc3 = st.columns([1, 1, 10])
            with _fc1:
                if st.button("👍", key=f"fbup_{_i}", help="Helpful"):
                    _handle_feedback(_i, 1)
            with _fc2:
                if st.button("👎", key=f"fbdn_{_i}", help="Not helpful"):
                    _handle_feedback(_i, -1)
        else:
            st.caption("✓ Helpful" if _rating == 1 else "✓ Feedback noted")

if user_input := st.chat_input("Ask about your research papers…", disabled=not _ai_available):
    try:
        req = AIRequest(message=user_input)
    except ValidationError as e:
        st.error(f"❌ {e.errors()[0]['msg']}")
        st.stop()

    chart_kind = _detect_chart_intent(req.message)

    st.session_state.chat_history.append({"role": "user", "content": req.message})
    with st.chat_message("user"):
        st.markdown(req.message)
    with st.chat_message("assistant"):
        with st.spinner("Thinking…"):
            response, error = get_ai_response(req.message, paper, chart_kind)
        if response:
            st.markdown(response)
            if chart_kind:
                _render_ai_chart(chart_kind)
            # RAG indicator
            retrieved = st.session_state.get("_rag_retrieved", [])
            if retrieved:
                titles = " · ".join(
                    f'"{p.get("title", "")[:45]}…"' if len(p.get("title", "")) > 45
                    else f'"{p.get("title", "")}"'
                    for p in retrieved
                )
                st.caption(f"📚 Context from your database ({len(retrieved)} papers): {titles}")
            ai_msg: dict = {"role": "assistant", "content": response}
            if chart_kind:
                ai_msg["chart_kind"] = chart_kind
            if retrieved:
                ai_msg["rag_count"]   = len(retrieved)
                ai_msg["rag_pub_ids"] = [p.get("id", "") for p in retrieved]
            st.session_state.chat_history.append(ai_msg)
        else:
            st.warning(f"⚠️ {error}")
    st.rerun()


# ── Footer ────────────────────────────────────────────────────────────────────
st.divider()
st.markdown(footer_html(), unsafe_allow_html=True)
