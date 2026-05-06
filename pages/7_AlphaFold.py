"""
ORC Research Dashboard - AlphaFold & Protein Structure
Protein structure prediction lookup via the AlphaFold EBI Public API.
"""

import json
import sys
import os
import html

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import requests

from utils.security import log_audit, log_error, RateLimiter
from utils.styles import (
    apply_styles, get_theme, hero_html, section_title_html,
    footer_html, render_navbar, DARK, LIGHT,
)

apply_styles()
render_navbar()

colors = DARK if get_theme() == "dark" else LIGHT
rate_limiter = RateLimiter()

_AF_BASE   = "https://alphafold.ebi.ac.uk/api"
_AF_ENTRY  = _AF_BASE + "/prediction/{uniprot_id}"
_UNIPROT_SEARCH = "https://rest.uniprot.org/uniprotkb/search?query={query}&format=json&size=5"

# ── Helpers ────────────────────────────────────────────────────────────────────

def _fetch_alphafold(uniprot_id: str) -> tuple[list | None, str | None]:
    uid = uniprot_id.strip().upper()
    allowed, wait = rate_limiter.is_allowed(f"af_{uid}", max_attempts=5, window_seconds=60)
    if not allowed:
        return None, f"Rate limit — please wait {wait}s"
    rate_limiter.record_attempt(f"af_{uid}")
    try:
        resp = requests.get(
            _AF_ENTRY.format(uniprot_id=uid),
            timeout=15,
            headers={"Accept": "application/json"},
        )
        if resp.status_code == 404:
            return None, f"No AlphaFold entry found for **{html.escape(uid)}**."
        resp.raise_for_status()
        log_audit("alphafold_lookup", uid[:10])
        return resp.json(), None
    except requests.RequestException as exc:
        log_error("alphafold_error", str(exc), page="AlphaFold")
        return None, "AlphaFold API unavailable — please try again later."


