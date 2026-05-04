"""
ORC Research Assistant — Scientific Analysis Engine
Tab 1: Paper Analysis (Q&A + structured insight)
Tab 2: Analyze Dataset (CSV / Excel → stats + charts + AI explanation)
Tab 3: Read Paper (PDF → AI summary + PowerPoint export)
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
    except ImportError as e:
        return None, "AI library not available"


def _rate_check(key: str, max_req: int = 20) -> tuple:
    sid = st.session_state.get("session_token", "default")
    allowed, wait = rate_limiter.is_allowed(f"ai_{sid}_{key}", max_req, 60)
    if allowed:
        rate_limiter.record_attempt(f"ai_{sid}_{key}")
    return allowed, wait


def _call_ai(system: str, user: str, json_mode: bool = False,
             temperature: float = 0.5, max_tokens: int = 1800) -> tuple:
    """Low-level AI call. Returns (response_text, error)."""
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


# ── Paper helpers (Tab 1) ─────────────────────────────────────────────────────

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


def get_ai_response(message: str, paper: dict | None = None) -> tuple:
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
    except Exception as e:
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
    except Exception as e:
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


# ── Dataset AI analysis (Tab 2) ───────────────────────────────────────────────

def ai_analyze_dataset(df, user_question: str = "") -> tuple:
    """Ask AI to decide the best analysis for the dataset. Returns (plan_dict, error)."""
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
    user = f"Dataset info:\n{ctx}\n\nUser question: {q}"
    text, err = _call_ai(system, user, json_mode=True, temperature=0.2)
    if err or not text:
        return None, err
    try:
        plan = json.loads(text)
        return plan, None
    except Exception:
        return None, "Could not parse AI analysis plan"


def ai_explain_results(results: dict, analysis_type: str) -> str:
    """Ask the AI to explain statistical results in plain English."""
    system = (
        "You are an expert statistician. Explain the following statistical results "
        "clearly and concisely in plain English for a non-specialist researcher. "
        "Be specific about what the numbers mean."
    )
    user = f"Analysis type: {analysis_type}\nResults: {json.dumps(results, default=str)}"
    text, _ = _call_ai(system, user, temperature=0.4, max_tokens=600)
    return text or "Could not generate explanation."


# ── PDF AI summary (Tab 3) ────────────────────────────────────────────────────

def ai_summarize_paper(sections: dict) -> tuple:
    """AI-generated structured summary of a PDF paper. Returns (summary_dict, error)."""
    prompt_text = build_ai_prompt(sections)
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
    text, err = _call_ai(system, prompt_text, json_mode=True, temperature=0.3, max_tokens=1200)
    if err or not text:
        return None, err
    try:
        return json.loads(text), None
    except Exception:
        return None, "Could not parse AI summary"


# ── Session state ─────────────────────────────────────────────────────────────

for key, val in [("chat_history", []), ("pending_action", None),
                 ("analysis_df", None), ("analysis_plan", None)]:
    if key not in st.session_state:
        st.session_state[key] = val

# ── Page ──────────────────────────────────────────────────────────────────────

st.markdown(hero_html("🔬 AI Research Assistant",
                      "Scientific analysis engine — papers, datasets, and AI-powered insights"),
            unsafe_allow_html=True)

api_key = (
    get_secret("AI_API_KEY") or get_secret("GROQ_API_KEY")
    or get_secret("GROQ_API") or get_secret("GROQ_TOKEN")
)
if not api_key:
    st.error("AI service not configured. Add an AI_API_KEY secret.")
    st.stop()

tab1, tab2, tab3 = st.tabs(["📚 Paper Analysis", "📊 Analyze Dataset", "📄 Read PDF Paper"])


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — Paper Analysis
# ══════════════════════════════════════════════════════════════════════════════
with tab1:
    paper = st.session_state.get("selected_paper")

    if paper:
        citations = paper.get("citation_count", 0) or 0
        safe_title   = escape(str(paper.get("title", "Unknown")))
        safe_journal = escape(str(paper.get("journal_name", "")))
        c1, c2 = st.columns([6, 1])
        with c1:
            st.markdown(
                f'<div class="orc-card" style="border-left:4px solid {colors["accent"]};padding:1rem 1.25rem">'
                f'<div style="font-weight:600;font-size:0.95rem">{safe_title}</div>'
                f'<div style="font-size:0.8rem;color:{colors["text2"]};margin-top:0.2rem">'
                f'📰 {safe_journal} · {paper.get("publication_year", "")} · {citations:,} citations</div>'
                f'</div>', unsafe_allow_html=True)
        with c2:
            st.write("")
            if st.button("✕ Clear", use_container_width=True):
                st.session_state.selected_paper = None
                st.rerun()
    else:
        st.info("Go to **Publications** and click Analyze on any paper to set context.")

    # Quick action buttons
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

    # Chat
    st.markdown(section_title_html("Chat"), unsafe_allow_html=True)
    ch_col, cl_col = st.columns([6, 1])
    with cl_col:
        if st.session_state.chat_history and st.button("🗑️ Clear", use_container_width=True):
            st.session_state.chat_history = []
            st.rerun()

    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    if user_input := st.chat_input("Ask about your research…"):
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
        st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — Dataset Analysis
# ══════════════════════════════════════════════════════════════════════════════
with tab2:
    st.markdown(hero_html("📊 Scientific Dataset Analysis",
                          "Upload any CSV or Excel file — AI decides the best statistical test"),
                unsafe_allow_html=True)

    uploaded = st.file_uploader(
        "Upload your dataset",
        type=["csv", "xlsx", "xls"],
        help="CSV or Excel file — any domain (clinical, social, biological, etc.)",
        key="dataset_upload",
    )

    if uploaded:
        file_bytes = uploaded.read()
        df, err = load_file(file_bytes, uploaded.name)

        if err:
            st.error(f"❌ {err}")
        else:
            st.session_state.analysis_df = df
            info = describe_dataset(df)

            # ── Data overview ──────────────────────────────────────────────
            st.markdown(section_title_html("Dataset Overview"), unsafe_allow_html=True)
            ov1, ov2, ov3, ov4 = st.columns(4)
            for col, icon, val, lbl in [
                (ov1, "📋", f"{info['rows']:,}",   "Rows"),
                (ov2, "📌", str(info['columns']),  "Columns"),
                (ov3, "🔢", str(len(info['numeric_columns'])),     "Numeric"),
                (ov4, "⚠️", str(info['missing_values']), "Missing"),
            ]:
                col.metric(lbl, val)

            with st.expander("🔍 Preview (first 10 rows)"):
                st.dataframe(df.head(10), use_container_width=True)

            if info["numeric_columns"]:
                with st.expander("📈 Descriptive Statistics"):
                    st.dataframe(
                        df[info["numeric_columns"]].describe().round(3),
                        use_container_width=True
                    )

            # ── Distribution grid ──────────────────────────────────────────
            if info["numeric_columns"]:
                with st.expander("📊 Variable Distributions"):
                    fig = distribution_grid(df, info["numeric_columns"])
                    st.plotly_chart(fig, use_container_width=True)

            # ── AI analysis plan ───────────────────────────────────────────
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
                atype = plan.get("analysis_type", "descriptive")
                reasoning = plan.get("reasoning", "")
                plain = plan.get("plain_english", "")
                cols_used  = plan.get("columns", info["numeric_columns"][:2])
                target_col = plan.get("target_column", "")
                group_col  = plan.get("group_column", "")
                chart_hint = plan.get("chart_type", "")

                # Validate columns exist
                cols_used  = [c for c in cols_used  if c in df.columns]
                target_col = target_col if target_col in df.columns else ""
                group_col  = group_col  if group_col  in df.columns else ""

                st.markdown(
                    f'<div class="orc-card" style="border-left:4px solid {colors["accent"]};padding:0.9rem 1.2rem">'
                    f'<div style="font-weight:600;font-size:0.85rem">🧠 AI chose: <code>{atype}</code></div>'
                    f'<div style="font-size:0.82rem;color:{colors["text2"]};margin-top:0.25rem">{reasoning}</div>'
                    f'<div style="font-size:0.82rem;color:{colors["text2"]};margin-top:0.15rem">{plain}</div>'
                    f'</div>', unsafe_allow_html=True)

                results = {}

                # ── Run the chosen analysis ───────────────────────────────
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
                            fig = regression_scatter(df, feats[0], target_col)
                            st.plotly_chart(fig, use_container_width=True)
                        if "error" not in results:
                            rc1, rc2, rc3 = st.columns(3)
                            rc1.metric("R²", results.get("r_squared", "—"))
                            rc2.metric("Adj. R²", results.get("adj_r_squared", "—"))
                            rc3.metric("F p-value", results.get("p_value_f", "—"))

                elif atype == "t_test" and len(cols_used) >= 2:
                    s1 = df[cols_used[0]].dropna()
                    s2 = df[cols_used[1]].dropna()
                    results = t_test_independent(s1, s2, cols_used[0], cols_used[1])
                    tc1, tc2 = st.columns(2)
                    tc1.metric("t-statistic", results.get("t_statistic", "—"))
                    tc2.metric("p-value", results.get("p_value", "—"))
                    if results.get("significant"):
                        st.success(results.get("interpretation", ""))
                    else:
                        st.info(results.get("interpretation", ""))

                elif atype == "anova" and cols_used and group_col:
                    val_col = cols_used[0] if cols_used[0] != group_col else (cols_used[1] if len(cols_used) > 1 else "")
                    if val_col:
                        results = one_way_anova(df, val_col, group_col)
                        ac1, ac2 = st.columns(2)
                        ac1.metric("F-statistic", results.get("f_statistic", "—"))
                        ac2.metric("p-value", results.get("p_value", "—"))
                        if results.get("group_means"):
                            import pandas as _pd
                            st.dataframe(_pd.DataFrame.from_dict(
                                results["group_means"], orient="index", columns=[val_col]
                            ), use_container_width=True)
                        msg_fn = st.success if results.get("significant") else st.info
                        msg_fn(results.get("interpretation", ""))

                elif atype == "chi_square" and len(cols_used) >= 2:
                    results = chi_square(df, cols_used[0], cols_used[1])
                    cc1, cc2 = st.columns(2)
                    cc1.metric("χ² statistic", results.get("chi2_statistic", "—"))
                    cc2.metric("p-value", results.get("p_value", "—"))
                    msg_fn = st.success if results.get("significant") else st.info
                    msg_fn(results.get("interpretation", ""))

                else:
                    # Descriptive fallback
                    if info["numeric_columns"]:
                        st.dataframe(
                            df[info["numeric_columns"]].describe().round(3),
                            use_container_width=True
                        )

                # ── Auto chart ────────────────────────────────────────────
                if cols_used:
                    x = cols_used[0]
                    y = cols_used[1] if len(cols_used) > 1 else None
                    if atype not in ("correlation",):
                        fig = auto_chart(df, x, y, hint=chart_hint,
                                         color=group_col if group_col else None)
                        st.plotly_chart(fig, use_container_width=True)

                # ── AI explanation ────────────────────────────────────────
                if results and "error" not in results:
                    with st.spinner("AI is writing the explanation…"):
                        explanation = ai_explain_results(results, atype)
                    st.markdown(section_title_html("AI Interpretation"), unsafe_allow_html=True)
                    st.markdown(
                        f'<div class="orc-card" style="padding:1rem 1.25rem;'
                        f'border-left:3px solid {colors["accent2"]}">'
                        f'<div style="font-size:0.88rem;line-height:1.75">{explanation}</div>'
                        f'</div>', unsafe_allow_html=True)

            # ── Manual analysis controls ──────────────────────────────────
            st.markdown(section_title_html("Manual Controls"), unsafe_allow_html=True)
            mc1, mc2 = st.columns(2)

            with mc1:
                num_cols = info["numeric_columns"]
                if len(num_cols) >= 2:
                    sel_corr = st.multiselect(
                        "Correlation — select columns",
                        num_cols, default=num_cols[:min(4, len(num_cols))],
                        key="manual_corr",
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
                        default=[c for c in num_cols if c != target][:2],
                        key="reg_feats",
                    )
                    if feats and st.button("📉 Run Regression"):
                        res = linear_regression(df, target, feats)
                        if "error" in res:
                            st.error(res["error"])
                        else:
                            st.json(res)
                            if len(feats) == 1:
                                st.plotly_chart(
                                    regression_scatter(df, feats[0], target),
                                    use_container_width=True
                                )

    elif not uploaded and st.session_state.get("analysis_df") is not None:
        st.info("Upload a file to start a new analysis.")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — PDF Paper Reader
# ══════════════════════════════════════════════════════════════════════════════
with tab3:
    st.markdown(hero_html("📄 Research Paper Reader",
                          "Upload any PDF paper — AI extracts, summarizes, and prepares slides"),
                unsafe_allow_html=True)

    pdf_file = st.file_uploader(
        "Upload a research paper (PDF)",
        type=["pdf"],
        help="Any research paper, thesis, or report in PDF format",
        key="pdf_upload",
    )

    if pdf_file:
        pdf_bytes = pdf_file.read()

        with st.spinner("Extracting text from PDF…"):
            text, extract_err = extract_text(pdf_bytes)

        if extract_err:
            st.error(f"❌ {extract_err}")
            st.info(
                "**Fix:** Add `PyMuPDF` to your Space requirements. "
                "It is already in `requirements.txt` — trigger a rebuild."
            )
        elif not text.strip():
            st.warning("⚠️ No text found. The PDF may be scanned (image-based). "
                       "OCR is required for image PDFs.")
        else:
            meta     = extract_metadata(text)
            sections = extract_sections(text)

            # Paper info
            st.markdown(section_title_html("Paper Detected"), unsafe_allow_html=True)
            st.markdown(
                f'<div class="orc-card" style="padding:0.9rem 1.25rem">'
                f'<div style="font-weight:600;font-size:0.93rem">{escape(meta["title"][:150])}</div>'
                f'<div style="font-size:0.78rem;color:{colors["muted"]};margin-top:0.2rem">'
                f'{len(text):,} characters extracted · {len(sections)} sections detected'
                + (f" · DOI: {meta['doi']}" if meta.get("doi") else "")
                + '</div></div>', unsafe_allow_html=True)

            # Raw sections
            if sections:
                with st.expander("📑 Extracted Sections"):
                    for name, content in sections.items():
                        st.markdown(f"**{name.title()}**")
                        st.caption(content[:400] + "…")

            # AI Summary
            st.markdown(section_title_html("AI Summary"), unsafe_allow_html=True)
            if st.button("🧠 Generate AI Summary", type="primary", use_container_width=True,
                         key="gen_summary"):
                with st.spinner("AI is reading the paper…"):
                    summary, sum_err = ai_summarize_paper(sections or {"full_text": text[:3000]})

                if sum_err:
                    st.error(f"❌ {sum_err}")
                else:
                    st.session_state["pdf_summary"] = summary
                    st.session_state["pdf_title"]   = meta["title"]
                    st.session_state["pdf_sections"] = sections

            summary = st.session_state.get("pdf_summary")
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
                        for l in summary["limitations"]:
                            st.markdown(f"• {l}")

                # ── Ask a question about the paper ────────────────────────
                st.markdown(section_title_html("Ask About This Paper"), unsafe_allow_html=True)
                pdf_q = st.text_input("Your question", key="pdf_question",
                                      placeholder="What statistical methods were used?")
                if pdf_q and st.button("Ask AI", key="pdf_ask"):
                    context = build_ai_prompt(sections or {}, max_chars=2500)
                    system  = (
                        "You are an expert research analyst. Answer questions about "
                        "the following research paper accurately and concisely.\n\n"
                        f"PAPER:\n{context}"
                    )
                    with st.spinner("Thinking…"):
                        answer, _ = _call_ai(system, pdf_q, temperature=0.4, max_tokens=800)
                    if answer:
                        st.markdown(answer)

                # ── Slide download ────────────────────────────────────────
                st.markdown(section_title_html("Export to Slides"), unsafe_allow_html=True)
                slide_title = st.text_input(
                    "Presentation title",
                    value=st.session_state.get("pdf_title", "Research Summary")[:120],
                    key="slide_title",
                )
                if st.button("🎞️ Generate PowerPoint", use_container_width=True, key="gen_pptx"):
                    with st.spinner("Building slides…"):
                        pptx_bytes = generate_slides(
                            slide_title,
                            st.session_state.get("pdf_sections", {}),
                            ai_summary=summary,
                        )
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
                        st.error("Slide generation failed — python-pptx may not be installed. "
                                 "It is in requirements.txt; trigger a Space rebuild.")

# ── Footer ────────────────────────────────────────────────────────────────────
st.divider()
st.markdown(footer_html("Scientific analysis engine — pandas · scipy · statsmodels · AI"), unsafe_allow_html=True)
