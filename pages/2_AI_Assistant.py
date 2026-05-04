"""
ORC Research Dashboard - AI Research Assistant
"""

import json
import streamlit as st
import sys
import os
from html import escape

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pydantic import ValidationError
from utils.security import get_secret, sanitize_string, log_audit, log_error, RateLimiter
from utils.styles import (
    apply_styles, get_theme, hero_html, section_title_html,
    footer_html, render_navbar, DARK, LIGHT
)
from utils.ai_schemas import (
    AIRequest, PaperContext, ACTION_PROMPTS, parse_action_response,
    PaperSummary, KeyFindings, Methodology, Implications,
)

st.set_page_config(page_title="AI Assistant", page_icon="🔬", layout="wide",
                   initial_sidebar_state="collapsed")
apply_styles()
render_navbar("ai assistant")

colors = DARK if get_theme() == "dark" else LIGHT

rate_limiter = RateLimiter()


# ============================================
# HELPERS
# ============================================

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
    except ImportError as e:
        log_error("ai_import_error", str(e), page="AI Assistant")
        return None, "AI library not available"


def _paper_system_block(ctx: PaperContext) -> str:
    return (
        f"\n\nYou are currently analyzing this paper:\n"
        f"- Title: {ctx.title}\n"
        f"- Journal: {ctx.journal_name}\n"
        f"- Year: {ctx.publication_year or 'N/A'}\n"
        f"- Citations: {ctx.citation_count}\n"
        f"- Abstract: {ctx.abstract}\n\n"
        f"Base all responses on this paper's information."
    )


def get_ai_response(message: str, paper: dict | None = None):
    """Validate input with AIRequest, call Groq, return (text, error)."""
    try:
        req = AIRequest(message=message)
    except ValidationError as e:
        return None, e.errors()[0]["msg"]

    session_id = st.session_state.get("session_token", "default")
    allowed, wait_time = rate_limiter.is_allowed(f"ai_{session_id}", max_attempts=20, window_seconds=60)
    if not allowed:
        return None, f"Rate limit exceeded. Please wait {wait_time} seconds."
    rate_limiter.record_attempt(f"ai_{session_id}")

    client, err = _groq_client()
    if not client:
        return None, err

    model = get_secret("AI_MODEL") or "llama-3.3-70b-versatile"

    system = (
        "You are an expert academic research assistant specializing in scientific publications. "
        "Be precise, professional, and helpful."
    )
    if paper:
        try:
            ctx = PaperContext.from_dict(paper)
            system += _paper_system_block(ctx)
        except Exception:
            pass

    messages = [{"role": "system", "content": system}]
    for msg in st.session_state.get("chat_history", [])[-6:]:
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": req.message})

    try:
        resp = client.chat.completions.create(
            model=model, messages=messages, temperature=0.7, max_tokens=1500,
        )
        log_audit("ai_request", "ok")
        return resp.choices[0].message.content, None
    except Exception as e:
        log_audit("ai_error", "service_error")
        log_error("ai_service_error", str(e), page="AI Assistant")
        return None, "AI service temporarily unavailable"


def get_structured_response(action: str, paper: dict):
    """Call Groq in JSON mode and validate result with the action's Pydantic schema."""
    session_id = st.session_state.get("session_token", "default")
    allowed, wait_time = rate_limiter.is_allowed(f"ai_{session_id}", max_attempts=20, window_seconds=60)
    if not allowed:
        return None, None, f"Rate limit exceeded. Please wait {wait_time} seconds."
    rate_limiter.record_attempt(f"ai_{session_id}")

    client, err = _groq_client()
    if not client:
        return None, None, err

    model = get_secret("AI_MODEL") or "llama-3.3-70b-versatile"
    json_schema, model_cls = ACTION_PROMPTS[action]

    try:
        ctx = PaperContext.from_dict(paper)
    except Exception:
        return None, None, "Invalid paper data"

    system = (
        "You are an expert academic research assistant. "
        "You always respond with valid JSON only — no extra text, no markdown code fences.\n\n"
        + json_schema
        + _paper_system_block(ctx)
    )

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": "Analyze this paper and return the JSON response."},
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
            max_tokens=1500,
        )
        raw = resp.choices[0].message.content
        validated = parse_action_response(action, raw)
        if validated:
            log_audit("ai_structured_request", action)
            return validated, raw, None
        log_error("ai_schema_validation_failed", f"action={action}", page="AI Assistant")
        return None, raw, None
    except Exception as e:
        log_audit("ai_error", "service_error")
        log_error("ai_service_error", str(e), page="AI Assistant")
        return None, None, "AI service temporarily unavailable"


