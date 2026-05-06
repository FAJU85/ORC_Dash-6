"""
ORC Research Assistant — Paper Analysis & Chat
Includes: structured quick actions, chat, result cache, and session export.
"""

import json
import datetime
import streamlit as st
import sys
import os
import html # Using module for escape

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pydantic import ValidationError
from utils.ai_schemas import (
    AIRequest, PaperContext, ACTION_PROMPTS, parse_action_response,
    PaperSummary, KeyFindings, Methodology, Implications,
)
from utils.security import get_secret, execute_query, log_audit, log_error, RateLimiter
from utils.styles import (
    apply_styles, get_theme, hero_html, section_title_html,
    footer_html, render_navbar, DARK, LIGHT,
)
from utils.prompt_builder import build_system_prompt
from utils.hf_data import load_ai_settings
from utils.model_router import classify_task, route_model, ModelDecision, STRUCTURED_MODEL

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
        f'margin:0.1rem 0.15rem 0.1rem 0">{html.escape(text)}</span>'
    )


def _label(text: str):
    st.markdown(
        f'<div style="font-size:0.72rem;font-weight:700;text-transform:uppercase;'
        f'letter-spacing:0.07em;color:{colors["text2"]};margin:0.75rem 0 0.25rem">'
        f'{html.escape(text)}</div>',
        unsafe_allow_html=True,
    )


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


# ── AI system prompt ──────────────────────────────────────────────────────────

def _get_system_base() -> str:
    """Build the full system prompt: private core + any admin custom instructions."""
    override = st.session_state.get("_ai_settings_override")
    settings = override if isinstance(override, dict) else load_ai_settings()
    admin_raw = settings.get("custom_instructions", "")
    return build_system_prompt(admin_raw)

def _groq_client() -> tuple[object | None, str | None]: # Groq client object or None, error string or None
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


def _rate_check(key: str, max_req: int = 20) -> tuple[bool, int]:
    sid = st.session_state.get("session_token", "default")
    allowed, wait = rate_limiter.is_allowed(f"ai_{sid}_{key}", max_req, 60)
    if allowed:
        rate_limiter.record_attempt(f"ai_{sid}_{key}")
    return allowed, wait


def _call_ai(system: str, user: str, json_mode: bool = False,
             temperature: float = 0.5, max_tokens: int = 1800,
             task_type: str = "free_chat") -> tuple[str | None, str | None]:
    allowed, wait = _rate_check("general")
    if not allowed:
        return None, f"Rate limit exceeded — wait {wait}s"
    client, err = _groq_client()
    if not client:
        return None, err

    settings = st.session_state.get("_ai_settings_override") or load_ai_settings()

    if json_mode:
        model  = get_secret("AI_MODEL") or STRUCTURED_MODEL
        reason = "Structured output — reliable 70B anchor model"
    else:
        decision = route_model(task_type, settings)
        model    = get_secret("AI_MODEL") or decision.model
        reason   = decision.reason

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
        log_audit("ai_request", f"model={model} task={task_type}")
        st.session_state["_ai_last_model"]     = model
        st.session_state["_ai_last_task_type"] = task_type
        st.session_state["_ai_last_reason"]    = reason
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


def get_ai_response(message: str, paper: dict | None = None) -> tuple[str | None, str | None]:
    try:
        req = AIRequest(message=message)
    except ValidationError:
        return None, "Your message could not be processed. Please rephrase and try again."
    system = _get_system_base()

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

    # ── File context (uploaded PDF / image description) ───────────────────────
    file_ctx = st.session_state.get("uploaded_file_context", "")
    if file_ctx:
        system += f"\n\nAttached document content:\n{file_ctx[:4000]}"

    if paper:
        system += _paper_context(paper)

    messages: list[dict] = [{"role": "system", "content": system}]
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


