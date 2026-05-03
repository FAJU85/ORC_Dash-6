"""
ORC Research Dashboard - AI Research Assistant
"""

import streamlit as st
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.security import get_secret, sanitize_string, log_audit, RateLimiter
from utils.styles import (
    apply_styles, get_theme, hero_html, section_title_html,
    footer_html, DARK, LIGHT
)

st.set_page_config(page_title="AI Assistant", page_icon="🔬", layout="wide")

apply_styles()

colors = DARK if get_theme() == "dark" else LIGHT

rate_limiter = RateLimiter()

# ============================================
# AI RESPONSE FUNCTION
# ============================================

def get_ai_response(message, paper=None):
    """
    Generate an assistant response for a user message, optionally grounded in metadata from a selected paper.
    
    Builds a chat request (including a system prompt and recent chat history), sends it to the configured Groq-backed AI model, and returns the model's reply or a concrete error message when the request cannot be fulfilled.
    
    Parameters:
        message (str): The user's input to send to the AI.
        paper (dict | None): Optional paper metadata used to ground responses. Expected keys include
            'title', 'journal_name', 'publication_year', 'citation_count', and 'abstract'. Only the first
            800 characters of the abstract are used.
    
    Returns:
        tuple:
            response (str | None): The assistant's reply on success, or `None` if an error occurred.
            error (str | None): `None` on success, or a human-readable error string on failure. Possible
                error values include:
                - "Rate limit exceeded. Please wait {seconds} seconds."
                - "AI service not configured"
                - "AI library not available"
                - "AI service temporarily unavailable"
    """
    session_id = st.session_state.get('session_token', 'default')
    allowed, wait_time = rate_limiter.is_allowed(f"ai_{session_id}", max_attempts=20, window_seconds=60)
    if not allowed:
        return None, f"Rate limit exceeded. Please wait {wait_time} seconds."

    rate_limiter.record_attempt(f"ai_{session_id}")

    api_key = get_secret("AI_API_KEY") or get_secret("GROQ_API_KEY")
    if not api_key:
        return None, "AI service not configured"

    model = get_secret("AI_MODEL") or "llama-3.3-70b-versatile"

    try:
        from groq import Groq
        client = Groq(api_key=api_key)

        system = """You are an expert academic research assistant. You help researchers understand and analyze scientific publications.

Your capabilities:
- Summarize research papers clearly and accurately
- Identify key findings, methodologies, and contributions
- Explain complex concepts in accessible language
- Compare and connect different studies
- Generate proper academic citations

Be precise, professional, and helpful. When analyzing a paper, focus on the most important aspects."""

        if paper:
            system += f"""

You are currently analyzing this paper:
- Title: {paper.get('title', 'N/A')}
- Journal: {paper.get('journal_name', 'N/A')}
- Year: {paper.get('publication_year', 'N/A')}
- Citations: {paper.get('citation_count', 'N/A')}
- Abstract: {paper.get('abstract', 'Not available')[:800]}

Base your responses on this paper's information."""

        messages = [{"role": "system", "content": system}]
        for msg in st.session_state.get('chat_history', [])[-6:]:
            messages.append({"role": msg["role"], "content": msg["content"]})
        messages.append({"role": "user", "content": sanitize_string(message, 2000)})

        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.7,
            max_tokens=1500,
        )

        log_audit("ai_request", "ok")
        return response.choices[0].message.content, None

    except ImportError:
        return None, "AI library not available"
    except Exception:
        log_audit("ai_error", "service_error")
        return None, "AI service temporarily unavailable"

# ============================================
# SESSION STATE
# ============================================

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

# ============================================
# PAGE
# ============================================

st.markdown(hero_html("🔬 AI Research Assistant", "Analyze papers, extract insights, and explore your research"), unsafe_allow_html=True)

api_key = get_secret("AI_API_KEY") or get_secret("GROQ_API_KEY")
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
    c1, c2 = st.columns([5, 1])
    with c1:
        st.markdown(
            f'<div class="orc-card" style="border-left:4px solid {colors["accent"]};padding:1rem 1.25rem;">'
            f'  <div style="font-weight:600;font-size:0.95rem;margin-bottom:0.4rem">{paper.get("title","Unknown")}</div>'
            f'  <div style="font-size:0.8rem;opacity:0.7">📰 {journal}</div>'
            f'  <div style="font-size:0.78rem;opacity:0.55;margin-top:0.2rem">{year} · {citations:,} citations</div>'
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
        f'<div style="font-size:0.8rem;opacity:0.6">Go to <strong>Publications</strong> and click Analyze on any paper</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

# ── Quick Actions ───────────────────────────────────────────────────────────
st.markdown(section_title_html("Quick Actions"), unsafe_allow_html=True)

col1, col2, col3, col4 = st.columns(4)

with col1:
    if st.button("📝 Summarize", use_container_width=True, disabled=not paper):
        st.session_state.pending = f"Please provide a comprehensive summary of this paper: {paper['title']}"

with col2:
    if st.button("🔍 Key Findings", use_container_width=True, disabled=not paper):
        st.session_state.pending = "What are the main findings and conclusions of this paper?"

with col3:
    if st.button("📊 Methodology", use_container_width=True, disabled=not paper):
        st.session_state.pending = "Explain the research methodology used in this study."

with col4:
    if st.button("🔗 Implications", use_container_width=True, disabled=not paper):
        st.session_state.pending = "What are the practical implications of this research?"

# ── Chat Interface ──────────────────────────────────────────────────────────
st.markdown(section_title_html("Chat"), unsafe_allow_html=True)

for msg in st.session_state.chat_history:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])

# Handle quick-action pending message
if "pending" in st.session_state and st.session_state.pending:
    user_msg = st.session_state.pending
    st.session_state.pending = None
    st.session_state.chat_history.append({"role": "user", "content": user_msg})
    with st.chat_message("user"):
        st.write(user_msg)
    with st.chat_message("assistant"):
        with st.spinner("Analyzing…"):
            response, error = get_ai_response(user_msg, paper)
        if response:
            st.write(response)
            st.session_state.chat_history.append({"role": "assistant", "content": response})
        else:
            st.warning(f"⚠️ {error}")
            st.session_state.chat_history.append({"role": "assistant", "content": f"⚠️ {error}"})
    st.rerun()

user_input = st.chat_input("Ask about your research papers…")

if user_input:
    sanitized = sanitize_string(user_input, 2000)
    st.session_state.chat_history.append({"role": "user", "content": sanitized})
    with st.chat_message("user"):
        st.write(sanitized)
    with st.chat_message("assistant"):
        with st.spinner("Thinking…"):
            response, error = get_ai_response(sanitized, paper)
        if response:
            st.write(response)
            st.session_state.chat_history.append({"role": "assistant", "content": response})
        else:
            st.warning(f"⚠️ {error}")
            st.session_state.chat_history.append({"role": "assistant", "content": f"⚠️ {error}"})
    st.rerun()

if st.session_state.chat_history:
    if st.button("🗑️ Clear Chat"):
        st.session_state.chat_history = []
        log_audit("chat_cleared")
        st.rerun()

# ── Footer ───────────────────────────────────────────────────────────────────
st.divider()
st.markdown(footer_html(), unsafe_allow_html=True)
