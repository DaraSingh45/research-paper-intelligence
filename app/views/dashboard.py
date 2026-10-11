"""
app/views/dashboard.py

The main analytics dashboard. Reads from the dbt marts via analytics/*.py.
If dbt hasn't been run yet, charts show a friendly empty state instead of
erroring.
"""
from __future__ import annotations

import streamlit as st

from analytics.authors import get_top_authors
from analytics.topics import get_top_topics, get_topic_growth
from analytics.trends import (
    get_category_distribution,
    get_citation_distribution,
    get_publication_trends,
)
from app.components.charts import bar_chart, histogram, line_chart, pie_chart
from app.components.metrics import render_paper_counts
from app.components.style import rpi_page_header, rpi_section
from database.repositories import PaperRepository


def render() -> None:
    rpi_page_header("Dashboard", "An overview of every paper collected from OpenAlex so far.")

    counts = PaperRepository.count_papers()
    render_paper_counts(counts)

    if counts.get("unique_papers", 0) == 0:
        st.info("No papers yet. Go to **New search** to run your first search.")
        return

    col1, col2 = st.columns(2, gap="medium")
    with col1:
        with st.container(border=True):
            head, ctrl = st.columns([3, 2])
            with head:
                rpi_section("Publications over time")
            with ctrl:
                granularity = st.selectbox(
                    "Granularity",
                    ["day", "week", "month", "year"],
                    index=2,
                    key="dash_granularity",
                    label_visibility="collapsed",
                    format_func=str.capitalize,
                )
            line_chart(get_publication_trends(granularity), x="period", y="paper_count")

    with col2:
        with st.container(border=True):
            rpi_section("Topic growth", "Top AI-derived topics by month")
            topic_growth_df = get_topic_growth()
            if not topic_growth_df.empty:
                top_topics = get_top_topics(limit=6)["topic"].tolist()
                filtered = topic_growth_df[topic_growth_df["topic"].isin(top_topics)]
                line_chart(filtered, x="month", y="paper_count", color="topic")
            else:
                st.caption("No topic data yet. Enable AI enrichment on a search to generate topics.")

    col3, col4 = st.columns(2, gap="medium")
    with col3:
        with st.container(border=True):
            rpi_section("Category distribution")
            pie_chart(get_category_distribution(), names="category_label", values="paper_count")

    with col4:
        with st.container(border=True):
            rpi_section("Top authors", "By number of papers")
            bar_chart(get_top_authors(limit=10), x="display_name", y="paper_count", horizontal=True)

    with st.container(border=True):
        rpi_section("Citation distribution", "How many times papers in the collection have been cited")
        histogram(get_citation_distribution(), x="citation_count")
