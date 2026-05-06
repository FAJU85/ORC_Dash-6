"""
ORC Research Dashboard - Genomic Analysis
DNA sequence and variant analysis via a genomic prediction service.
"""

import sys
import os
import html
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import requests

from utils.security import get_secret, log_audit, log_error, RateLimiter
from utils.styles import (
    apply_styles, get_theme, hero_html, section_title_html,
    footer_html, render_navbar, DARK, LIGHT,
)

apply_styles()
render_navbar()

colors = DARK if get_theme() == "dark" else LIGHT
rate_limiter = RateLimiter()

# ── API config (read from secrets) ────────────────────────────────────────────
_API_KEY      = get_secret("ALPHA_GENOME_API_KEY") or ""
_API_BASE_URL = get_secret("ALPHA_GENOME_BASE_URL") or "https://alphagenomic.googleapis.com/v1"
_HEADERS      = {
    "Content-Type": "application/json",
    "Accept":       "application/json",
    "X-Goog-Api-Key": _API_KEY,
}

# ── Helpers ────────────────────────────────────────────────────────────────────

def _rate_guard(key: str) -> tuple[bool, int]:
    allowed, wait = rate_limiter.is_allowed(f"genome_{key}", max_attempts=10, window_seconds=60)
    if allowed:
        rate_limiter.record_attempt(f"genome_{key}")
    return allowed, wait


def _post(endpoint: str, body: dict) -> tuple[dict | None, str | None]:
    url = f"{_API_BASE_URL.rstrip('/')}/{endpoint.lstrip('/')}"
    try:
        resp = requests.post(url, headers=_HEADERS, json=body, timeout=30)
        if resp.status_code == 401:
            return None, "Invalid or missing API key — set **ALPHA_GENOME_API_KEY** in secrets."
        if resp.status_code == 400:
            detail = resp.json().get("error", {}).get("message", resp.text[:200])
            return None, f"Bad request: {detail}"
        resp.raise_for_status()
        return resp.json(), None
    except requests.Timeout:
        return None, "Request timed out — try a shorter sequence."
    except requests.RequestException as exc:
        log_error("genome_api", str(exc), page="Genomic Analysis")
        return None, f"Service unavailable: {exc}"


def _analyse_sequence(sequence: str, tasks: list[str]) -> tuple[dict | None, str | None]:
    allowed, wait = _rate_guard("sequence")
    if not allowed:
        return None, f"Rate limit — please wait {wait}s"
    body = {"sequence": sequence.upper(), "tasks": tasks}
    log_audit("genome_sequence", f"len={len(sequence)}")
    return _post("sequences:predict", body)


def _analyse_variant(
    chrom: str, pos: int, ref: str, alt: str,
    genome_build: str = "GRCh38",
) -> tuple[dict | None, str | None]:
    allowed, wait = _rate_guard("variant")
    if not allowed:
        return None, f"Rate limit — please wait {wait}s"
    body = {
        "genomeBuild": genome_build,
        "variants": [{"chromosome": chrom, "position": pos, "ref": ref, "alt": alt}],
    }
    log_audit("genome_variant", f"{chrom}:{pos}{ref}>{alt}")
    return _post("variants:predict", body)


def _analyse_region(
    chrom: str, start: int, end: int, genome_build: str = "GRCh38",
) -> tuple[dict | None, str | None]:
    allowed, wait = _rate_guard("region")
    if not allowed:
        return None, f"Rate limit — please wait {wait}s"
    body = {
        "genomeBuild": genome_build,
        "region": {"chromosome": chrom, "start": start, "end": end},
    }
    log_audit("genome_region", f"{chrom}:{start}-{end}")
    return _post("regions:predict", body)


def _validate_dna(seq: str) -> bool:
    return bool(seq) and all(c in "ACGTNacgtn" for c in seq)


def _render_track(label: str, value: float | None, unit: str = "", max_val: float = 1.0) -> None:
    if value is None:
        return
    pct = min(100, max(0, (value / max_val) * 100)) if max_val else 0
    bar_color = colors["accent"] if pct >= 50 else colors["muted"]
    st.markdown(
        f'<div style="margin-bottom:0.5rem">'
        f'  <div style="display:flex;justify-content:space-between;'
        f'       font-size:0.8rem;color:{colors["text2"]};margin-bottom:0.15rem">'
        f'    <span>{html.escape(label)}</span>'
        f'    <span style="color:{colors["text"]};font-weight:600">'
        f'    {value:.3f}{" " + html.escape(unit) if unit else ""}</span>'
        f'  </div>'
        f'  <div style="background:{colors["surface2"]};border-radius:4px;height:7px">'
        f'    <div style="width:{pct:.1f}%;background:{bar_color};'
        f'         border-radius:4px;height:7px;transition:width .3s"></div>'
        f'  </div>'
        f'</div>',
        unsafe_allow_html=True,
    )


