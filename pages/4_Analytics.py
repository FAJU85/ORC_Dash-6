"""
ORC Research Dashboard - Analytics
Interactive visualizations with per-researcher filtering.
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.security import execute_query
from utils.hf_data import get_active_researchers, load_publications
from utils.ui import apply_theme, get_chart_theme, render_footer, render_empty_state

st.set_page_config(page_title="Analytics", page_icon="📈", layout="wide")
apply_theme()

st.title("📈 Analytics")

# ── Researcher Filter ───────────────────────────────────────────────────────
researchers = get_active_researchers()
researcher_map = {r.get('name', r.get('orcid', '')): r.get('orcid') for r in researchers if r.get('orcid')}

if researcher_map:
    selected_researcher = st.selectbox(
        "👤 Researcher",
        ["All Researchers"] + list(researcher_map.keys()),
    )
else:
    selected_researcher = "All Researchers"

# Load publications (filtered or all)
if selected_researcher != "All Researchers" and selected_researcher in researcher_map:
    filter_orcid = researcher_map[selected_researcher]
    pubs = load_publications(orcid=filter_orcid)
else:
    pubs, _ = execute_query("SELECT * FROM publications ORDER BY publication_year DESC")
    pubs = pubs or []

if not pubs:
    render_empty_state(
        "No publications to visualise",
        "Sync publications first to see charts and analytics.",
        cta_label="Go to Publications →",
        cta_page="pages/1_Publications.py",
    )
    st.stop()

df = pd.DataFrame(pubs)

# ── Overview Metrics ────────────────────────────────────────────────────────
st.header("📊 Overview")

citations_sorted = []
if 'citation_count' in df.columns:
    citations_sorted = sorted(df['citation_count'].fillna(0).tolist(), reverse=True)

# h-index
h_index = 0
for i, c in enumerate(citations_sorted, 1):
    if c >= i:
        h_index = i
    else:
        break

# i10-index
i10_index = sum(1 for c in citations_sorted if c >= 10)

c1, c2, c3, c4, c5, c6 = st.columns(6)
with c1:
    st.metric("Publications", len(df))
with c2:
    total_cit = int(df['citation_count'].sum()) if 'citation_count' in df else 0
    st.metric("Total Citations", f"{total_cit:,}")
with c3:
    st.metric("h-index", h_index)
with c4:
    st.metric("i10-index", i10_index)
with c5:
    avg_cit = df['citation_count'].mean() if 'citation_count' in df else 0
    st.metric("Avg Citations", f"{avg_cit:.1f}")
with c6:
    oa_count = int(df['open_access'].sum()) if 'open_access' in df else 0
    st.metric("Open Access", oa_count)

st.divider()

# ── Tabs ────────────────────────────────────────────────────────────────────
tab_pub, tab_cite, tab_collab, tab_journals = st.tabs([
    "📅 Publications", "📈 Citations", "🕸️ Co-authorship", "📰 Journals"
])

# ── Tab 1: Publications ──────────────────────────────────────────────────────
with tab_pub:
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Publications by Year")
        if 'publication_year' in df.columns:
            year_counts = df.groupby('publication_year').size().reset_index(name='count')
            year_counts = year_counts.sort_values('publication_year')
            fig = px.bar(year_counts, x='publication_year', y='count',
                         labels={'publication_year': 'Year', 'count': 'Publications'},
                         color_discrete_sequence=['#06b6d4'])
            fig.update_layout(showlegend=False, **get_chart_theme())
            st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("Source Breakdown")
        if 'source' in df.columns:
            src_counts = df['source'].value_counts().reset_index()
            src_counts.columns = ['source', 'count']
            label_map = {'openalex': 'OpenAlex', 'crossref': 'CrossRef', 'pubmed': 'PubMed'}
            src_counts['source'] = src_counts['source'].map(lambda x: label_map.get(x, x.title()))
            fig = px.pie(src_counts, values='count', names='source',
                         color_discrete_sequence=['#06b6d4', '#8b5cf6', '#22c55e'])
            fig.update_layout(**get_chart_theme())
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.caption("Source data unavailable.")

    # Most-cited papers
    st.subheader("🏆 Most Cited Papers")
    if 'citation_count' in df.columns:
        top = df.nlargest(10, 'citation_count')[['title', 'journal_name', 'publication_year', 'citation_count']]
        top['title_short'] = top['title'].str[:55] + '…'
        fig = px.bar(top, y='title_short', x='citation_count', orientation='h',
                     labels={'title_short': '', 'citation_count': 'Citations'},
                     color_discrete_sequence=['#22c55e'])
        fig.update_layout(yaxis={'categoryorder': 'total ascending'}, height=420,
                          **get_chart_theme())
        st.plotly_chart(fig, use_container_width=True)


# ── Tab 2: Citations ─────────────────────────────────────────────────────────
with tab_cite:
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Citations by Year")
        if 'publication_year' in df.columns and 'citation_count' in df.columns:
            year_cit = df.groupby('publication_year')['citation_count'].sum().reset_index()
            year_cit = year_cit.sort_values('publication_year')
            fig = px.line(year_cit, x='publication_year', y='citation_count',
                          labels={'publication_year': 'Year', 'citation_count': 'Citations'},
                          markers=True)
            fig.update_traces(line_color='#8b5cf6')
            fig.update_layout(**get_chart_theme())
            st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("Year-over-Year Citation Growth")
        if 'publication_year' in df.columns and 'citation_count' in df.columns:
            yoy = df.groupby('publication_year')['citation_count'].sum().reset_index()
            yoy = yoy.sort_values('publication_year')
            if len(yoy) >= 2:
                yoy['growth'] = yoy['citation_count'].pct_change() * 100
                yoy_plot = yoy.dropna(subset=['growth'])
                colors = ['#22c55e' if g >= 0 else '#ef4444' for g in yoy_plot['growth']]
                fig = go.Figure(go.Bar(
                    x=yoy_plot['publication_year'],
                    y=yoy_plot['growth'],
                    marker_color=colors,
                    text=yoy_plot['growth'].apply(lambda x: f"{x:+.1f}%"),
                    textposition='outside',
                ))
                fig.update_layout(
                    xaxis_title="Year",
                    yaxis_title="Growth (%)",
                    showlegend=False,
                    **get_chart_theme(),
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.caption("Need at least 2 years of data to show growth.")

    st.subheader("Citation Distribution")
    if 'citation_count' in df.columns:
        fig = px.histogram(df, x='citation_count', nbins=20,
                           labels={'citation_count': 'Citations', 'count': 'Papers'},
                           color_discrete_sequence=['#f59e0b'])
        fig.update_layout(**get_chart_theme())
        st.plotly_chart(fig, use_container_width=True)


# ── Tab 3: Co-authorship Network ─────────────────────────────────────────────
with tab_collab:
    st.subheader("🕸️ Co-authorship Network")
    st.caption("Shows the top collaborating authors based on shared publications.")

    try:
        import networkx as nx

        # Build edge list from author pairs
        edges: dict = {}
        node_pub_count: dict = {}

        for _, row in df.iterrows():
            authors = row.get('authors', [])
            if not isinstance(authors, list):
                continue
            clean = [a.strip() for a in authors if a and a.strip()]
            for a in clean:
                node_pub_count[a] = node_pub_count.get(a, 0) + 1
            for i in range(len(clean)):
                for j in range(i + 1, len(clean)):
                    pair = tuple(sorted([clean[i], clean[j]]))
                    edges[pair] = edges.get(pair, 0) + 1

        if not edges:
            st.info("No co-authorship data available. Sync publications with author information first.")
        else:
            # Keep top N authors by publication count for readability
            max_nodes = 30
            top_authors = sorted(node_pub_count, key=lambda a: node_pub_count[a], reverse=True)[:max_nodes]
            top_set = set(top_authors)

            G = nx.Graph()
            for (a, b), weight in edges.items():
                if a in top_set and b in top_set:
                    G.add_edge(a, b, weight=weight)

            if G.number_of_nodes() == 0:
                st.info("Not enough co-author data to build the network.")
            else:
                pos = nx.spring_layout(G, seed=42, k=0.8)

                # Build Plotly traces
                edge_x, edge_y = [], []
                for u, v in G.edges():
                    x0, y0 = pos[u]
                    x1, y1 = pos[v]
                    edge_x += [x0, x1, None]
                    edge_y += [y0, y1, None]

                edge_trace = go.Scatter(
                    x=edge_x, y=edge_y,
                    line=dict(width=0.8, color='#475569'),
                    hoverinfo='none',
                    mode='lines',
                )

                node_x = [pos[n][0] for n in G.nodes()]
                node_y = [pos[n][1] for n in G.nodes()]
                node_text = list(G.nodes())
                node_size = [max(8, min(30, node_pub_count.get(n, 1) * 3)) for n in G.nodes()]
                node_color = [G.degree(n) for n in G.nodes()]

                node_trace = go.Scatter(
                    x=node_x, y=node_y,
                    mode='markers+text',
                    hoverinfo='text',
                    text=node_text,
                    textposition='top center',
                    textfont=dict(size=8),
                    marker=dict(
                        showscale=True,
                        colorscale='Viridis',
                        color=node_color,
                        size=node_size,
                        colorbar=dict(
                            thickness=12,
                            title='Connections',
                            xanchor='left',
                        ),
                        line_width=1,
                    ),
                    hovertext=[
                        f"{n}<br>Publications: {node_pub_count.get(n, 0)}<br>Connections: {G.degree(n)}"
                        for n in G.nodes()
                    ],
                )

                fig = go.Figure(
                    data=[edge_trace, node_trace],
                    layout=go.Layout(
                        showlegend=False,
                        hovermode='closest',
                        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                        height=550,
                        margin=dict(l=0, r=0, t=20, b=0),
                        **get_chart_theme(),
                    ),
                )
                st.plotly_chart(fig, use_container_width=True)
                st.caption(
                    f"Showing top {G.number_of_nodes()} authors · "
                    f"{G.number_of_edges()} co-authorship links · "
                    f"Node size = publications · Color = connections"
                )

    except ImportError:
        st.warning("networkx is required for the co-authorship graph. Add it to requirements.txt.")


# ── Tab 4: Journals ──────────────────────────────────────────────────────────
with tab_journals:
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Top Journals")
        if 'journal_name' in df.columns:
            jcounts = df['journal_name'].value_counts().head(10).reset_index()
            jcounts.columns = ['journal', 'count']
            jcounts['journal_short'] = jcounts['journal'].str[:45] + '…'
            fig = px.bar(jcounts, x='count', y='journal_short', orientation='h',
                         labels={'count': 'Publications', 'journal_short': ''},
                         color_discrete_sequence=['#06b6d4'])
            fig.update_layout(yaxis={'categoryorder': 'total ascending'}, height=380,
                              **get_chart_theme())
            st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("Open Access Distribution")
        if 'open_access' in df.columns:
            oa = int(df['open_access'].sum())
            closed = len(df) - oa
            fig = px.pie(values=[oa, closed],
                         names=['Open Access', 'Subscription'],
                         color_discrete_sequence=['#22c55e', '#64748b'])
            fig.update_layout(**get_chart_theme())
            st.plotly_chart(fig, use_container_width=True)

    # Per-journal citation performance
    st.subheader("Citation Performance by Journal")
    if 'journal_name' in df.columns and 'citation_count' in df.columns:
        jperf = (
            df.groupby('journal_name')
            .agg(papers=('citation_count', 'count'), avg_cit=('citation_count', 'mean'))
            .reset_index()
        )
        jperf = jperf[jperf['papers'] >= 2].nlargest(12, 'avg_cit')
        jperf['journal_short'] = jperf['journal_name'].str[:45] + '…'
        fig = px.bar(jperf, x='avg_cit', y='journal_short', orientation='h',
                     labels={'avg_cit': 'Avg Citations', 'journal_short': ''},
                     color='avg_cit',
                     color_continuous_scale='Blues')
        fig.update_layout(yaxis={'categoryorder': 'total ascending'}, height=400,
                          showlegend=False, **get_chart_theme())
        st.plotly_chart(fig, use_container_width=True)
        st.caption("Journals with at least 2 publications. Sorted by average citations per paper.")

render_footer()
