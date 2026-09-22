"""
app/views/dashboard.py

The main analytics dashboard (Section 28). Reads from the dbt marts via
analytics/*.py. If dbt hasn't been run yet, charts show a friendly empty
state instead of erroring.
"""
from __future__ import annotations

import streamlit as st

from analytics.authors import get_top_authors
from analytics.trends import (
    get_category_distribution,
    get_citation_distribution,
    get_publication_trends,
    get_source_distribution,
)
from analytics.topics import get_top_topics, get_topic_growth
from app.components.charts import bar_chart, histogram, line_chart, pie_chart
from app.components.metrics import render_paper_counts
from app.components.style import rpi_page_header
from database.repositories import PaperRepository


def render() -> None:
    rpi_page_header("Dashboard", "An overview of everything collected so far.")

    counts = PaperRepository.count_papers()
    render_paper_counts(counts)

    if counts.get("unique_papers", 0) == 0:
        st.info("No papers yet. Head to the **Research** page to run your first search.")
        return

    col1, col2 = st.columns(2, gap="large")
    with col1:
        st.markdown("**Publications over time**")
        granularity = st.selectbox(
            "Granularity", ["day", "week", "month", "year"], index=2, key="dash_granularity", label_visibility="collapsed"
        )
        trends_df = get_publication_trends(granularity)
        line_chart(trends_df, x="period", y="paper_count")

    with col2:
        st.markdown("**Topic growth**")
        topic_growth_df = get_topic_growth()
        if not topic_growth_df.empty:
            top_topics = get_top_topics(limit=6)["topic"].tolist()
            filtered = topic_growth_df[topic_growth_df["topic"].isin(top_topics)]
            line_chart(filtered, x="month", y="paper_count", color="topic")
        else:
            st.info("No topic data yet. Enable AI Enrichment on a search to generate topics.")

    col3, col4 = st.columns(2, gap="large")
    with col3:
        st.markdown("**Category distribution**")
        cat_df = get_category_distribution()
        pie_chart(cat_df, names="category_label", values="paper_count")

    with col4:
        st.markdown("**Top authors**")
        authors_df = get_top_authors(limit=10)
        bar_chart(authors_df, x="display_name", y="paper_count", horizontal=True)

    col5, col6 = st.columns(2, gap="large")
    with col5:
        st.markdown("**Citation distribution**")
        citations_df = get_citation_distribution()
        histogram(citations_df, x="citation_count")

    with col6:
        st.markdown("**Source distribution**")
        source_df = get_source_distribution()
        bar_chart(source_df, x="source_name", y="paper_count")
