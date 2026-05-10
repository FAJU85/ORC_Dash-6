"""
ORC Research Dashboard - Analytics
Publication trends, citation metrics, collaboration network, and keyword analysis.
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from collections import Counter
import sys
import os
import json # Added for parsing author data

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.hf_data import get_active_researchers, load_publications, get_publications_sorted, load_cms_content
from utils.styles import (
    apply_styles, get_theme, hero_html, section_title_html,
    metric_card_html, footer_html, chart_layout, chart_colors,
    render_navbar, DARK, LIGHT, PLOTLY_CONFIG,
)

apply_styles()
render_navbar()

colors = DARK if get_theme() == "dark" else LIGHT
_cms = st.session_state.get("_cms_override") or load_cms_content()

_analytics_hero = _cms.get("analytics_hero", {})
st.markdown(
    hero_html(
        _analytics_hero.get("title", "").strip() or "📈 Analytics",
        _analytics_hero.get("subtitle", "").strip() or "Research metrics, publication trends, and collaboration insights",
    ),
    unsafe_allow_html=True,
)

# ── Researcher Filter ────────────────────────────────────────────────────────
researchers = get_active_researchers()
researcher_map = {r.get('name', r.get('orcid', '')): r.get('orcid') for r in researchers if r.get('orcid')}

if researcher_map:
    selected_researcher = st.selectbox(
        "👤 Researcher",
        ["All Researchers"] + list(researcher_map.keys()),
        label_visibility="collapsed",
    )
else:
    selected_researcher = "All Researchers"

if selected_researcher != "All Researchers" and selected_researcher in researcher_map:
    pubs = load_publications(orcid=researcher_map[selected_researcher])
else:
    pubs = get_publications_sorted("year")

if not pubs:
    st.markdown(
        f'<div style="background:{colors["surface"]};border-radius:6px;'
        f'padding:2.5rem;text-align:center;color:{colors["text"]}">'
        f'<div style="font-size:2.5rem;margin-bottom:0.75rem">📭</div>'
        f'<div style="font-weight:600;font-size:1rem;margin-bottom:0.25rem;color:{colors["text"]}">No data available</div>'
        f'<div style="font-size:0.85rem;color:{colors["text2"]}">Sync publications from the <b>Publications</b> page first</div>'
        f'</div>',
        unsafe_allow_html=True,
    )
    st.stop()

df = pd.DataFrame(pubs)

# Ensure authors are always a list, even if stored as JSON string
if "authors" in df.columns:
    df["authors"] = df["authors"].apply(lambda x: json.loads(x) if isinstance(x, str) else x)
    df["authors"] = df["authors"].apply(lambda x: x if isinstance(x, list) else [])

if "citation_count" in df.columns:
    df["citation_count"] = pd.to_numeric(df["citation_count"], errors="coerce").fillna(0)
if "open_access" in df.columns:
    df["open_access"] = df["open_access"].astype(str).str.lower().isin({"1", "true", "yes"})

ccs = chart_colors()


# ── Overview Metrics ─────────────────────────────────────────────────────────
st.markdown(section_title_html("Overview"), unsafe_allow_html=True)

citations_sorted = sorted(df["citation_count"].tolist(), reverse=True) if "citation_count" in df.columns else []
h_index = sum(1 for i, c in enumerate(citations_sorted, 1) if c >= i)
total_cit = int(df["citation_count"].sum()) if "citation_count" in df.columns else 0
avg_cit   = df["citation_count"].mean()     if "citation_count" in df.columns else 0
oa_count  = int(df["open_access"].sum())    if "open_access"    in df.columns else 0

mc1, mc2, mc3, mc4, mc5 = st.columns(5)
for col, icon, val, lbl in [
    (mc1, "📄", f"{len(df):,}",       "Publications"),
    (mc2, "📈", f"{total_cit:,.0f}",  "Total Citations"),
    (mc3, "🎯", str(h_index),          "h-index"),
    (mc4, "📊", f"{avg_cit:.1f}",     "Avg Citations"),
    (mc5, "🔓", str(oa_count),         "Open Access"),
]:
    col.markdown(metric_card_html(icon, val, lbl), unsafe_allow_html=True)


# ── Publication Trends ───────────────────────────────────────────────────────
st.markdown(section_title_html("Publication Trends"), unsafe_allow_html=True)
col1, col2 = st.columns(2)

with col1:
    try:
        if "publication_year" not in df.columns:
            st.info("Publication year data not available.")
        else:
            year_counts = df.groupby("publication_year").size().reset_index(name="count")
            year_counts = year_counts.sort_values("publication_year")
            year_counts["cumulative"] = year_counts["count"].cumsum()
            fig = go.Figure()
            fig.add_bar(x=year_counts["publication_year"], y=year_counts["count"],
                        name="Per Year", marker_color=ccs[0])
            fig.add_scatter(x=year_counts["publication_year"], y=year_counts["cumulative"],
                            name="Cumulative", mode="lines+markers",
                            line=dict(color=ccs[1], width=2), yaxis="y2")
            _ly = chart_layout("Publications by Year")
            _ly["yaxis2"] = dict(overlaying="y", side="right",
                                 tickfont=dict(color=colors["text2"]),
                                 title_font=dict(color=colors["text2"]))
            _ly["legend"] = dict(font=dict(color=colors["text2"]), bgcolor="rgba(0,0,0,0)")
            fig.update_layout(**_ly)
            st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)
    except Exception as e:
        st.info("Publications by Year chart unavailable — data could not be loaded.")

with col2:
    try:
        if "publication_year" not in df.columns or "citation_count" not in df.columns:
            st.info("Year or citation data not available.")
        else:
            year_cit = df.groupby("publication_year")["citation_count"].sum().reset_index()
            year_cit = year_cit.sort_values("publication_year")
            fig = px.bar(year_cit, x="publication_year", y="citation_count",
                         labels={"publication_year": "Year", "citation_count": "Citations"},
                         color_discrete_sequence=[ccs[2]])
            fig.update_layout(**chart_layout("Citation Impact by Year"))
            st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)
    except Exception as e:
        st.info("Citation Impact chart unavailable — data could not be loaded.")


# ── Most Cited Papers ────────────────────────────────────────────────────────
st.markdown(section_title_html("Most Cited Papers"), unsafe_allow_html=True)
try:
    if "citation_count" not in df.columns:
        st.info("Citation data not available.")
    else:
        top = df.nlargest(10, "citation_count")[
            ["title", "journal_name", "publication_year", "citation_count"]
        ].copy()
        top["label"] = top["title"].str[:60] + "…"
        fig = px.bar(top, y="label", x="citation_count", orientation="h",
                     labels={"label": "", "citation_count": "Citations"},
                     color="citation_count", color_continuous_scale=["#2f81f7", "#a371f7"])
        layout = chart_layout()
        layout["yaxis"] = {**layout.get("yaxis", {}), "categoryorder": "total ascending"}
        layout["height"] = 400
        layout["coloraxis_showscale"] = False
        fig.update_layout(**layout)
        st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)
except Exception as e:
    st.info("Most Cited Papers chart unavailable — data could not be loaded.")


# ── Research Collaborations ──────────────────────────────────────────────────
st.markdown(section_title_html("Research Collaborations"), unsafe_allow_html=True)

col1, col2 = st.columns(2)

with col1:
    try:
        # Co-author frequency chart
        co_author_counter = Counter()
        for pub in pubs:
            authors = pub.get("authors", [])
            if not isinstance(authors, list):
                authors = []
            names = [a.get("name", "") if isinstance(a, dict) else str(a) for a in authors]
            for name in names:
                if name.strip():
                    co_author_counter[name.strip()] += 1
        if co_author_counter:
            top_collabs = co_author_counter.most_common(15)
            cdf = pd.DataFrame(top_collabs, columns=["author", "papers"])
            fig = px.bar(cdf, x="papers", y="author", orientation="h",
                         labels={"author": "", "papers": "Joint Publications"},
                         color="papers", color_continuous_scale=["#2f81f7", "#a371f7"])
            layout = chart_layout("Top Co-Authors")
            layout["yaxis"] = {**layout.get("yaxis", {}), "categoryorder": "total ascending"}
            layout["height"] = 420
            layout["coloraxis_showscale"] = False
            fig.update_layout(**layout)
            st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)
        else:
            st.info("No co-author data available.")
    except Exception:
        st.info("Co-author chart unavailable.")

with col2:
    try:
        # Publications per year by open-access status
        if "publication_year" in df.columns and "open_access" in df.columns:
            oa_year = df.groupby(["publication_year", "open_access"]).size().reset_index(name="count")
            oa_year["access_type"] = oa_year["open_access"].map({True: "Open Access", False: "Closed"})
            fig = px.bar(oa_year, x="publication_year", y="count", color="access_type",
                         labels={"publication_year": "Year", "count": "Publications", "access_type": ""},
                         color_discrete_map={"Open Access": ccs[0], "Closed": ccs[3]},
                         barmode="stack")
            fig.update_layout(**chart_layout("Open Access vs Closed by Year"))
            st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)
        else:
            st.info("Open access data not available.")
    except Exception:
        st.info("Open access chart unavailable.")

# Journal distribution
try:
    if "journal_name" in df.columns:
        journal_counts = df["journal_name"].dropna().value_counts().head(12).reset_index()
        journal_counts.columns = ["journal", "count"]
        fig = px.bar(journal_counts, x="count", y="journal", orientation="h",
                     labels={"journal": "", "count": "Publications"},
                     color="count", color_continuous_scale=["#0C539F", "#FA9F37"])
        layout = chart_layout("Publications by Journal")
        layout["yaxis"] = {**layout.get("yaxis", {}), "categoryorder": "total ascending"}
        layout["height"] = 380
        layout["coloraxis_showscale"] = False
        fig.update_layout(**layout)
        st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)
except Exception:
    st.info("Journal distribution chart unavailable.")


# ── Footer ───────────────────────────────────────────────────────────────────
st.divider()
st.markdown(footer_html(), unsafe_allow_html=True)
