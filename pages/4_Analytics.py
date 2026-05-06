"""
ORC Research Dashboard - Analytics
Publication trends, citation metrics, collaboration network, and keyword analysis.
"""

import re
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from collections import Counter
import sys
import os
import json # Added for parsing author data

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.hf_data import get_active_researchers, load_publications, get_publications_sorted
from utils.styles import (
    apply_styles, get_theme, hero_html, section_title_html,
    metric_card_html, footer_html, chart_layout, chart_colors,
    render_navbar, DARK, LIGHT, PLOTLY_CONFIG,
)

apply_styles()
render_navbar()

colors = DARK if get_theme() == "dark" else LIGHT

st.markdown(hero_html("📈 Analytics", "Research metrics, publication trends, and collaboration insights"),
            unsafe_allow_html=True)

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
            fig = px.area(year_cit, x="publication_year", y="citation_count",
                          labels={"publication_year": "Year", "citation_count": "Citations"},
                          color_discrete_sequence=[ccs[2]])
            fig.update_traces(line_color=ccs[2], opacity=0.7)
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


# ── Journal & Open Access ────────────────────────────────────────────────────
st.markdown(section_title_html("Distribution"), unsafe_allow_html=True)
col1, col2 = st.columns(2)

with col1:
    try:
        if "journal_name" not in df.columns:
            st.info("Journal data not available.")
        else:
            jcounts = df["journal_name"].value_counts().head(8).reset_index()
            jcounts.columns = ["journal", "count"]
            fig = px.pie(jcounts, values="count", names="journal",
                         color_discrete_sequence=ccs, hole=0.4)
            fig.update_layout(**chart_layout("Top Journals"))
            fig.update_traces(textfont_color=colors["text"])
            st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)
    except Exception as e:
        st.info("Journal distribution chart unavailable — data could not be loaded.")

with col2:
    try:
        if "open_access" not in df.columns:
            st.info("Open access data not available.")
        else:
            oa     = int(df["open_access"].sum())
            closed = len(df) - oa
            fig = px.pie(values=[oa, closed],
                         names=["Open Access", "Subscription"],
                         color_discrete_sequence=[colors["success"], colors["muted"]],
                         hole=0.4)
            fig.update_layout(**chart_layout("Open Access"))
            fig.update_traces(textfont_color=colors["text"])
            st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)
    except Exception as e:
        st.info("Open Access chart unavailable — data could not be loaded.")


# ── Citation Distribution ────────────────────────────────────────────────────
st.markdown(section_title_html("Citation Distribution"), unsafe_allow_html=True)
if "citation_count" in df.columns:
    col1, col2 = st.columns(2)
    with col1:
        try:
            fig = px.histogram(df, x="citation_count", nbins=20,
                               labels={"citation_count": "Citations", "count": "Papers"},
                               color_discrete_sequence=[ccs[3]])
            fig.update_layout(**chart_layout("Distribution of Citations per Paper"))
            st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)
        except Exception as e:
            st.info("Histogram unavailable — data could not be loaded.")
    with col2:
        try:
            if "publication_year" in df.columns:
                fig = px.scatter(df, x="publication_year", y="citation_count",
                                 size="citation_count", size_max=40,
                                 labels={"publication_year": "Year", "citation_count": "Citations"},
                                 color_discrete_sequence=[ccs[0]])
                fig.update_layout(**chart_layout("Citations vs. Publication Year"))
                st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)
        except Exception as e:
            st.info("Scatter chart unavailable — data could not be loaded.")


# ── Keyword Frequency ────────────────────────────────────────────────────────
st.markdown(section_title_html("Top Research Keywords"), unsafe_allow_html=True)

_STOP = {
    "the","a","an","of","in","and","or","for","to","with","on","at","by","from",
    "is","are","was","were","be","been","being","have","has","had","do","does",
    "did","will","would","could","should","may","might","that","this","these",
    "those","it","its","as","into","using","based","study","analysis","between",
    "among","within","across","through","over","after","before","during","via",
    "than","more","less","also","both","each","some","such","their","effect",
    "effects","impact","role","use","new","high","low","large","small","patients",
    "results","data","methods","conclusion","conclusions","approach",
}

