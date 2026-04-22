"""
ORC Research Dashboard - Analytics
Secure data visualization
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.security import execute_query

st.set_page_config(page_title="Analytics", page_icon="📈", layout="wide")

# ============================================
# PAGE
# ============================================

st.title("📈 Analytics")

# Fetch data
pubs, error = execute_query("SELECT * FROM publications ORDER BY publication_year DESC")

if error:
    st.error("❌ Could not load data")
    st.stop()

if not pubs:
    st.info("📭 No data available. Sync publications from the **Publications** page first.")
    st.stop()

df = pd.DataFrame(pubs)

# ============================================
# METRICS
# ============================================

st.header("📊 Overview")

# Calculate h-index
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

col1, col2, col3, col4, col5 = st.columns(5)

with col1:
    st.metric("Publications", len(df))
with col2:
    st.metric("Total Citations", f"{df['citation_count'].sum():,.0f}")
with col3:
    st.metric("h-index", h_index)
with col4:
    st.metric("Avg Citations", f"{df['citation_count'].mean():.1f}")
with col5:
    oa_count = df['open_access'].sum() if 'open_access' in df else 0
    st.metric("Open Access", int(oa_count))

st.divider()

# ============================================
# CHARTS
# ============================================

col1, col2 = st.columns(2)

with col1:
    st.subheader("📅 Publications by Year")
    
    if 'publication_year' in df.columns:
        year_counts = df.groupby('publication_year').size().reset_index(name='count')
        year_counts = year_counts.sort_values('publication_year')
        
        fig = px.bar(year_counts, x='publication_year', y='count',
                     labels={'publication_year': 'Year', 'count': 'Publications'},
                     color_discrete_sequence=['#06b6d4'])
        fig.update_layout(
            showlegend=False,
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)',
            font_color='#94a3b8'
        )
        st.plotly_chart(fig, use_container_width=True)

with col2:
    st.subheader("📈 Citations by Year")
    
    if 'publication_year' in df.columns and 'citation_count' in df.columns:
        year_citations = df.groupby('publication_year')['citation_count'].sum().reset_index()
        year_citations = year_citations.sort_values('publication_year')
        
        fig = px.line(year_citations, x='publication_year', y='citation_count',
                      labels={'publication_year': 'Year', 'citation_count': 'Citations'},
                      markers=True)
        fig.update_traces(line_color='#8b5cf6')
        fig.update_layout(
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)',
            font_color='#94a3b8'
        )
        st.plotly_chart(fig, use_container_width=True)

st.divider()

# Top papers
st.subheader("🏆 Most Cited Papers")

if 'citation_count' in df.columns:
    top_papers = df.nlargest(10, 'citation_count')[['title', 'journal_name', 'publication_year', 'citation_count']]
    top_papers['title_short'] = top_papers['title'].str[:50] + '...'
    
    fig = px.bar(top_papers, y='title_short', x='citation_count', orientation='h',
                 labels={'title_short': '', 'citation_count': 'Citations'},
                 color_discrete_sequence=['#22c55e'])
    fig.update_layout(
        yaxis={'categoryorder': 'total ascending'},
        height=400,
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        font_color='#94a3b8'
    )
    st.plotly_chart(fig, use_container_width=True)

st.divider()

# Journals
col1, col2 = st.columns(2)

with col1:
    st.subheader("📰 Top Journals")
    
    if 'journal_name' in df.columns:
        journal_counts = df['journal_name'].value_counts().head(8).reset_index()
        journal_counts.columns = ['journal', 'count']
        
        fig = px.pie(journal_counts, values='count', names='journal',
                     color_discrete_sequence=px.colors.qualitative.Set3)
        fig.update_layout(
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)',
            font_color='#94a3b8'
        )
        st.plotly_chart(fig, use_container_width=True)

with col2:
    st.subheader("🔓 Open Access Distribution")
    
    if 'open_access' in df.columns:
        oa_count = int(df['open_access'].sum())
        closed_count = len(df) - oa_count
        
        fig = px.pie(values=[oa_count, closed_count], 
                     names=['Open Access', 'Subscription'],
                     color_discrete_sequence=['#22c55e', '#64748b'])
        fig.update_layout(
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)',
            font_color='#94a3b8'
        )
        st.plotly_chart(fig, use_container_width=True)

# Citation distribution
st.divider()
st.subheader("📊 Citation Distribution")

if 'citation_count' in df.columns:
    fig = px.histogram(df, x='citation_count', nbins=20,
                       labels={'citation_count': 'Citations', 'count': 'Papers'},
                       color_discrete_sequence=['#f59e0b'])
    fig.update_layout(
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        font_color='#94a3b8'
    )
    st.plotly_chart(fig, use_container_width=True)
