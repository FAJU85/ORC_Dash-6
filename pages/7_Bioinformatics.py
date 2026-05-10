"""
ORC Research Dashboard - Bioinformatics
Protein structure lookup and genomic sequence analysis in one place.
"""

import sys
import os
import html

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import requests

from utils.security import get_secret, log_audit, log_error, RateLimiter, is_admin_authenticated
from utils.hf_data import load_cms_content
from utils.styles import (
    apply_styles, get_theme, hero_html, section_title_html,
    footer_html, render_navbar, DARK, LIGHT,
)

apply_styles()
render_navbar()

colors      = DARK if get_theme() == "dark" else LIGHT
_cms = st.session_state.get("_cms_override") or load_cms_content()
rate_limiter = RateLimiter()

# ── Genomic analysis API config (from secrets) ────────────────────────────────
_GENOME_KEY      = get_secret("ALPHA_GENOME_API_KEY") or ""
_GENOME_BASE_URL = get_secret("ALPHA_GENOME_BASE_URL") or "https://alphagenomic.googleapis.com/v1"
_GENOME_HEADERS  = {
    "Content-Type":   "application/json",
    "Accept":         "application/json",
    "X-Goog-Api-Key": _GENOME_KEY,
}

# ── Protein structure endpoints (no key required) ─────────────────────────────
_AF_ENTRY       = "https://alphafold.ebi.ac.uk/api/prediction/{uid}"
_UNIPROT_SEARCH = "https://rest.uniprot.org/uniprotkb/search?query={q}&format=json&size=5"

# ══════════════════════════════════════════════════════════════════════════════
# Shared helpers
# ══════════════════════════════════════════════════════════════════════════════

def _rate_guard(key: str, max_req: int = 10) -> tuple[bool, int]:
    allowed, wait = rate_limiter.is_allowed(key, max_attempts=max_req, window_seconds=60)
    if allowed:
        rate_limiter.record_attempt(key)
    return allowed, wait


