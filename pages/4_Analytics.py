"""
ORC Research Dashboard - Analytics
Interactive visualizations with per-researcher filtering.
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.security import execute_query
from utils.hf_data import get_active_researchers, load_publications

st.set_page_config(page_title="Analytics", page_icon="📈", layout="wide")

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
    st.info("📭 No data available. Sync publications from the **Publications** page first.")
    st.stop()

df = pd.DataFrame(pubs)

# ── Overview Metrics ────────────────────────────────────────────────────────
st.header("📊 Overview")

if 'citation_count' in df.columns:
    citations = sorted(df['citation_count'].fillna(0).tolist(), reverse=True)
else:
    citations = []

h_index = 0
for i, c in enumerate(citations, 1):
    if c >= i:
        h_index = i
    else:
        break

c1, c2, c3, c4, c5 = st.columns(5)
with c1:
    st.metric("Publications", len(df))
with c2:
    total_cit = df['citation_count'].sum() if 'citation_count' in df else 0
    st.metric("Total Citations", f"{total_cit:,.0f}")
with c3:
    st.metric("h-index", h_index)
with c4:
    avg_cit = df['citation_count'].mean() if 'citation_count' in df else 0
    st.metric("Avg Citations", f"{avg_cit:.1f}")
with c5:
    oa_count = int(df['open_access'].sum()) if 'open_access' in df else 0
    st.metric("Open Access", oa_count)

st.divider()

# ── Year Charts ─────────────────────────────────────────────────────────────
col1, col2 = st.columns(2)

with col1:
    st.subheader("📅 Publications by Year")
    if 'publication_year' in df.columns:
        year_counts = df.groupby('publication_year').size().reset_index(name='count')
        year_counts = year_counts.sort_values('publication_year')
        fig = px.bar(year_counts, x='publication_year', y='count',
                     labels={'publication_year': 'Year', 'count': 'Publications'},
                     color_discrete_sequence=['#06b6d4'])
        fig.update_layout(showlegend=False, plot_bgcolor='rgba(0,0,0,0)',
                          paper_bgcolor='rgba(0,0,0,0)', font_color='#94a3b8')
        st.plotly_chart(fig, use_container_width=True)

with col2:
    st.subheader("📈 Citations by Year")
    if 'publication_year' in df.columns and 'citation_count' in df.columns:
        year_cit = df.groupby('publication_year')['citation_count'].sum().reset_index()
        year_cit = year_cit.sort_values('publication_year')
        fig = px.line(year_cit, x='publication_year', y='citation_count',
                      labels={'publication_year': 'Year', 'citation_count': 'Citations'},
                      markers=True)
        fig.update_traces(line_color='#8b5cf6')
        fig.update_layout(plot_bgcolor='rgba(0,0,0,0)',
                          paper_bgcolor='rgba(0,0,0,0)', font_color='#94a3b8')
        st.plotly_chart(fig, use_container_width=True)

st.divider()

# ── Top Papers ──────────────────────────────────────────────────────────────
st.subheader("🏆 Most Cited Papers")
if 'citation_count' in df.columns:
    top = df.nlargest(10, 'citation_count')[['title', 'journal_name', 'publication_year', 'citation_count']]
    top['title_short'] = top['title'].str[:50] + '…'
    fig = px.bar(top, y='title_short', x='citation_count', orientation='h',
                 labels={'title_short': '', 'citation_count': 'Citations'},
                 color_discrete_sequence=['#22c55e'])
    fig.update_layout(yaxis={'categoryorder': 'total ascending'}, height=400,
                      plot_bgcolor='rgba(0,0,0,0)',
                      paper_bgcolor='rgba(0,0,0,0)', font_color='#94a3b8')
    st.plotly_chart(fig, use_container_width=True)

st.divider()

# ── Journal & Open Access ───────────────────────────────────────────────────
col1, col2 = st.columns(2)

with col1:
    st.subheader("📰 Top Journals")
    if 'journal_name' in df.columns:
        jcounts = df['journal_name'].value_counts().head(8).reset_index()
        jcounts.columns = ['journal', 'count']
        fig = px.pie(jcounts, values='count', names='journal',
                     color_discrete_sequence=px.colors.qualitative.Set3)
        fig.update_layout(plot_bgcolor='rgba(0,0,0,0)',
                          paper_bgcolor='rgba(0,0,0,0)', font_color='#94a3b8')
        st.plotly_chart(fig, use_container_width=True)

with col2:
    st.subheader("🔓 Open Access Distribution")
    if 'open_access' in df.columns:
        oa = int(df['open_access'].sum())
        closed = len(df) - oa
        fig = px.pie(values=[oa, closed],
                     names=['Open Access', 'Subscription'],
                     color_discrete_sequence=['#22c55e', '#64748b'])
        fig.update_layout(plot_bgcolor='rgba(0,0,0,0)',
                          paper_bgcolor='rgba(0,0,0,0)', font_color='#94a3b8')
        st.plotly_chart(fig, use_container_width=True)

st.divider()

# ── Citation Distribution ───────────────────────────────────────────────────
st.subheader("📊 Citation Distribution")
if 'citation_count' in df.columns:
    fig = px.histogram(df, x='citation_count', nbins=20,
                       labels={'citation_count': 'Citations', 'count': 'Papers'},
                       color_discrete_sequence=['#f59e0b'])
    fig.update_layout(plot_bgcolor='rgba(0,0,0,0)',
                      paper_bgcolor='rgba(0,0,0,0)', font_color='#94a3b8')
    st.plotly_chart(fig, use_container_width=True)