# ── Page ───────────────────────────────────────────────────────────────────────

st.markdown(
    hero_html("🔬 Genomic Analysis",
              "Predict regulatory activity, variant effects, and expression signals from DNA"),
    unsafe_allow_html=True,
)

if not _API_KEY:
    st.warning(
        "⚠️ No API key configured. "
        "Add **ALPHA_GENOME_API_KEY** (and optionally **ALPHA_GENOME_BASE_URL**) to your secrets."
    )

# ── Mode tabs ──────────────────────────────────────────────────────────────────
tab_seq, tab_var, tab_reg = st.tabs(
    ["🧬 Sequence", "🔀 Variant Effect", "📍 Genomic Region"]
)

# ═══════════════════════════════════════════════════════════════════════════════
# Tab 1 — Raw sequence prediction
# ═══════════════════════════════════════════════════════════════════════════════
with tab_seq:
    st.markdown(section_title_html("DNA Sequence Analysis"), unsafe_allow_html=True)
    st.caption(
        "Paste a raw DNA sequence (A/C/G/T). "
        "Recommended length: 512–131 072 bases."
    )

    seq_input = st.text_area(
        "DNA sequence",
        placeholder="ATCGATCGATCG…",
        height=120,
        label_visibility="collapsed",
    )

    task_opts = {
        "Gene expression":          "GENE_EXPRESSION",
        "Chromatin accessibility":  "CHROMATIN_ACCESSIBILITY",
        "Histone modification":     "HISTONE_MODIFICATION",
        "Transcription factor binding": "TF_BINDING",
        "3D genome contacts":       "GENOME_CONTACTS",
    }
    chosen_tasks = st.multiselect(
        "Prediction targets",
        list(task_opts.keys()),
        default=["Gene expression", "Chromatin accessibility"],
    )

    if st.button("▶ Run Sequence Analysis", type="primary",
                 disabled=not _API_KEY or not seq_input.strip()):
        seq_clean = seq_input.strip().replace(" ", "").replace("\n", "")
        if not _validate_dna(seq_clean):
            st.error("❌ Sequence contains invalid characters. Use A, C, G, T, N only.")
        elif len(seq_clean) < 32:
            st.error("❌ Sequence too short (minimum 32 bases).")
        else:
            tasks_codes = [task_opts[t] for t in chosen_tasks]
            with st.spinner("Analysing sequence…"):
                result, err = _analyse_sequence(seq_clean, tasks_codes)
            if err:
                st.error(f"❌ {err}")
            else:
                st.success(f"✅ Analysis complete — {len(seq_clean):,} bases processed.")
                st.markdown(section_title_html("Predictions"), unsafe_allow_html=True)

                predictions = result.get("predictions", {})
                if not predictions:
                    with st.expander("📋 Raw response"):
                        st.json(result)
                else:
                    for task_label, task_key_code in task_opts.items():
                        task_data = predictions.get(task_key_code)
                        if not task_data:
                            continue
                        st.markdown(
                            f'<div style="font-size:0.78rem;font-weight:700;'
                            f'text-transform:uppercase;letter-spacing:0.08em;'
                            f'color:{colors["text2"]};margin:1rem 0 0.4rem">'
                            f'{html.escape(task_label)}</div>',
                            unsafe_allow_html=True,
                        )
                        if isinstance(task_data, dict):
                            for track, val in task_data.items():
                                if isinstance(val, (int, float)):
                                    _render_track(track, float(val))
                        elif isinstance(task_data, list):
                            st.line_chart(task_data, height=140)

                    with st.expander("📋 Full API response"):
                        st.json(result)

# ═══════════════════════════════════════════════════════════════════════════════
# Tab 2 — Variant effect prediction
# ═══════════════════════════════════════════════════════════════════════════════
with tab_var:
    st.markdown(section_title_html("Variant Effect Prediction"), unsafe_allow_html=True)
    st.caption(
        "Predict how a single nucleotide variant alters regulatory activity "
        "compared to the reference genome."
    )

    vc1, vc2, vc3 = st.columns([2, 1, 2])
    with vc1:
        var_chrom = st.text_input("Chromosome", placeholder="chr17", key="var_chrom")
    with vc2:
        var_build = st.selectbox("Genome build", ["GRCh38", "GRCh37"], key="var_build")
    with vc3:
        var_pos = st.number_input("Position (1-based)", min_value=1, step=1, key="var_pos")

    vr1, vr2 = st.columns(2)
    with vr1:
        var_ref = st.text_input("Reference allele", placeholder="A", key="var_ref",
                                max_chars=10)
    with vr2:
        var_alt = st.text_input("Alternate allele", placeholder="G", key="var_alt",
                                max_chars=10)

    if st.button("▶ Predict Variant Effect", type="primary",
                 disabled=not _API_KEY or not all([var_chrom, var_ref, var_alt])):
        chrom_clean = var_chrom.strip()
        ref_clean   = var_ref.strip().upper()
        alt_clean   = var_alt.strip().upper()
        if not _validate_dna(ref_clean) or not _validate_dna(alt_clean):
            st.error("❌ Alleles must contain only A, C, G, T.")
        else:
            with st.spinner(f"Predicting effect of {html.escape(chrom_clean)}:"
                            f"{int(var_pos)} {html.escape(ref_clean)}→{html.escape(alt_clean)}…"):
                result, err = _analyse_variant(
                    chrom_clean, int(var_pos), ref_clean, alt_clean, var_build
                )
            if err:
                st.error(f"❌ {err}")
            else:
                effect = result.get("variantEffect", {})
                score  = effect.get("score")
                label  = effect.get("interpretation", "")
                tracks = effect.get("trackDeltas", {})

                if score is not None:
                    col_a, col_b = st.columns(2)
                    col_a.metric("Effect score", f"{score:+.4f}")
                    col_b.metric("Interpretation", label or "—")

                if tracks:
                    st.markdown(section_title_html("Track Δ (alt − ref)"),
                                unsafe_allow_html=True)
                    for track, delta in tracks.items():
                        if isinstance(delta, (int, float)):
                            _render_track(track, float(delta), max_val=max(abs(delta), 1.0))

                with st.expander("📋 Full API response"):
                    st.json(result)