try:
    if "title" not in df.columns:
        st.info("Title data not available for keyword analysis.")
    else:
        all_words: list = []
        for title in df["title"].dropna():
            words = re.findall(r"\b[a-zA-Z]{4,}\b", str(title).lower())
            all_words.extend(w for w in words if w not in _STOP)

        if all_words:
            top_words = Counter(all_words).most_common(25)
            wdf = pd.DataFrame(top_words, columns=["keyword", "count"])
            fig = px.bar(wdf, x="count", y="keyword", orientation="h",
                         labels={"keyword": "", "count": "Frequency"},
                         color="count",
                         color_continuous_scale=["#2f81f7", "#a371f7"])
            layout = chart_layout("Most Frequent Keywords in Paper Titles")
            layout["yaxis"] = {**layout.get("yaxis", {}), "categoryorder": "total ascending"}
            layout["height"] = 500
            layout["coloraxis_showscale"] = False
            fig.update_layout(**layout)
            st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)
        else:
            st.info("Not enough title data to extract keywords.")
except Exception as e:
    st.info("Keyword analysis unavailable — data could not be loaded.")


# ── Author Collaboration Network ─────────────────────────────────────────────
st.markdown(section_title_html("Author Collaboration Network"), unsafe_allow_html=True)

try:
    import networkx as nx

    G = nx.Graph()

    for _, row in df.iterrows():
        authors = row.get("authors", [])
        if isinstance(authors, str):
            try:
                authors = json.loads(authors)
            except Exception:
                authors = []
        if not isinstance(authors, list):
            continue
        clean = [str(a).strip() for a in authors[:8] if a and str(a).strip()]
        for i, a1 in enumerate(clean):
            for a2 in clean[i + 1:]:
                if G.has_edge(a1, a2):
                    G[a1][a2]["weight"] += 1
                else:
                    G.add_edge(a1, a2, weight=1)

    if len(G.nodes) >= 3:
        original_node_count = len(G.nodes)
        if original_node_count > 40:
            top_nodes = sorted(G.degree, key=lambda x: x[1], reverse=True)[:40]
            G = G.subgraph([n for n, _ in top_nodes]).copy()

        pos = nx.spring_layout(G, seed=42, k=1.5)

        edge_traces = []
        for u, v, data in G.edges(data=True):
            x0, y0 = pos[u]
            x1, y1 = pos[v]
            w = data.get("weight", 1)
            edge_traces.append(
                go.Scatter(
                    x=[x0, x1, None], y=[y0, y1, None],
                    mode="lines",
                    line=dict(width=min(w * 1.2, 5), color=colors["border"]),
                    hoverinfo="none",
                    showlegend=False,
                )
            )

        degree = dict(G.degree())
        node_x  = [pos[n][0] for n in G.nodes]
        node_y  = [pos[n][1] for n in G.nodes]
        node_sz = [6 + degree[n] * 3 for n in G.nodes]
        node_lbl = [n if len(n) <= 22 else n[:20] + "…" for n in G.nodes]
        node_hover = [f"{n}<br>Co-authorships: {degree[n]}" for n in G.nodes]

        node_trace = go.Scatter(
            x=node_x, y=node_y,
            mode="markers+text",
            text=node_lbl,
            textposition="top center",
            textfont=dict(size=9, color=colors["text2"]),
            hovertext=node_hover,
            hoverinfo="text",
            marker=dict(
                size=node_sz,
                color=colors["accent"],
                line=dict(width=1.5, color=colors["surface"]),
            ),
            showlegend=False,
        )

        layout = chart_layout("Author Collaboration Network")
        layout.update({
            "xaxis": dict(showgrid=False, zeroline=False, showticklabels=False),
            "yaxis": dict(showgrid=False, zeroline=False, showticklabels=False),
            "height": 480,
        })

        fig = go.Figure(data=edge_traces + [node_trace])
        fig.update_layout(**layout)
        st.plotly_chart(fig, use_container_width=True, config=PLOTLY_CONFIG)
        caption_text = (
            f"{len(G.nodes)} authors · {len(G.edges)} co-authorship links — "
            "node size reflects number of collaborations"
        )
        if original_node_count > 40:
            caption_text += " (showing top 40 by collaborations)"
        st.caption(caption_text)

    elif 1 <= len(G.nodes) < 3:
        st.info("Not enough co-authorship data to draw a network yet. "
                "Sync more publications or add more researchers.")
    else:
        st.info("Author data not available for the current selection.")

except ImportError:
    st.info("Network visualization requires networkx — it is listed in requirements.txt.")
except Exception:
    st.info("Collaboration network unavailable — data could not be loaded.")


# ── Footer ───────────────────────────────────────────────────────────────────
st.divider()
st.markdown(footer_html(), unsafe_allow_html=True)
