"""
app/views/topics.py

Topic analytics (Section 30). All topic data comes from validated LLM
enrichments -- if AI enrichment was never enabled, this page explains
that instead of showing empty charts with no context.
"""
from __future__ import annotations

import streamlit as st

from analytics.topics import get_top_topics, get_topic_growth, get_topics_by_category
from app.components.charts import bar_chart, line_chart
from app.components.style import rpi_page_header


def render() -> None:
    rpi_page_header("Topics", "AI-derived topics from papers where enrichment was enabled.")

    top_topics = get_top_topics(limit=20)
    if top_topics.empty:
        st.info("No topic data yet. Run a search with AI Enrichment enabled to see topics here.")
        return

    st.markdown("**Top topics**")
    bar_chart(top_topics, x="topic", y="total_paper_count", horizontal=True)

    st.markdown("**Topic growth over time**")
    selected_topic = st.selectbox(
        "Focus on a topic (optional)", ["All top topics"] + top_topics["topic"].tolist(), key="topics_focus"
    )
    growth_df = get_topic_growth(None if selected_topic == "All top topics" else selected_topic)
    if selected_topic == "All top topics" and not growth_df.empty:
        top_names = top_topics["topic"].head(8).tolist()
        growth_df = growth_df[growth_df["topic"].isin(top_names)]
    line_chart(growth_df, x="month", y="paper_count", color="topic")

    st.markdown("**Topics by category**")
    by_category = get_topics_by_category(limit_per_category=5)
    if by_category.empty:
        st.info("No category-linked topic data yet.")
    else:
        for category in by_category["category_label"].dropna().unique():
            with st.expander(category or "Uncategorized"):
                subset = by_category[by_category["category_label"] == category]
                bar_chart(subset, x="topic", y="paper_count", horizontal=True)
