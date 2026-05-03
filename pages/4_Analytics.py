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
from utils.styles import (
    apply_styles, get_theme, hero_html, section_title_html,
    metric_card_html, footer_html, chart_layout, chart_colors, DARK, LIGHT
)

st.set_page_config(page_title="Analytics", page_icon="📈", layout="wide")

apply_styles()

colors = DARK if get_theme() == "dark" else LIGHT

st.markdown(hero_html("📈 Analytics", "Interactive research metrics and publication visualizations"), unsafe_allow_html=True)

# ── Researcher Filter ───────────────────────────────────────────────────────
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

# Load publications (filtered or all)
if selected_researcher != "All Researchers" and selected_researcher in researcher_map:
    filter_orcid = researcher_map[selected_researcher]
    pubs = load_publications(orcid=filter_orcid)
else:
    pubs, _ = execute_query("SELECT * FROM publications ORDER BY publication_year DESC")
    pubs = pubs or []

if not pubs:
    st.markdown(
        f'<div class="orc-card" style="text-align:center;padding:2.5rem;">'
        f'<div style="font-size:2.5rem;margin-bottom:0.75rem">📭</div>'
        f'<div style="font-weight:600;font-size:1rem;margin-bottom:0.25rem">No data available</div>'
        f'<div style="font-size:0.85rem;color:{colors["text2"]}">Sync publications from the <strong>Publications</strong> page first</div>'
        f'</div>',
        unsafe_allow_html=True,
    )
    st.stop()

df = pd.DataFrame(pubs)
ccs = chart_colors()

# ── Overview Metrics ────────────────────────────────────────────────────────
st.markdown(section_title_html("Overview"), unsafe_allow_html=True)

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

total_cit = df['citation_count'].sum() if 'citation_count' in df.columns else 0
avg_cit   = df['citation_count'].mean() if 'citation_count' in df.columns else 0
oa_count  = int(df['open_access'].sum()) if 'open_access' in df.columns else 0

mc1, mc2, mc3, mc4, mc5 = st.columns(5)
for col, icon, val, lbl in [
    (mc1, "📄", f"{len(df):,}",       "Publications"),
    (mc2, "📈", f"{total_cit:,.0f}",  "Citations"),
    (mc3, "🎯", str(h_index),          "h-index"),
    (mc4, "📊", f"{avg_cit:.1f}",     "Avg Citations"),
    (mc5, "🔓", str(oa_count),         "Open Access"),
]:
    col.markdown(metric_card_html(icon, val, lbl), unsafe_allow_html=True)

# ── Year Charts ─────────────────────────────────────────────────────────────
st.markdown(section_title_html("Publication Trends"), unsafe_allow_html=True)
col1, col2 = st.columns(2)

with col1:
    if 'publication_year' in df.columns:
        year_counts = df.groupby('publication_year').size().reset_index(name='count')
        year_counts = year_counts.sort_values('publication_year')
        fig = px.bar(year_counts, x='publication_year', y='count',
                     labels={'publication_year': 'Year', 'count': 'Publications'},
                     color_discrete_sequence=[ccs[0]])
        fig.update_layout(**chart_layout("Publications by Year"))
        st.plotly_chart(fig, use_container_width=True)

with col2:
    if 'publication_year' in df.columns and 'citation_count' in df.columns:
        year_cit = df.groupby('publication_year')['citation_count'].sum().reset_index()
        year_cit = year_cit.sort_values('publication_year')
        fig = px.line(year_cit, x='publication_year', y='citation_count',
                      labels={'publication_year': 'Year', 'citation_count': 'Citations'},
                      markers=True, color_discrete_sequence=[ccs[1]])
        fig.update_layout(**chart_layout("Citations by Year"))
        st.plotly_chart(fig, use_container_width=True)

# ── Top Papers ──────────────────────────────────────────────────────────────
st.markdown(section_title_html("Most Cited Papers"), unsafe_allow_html=True)
if 'citation_count' in df.columns:
    top = df.nlargest(10, 'citation_count')[['title', 'journal_name', 'publication_year', 'citation_count']].copy()
    top['title_short'] = top['title'].str[:55] + '…'
    fig = px.bar(top, y='title_short', x='citation_count', orientation='h',
                 labels={'title_short': '', 'citation_count': 'Citations'},
                 color_discrete_sequence=[ccs[2]])
    layout = chart_layout()
    layout['yaxis'] = {**layout.get('yaxis', {}), 'categoryorder': 'total ascending'}
    layout['height'] = 380
    fig.update_layout(**layout)
    st.plotly_chart(fig, use_container_width=True)

# ── Journal & Open Access ───────────────────────────────────────────────────
st.markdown(section_title_html("Distribution"), unsafe_allow_html=True)
col1, col2 = st.columns(2)

with col1:
    if 'journal_name' in df.columns:
        jcounts = df['journal_name'].value_counts().head(8).reset_index()
        jcounts.columns = ['journal', 'count']
        fig = px.pie(jcounts, values='count', names='journal',
                     color_discrete_sequence=ccs,
                     hole=0.35)
        fig.update_layout(**chart_layout("Top Journals"))
        fig.update_traces(textfont_color=colors["text"])
        st.plotly_chart(fig, use_container_width=True)

with col2:
    if 'open_access' in df.columns:
        oa  = int(df['open_access'].sum())
        closed = len(df) - oa
        fig = px.pie(values=[oa, closed],
                     names=['Open Access', 'Subscription'],
                     color_discrete_sequence=[colors["success"], colors["muted"]],
                     hole=0.35)
        fig.update_layout(**chart_layout("Open Access Distribution"))
        fig.update_traces(textfont_color=colors["text"])
        st.plotly_chart(fig, use_container_width=True)

# ── Citation Distribution ───────────────────────────────────────────────────
st.markdown(section_title_html("Citation Distribution"), unsafe_allow_html=True)
if 'citation_count' in df.columns:
    fig = px.histogram(df, x='citation_count', nbins=20,
                       labels={'citation_count': 'Citations', 'count': 'Papers'},
                       color_discrete_sequence=[ccs[3]])
    fig.update_layout(**chart_layout())
    st.plotly_chart(fig, use_container_width=True)

# ── Footer ───────────────────────────────────────────────────────────────────
st.divider()
st.markdown(footer_html(), unsafe_allow_html=True)