def _build_chat_messages(message: str, paper: dict | None) -> tuple[list[dict], str | None]:
    """Build the messages list for a chat turn, injecting RAG + file context."""
    system = _get_system_base()
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

    file_ctx = st.session_state.get("uploaded_file_context", "")
    if file_ctx:
        system += f"\n\nAttached document content:\n{file_ctx[:4000]}"

    if paper:
        system += _paper_context(paper)

    msgs: list[dict] = [{"role": "system", "content": system}]
    for m in st.session_state.get("chat_history", [])[-6:]:
        msgs.append({"role": m["role"], "content": m["content"]})
    msgs.append({"role": "user", "content": message})
    return msgs, None


def _stream_response_into_container(
    messages: list[dict],
    task_type: str = "free_chat",
) -> tuple[str | None, str | None]:
    """Stream the AI response into the current Streamlit container; returns (full_text, error)."""
    allowed, wait = _rate_check("chat")
    if not allowed:
        return None, f"Rate limit exceeded — wait {wait}s"
    client, err = _groq_client()
    if not client:
        return None, err

    settings = st.session_state.get("_ai_settings_override") or load_ai_settings()
    decision  = route_model(task_type, settings)
    model     = get_secret("AI_MODEL") or decision.model

    st.session_state["_ai_last_model"]     = model
    st.session_state["_ai_last_task_type"] = task_type
    st.session_state["_ai_last_reason"]    = decision.reason

    def _gen():
        stream = client.chat.completions.create(
            model=model, messages=messages,
            temperature=0.7, max_tokens=1500, stream=True,
        )
        for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta

    try:
        full_text: str = st.write_stream(_gen())
        log_audit("ai_chat", f"streamed model={model} task={task_type}")
        return full_text, None
    except Exception:
        # Fallback: try next models in chain without streaming
        for fallback_model in decision.fallback_chain:
            if fallback_model == model:
                continue
            try:
                resp = client.chat.completions.create(
                    model=fallback_model, messages=messages,
                    temperature=0.7, max_tokens=1500,
                )
                text = resp.choices[0].message.content or ""
                st.markdown(text)
                st.session_state["_ai_last_model"] = fallback_model
                log_audit("ai_chat", f"fallback model={fallback_model} task={task_type}")
                return text, None
            except Exception:
                continue
        return None, "AI service temporarily unavailable"


def get_structured_response(action: str, paper: dict) -> tuple[PaperSummary | KeyFindings | Methodology | Implications | None, str | None, str | None]:
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
    system = _get_system_base() + "\n\nRespond with valid JSON only.\n\n" + json_schema + _paper_context(paper)
    model  = get_secret("AI_MODEL") or STRUCTURED_MODEL
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": "Analyze this paper and return the JSON."}],
            response_format={"type": "json_object"},
            temperature=0.3, max_tokens=1500,
        )
        raw = resp.choices[0].message.content
        validated = parse_action_response(action, raw)
        log_audit("ai_structured", f"action={action} model={model}")
        st.session_state["_ai_last_model"]     = model
        st.session_state["_ai_last_task_type"] = "structured_json"
        st.session_state["_ai_last_reason"]    = "Structured output — reliable 70B anchor model"
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

def _bullet(items: list) -> None:
    for item in items:
        st.markdown(f"- {item}")


