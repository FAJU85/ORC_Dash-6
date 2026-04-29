"""
ORC Research Dashboard - AI Research Assistant
"""

import json
import streamlit as st
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pydantic import ValidationError
from utils.security import get_secret, sanitize_string, log_audit, log_error, RateLimiter
from utils.ui import apply_theme, render_footer
from utils.ai_schemas import (
    AIRequest, PaperContext, ACTION_PROMPTS, parse_action_response,
    PaperSummary, KeyFindings, Methodology, Implications,
)

st.set_page_config(page_title="AI Assistant", page_icon="🔬", layout="wide")
apply_theme()

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


# ── Option B: validated chat response ────────────────────────────────────────

def get_ai_response(message: str, paper: dict | None = None):
    """Validate input with AIRequest, call Groq, return (text, error)."""
    # Input validation
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


# ── Option A: structured quick-action response ────────────────────────────────

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
        # Pydantic validation failed — fall back to raw text
        log_error("ai_schema_validation_failed", f"action={action}", page="AI Assistant")
        return None, raw, None
    except Exception as e:
        log_audit("ai_error", "service_error")
        log_error("ai_service_error", str(e), page="AI Assistant")
        return None, None, "AI service temporarily unavailable"


# ── Structured response renderers ─────────────────────────────────────────────

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
    ("pending", None),
]:
    if key not in st.session_state:
        st.session_state[key] = val

# ============================================
# PAGE
# ============================================

st.title("🔬 AI Research Assistant")

api_key = (
    get_secret("AI_API_KEY") or get_secret("GROQ_API_KEY")
    or get_secret("GROQ_API") or get_secret("GROQ_TOKEN")
)
if not api_key:
    st.error("❌ AI service not configured")
    st.info("Contact administrator to enable AI features.")
    st.stop()

st.divider()

# ── Selected Paper ────────────────────────────────────────────────────────────
paper = st.session_state.get("selected_paper")

st.header("📄 Selected Paper")
if paper:
    st.markdown(f"**{paper.get('title', 'Unknown')}**")
    st.caption(
        f"📰 {paper.get('journal_name', '')}  •  "
        f"{paper.get('publication_year', '')}  •  "
        f"{paper.get('citation_count', 0)} citations"
    )
    if st.button("❌ Clear Selection"):
        st.session_state.selected_paper = None
        log_audit("paper_deselected")
        st.rerun()
else:
    st.info("💡 Select a paper from the **Publications** page for detailed analysis.")

st.divider()

# ── Quick Actions (structured / Option A) ────────────────────────────────────
st.header("⚡ Quick Actions")
st.caption("Returns validated structured cards instead of raw text.")

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
        with st.expander("🔧 Raw JSON response"):
            st.code(raw, language="json")
    elif raw:
        # Schema validation failed — show raw text as fallback
        st.info(raw)
    st.divider()

st.divider()

# ── Chat Interface (validated / Option B) ────────────────────────────────────
chat_col, clear_col = st.columns([5, 1])
with chat_col:
    st.header("💬 Chat")
with clear_col:
    st.write("")
    st.write("")
    if st.session_state.chat_history:
        if st.button("🗑️ Clear", use_container_width=True):
            st.session_state.chat_history = []
            log_audit("chat_cleared")
            st.rerun()

for msg in st.session_state.chat_history:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])

# Chat input — validated by AIRequest before reaching the AI
user_input = st.chat_input("Ask about your research papers…")

if user_input:
    # Option B: validate input before anything else
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

render_footer(note="Select a paper from Publications for context-aware analysis.")