def _search_uniprot(query: str) -> list[dict]:
    try:
        resp = requests.get(
            _UNIPROT_SEARCH.format(query=requests.utils.quote(query)),
            timeout=10,
            headers={"Accept": "application/json"},
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
        out = []
        for r in results:
            pid   = r.get("primaryAccession", "")
            names = r.get("proteinDescription", {})
            rec   = names.get("recommendedName", {}) or names.get("submissionNames", [{}])[0]
            pname = rec.get("fullName", {}).get("value", "") if rec else ""
            gene  = ""
            genes = r.get("genes", [])
            if genes:
                gene = genes[0].get("geneName", {}).get("value", "")
            org = r.get("organism", {}).get("scientificName", "")
            out.append({"id": pid, "protein": pname, "gene": gene, "organism": org})
        return out
    except Exception:
        return []


def _confidence_color(score: float) -> str:
    if score >= 90:
        return "#00c7ff"   # Very high — blue
    if score >= 70:
        return "#65cb5e"   # Confident — green
    if score >= 50:
        return "#ffdb13"   # Low — yellow
    return "#ff7d45"        # Very low — orange


def _confidence_label(score: float) -> str:
    if score >= 90:
        return "Very high"
    if score >= 70:
        return "Confident"
    if score >= 50:
        return "Low"
    return "Very low"


# ── Page ───────────────────────────────────────────────────────────────────────

st.markdown(
    hero_html("🧬 AlphaFold Protein Structures",
              "Look up predicted 3D protein structures via the AlphaFold EBI Public API"),
    unsafe_allow_html=True,
)

# ── Search / Lookup ────────────────────────────────────────────────────────────
st.markdown(section_title_html("Protein Lookup"), unsafe_allow_html=True)

search_col, id_col = st.columns([3, 2])

with search_col:
    protein_query = st.text_input(
        "Search protein / gene name",
        placeholder="e.g. BRCA2, p53, insulin…",
        label_visibility="visible",
    )

with id_col:
    uniprot_id = st.text_input(
        "UniProt Accession ID",
        placeholder="e.g. P04637, P38398…",
        label_visibility="visible",
    )

# UniProt search autocomplete
if protein_query and not uniprot_id:
    with st.spinner("Searching UniProt…"):
        hits = _search_uniprot(protein_query)
    if hits:
        options = {
            f"{h['id']} — {h['protein']} ({h['gene']}) · {h['organism']}": h["id"]
            for h in hits
        }
        chosen = st.selectbox("Select a UniProt entry", list(options.keys()),
                              label_visibility="collapsed")
        if chosen:
            uniprot_id = options[chosen]
    else:
        st.info("No UniProt results for that query.")

lookup_btn = st.button("🔍 Fetch Structure", type="primary",
                       disabled=not uniprot_id.strip())

# ── Results ────────────────────────────────────────────────────────────────────
if lookup_btn and uniprot_id.strip():
    uid = uniprot_id.strip().upper()
    with st.spinner(f"Fetching AlphaFold data for **{html.escape(uid)}**…"):
        entries, err = _fetch_alphafold(uid)

    if err:
        st.error(f"❌ {err}")
    elif entries:
        for entry in entries:
            gene_name   = entry.get("gene", "") or ""
            protein_name = entry.get("uniprotDescription", "") or entry.get("uniprotId", uid)
            organism    = entry.get("organismScientificName", "")
            model_url   = entry.get("pdbUrl", "")
            cif_url     = entry.get("cifUrl", "")
            pae_url     = entry.get("paeImageUrl", "")
            mean_conf   = entry.get("confidenceAvgLocalScore", 0.0) or 0.0
            conf_version = entry.get("latestVersion", "")
            seq_len     = entry.get("uniprotSequence", "")
            seq_len_n   = len(seq_len) if seq_len else 0

            conf_color  = _confidence_color(mean_conf)
            conf_label  = _confidence_label(mean_conf)

            # ── Header card ──────────────────────────────────────────────────
            st.markdown(
                f'<div class="orc-card" style="border-left:4px solid {colors["accent"]}">'
                f'  <div style="font-size:1.05rem;font-weight:700;color:{colors["text"]}">'
                f'    {html.escape(protein_name)}'
                f'  </div>'
                f'  <div style="font-size:0.82rem;color:{colors["text2"]};margin-top:0.2rem">'
                f'    🧬 {html.escape(gene_name) or "—"} &nbsp;·&nbsp; '
                f'    <i>{html.escape(organism)}</i> &nbsp;·&nbsp; '
                f'    UniProt: <code>{html.escape(uid)}</code>'
                f'    {(" &nbsp;·&nbsp; v" + html.escape(str(conf_version))) if conf_version else ""}'
                f'  </div>'
                f'</div>',
                unsafe_allow_html=True,
            )

            # ── Metrics row ───────────────────────────────────────────────────
            m1, m2, m3 = st.columns(3)
            m1.metric("Mean pLDDT", f"{mean_conf:.1f}")
            m2.metric("Confidence", conf_label)
            m3.metric("Sequence length", f"{seq_len_n:,} aa" if seq_len_n else "N/A")

            # ── Confidence colour scale legend ────────────────────────────────
            st.markdown(
                f'<div style="font-size:0.77rem;color:{colors["text2"]};margin:0.25rem 0 0.75rem">'
                f'pLDDT confidence: '
                f'<span style="color:#00c7ff">■ ≥90 Very high</span> &nbsp;'
                f'<span style="color:#65cb5e">■ ≥70 Confident</span> &nbsp;'
                f'<span style="color:#ffdb13">■ ≥50 Low</span> &nbsp;'
                f'<span style="color:#ff7d45">■ &lt;50 Very low</span>'
                f'</div>',
                unsafe_allow_html=True,
            )

            # ── PAE image ─────────────────────────────────────────────────────
            if pae_url:
                st.markdown(section_title_html("Predicted Aligned Error (PAE)"),
                            unsafe_allow_html=True)
                img_col, desc_col = st.columns([1, 2])
                with img_col:
                    st.image(pae_url, caption="PAE matrix — lower = more confident relative position")
                with desc_col:
                    st.markdown(
                        f'<div style="font-size:0.85rem;color:{colors["text"]};line-height:1.7">'
                        f'The <b>Predicted Aligned Error (PAE)</b> matrix shows AlphaFold\'s '
                        f'confidence in the relative position of every pair of residues. '
                        f'Dark green (low PAE) indicates high confidence in the relative '
                        f'positions of two residues. High-PAE regions often correspond to '
                        f'flexible linkers or independently folding domains.'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

            # ── Download links ────────────────────────────────────────────────
            st.markdown(section_title_html("Downloads"), unsafe_allow_html=True)
            dl_cols = st.columns(3)
            with dl_cols[0]:
                if model_url:
                    st.markdown(
                        f'<a href="{html.escape(model_url)}" target="_blank" rel="noopener" '
                        f'style="display:inline-flex;align-items:center;gap:0.3rem;'
                        f'background:{colors["accent"]};color:#fff;'
                        f'border-radius:8px;padding:0.4rem 0.9rem;'
                        f'text-decoration:none;font-size:0.83rem;font-weight:600">'
                        f'⬇️ PDB Structure</a>',
                        unsafe_allow_html=True,
                    )
            with dl_cols[1]:
                if cif_url:
                    st.markdown(
                        f'<a href="{html.escape(cif_url)}" target="_blank" rel="noopener" '
                        f'style="display:inline-flex;align-items:center;gap:0.3rem;'
                        f'background:{colors["surface2"]};color:{colors["text"]};'
                        f'border:1px solid {colors["border"]};'
                        f'border-radius:8px;padding:0.4rem 0.9rem;'
                        f'text-decoration:none;font-size:0.83rem;font-weight:500">'
                        f'⬇️ mmCIF Structure</a>',
                        unsafe_allow_html=True,
                    )
            with dl_cols[2]:
                af_page = f"https://alphafold.ebi.ac.uk/entry/{uid}"
                st.markdown(
                    f'<a href="{html.escape(af_page)}" target="_blank" rel="noopener" '
                    f'style="display:inline-flex;align-items:center;gap:0.3rem;'
                    f'background:{colors["surface2"]};color:{colors["text"]};'
                    f'border:1px solid {colors["border"]};'
                    f'border-radius:8px;padding:0.4rem 0.9rem;'
                    f'text-decoration:none;font-size:0.83rem;font-weight:500">'
                    f'🔗 View on AlphaFold DB</a>',
                    unsafe_allow_html=True,
                )

            # ── Raw JSON expander ─────────────────────────────────────────────
            with st.expander("📋 Full API response"):
                st.json(entry)

            st.markdown('<div style="margin-bottom:1.5rem"></div>', unsafe_allow_html=True)

# ── About section ──────────────────────────────────────────────────────────────
with st.expander("ℹ️ About AlphaFold & this integration"):
    st.markdown(
        f'<div style="font-size:0.87rem;color:{colors["text"]};line-height:1.75">'
        f'<b>AlphaFold</b> is an AI system developed by DeepMind that predicts a '
        f'protein\'s 3D structure from its amino acid sequence. The '
        f'<b>AlphaFold Protein Structure Database</b> (partnered with EMBL-EBI) '
        f'provides open access to over 200 million protein structure predictions.'
        f'<br><br>'
        f'This page uses the <b>AlphaFold EBI Public API</b> — no API key required. '
        f'Structures are looked up by UniProt Accession ID. '
        f'You can also search by protein or gene name to find the relevant UniProt ID.'
        f'<br><br>'
        f'<b>pLDDT</b> (predicted local distance difference test) is a per-residue '
        f'confidence metric (0–100). Regions with pLDDT &lt; 50 are often '
        f'intrinsically disordered.'
        f'</div>',
        unsafe_allow_html=True,
    )

# ── Footer ─────────────────────────────────────────────────────────────────────
st.divider()
st.markdown(footer_html(), unsafe_allow_html=True)
