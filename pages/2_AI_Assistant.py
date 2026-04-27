"""
ORC Research Dashboard - AI Research Assistant
"""

import streamlit as st
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.security import get_secret, sanitize_string, log_audit, RateLimiter
from utils.ui import apply_theme

st.set_page_config(page_title="AI Assistant", page_icon="🔬", layout="wide")
apply_theme()

rate_limiter = RateLimiter()

# ============================================
# AI RESPONSE FUNCTION
# ============================================

def get_ai_response(message, paper=None):
    """Get response from the configured AI service"""

    session_id = st.session_state.get('session_token', 'default')
    allowed, wait_time = rate_limiter.is_allowed(f"ai_{session_id}", max_attempts=20, window_seconds=60)
    if not allowed:
        return None, f"Rate limit exceeded. Please wait {wait_time} seconds."

    rate_limiter.record_attempt(f"ai_{session_id}")

    api_key = get_secret("AI_API_KEY") or get_secret("GROQ_API_KEY")
    if not api_key:
        return None, "AI service not configured"

    # Model is configurable; fall back to a capable default
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

st.title("🔬 AI Research Assistant")

api_key = get_secret("AI_API_KEY") or get_secret("GROQ_API_KEY")
if not api_key:
    st.error("❌ AI service not configured")
    st.info("Contact administrator to enable AI features.")
    st.stop()

st.divider()

# ── Selected Paper ──────────────────────────────────────────────────────────
paper = st.session_state.get("selected_paper")

st.header("📄 Selected Paper")

if paper:
    st.markdown(f"""
**{paper.get('title', 'Unknown')}**
📰 {paper.get('journal_name', '')} • {paper.get('publication_year', '')} • {paper.get('citation_count', 0)} citations
    """)
    if st.button("❌ Clear Selection"):
        st.session_state.selected_paper = None
        log_audit("paper_deselected")
        st.rerun()
else:
    st.info("💡 Select a paper from the **Publications** page for detailed analysis.")

st.divider()

# ── Quick Actions ───────────────────────────────────────────────────────────
st.header("⚡ Quick Actions")

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

st.divider()

# ── Chat Interface ──────────────────────────────────────────────────────────
chat_header_col, clear_col = st.columns([5, 1])
with chat_header_col:
    st.header("💬 Chat")
with clear_col:
    st.write("")
    st.write("")
    if st.session_state.chat_history:
        if st.button("🗑️ Clear", use_container_width=True, help="Clear chat history"):
            st.session_state.chat_history = []
            log_audit("chat_cleared")
            st.rerun()

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

# Chat input
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

st.divider()
st.markdown(
    "<div style='text-align:center;color:#64748b;font-size:0.8rem;'>"
    "Select a paper from Publications for detailed analysis"
    "</div>",
    unsafe_allow_html=True,
)