def _bullet(items: list[str]):
    for item in items:
        st.markdown(f"• {item}")


def render_structured(result):
    if isinstance(result, PaperSummary):
        st.markdown("**Overview**")
        st.info(result.overview)
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Objectives**")
            _bullet(result.objectives)
            st.markdown("**Methodology**")
            st.write(result.methods)
        with col2:
            st.markdown("**Key Results**")
            _bullet(result.results)
            st.markdown("**Conclusion**")
            st.success(result.conclusion)

    elif isinstance(result, KeyFindings):
        st.markdown("**Key Findings**")
        for i, f in enumerate(result.findings, 1):
            st.markdown(f"**{i}.** {f}")
        st.markdown("**Significance**")
        st.info(result.significance)
        if result.limitations:
            with st.expander("⚠️ Study Limitations"):
                _bullet(result.limitations)

    elif isinstance(result, Methodology):
        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"**Study Design**\n\n{result.study_design}")
            st.markdown(f"**Sample**\n\n{result.sample}")
            st.markdown(f"**Data Collection**\n\n{result.data_collection}")
        with col2:
            st.markdown(f"**Analysis Method**\n\n{result.analysis_method}")
            if result.tools:
                st.markdown("**Tools & Software**")
                st.markdown(" · ".join(f"`{t}`" for t in result.tools))

    elif isinstance(result, Implications):
        tab_c, tab_r, tab_p = st.tabs(["🏥 Clinical", "🔬 Research", "📋 Policy"])
        with tab_c:
            _bullet(result.clinical) if result.clinical else st.caption("None identified")
        with tab_r:
            _bullet(result.research) if result.research else st.caption("None identified")
        with tab_p:
            _bullet(result.policy) if result.policy else st.caption("None identified")
        st.markdown("**Overall Significance**")
        st.info(result.summary)


# ============================================
# SESSION STATE
# ============================================

for key, val in [
    ("chat_history", []),
    ("pending_action", None),
]:
    if key not in st.session_state:
        st.session_state[key] = val

# ============================================
# PAGE
# ============================================

st.markdown(hero_html("🔬 AI Research Assistant", "Analyze papers, extract insights, and explore your research"), unsafe_allow_html=True)

api_key = (
    get_secret("AI_API_KEY") or get_secret("GROQ_API_KEY")
    or get_secret("GROQ_API") or get_secret("GROQ_TOKEN")
)
if not api_key:
    st.markdown(
        f'<div class="orc-card" style="border-left:4px solid {colors["error"]};padding:1.25rem 1.5rem;">'
        f'<div style="font-weight:600;font-size:0.95rem;margin-bottom:0.3rem">❌ AI Service Not Configured</div>'
        f'<div style="font-size:0.85rem;opacity:0.7">Contact the administrator to enable AI features.</div>'
        f'</div>',
        unsafe_allow_html=True,
    )
    st.divider()
    st.markdown(footer_html(), unsafe_allow_html=True)
    st.stop()

# ── Selected Paper Card ─────────────────────────────────────────────────────
st.markdown(section_title_html("Selected Paper"), unsafe_allow_html=True)

paper = st.session_state.get("selected_paper")