# ═══════════════════════════════════════════════════════════════════════════════
# Tab 3 — Genomic region analysis
# ═══════════════════════════════════════════════════════════════════════════════
with tab_reg:
    st.markdown(section_title_html("Genomic Region Analysis"), unsafe_allow_html=True)
    st.caption(
        "Predict regulatory signals across a genomic window "
        "(max recommended span: 131 072 bp)."
    )

    rc1, rc2, rc3 = st.columns([2, 1, 1])
    with rc1:
        reg_chrom = st.text_input("Chromosome", placeholder="chr17", key="reg_chrom")
    with rc2:
        reg_start = st.number_input("Start (bp)", min_value=1, step=1, key="reg_start")
    with rc3:
        reg_end   = st.number_input("End (bp)", min_value=2, step=1, value=131073,
                                    key="reg_end")
    reg_build = st.selectbox("Genome build", ["GRCh38", "GRCh37"], key="reg_build")

    if st.button("▶ Analyse Region", type="primary",
                 disabled=not _API_KEY or not reg_chrom.strip()):
        chrom_r = reg_chrom.strip()
        start_r = int(reg_start)
        end_r   = int(reg_end)
        span    = end_r - start_r
        if start_r >= end_r:
            st.error("❌ Start must be less than End.")
        elif span > 500_000:
            st.error("❌ Region too large (max 500 000 bp per request).")
        else:
            with st.spinner(f"Analysing {html.escape(chrom_r)}:{start_r:,}–{end_r:,} "
                            f"({span:,} bp)…"):
                result, err = _analyse_region(chrom_r, start_r, end_r, reg_build)
            if err:
                st.error(f"❌ {err}")
            else:
                tracks = result.get("tracks", {})
                if tracks:
                    st.markdown(section_title_html("Signal Tracks"), unsafe_allow_html=True)
                    for name, values in tracks.items():
                        st.caption(name)
                        if isinstance(values, list) and values:
                            st.area_chart(values, height=100)
                        elif isinstance(values, (int, float)):
                            _render_track(name, float(values))
                else:
                    st.info("No track data returned for this region.")
                    with st.expander("📋 Raw response"):
                        st.json(result)

                with st.expander("📋 Full API response"):
                    st.json(result)


# ── About ──────────────────────────────────────────────────────────────────────
with st.expander("ℹ️ About this integration"):
    st.markdown(
        f'<div style="font-size:0.87rem;color:{colors["text"]};line-height:1.75">'
        f'This page connects to a genomic prediction service that applies '
        f'deep learning to DNA sequences. It can predict gene expression levels, '
        f'chromatin accessibility, histone modifications, transcription factor '
        f'binding, and the regulatory impact of sequence variants — without '
        f'requiring wet-lab experiments.'
        f'<br><br>'
        f'<b>Sequence mode</b>: paste raw DNA and select prediction targets.<br>'
        f'<b>Variant mode</b>: supply chromosomal coordinates and alleles to '
        f'quantify a variant\'s regulatory effect (alt − ref delta).<br>'
        f'<b>Region mode</b>: query a chromosomal window to get per-position '
        f'signal tracks across multiple regulatory features.'
        f'<br><br>'
        f'Set <code>ALPHA_GENOME_API_KEY</code> and (optionally) '
        f'<code>ALPHA_GENOME_BASE_URL</code> in your deployment secrets to enable '
        f'live queries.'
        f'</div>',
        unsafe_allow_html=True,
    )

# ── Footer ─────────────────────────────────────────────────────────────────────
st.divider()
st.markdown(footer_html(), unsafe_allow_html=True)