def _render_track(label: str, value: float, max_val: float = 1.0, unit: str = "") -> None:
    pct       = min(100, max(0, (value / max_val) * 100)) if max_val else 0
    bar_color = colors["accent"] if pct >= 50 else colors["muted"]
    st.markdown(
        f'<div style="margin-bottom:0.5rem">'
        f'  <div style="display:flex;justify-content:space-between;'
        f'       font-size:0.8rem;color:{colors["text2"]};margin-bottom:0.15rem">'
        f'    <span>{html.escape(label)}</span>'
        f'    <span style="color:{colors["text"]};font-weight:600">'
        f'      {value:.3f}{" " + html.escape(unit) if unit else ""}'
        f'    </span>'
        f'  </div>'
        f'  <div style="background:{colors["surface2"]};border-radius:4px;height:7px">'
        f'    <div style="width:{pct:.1f}%;background:{bar_color};'
        f'         border-radius:4px;height:7px;transition:width .3s"></div>'
        f'  </div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def _link_btn(label: str, url: str, primary: bool = False) -> str:
    bg     = colors["accent"] if primary else colors["surface2"]
    color  = "#ffffff"        if primary else colors["text"]
    border = f"border:1px solid {colors['border']};" if not primary else ""
    return (
        f'<a href="{html.escape(url)}" target="_blank" rel="noopener" '
        f'style="display:inline-flex;align-items:center;gap:0.3rem;'
        f'background:{bg};color:{color};{border}'
        f'border-radius:8px;padding:0.4rem 0.9rem;'
        f'text-decoration:none;font-size:0.83rem;font-weight:{"600" if primary else "500"}">'
        f'{label}</a>'
    )


# ══════════════════════════════════════════════════════════════════════════════
# Protein structure helpers
# ══════════════════════════════════════════════════════════════════════════════

def _fetch_structure(uniprot_id: str) -> tuple[list | None, str | None]:
    uid = uniprot_id.strip().upper()
    ok, wait = _rate_guard(f"af_{uid}", max_req=5)
    if not ok:
        return None, f"Rate limit — please wait {wait}s"
    try:
        resp = requests.get(
            _AF_ENTRY.format(uid=uid),
            timeout=15,
            headers={"Accept": "application/json"},
        )
        if resp.status_code == 404:
            return None, f"No structure entry found for **{html.escape(uid)}**."
        resp.raise_for_status()
        log_audit("structure_lookup", uid[:10])
        return resp.json(), None
    except requests.RequestException as exc:
        log_error("structure_error", str(exc), page="Bioinformatics")
        return None, "Structure database unavailable — please try again later."


def _search_uniprot(query: str) -> list[dict]:
    try:
        resp = requests.get(
            _UNIPROT_SEARCH.format(q=requests.utils.quote(query)),
            timeout=10,
            headers={"Accept": "application/json"},
        )
        resp.raise_for_status()
        out = []
        for r in resp.json().get("results", []):
            pid   = r.get("primaryAccession", "")
            names = r.get("proteinDescription", {})
            rec   = names.get("recommendedName") or (names.get("submissionNames") or [{}])[0]
            pname = rec.get("fullName", {}).get("value", "") if rec else ""
            genes = r.get("genes", [])
            gene  = genes[0].get("geneName", {}).get("value", "") if genes else ""
            org   = r.get("organism", {}).get("scientificName", "")
            out.append({"id": pid, "protein": pname, "gene": gene, "organism": org})
        return out
    except Exception as exc:
        log_error("uniprot_search", str(exc), page="Bioinformatics")
        return []


def _conf_color(score: float) -> str:
    if score >= 90: return "#00c7ff"
    if score >= 70: return "#65cb5e"
    if score >= 50: return "#ffdb13"
    return "#ff7d45"


def _conf_label(score: float) -> str:
    if score >= 90: return "Very high"
    if score >= 70: return "Confident"
    if score >= 50: return "Low"
    return "Very low"


# ══════════════════════════════════════════════════════════════════════════════
# Genomic analysis helpers
# ══════════════════════════════════════════════════════════════════════════════

def _genome_post(endpoint: str, body: dict) -> tuple[dict | None, str | None]:
    url = f"{_GENOME_BASE_URL.rstrip('/')}/{endpoint.lstrip('/')}"
    try:
        resp = requests.post(url, headers=_GENOME_HEADERS, json=body, timeout=30)
        if resp.status_code == 401:
            return None, (
                "Authentication failed. Contact the system administrator."
                if not is_admin_authenticated()
                else "Authentication failed — check ALPHA_GENOME_API_KEY in your secrets."
            )
        if resp.status_code == 403:
            return None, (
                "Access denied. Contact the system administrator."
                if not is_admin_authenticated()
                else "Access denied — API key lacks permission for this endpoint."
            )
        if resp.status_code == 404:
            return None, (
                "Service endpoint not found. Contact the system administrator."
                if not is_admin_authenticated()
                else "Service endpoint not found — verify ALPHA_GENOME_BASE_URL in your secrets."
            )
        if resp.status_code == 400:
            try:
                detail = resp.json().get("error", {}).get("message", resp.text[:200])
            except (ValueError, KeyError):
                detail = resp.text[:200]
            return None, f"Bad request: {detail}"
        resp.raise_for_status()
        return resp.json(), None
    except requests.Timeout:
        return None, "Request timed out — try a shorter sequence."
    except requests.ConnectionError:
        return None, (
            "Cannot reach the genomic analysis service. Please try again later."
            if not is_admin_authenticated()
            else "Cannot reach the service — check your network connection or ALPHA_GENOME_BASE_URL."
        )
    except requests.RequestException as exc:
        log_error("genome_api", str(exc), page="Bioinformatics")
        return None, f"Service unavailable: {exc}"


def _validate_dna(seq: str) -> bool:
    return bool(seq) and all(c in "ACGTNacgtn" for c in seq)


def _analyse_sequence(sequence: str, tasks: list[str]) -> tuple[dict | None, str | None]:
    ok, wait = _rate_guard("genome_seq")
    if not ok:
        return None, f"Rate limit — please wait {wait}s"
    log_audit("genome_sequence", f"len={len(sequence)}")
    return _genome_post("sequences:predict", {"sequence": sequence.upper(), "tasks": tasks})


def _analyse_variant(chrom: str, pos: int, ref: str, alt: str,
                     build: str = "GRCh38") -> tuple[dict | None, str | None]:
    ok, wait = _rate_guard("genome_var")
    if not ok:
        return None, f"Rate limit — please wait {wait}s"
    log_audit("genome_variant", f"{chrom}:{pos}{ref}>{alt}")
    return _genome_post("variants:predict", {
        "genomeBuild": build,
        "variants": [{"chromosome": chrom, "position": pos, "ref": ref, "alt": alt}],
    })


def _analyse_region(chrom: str, start: int, end: int,
                    build: str = "GRCh38") -> tuple[dict | None, str | None]:
    ok, wait = _rate_guard("genome_reg")
    if not ok:
        return None, f"Rate limit — please wait {wait}s"
    log_audit("genome_region", f"{chrom}:{start}-{end}")
    return _genome_post("regions:predict", {
        "genomeBuild": build,
        "region": {"chromosome": chrom, "start": start, "end": end},
    })


# ══════════════════════════════════════════════════════════════════════════════
# Page
# ══════════════════════════════════════════════════════════════════════════════

_bio_hero = _cms.get("bioinformatics_hero", {})
if _bio_hero.get("enabled", True):
    st.markdown(
        hero_html(
            _bio_hero.get("title", "").strip() or "🧬 Bioinformatics",
            _bio_hero.get("subtitle", "").strip() or "Protein structure prediction · Genomic sequence & variant analysis",
        ),
        unsafe_allow_html=True,
    )

tab_protein, tab_genomics = st.tabs(["🔬 Protein Structure", "🧪 Genomic Analysis"])


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — Protein Structure
# ══════════════════════════════════════════════════════════════════════════════
with tab_protein:
    st.markdown(section_title_html("Protein Lookup"), unsafe_allow_html=True)

    sc1, sc2 = st.columns([3, 2])
    with sc1:
        protein_query = st.text_input(
            "Search by protein / gene name",
            placeholder="e.g. BRCA2, p53, insulin…",
        )
    with sc2:
        uniprot_id = st.text_input(
            "UniProt Accession ID",
            placeholder="e.g. P04637, P38398…",
        )

    # Name → ID search
    if protein_query and not uniprot_id:
        with st.spinner("Searching protein database…"):
            hits = _search_uniprot(protein_query)
        if hits:
            options = {
                f"{h['id']} — {h['protein']} ({h['gene']}) · {h['organism']}": h["id"]
                for h in hits
            }
            chosen = st.selectbox("Select entry", list(options.keys()),
                                  label_visibility="collapsed")
            if chosen:
                uniprot_id = options[chosen]
        else:
            st.info("No results found for that query.")

    if st.button("🔍 Fetch Structure", type="primary", disabled=not uniprot_id.strip(),
                 key="btn_fetch_structure"):
        uid = uniprot_id.strip().upper()
        with st.spinner(f"Fetching structure data for **{html.escape(uid)}**…"):
            entries, err = _fetch_structure(uid)

        if err:
            st.error(f"❌ {err}")
        elif entries:
            for entry in entries:
                gene_name    = entry.get("gene", "") or ""
                protein_name = entry.get("uniprotDescription", "") or entry.get("uniprotId", uid)
                organism     = entry.get("organismScientificName", "")
                model_url    = entry.get("pdbUrl", "")
                cif_url      = entry.get("cifUrl", "")
                pae_url      = entry.get("paeImageUrl", "")
                mean_conf    = float(entry.get("confidenceAvgLocalScore", 0) or 0)
                conf_version = entry.get("latestVersion", "")
                seq          = entry.get("uniprotSequence", "")
                seq_len      = len(seq) if seq else 0

                # Header card
                st.markdown(
                    f'<div class="orc-card" style="border-left:4px solid {colors["accent"]}">'
                    f'  <div style="font-size:1.05rem;font-weight:700;color:{colors["text"]}">'
                    f'    {html.escape(protein_name)}</div>'
                    f'  <div style="font-size:0.82rem;color:{colors["text2"]};margin-top:0.2rem">'
                    f'    🧬 {html.escape(gene_name) or "—"} &nbsp;·&nbsp; '
                    f'    <i>{html.escape(organism)}</i> &nbsp;·&nbsp; '
                    f'    ID: <code>{html.escape(uid)}</code>'
                    f'    {(" &nbsp;·&nbsp; v" + html.escape(str(conf_version))) if conf_version else ""}'
                    f'  </div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

                # Metrics
                m1, m2, m3 = st.columns(3)
                m1.metric("Mean pLDDT", f"{mean_conf:.1f}")
                m2.metric("Confidence", _conf_label(mean_conf))
                m3.metric("Sequence length", f"{seq_len:,} aa" if seq_len else "N/A")

                # Confidence legend
                st.markdown(
                    f'<div style="font-size:0.77rem;color:{colors["text2"]};margin:0.25rem 0 0.75rem">'
                    f'pLDDT: <span style="color:#00c7ff">■ ≥90 Very high</span> &nbsp;'
                    f'<span style="color:#65cb5e">■ ≥70 Confident</span> &nbsp;'
                    f'<span style="color:#ffdb13">■ ≥50 Low</span> &nbsp;'
                    f'<span style="color:#ff7d45">■ &lt;50 Very low</span></div>',
                    unsafe_allow_html=True,
                )

                # PAE image
                if pae_url:
                    st.markdown(section_title_html("Predicted Aligned Error (PAE)"),
                                unsafe_allow_html=True)
                    img_col, desc_col = st.columns([1, 2])
                    with img_col:
                        st.image(pae_url,
                                 caption="PAE matrix — lower = more confident relative position")
                    with desc_col:
                        st.markdown(
                            f'<div style="font-size:0.85rem;color:{colors["text"]};line-height:1.7">'
                            f'The <b>Predicted Aligned Error</b> matrix shows confidence in the '
                            f'relative position of every pair of residues. '
                            f'Low values (dark green) indicate high confidence. '
                            f'High-PAE regions often correspond to flexible linkers or '
                            f'independently folding domains.'
                            f'</div>',
                            unsafe_allow_html=True,
                        )

                # Downloads
                st.markdown(section_title_html("Downloads"), unsafe_allow_html=True)
                dl1, dl2 = st.columns(2)
                with dl1:
                    if model_url:
                        st.markdown(_link_btn("⬇️ PDB Structure", model_url, primary=True),
                                    unsafe_allow_html=True)
                with dl2:
                    if cif_url:
                        st.markdown(_link_btn("⬇️ mmCIF Structure", cif_url),
                                    unsafe_allow_html=True)

                with st.expander("📋 Full response"):
                    st.json(entry)

                st.markdown('<div style="margin-bottom:1.5rem"></div>', unsafe_allow_html=True)

    with st.expander("ℹ️ About protein structure prediction"):
        st.markdown(
            f'<div style="font-size:0.87rem;color:{colors["text"]};line-height:1.75">'
            f'This tab queries a public protein structure database containing over '
            f'200 million predicted structures. Structures are looked up by protein '
            f'accession ID. You can also search by gene or protein name to find '
            f'the correct identifier.'
            f'<br><br>'
            f'<b>pLDDT</b> (predicted local distance difference test) is a per-residue '
            f'confidence metric (0–100). Values below 50 often indicate intrinsically '
            f'disordered regions.'
            f'</div>',
            unsafe_allow_html=True,
        )


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — Genomic Analysis
# ══════════════════════════════════════════════════════════════════════════════
with tab_genomics:

    if not _GENOME_KEY:
        if is_admin_authenticated():
            st.warning(
                "⚠️ Genomic analysis is not configured — "
                "add ALPHA_GENOME_API_KEY (and optionally ALPHA_GENOME_BASE_URL) to your secrets."
            )
        else:
            st.info("⚠️ Genomic analysis is not available. Contact the administrator to enable this feature.")

    seq_tab, var_tab, reg_tab = st.tabs(
        ["🧬 Sequence", "🔀 Variant Effect", "📍 Genomic Region"]
    )

    # ── Sequence ──────────────────────────────────────────────────────────────
    with seq_tab:
        st.markdown(section_title_html("DNA Sequence Analysis"), unsafe_allow_html=True)
        st.caption("Paste a raw DNA sequence (A/C/G/T). Recommended length: 512 – 131 072 bases.")

        seq_input = st.text_area(
            "DNA sequence", placeholder="ATCGATCGATCG…",
            height=120, label_visibility="collapsed", key="g_seq_input",
        )
        task_opts = {
            "Gene expression":             "GENE_EXPRESSION",
            "Chromatin accessibility":     "CHROMATIN_ACCESSIBILITY",
            "Histone modification":        "HISTONE_MODIFICATION",
            "Transcription factor binding":"TF_BINDING",
            "3D genome contacts":          "GENOME_CONTACTS",
        }
        chosen_tasks = st.multiselect(
            "Prediction targets", list(task_opts.keys()),
            default=["Gene expression", "Chromatin accessibility"],
            key="g_tasks",
        )

        if st.button("▶ Run Sequence Analysis", type="primary", key="btn_seq_run",
                     disabled=not _GENOME_KEY or not seq_input.strip()):
            seq_clean = seq_input.strip().replace(" ", "").replace("\n", "")
            if not _validate_dna(seq_clean):
                st.error("❌ Invalid characters — use A, C, G, T, N only.")
            elif len(seq_clean) < 32:
                st.error("❌ Sequence too short (minimum 32 bases).")
            else:
                with st.spinner("Analysing sequence…"):
                    result, err = _analyse_sequence(seq_clean, [task_opts[t] for t in chosen_tasks])
                if err:
                    st.error(f"❌ {err}")
                else:
                    st.success(f"✅ Analysis complete — {len(seq_clean):,} bases processed.")
                    predictions = result.get("predictions", {})
                    if not predictions:
                        with st.expander("📋 Raw response"):
                            st.json(result)
                    else:
                        st.markdown(section_title_html("Predictions"), unsafe_allow_html=True)
                        for t_label, t_code in task_opts.items():
                            t_data = predictions.get(t_code)
                            if not t_data:
                                continue
                            st.markdown(
                                f'<div style="font-size:0.78rem;font-weight:700;'
                                f'text-transform:uppercase;letter-spacing:0.08em;'
                                f'color:{colors["text2"]};margin:1rem 0 0.4rem">'
                                f'{html.escape(t_label)}</div>',
                                unsafe_allow_html=True,
                            )
                            if isinstance(t_data, dict):
                                for track, val in t_data.items():
                                    if isinstance(val, (int, float)):
                                        _render_track(track, float(val))
                            elif isinstance(t_data, list):
                                st.line_chart(t_data, height=140)
                        with st.expander("📋 Full response"):
                            st.json(result)

    # ── Variant Effect ────────────────────────────────────────────────────────
    with var_tab:
        st.markdown(section_title_html("Variant Effect Prediction"), unsafe_allow_html=True)
        st.caption("Predict how a single nucleotide variant alters regulatory activity.")

        vc1, vc2, vc3 = st.columns([2, 1, 2])
        with vc1:
            var_chrom = st.text_input("Chromosome", placeholder="chr17", key="g_var_chrom")
        with vc2:
            var_build = st.selectbox("Build", ["GRCh38", "GRCh37"], key="g_var_build")
        with vc3:
            var_pos = st.number_input("Position (1-based)", min_value=1, step=1, key="g_var_pos")
        vr1, vr2 = st.columns(2)
        with vr1:
            var_ref = st.text_input("Reference allele", placeholder="A",
                                    max_chars=10, key="g_var_ref")
        with vr2:
            var_alt = st.text_input("Alternate allele", placeholder="G",
                                    max_chars=10, key="g_var_alt")

        if st.button("▶ Predict Variant Effect", type="primary", key="btn_var_run",
                     disabled=not _GENOME_KEY or not all([var_chrom, var_ref, var_alt])):
            rc = var_chrom.strip()
            rr = var_ref.strip().upper()
            ra = var_alt.strip().upper()
            if not _validate_dna(rr) or not _validate_dna(ra):
                st.error("❌ Alleles must contain only A, C, G, T.")
            else:
                with st.spinner(f"Predicting {html.escape(rc)}:{int(var_pos)} "
                                f"{html.escape(rr)}→{html.escape(ra)}…"):
                    result, err = _analyse_variant(rc, int(var_pos), rr, ra, var_build)
                if err:
                    st.error(f"❌ {err}")
                else:
                    effect = result.get("variantEffect", {})
                    score  = effect.get("score")
                    interp = effect.get("interpretation", "")
                    deltas = effect.get("trackDeltas", {})
                    if score is not None:
                        ca, cb = st.columns(2)
                        ca.metric("Effect score", f"{score:+.4f}")
                        cb.metric("Interpretation", interp or "—")
                    if deltas:
                        st.markdown(section_title_html("Track Δ (alt − ref)"),
                                    unsafe_allow_html=True)
                        for track, delta in deltas.items():
                            if isinstance(delta, (int, float)):
                                _render_track(track, float(delta),
                                              max_val=max(abs(delta), 1.0))
                    with st.expander("📋 Full response"):
                        st.json(result)

    # ── Genomic Region ────────────────────────────────────────────────────────
    with reg_tab:
        st.markdown(section_title_html("Genomic Region Analysis"), unsafe_allow_html=True)
        st.caption("Predict regulatory signals across a chromosomal window (max 500 000 bp).")

        rc1, rc2, rc3 = st.columns([2, 1, 1])
        with rc1:
            reg_chrom = st.text_input("Chromosome", placeholder="chr17", key="g_reg_chrom")
        with rc2:
            reg_start = st.number_input("Start (bp)", min_value=1, step=1, key="g_reg_start")
        with rc3:
            reg_end = st.number_input("End (bp)", min_value=2, step=1,
                                      value=131073, key="g_reg_end")
        reg_build = st.selectbox("Genome build", ["GRCh38", "GRCh37"], key="g_reg_build")

        if st.button("▶ Analyse Region", type="primary", key="btn_reg_run",
                     disabled=not _GENOME_KEY or not reg_chrom.strip()):
            cr = reg_chrom.strip()
            sr = int(reg_start)
            er = int(reg_end)
            if sr >= er:
                st.error("❌ Start must be less than End.")
            elif er - sr > 500_000:
                st.error("❌ Region too large (max 500 000 bp).")
            else:
                with st.spinner(f"Analysing {html.escape(cr)}:{sr:,}–{er:,} ({er-sr:,} bp)…"):
                    result, err = _analyse_region(cr, sr, er, reg_build)
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
                    with st.expander("📋 Full response"):
                        st.json(result)

    with st.expander("ℹ️ About genomic analysis"):
        st.markdown(
            f'<div style="font-size:0.87rem;color:{colors["text"]};line-height:1.75">'
            f'This tab connects to a genomic prediction service that applies deep learning '
            f'to DNA sequences to predict gene expression, chromatin accessibility, '
            f'histone modifications, transcription factor binding, and variant effects — '
            f'without wet-lab experiments.'
            + (
                '<br><br>Contact your system administrator to configure API access for live queries.'
                if not is_admin_authenticated()
                else '<br><br>Configure ALPHA_GENOME_API_KEY (and optionally ALPHA_GENOME_BASE_URL) in your secrets to enable live queries.'
            )
            + '</div>',
            unsafe_allow_html=True,
        )


# ── Footer ─────────────────────────────────────────────────────────────────────
st.divider()
st.markdown(footer_html(), unsafe_allow_html=True)
