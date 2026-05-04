"""
ORC Research Assistant — Scientific Analysis Engine
Single unified page: paper Q&A, dataset analysis, and PDF reading
with file attachment support (PDF · CSV · Excel).
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
from utils.data_analysis import (
    load_file, describe_dataset, dataset_context_for_ai,
    correlation_analysis, linear_regression, regression_scatter,
    t_test_independent, one_way_anova, chi_square,
    auto_chart, distribution_grid,
)
from utils.pdf_extractor import (
    extract_text, extract_sections, extract_metadata,
    build_ai_prompt, generate_slides,
)

st.set_page_config(page_title="AI Assistant", page_icon="🔬", layout="wide",
                   initial_sidebar_state="collapsed")
apply_styles()
render_navbar("ai assistant")

colors = DARK if get_theme() == "dark" else LIGHT
rate_limiter = RateLimiter()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _card(content: str, border_color: str = "", extra_style: str = "") -> str:
    """Build a theme-aware card HTML snippet with explicit background and text color."""
    border = f"border-left:4px solid {border_color};" if border_color else ""
    return (
        f'<div style="background:{colors["surface"]};border-radius:6px;'
        f'padding:1rem 1.25rem;margin-bottom:0.65rem;color:{colors["text"]};{border}{extra_style}">'
        f'{content}</div>'
    )


def _ai_text_html(text: str) -> str:
    """Escape AI text and convert newlines to <br> for safe HTML rendering."""
    return escape(str(text)).replace('\n', '<br>')


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


def get_ai_response(message: str, paper: dict | None = None,
                    file_context: str = "") -> tuple:
    try:
        req = AIRequest(message=message)
    except ValidationError as e:
        return None, e.errors()[0]["msg"]
    system = (
        "You are an expert academic research assistant. "
        "Be precise, concise, and professional."
    )
    if paper:
        system += _paper_context(paper)
    if file_context:
        system += f"\n\nAttached file context:\n{file_context}"

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
    allowed, wait = _rate_check("structured")
    if not allowed:
        return None, None, f"Rate limit exceeded — wait {wait}s"
    client, err = _groq_client()
    if not client:
        return None, None, err
    json_schema, model_cls = ACTION_PROMPTS[action]
    try:
        ctx = PaperContext.from_dict(paper)
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
        return validated, raw, None
    except Exception:
        return None, None, "AI service temporarily unavailable"


def _bullet(items: list):
    for item in items:
        st.markdown(f"• {item}")


def render_structured(result):
    if isinstance(result, PaperSummary):
        st.markdown("**Overview**")
        st.info(result.overview)
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Objectives**"); _bullet(result.objectives)
            st.markdown("**Methodology**"); st.write(result.methods)
        with c2:
            st.markdown("**Key Results**"); _bullet(result.results)
            st.markdown("**Conclusion**");  st.success(result.conclusion)
    elif isinstance(result, KeyFindings):
        for i, f in enumerate(result.findings, 1):
            st.markdown(f"**{i}.** {f}")
        st.info(result.significance)
        if result.limitations:
            with st.expander("⚠️ Limitations"):
                _bullet(result.limitations)
    elif isinstance(result, Methodology):
        c1, c2 = st.columns(2)
        with c1:
            st.markdown(f"**Design**\n\n{result.study_design}")
            st.markdown(f"**Sample**\n\n{result.sample}")
        with c2:
            st.markdown(f"**Analysis**\n\n{result.analysis_method}")
            if result.tools:
                st.markdown("**Tools:** " + " · ".join(f"`{t}`" for t in result.tools))
    elif isinstance(result, Implications):
        t1, t2, t3 = st.tabs(["🏥 Clinical", "🔬 Research", "📋 Policy"])
        with t1: _bullet(result.clinical) if result.clinical else st.caption("None")
        with t2: _bullet(result.research) if result.research else st.caption("None")
        with t3: _bullet(result.policy)   if result.policy   else st.caption("None")
        st.info(result.summary)


# ── Dataset AI analysis ───────────────────────────────────────────────────────

def ai_analyze_dataset(df, user_question: str = "") -> tuple:
    ctx = dataset_context_for_ai(df)
    system = (
        "You are a senior data scientist and statistician. "
        "Given a dataset description, choose the most appropriate statistical analysis.\n\n"
        "Respond with JSON only:\n"
        '{"analysis_type": "descriptive|correlation|regression|t_test|anova|chi_square", '
        '"columns": ["col1", "col2"], '
        '"target_column": "col_name_or_empty", '
        '"group_column": "col_name_or_empty", '
        '"chart_type": "histogram|scatter|bar|heatmap|box", '
        '"reasoning": "one sentence why", '
        '"plain_english": "short explanation of what this analysis will reveal"}'
    )
    q = user_question or "What is the most informative analysis I can run on this dataset?"
    text, err = _call_ai(system, f"Dataset info:\n{ctx}\n\nUser question: {q}",
                         json_mode=True, temperature=0.2)
    if err or not text:
        return None, err
    try:
        return json.loads(text), None
    except Exception:
        return None, "Could not parse AI analysis plan"


def ai_explain_results(results: dict, analysis_type: str) -> str:
    system = (
        "You are an expert statistician. Explain the following statistical results "
        "clearly and concisely in plain English for a non-specialist researcher. "
        "Be specific about what the numbers mean."
    )
    text, _ = _call_ai(system,
                       f"Analysis type: {analysis_type}\nResults: {json.dumps(results, default=str)}",
                       temperature=0.4, max_tokens=600)
    return text or "Could not generate explanation."


# ── PDF AI summary ────────────────────────────────────────────────────────────

def ai_summarize_paper(sections: dict) -> tuple:
    system = (
        "You are a scientific research assistant. Analyze this research paper and "
        "return a structured JSON summary.\n\n"
        'Respond with JSON only:\n'
        '{"title": "...", "overview": "2-3 sentence overview", '
        '"objectives": ["objective 1", "objective 2"], '
        '"methods": "brief description", '
        '"results": ["key result 1", "key result 2", "key result 3"], '
        '"conclusion": "main conclusion", '
        '"limitations": ["limitation 1"], '
        '"field": "field of study"}'
    )
    text, err = _call_ai(system, build_ai_prompt(sections),
                         json_mode=True, temperature=0.3, max_tokens=1200)
    if err or not text:
        return None, err
    try:
        return json.loads(text), None
    except Exception:
        return None, "Could not parse AI summary"


# ── Session state ─────────────────────────────────────────────────────────────

for key, val in [
    ("chat_history", []),
    ("pending_action", None),
    ("attached_df", None),
    ("attached_pdf_text", None),
    ("attached_pdf_sections", {}),
    ("attached_pdf_summary", None),
    ("attached_pdf_title", ""),
    ("attached_file_name", ""),
    ("attached_file_type", None),   # "csv" | "excel" | "pdf"
    ("analysis_plan", None),
]:
    if key not in st.session_state:
        st.session_state[key] = val


# ── Page ──────────────────────────────────────────────────────────────────────

st.markdown(
    hero_html("🔬 AI Research Assistant",
              "Ask questions, analyze datasets, read papers — attach any file to get started"),
    unsafe_allow_html=True,
)

api_key = (
    get_secret("AI_API_KEY") or get_secret("GROQ_API_KEY")
    or get_secret("GROQ_API") or get_secret("GROQ_TOKEN")
)
if not api_key:
    st.error("AI service not configured. Add an AI_API_KEY secret.")
    st.stop()


# ── Context panel — paper card ────────────────────────────────────────────────

paper = st.session_state.get("selected_paper")
if paper:
    citations = paper.get("citation_count", 0) or 0
    c1, c2 = st.columns([8, 1])
    with c1:
        st.markdown(
            _card(
                f'<div style="font-weight:600;font-size:0.95rem;color:{colors["text"]}">'
                f'{escape(str(paper.get("title", "Unknown")))}</div>'
                f'<div style="font-size:0.8rem;color:{colors["text2"]};margin-top:0.2rem">'
                f'📰 {escape(str(paper.get("journal_name", "")))} · '
                f'{paper.get("publication_year", "")} · {citations:,} citations</div>',
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
        f'<div style="font-size:0.83rem;color:{colors["text2"]};'
        f'margin-bottom:0.75rem;padding:0.5rem 0">'
        f'💡 Go to <b>Publications</b> and click <b>Analyze</b> on any paper to set context — '
        f'or attach a file below.</div>',
        unsafe_allow_html=True,
    )


# ── File attachment ───────────────────────────────────────────────────────────

file_context_for_chat = ""

with st.expander("📎 Attach a file — PDF paper · CSV · Excel", expanded=False):
    uploaded = st.file_uploader(
        "Drag and drop or browse",
        type=["pdf", "csv", "xlsx", "xls"],
        label_visibility="collapsed",
        key="universal_file_upload",
    )
    if uploaded:
        file_bytes = uploaded.read()
        name_lower = uploaded.name.lower()

        if name_lower.endswith(".pdf"):
            with st.spinner("Reading PDF…"):
                text, extract_err = extract_text(file_bytes)
            if extract_err:
                st.error(f"❌ {extract_err}")
            elif not text.strip():
                st.warning("⚠️ No readable text found — the PDF may be image-based.")
            else:
                sections = extract_sections(text)
                meta     = extract_metadata(text)
                st.session_state.attached_pdf_text     = text
                st.session_state.attached_pdf_sections = sections
                st.session_state.attached_pdf_title    = meta.get("title", uploaded.name)
                st.session_state.attached_file_name    = uploaded.name
                st.session_state.attached_file_type    = "pdf"
                st.session_state.attached_df           = None
                st.session_state.attached_pdf_summary  = None
                st.session_state.analysis_plan         = None
                st.success(f"✅ PDF loaded — {len(text):,} characters · {len(sections)} sections detected")

        elif name_lower.endswith((".csv", ".xlsx", ".xls")):
            df, err = load_file(file_bytes, uploaded.name)
            if err:
                st.error(f"❌ {err}")
            else:
                st.session_state.attached_df           = df
                st.session_state.attached_file_name    = uploaded.name
                st.session_state.attached_file_type    = "excel" if name_lower.endswith((".xlsx", ".xls")) else "csv"
                st.session_state.attached_pdf_text     = None
                st.session_state.attached_pdf_sections = {}
                st.session_state.attached_pdf_summary  = None
                st.session_state.analysis_plan         = None
                info = describe_dataset(df)
                st.success(
                    f"✅ Dataset loaded — {info['rows']:,} rows × {info['columns']} columns · "
                    f"{len(info['numeric_columns'])} numeric · "
                    f"{info['missing_values']} missing values"
                )

    # Clear attachment
    if st.session_state.get("attached_file_type"):
        if st.button("✕ Remove attachment", type="secondary"):
            for k in ("attached_df", "attached_pdf_text", "attached_pdf_sections",
                      "attached_pdf_summary", "attached_pdf_title",
                      "attached_file_name", "attached_file_type", "analysis_plan"):
                st.session_state[k] = None if k not in ("attached_pdf_sections",) else {}
            st.rerun()


# ── Attached file context card ────────────────────────────────────────────────

attached_type = st.session_state.get("attached_file_type")
attached_name = st.session_state.get("attached_file_name", "")

if attached_type == "pdf":
    pdf_text = st.session_state.get("attached_pdf_text", "")
    sections = st.session_state.get("attached_pdf_sections", {})
    st.markdown(
        _card(
            f'<div style="font-weight:600;font-size:0.88rem;color:{colors["text"]}">📄 {escape(attached_name)}</div>'
            f'<div style="font-size:0.78rem;color:{colors["text2"]};margin-top:0.15rem">'
            f'{len(pdf_text or ""):,} characters · {len(sections)} sections</div>',
            border_color=colors["accent2"],
        ),
        unsafe_allow_html=True,
    )
    file_context_for_chat = build_ai_prompt(sections or {"text": (pdf_text or "")[:3000]}, max_chars=2500)

elif attached_type in ("csv", "excel"):
    df = st.session_state.get("attached_df")
    if df is not None:
        info = describe_dataset(df)
        st.markdown(
            _card(
                f'<div style="font-weight:600;font-size:0.88rem;color:{colors["text"]}">📊 {escape(attached_name)}</div>'
                f'<div style="font-size:0.78rem;color:{colors["text2"]};margin-top:0.15rem">'
                f'{info["rows"]:,} rows · {info["columns"]} columns · '
                f'{len(info["numeric_columns"])} numeric · {info["missing_values"]} missing</div>',
                border_color=colors["accent"],
            ),
            unsafe_allow_html=True,
        )
        file_context_for_chat = dataset_context_for_ai(df)


# ── Quick Actions (paper) ─────────────────────────────────────────────────────

st.markdown(section_title_html("Quick Actions"), unsafe_allow_html=True)
qa1, qa2, qa3, qa4 = st.columns(4)
for col, label, action in [
    (qa1, "📝 Summarize",    "summarize"),
    (qa2, "🔍 Key Findings", "findings"),
    (qa3, "📊 Methodology",  "methodology"),
    (qa4, "🔗 Implications", "implications"),
]:
    with col:
        if st.button(label, use_container_width=True, disabled=not paper):
            st.session_state.pending_action = action

if st.session_state.pending_action and paper:
    action = st.session_state.pending_action
    st.session_state.pending_action = None
    labels = {"summarize": "📝 Summary", "findings": "🔍 Key Findings",
              "methodology": "📊 Methodology", "implications": "🔗 Implications"}
    st.markdown(section_title_html(labels.get(action, action.title())), unsafe_allow_html=True)
    with st.spinner("Analyzing…"):
        validated, raw, error = get_structured_response(action, paper)
    if error:
        st.warning(f"⚠️ {error}")
    elif validated:
        render_structured(validated)
    elif raw:
        st.info(raw)


# ── Dataset analysis panel ────────────────────────────────────────────────────

if attached_type in ("csv", "excel"):
    df = st.session_state.get("attached_df")
    if df is not None:
        info = describe_dataset(df)
        st.markdown(section_title_html("Dataset Overview"), unsafe_allow_html=True)

        ov1, ov2, ov3, ov4 = st.columns(4)
        for col, lbl, val in [
            (ov1, "Rows",    f"{info['rows']:,}"),
            (ov2, "Columns", str(info["columns"])),
            (ov3, "Numeric", str(len(info["numeric_columns"]))),
            (ov4, "Missing", str(info["missing_values"])),
        ]:
            col.metric(lbl, val)

        with st.expander("🔍 Preview (first 10 rows)"):
            st.dataframe(df.head(10), use_container_width=True)

        if info["numeric_columns"]:
            with st.expander("📈 Descriptive Statistics"):
                st.dataframe(df[info["numeric_columns"]].describe().round(3),
                             use_container_width=True)
            with st.expander("📊 Variable Distributions"):
                st.plotly_chart(distribution_grid(df, info["numeric_columns"]),
                                use_container_width=True)

        st.markdown(section_title_html("AI Analysis Engine"), unsafe_allow_html=True)
        user_q = st.text_input(
            "What would you like to discover?",
            placeholder="e.g. Is there a relationship between age and blood pressure?",
            key="analysis_question",
        )
        if st.button("🧠 Run AI Analysis", type="primary", use_container_width=True):
            with st.spinner("AI is planning the analysis…"):
                plan, plan_err = ai_analyze_dataset(df, user_q)
            st.session_state.analysis_plan = plan
            if plan_err:
                st.error(f"❌ {plan_err}")

        plan = st.session_state.get("analysis_plan")
        if plan:
            atype      = plan.get("analysis_type", "descriptive")
            reasoning  = plan.get("reasoning", "")
            plain      = plan.get("plain_english", "")
            cols_used  = plan.get("columns", info["numeric_columns"][:2])
            target_col = plan.get("target_column", "")
            group_col  = plan.get("group_column", "")
            chart_hint = plan.get("chart_type", "")

            cols_used  = [c for c in cols_used  if c in df.columns]
            target_col = target_col if target_col in df.columns else ""
            group_col  = group_col  if group_col  in df.columns else ""

            st.markdown(
                _card(
                    f'<div style="font-weight:600;font-size:0.85rem;color:{colors["text"]}">'
                    f'🧠 AI chose: <code style="background:{colors["surface2"]};'
                    f'padding:0.1rem 0.3rem;border-radius:3px;color:{colors["accent"]}">'
                    f'{escape(atype)}</code></div>'
                    f'<div style="font-size:0.82rem;color:{colors["text2"]};margin-top:0.25rem">'
                    f'{escape(reasoning)}</div>'
                    f'<div style="font-size:0.82rem;color:{colors["text2"]};margin-top:0.15rem">'
                    f'{escape(plain)}</div>',
                    border_color=colors["accent"],
                ),
                unsafe_allow_html=True,
            )

            results = {}

            if atype == "correlation" and len(cols_used) >= 2:
                corr_df, fig = correlation_analysis(df, cols_used)
                if fig:
                    st.plotly_chart(fig, use_container_width=True)
                if corr_df is not None:
                    results = corr_df.to_dict()

            elif atype == "regression" and target_col and cols_used:
                feats = [c for c in cols_used if c != target_col]
                if feats:
                    results = linear_regression(df, target_col, feats)
                    if len(feats) == 1:
                        st.plotly_chart(regression_scatter(df, feats[0], target_col),
                                        use_container_width=True)
                    if "error" not in results:
                        rc1, rc2, rc3 = st.columns(3)
                        rc1.metric("R²",       results.get("r_squared", "—"))
                        rc2.metric("Adj. R²",  results.get("adj_r_squared", "—"))
                        rc3.metric("F p-value", results.get("p_value_f", "—"))

            elif atype == "t_test" and len(cols_used) >= 2:
                s1 = df[cols_used[0]].dropna()
                s2 = df[cols_used[1]].dropna()
                results = t_test_independent(s1, s2, cols_used[0], cols_used[1])
                tc1, tc2 = st.columns(2)
                tc1.metric("t-statistic", results.get("t_statistic", "—"))
                tc2.metric("p-value",     results.get("p_value", "—"))
                msg_fn = st.success if results.get("significant") else st.info
                msg_fn(results.get("interpretation", ""))

            elif atype == "anova" and cols_used and group_col:
                val_col = next((c for c in cols_used if c != group_col), "")
                if val_col:
                    results = one_way_anova(df, val_col, group_col)
                    ac1, ac2 = st.columns(2)
                    ac1.metric("F-statistic", results.get("f_statistic", "—"))
                    ac2.metric("p-value",     results.get("p_value", "—"))
                    if results.get("group_means"):
                        import pandas as _pd
                        st.dataframe(
                            _pd.DataFrame.from_dict(results["group_means"],
                                                    orient="index", columns=[val_col]),
                            use_container_width=True,
                        )
                    msg_fn = st.success if results.get("significant") else st.info
                    msg_fn(results.get("interpretation", ""))

            elif atype == "chi_square" and len(cols_used) >= 2:
                results = chi_square(df, cols_used[0], cols_used[1])
                cc1, cc2 = st.columns(2)
                cc1.metric("χ² statistic", results.get("chi2_statistic", "—"))
                cc2.metric("p-value",      results.get("p_value", "—"))
                msg_fn = st.success if results.get("significant") else st.info
                msg_fn(results.get("interpretation", ""))

            else:
                if info["numeric_columns"]:
                    st.dataframe(df[info["numeric_columns"]].describe().round(3),
                                 use_container_width=True)

            if cols_used and atype != "correlation":
                x = cols_used[0]
                y = cols_used[1] if len(cols_used) > 1 else None
                st.plotly_chart(
                    auto_chart(df, x, y, hint=chart_hint,
                               color=group_col if group_col else None),
                    use_container_width=True,
                )

            if results and "error" not in results:
                with st.spinner("AI is writing the explanation…"):
                    explanation = ai_explain_results(results, atype)
                st.markdown(section_title_html("AI Interpretation"), unsafe_allow_html=True)
                st.markdown(
                    _card(
                        f'<div style="font-size:0.75rem;font-weight:600;'
                        f'color:{colors["text2"]};margin-bottom:0.5rem;'
                        f'text-transform:uppercase;letter-spacing:0.06em">Interpretation</div>'
                        f'<div style="font-size:0.88rem;line-height:1.75;color:{colors["text"]}">'
                        f'{_ai_text_html(explanation)}</div>',
                        border_color=colors["accent2"],
                    ),
                    unsafe_allow_html=True,
                )

        # Manual controls
        with st.expander("🔧 Manual Analysis Controls"):
            mc1, mc2 = st.columns(2)
            num_cols = info["numeric_columns"]
            with mc1:
                if len(num_cols) >= 2:
                    sel_corr = st.multiselect(
                        "Correlation — select columns", num_cols,
                        default=num_cols[:min(4, len(num_cols))], key="manual_corr",
                    )
                    if sel_corr and len(sel_corr) >= 2 and st.button("📈 Run Correlation"):
                        corr_df, fig = correlation_analysis(df, sel_corr)
                        if fig:
                            st.plotly_chart(fig, use_container_width=True)
            with mc2:
                if len(num_cols) >= 2:
                    target = st.selectbox("Regression target", num_cols, key="reg_target")
                    feats  = st.multiselect(
                        "Features", [c for c in num_cols if c != target],
                        default=[c for c in num_cols if c != target][:2], key="reg_feats",
                    )
                    if feats and st.button("📉 Run Regression"):
                        res = linear_regression(df, target, feats)
                        if "error" in res:
                            st.error(res["error"])
                        else:
                            st.json(res)
                            if len(feats) == 1:
                                st.plotly_chart(regression_scatter(df, feats[0], target),
                                                use_container_width=True)


# ── PDF reading panel ─────────────────────────────────────────────────────────

if attached_type == "pdf":
    pdf_sections = st.session_state.get("attached_pdf_sections", {})
    pdf_text     = st.session_state.get("attached_pdf_text", "")
    pdf_title    = st.session_state.get("attached_pdf_title", "")

    if pdf_sections:
        with st.expander("📑 Extracted Sections"):
            for name, content in pdf_sections.items():
                st.markdown(f"**{name.title()}**")
                st.caption(content[:400] + "…")

    st.markdown(section_title_html("AI Paper Summary"), unsafe_allow_html=True)

    col_gen, col_dl = st.columns([3, 1])
    with col_gen:
        if st.button("🧠 Generate AI Summary", type="primary", use_container_width=True,
                     key="gen_summary"):
            with st.spinner("AI is reading the paper…"):
                summary, sum_err = ai_summarize_paper(
                    pdf_sections or {"full_text": (pdf_text or "")[:3000]}
                )
            if sum_err:
                st.error(f"❌ {sum_err}")
            else:
                st.session_state.attached_pdf_summary = summary

    summary = st.session_state.get("attached_pdf_summary")
    if summary:
        overview = summary.get("overview", "")
        if overview:
            st.info(overview)

        sc1, sc2 = st.columns(2)
        with sc1:
            if summary.get("objectives"):
                st.markdown("**Objectives**")
                for o in summary["objectives"]:
                    st.markdown(f"• {o}")
            if summary.get("methods"):
                st.markdown(f"**Methodology**\n\n{summary['methods']}")
        with sc2:
            if summary.get("results"):
                st.markdown("**Key Results**")
                for r in summary["results"]:
                    st.markdown(f"• {r}")
            if summary.get("conclusion"):
                st.success(summary["conclusion"])

        if summary.get("limitations"):
            with st.expander("⚠️ Limitations"):
                for lim in summary["limitations"]:
                    st.markdown(f"• {lim}")

        # Slide export
        st.markdown(section_title_html("Export to Slides"), unsafe_allow_html=True)
        slide_title = st.text_input(
            "Presentation title",
            value=(pdf_title or "Research Summary")[:120],
            key="slide_title",
        )
        if st.button("🎞️ Generate PowerPoint", use_container_width=True, key="gen_pptx"):
            with st.spinner("Building slides…"):
                pptx_bytes = generate_slides(slide_title, pdf_sections, ai_summary=summary)
            if pptx_bytes:
                st.download_button(
                    label="⬇️ Download .pptx",
                    data=pptx_bytes,
                    file_name=f"{slide_title[:40].replace(' ', '_')}.pptx",
                    mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
                    type="primary",
                    use_container_width=True,
                )
            else:
                st.error("Slide generation failed — python-pptx may not be installed yet.")


# ── Chat ──────────────────────────────────────────────────────────────────────

st.markdown(section_title_html("Chat"), unsafe_allow_html=True)
ch_col, cl_col = st.columns([8, 1])
with cl_col:
    if st.session_state.chat_history and st.button("🗑️ Clear", use_container_width=True):
        st.session_state.chat_history = []
        st.rerun()

for msg in st.session_state.chat_history:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])

if user_input := st.chat_input("Ask about your research, paper, or dataset…"):
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
            response, error = get_ai_response(req.message, paper,
                                              file_context=file_context_for_chat)
        if response:
            st.write(response)
            st.session_state.chat_history.append({"role": "assistant", "content": response})
        else:
            st.warning(f"⚠️ {error}")
    st.rerun()


# ── Footer ────────────────────────────────────────────────────────────────────
st.divider()
st.markdown(footer_html("Scientific analysis engine — statistics · charts · AI"),
            unsafe_allow_html=True)