if paper:
    citations = paper.get('citation_count', 0) or 0
    year = paper.get('publication_year', '')
    journal = paper.get('journal_name', '')
    safe_title = escape(str(paper.get("title", "Unknown")), quote=True)
    safe_journal = escape(str(journal), quote=True)
    c1, c2 = st.columns([5, 1])
    with c1:
        st.markdown(
            f'<div class="orc-card" style="border-left:4px solid {colors["accent"]};padding:1rem 1.25rem;">'
            f'  <div style="font-weight:600;font-size:0.95rem;margin-bottom:0.4rem">{safe_title}</div>'
            f'  <div style="font-size:0.8rem;color:{colors["text2"]}">📰 {safe_journal}</div>'
            f'  <div style="font-size:0.78rem;color:{colors["muted"]};margin-top:0.2rem">{year} · {citations:,} citations</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
    with c2:
        st.write("")
        st.write("")
        if st.button("✕ Clear", use_container_width=True):
            st.session_state.selected_paper = None
            log_audit("paper_deselected")
            st.rerun()
else:
    st.markdown(
        f'<div class="orc-card" style="text-align:center;padding:1.5rem;border:1px dashed {colors["border"]};">'
        f'<div style="font-size:1.75rem;margin-bottom:0.4rem">📄</div>'
        f'<div style="font-weight:600;font-size:0.9rem;margin-bottom:0.2rem">No paper selected</div>'
        f'<div style="font-size:0.8rem;color:{colors["text2"]}">Go to <strong>Publications</strong> and click Analyze on any paper</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

# ── Quick Actions ───────────────────────────────────────────────────────────
st.markdown(section_title_html("Quick Actions"), unsafe_allow_html=True)

col1, col2, col3, col4 = st.columns(4)
with col1:
    if st.button("📝 Summarize", use_container_width=True, disabled=not paper):
        st.session_state.pending_action = "summarize"
with col2:
    if st.button("🔍 Key Findings", use_container_width=True, disabled=not paper):
        st.session_state.pending_action = "findings"
with col3:
    if st.button("📊 Methodology", use_container_width=True, disabled=not paper):
        st.session_state.pending_action = "methodology"
with col4:
    if st.button("🔗 Implications", use_container_width=True, disabled=not paper):
        st.session_state.pending_action = "implications"

# Process structured action
if st.session_state.pending_action and paper:
    action = st.session_state.pending_action
    st.session_state.pending_action = None
    st.divider()
    action_labels = {
        "summarize": "📝 Paper Summary",
        "findings": "🔍 Key Findings",
        "methodology": "📊 Methodology",
        "implications": "🔗 Implications",
    }
    st.subheader(action_labels.get(action, action.title()))
    with st.spinner("Analyzing with validated schema…"):
        validated, raw, error = get_structured_response(action, paper)

    if error:
        st.warning(f"⚠️ {error}")
    elif validated:
        render_structured(validated)
    elif raw:
        st.info(raw)
    st.divider()

# ── Chat Interface ──────────────────────────────────────────────────────────
st.markdown(section_title_html("Chat"), unsafe_allow_html=True)

chat_col, clear_col = st.columns([5, 1])
with clear_col:
    if st.session_state.chat_history:
        if st.button("🗑️ Clear", use_container_width=True):
            st.session_state.chat_history = []
            log_audit("chat_cleared")
            st.rerun()

for msg in st.session_state.chat_history:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])

user_input = st.chat_input("Ask about your research papers…")

if user_input:
    try:
        req = AIRequest(message=user_input)
    except ValidationError as e:
        st.error(f"❌ {e.errors()[0]['msg']}")
        st.stop()

    st.session_state.chat_history.append({"role": "user", "content": req.message})
    with st.chat_message("user"):
        st.write(req.message)
    with st.chat_message("assistant"):
        with st.spinner("Thinking…"):
            response, error = get_ai_response(req.message, paper)
        if response:
            st.write(response)
            st.session_state.chat_history.append({"role": "assistant", "content": response})
        else:
            st.warning(f"⚠️ {error}")
            st.session_state.chat_history.append({"role": "assistant", "content": f"⚠️ {error}"})
    st.rerun()

# ── Footer ───────────────────────────────────────────────────────────────────
st.divider()
st.markdown(footer_html("Select a paper from Publications for context-aware analysis."), unsafe_allow_html=True)