def render_structured(result: PaperSummary | KeyFindings | Methodology | Implications) -> None:
    if isinstance(result, PaperSummary):
        st.markdown(
            _card(
                f'<div style="font-size:0.9rem;line-height:1.7;color:{colors["text"]}">'
                f'{html.escape(result.overview)}</div>',
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
                f'{html.escape(result.methods)}</div>',
                unsafe_allow_html=True,
            )
        with c2:
            _label("Key Results")
            _bullet(result.results)
            _label("Conclusion")
            st.markdown(
                _card(
                    f'<div style="font-size:0.87rem;color:{colors["text"]};line-height:1.65">'
                    f'{html.escape(result.conclusion)}</div>',
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
                    f'{html.escape(f)}</div>',
                ),
                unsafe_allow_html=True,
            )
        st.markdown(
            _card(
                f'<div style="font-size:0.8rem;font-weight:700;color:{colors["text2"]};'
                f'text-transform:uppercase;letter-spacing:0.05em;margin-bottom:0.2rem">'
                f'Significance</div>'
                f'<div style="font-size:0.9rem;color:{colors["text"]};line-height:1.65">'
                f'{html.escape(result.significance)}</div>',
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
                f'{html.escape(result.study_design)}</div>',
                unsafe_allow_html=True,
            )
            _label("Sample")
            st.markdown(
                f'<div style="font-size:0.88rem;color:{colors["text"]};line-height:1.65">'
                f'{html.escape(result.sample)}</div>',
                unsafe_allow_html=True,
            )
        with c2:
            _label("Analysis Method")
            st.markdown(
                f'<div style="font-size:0.88rem;color:{colors["text"]};line-height:1.65">'
                f'{html.escape(result.analysis_method)}</div>',
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
                f'{html.escape(result.summary)}</div>',
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
    ("_rag_retrieved", []),
    ("_rag_index_cache", {}),
    ("confirm_clear_chat", False),
    ("uploaded_file_context", ""),
    ("uploaded_file_name", ""),
    ("conversation_sessions", {}),
    ("current_session_name", "Session 1"),
    ("_ai_last_model", ""),
    ("_ai_last_task_type", ""),
    ("_ai_last_reason", ""),
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
                f'{html.escape(str(paper.get("title", "Unknown")))}</div>'
                f'<div style="font-size:0.8rem;color:{colors["text2"]};margin-top:0.25rem">'
                f'📰 {html.escape(str(paper.get("journal_name", "")))} &nbsp;·&nbsp; '
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
                f'{html.escape(raw)}</div>'
            ),
            unsafe_allow_html=True,
        )


# ── Conversation History ──────────────────────────────────────────────────────

with st.expander(
    f"💬 Conversation History  "
    f"({len(st.session_state.conversation_sessions)} saved)",
    expanded=False,
):
    sessions = st.session_state.conversation_sessions
    if sessions:
        _sess_cols = st.columns([3, 1, 1])
        with _sess_cols[0]:
            _load_name = st.selectbox(
                "Saved sessions", list(sessions.keys()),
                label_visibility="collapsed",
                key="_load_session_select",
            )
        with _sess_cols[1]:
            if st.button("📂 Load", use_container_width=True, key="_load_session_btn"):
                if _load_name and _load_name in sessions:
                    st.session_state.chat_history = list(sessions[_load_name])
                    st.session_state.current_session_name = _load_name
                    st.rerun()
        with _sess_cols[2]:
            if st.button("🗑 Delete", use_container_width=True, key="_del_session_btn"):
                if _load_name and _load_name in sessions:
                    del st.session_state.conversation_sessions[_load_name]
                    st.rerun()
    else:
        st.caption("No saved sessions yet — save the current chat below.")

    st.divider()
    _save_cols = st.columns([3, 1])
    with _save_cols[0]:
        _new_name = st.text_input(
            "Session name",
            value=st.session_state.current_session_name,
            label_visibility="collapsed",
            placeholder="Name this conversation…",
            key="_save_session_name",
        )
    with _save_cols[1]:
        if st.button("💾 Save", use_container_width=True, key="_save_session_btn",
                     disabled=not st.session_state.chat_history):
            _sname = (_new_name or st.session_state.current_session_name).strip()
            if _sname:
                st.session_state.conversation_sessions[_sname] = list(
                    st.session_state.chat_history
                )
                st.session_state.current_session_name = _sname
                st.success(f"Saved as "{_sname}"")


# ── File Upload ───────────────────────────────────────────────────────────────

with st.expander(
    "📎 Attach a file  "
    + (f"(**{html.escape(st.session_state.uploaded_file_name)}** loaded)"
       if st.session_state.uploaded_file_name else "(PDF or image)"),
    expanded=False,
):
    _up = st.file_uploader(
        "Attach PDF or image",
        type=["pdf", "png", "jpg", "jpeg", "webp"],
        label_visibility="collapsed",
        key="_file_uploader",
    )
    if _up is not None and _up.name != st.session_state.uploaded_file_name:
        with st.spinner("Processing file…"):
            _ctx = ""
            if _up.type == "application/pdf":
                try:
                    from utils.pdf_extractor import extract_text
                    _ctx, _err = extract_text(_up.read())
                    if _err:
                        st.warning(f"⚠️ PDF extraction issue: {_err}")
                        _ctx = _ctx or ""
                except Exception as _exc:
                    st.warning(f"⚠️ Could not extract PDF text: {_exc}")
            else:
                _ctx = (
                    f"[Image attached: {html.escape(_up.name)}. "
                    "Describe its content in your question for best results.]"
                )
        st.session_state.uploaded_file_context = _ctx
        st.session_state.uploaded_file_name    = _up.name
        if _ctx:
            st.success(
                f"✅ {html.escape(_up.name)} loaded — "
                f"{len(_ctx):,} characters of context available."
            )

    if st.session_state.uploaded_file_name:
        if st.button("✕ Clear file", key="_clear_file_btn"):
            st.session_state.uploaded_file_context = ""
            st.session_state.uploaded_file_name    = ""
            st.rerun()


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
    if st.session_state.chat_history:
        if st.button("🗑️ Clear", use_container_width=True):
            st.session_state.confirm_clear_chat = True

    if st.session_state.get("confirm_clear_chat"):
        st.warning("Are you sure you want to clear the entire chat history? This action cannot be undone.")
        col_chat_c1, col_chat_c2 = st.columns(2)
        with col_chat_c1:
            if st.button("Confirm Clear Chat", key="confirm_clear_chat_yes", type="secondary", use_container_width=True):
                st.session_state.chat_history = []
                st.session_state.confirm_clear_chat = False
                st.rerun()
        with col_chat_c2:
            if st.button("Cancel Clear Chat", key="confirm_clear_chat_no", use_container_width=True):
                st.session_state.confirm_clear_chat = False
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
        if msg.get("rag_count") and msg["role"] == "assistant":
            st.caption(f"📚 {msg['rag_count']} paper(s) retrieved from your database")

    # ── Feedback buttons (assistant messages only) ────────────────────────────
    if msg["role"] == "assistant" and _ai_available:
        _fb_key = f"_fb_{_i}"
        _rating = st.session_state.get(_fb_key)
        if _rating is None:
            _fc1, _fc2, _fc3 = st.columns([1, 1, 10])
            with _fc1:
                if st.button("👍 Helpful", key=f"fbup_{_i}"):
                    _handle_feedback(_i, 1)
            with _fc2:
                if st.button("👎 Not helpful", key=f"fbdn_{_i}"):
                    _handle_feedback(_i, -1)
        else:
            st.caption("✓ Helpful" if _rating == 1 else "✓ Feedback noted")

if user_input := st.chat_input("Ask about your research papers…", disabled=not _ai_available):
    try:
        req = AIRequest(message=user_input)
    except ValidationError:
        st.error("❌ Your message could not be processed. Please try rephrasing it.")
        st.stop()

    st.session_state.chat_history.append({"role": "user", "content": req.message})
    with st.chat_message("user"):
        st.markdown(req.message)

    messages, _ = _build_chat_messages(req.message, paper)
    _task_type   = classify_task(req.message)

    with st.chat_message("assistant"):
        response, error = _stream_response_into_container(messages, task_type=_task_type)
        if response:
            # Model routing indicator
            _last_model  = st.session_state.get("_ai_last_model", "")
            _last_reason = st.session_state.get("_ai_last_reason", "")
            if _last_model:
                st.caption(f"🤖 {_last_model} — {_last_reason}")
            # RAG indicator shown after streaming completes
            retrieved = st.session_state.get("_rag_retrieved", [])
            if retrieved:
                titles = " · ".join(
                    f'"{p.get("title", "")[:45]}…"' if len(p.get("title", "")) > 45
                    else f'"{p.get("title", "")}"'
                    for p in retrieved
                )
                st.caption(f"📚 {len(retrieved)} paper(s) from your database: {titles}")
            ai_msg: dict = {"role": "assistant", "content": response}
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
