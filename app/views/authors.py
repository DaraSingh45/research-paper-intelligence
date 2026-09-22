"""
app/views/authors.py

Author analytics (Section 31): top authors, authors by category, and
publication/citation statistics.
"""
from __future__ import annotations

import streamlit as st

from analytics.authors import get_author_publication_counts, get_authors_by_category, get_top_authors
from app.components.charts import bar_chart, histogram
from app.components.filters import render_category_selectbox
from app.components.style import rpi_page_header


def render() -> None:
    rpi_page_header("Authors", "Who's publishing, how often, and in which categories.")

    top_authors = get_top_authors(limit=50)
    if top_authors.empty:
        st.info("No author data yet. Run a search on the Research page first.")
        return

    st.markdown("**Top authors**")
    bar_chart(top_authors.head(15), x="display_name", y="paper_count", horizontal=True)
    st.dataframe(
        top_authors[["display_name", "paper_count", "total_citations", "avg_citations", "top_category"]].rename(
            columns={
                "display_name": "Author",
                "paper_count": "Papers",
                "total_citations": "Total citations",
                "avg_citations": "Avg citations",
                "top_category": "Top category",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )

    st.divider()
    st.markdown("**Authors by category**")
    category_id = render_category_selectbox("authors_category", include_all=False)
    if category_id:
        from config.loader import get_category_labels

        label = get_category_labels().get(category_id)
        filtered = get_authors_by_category(label, limit=20) if label else top_authors.iloc[0:0]
        if filtered.empty:
            st.info("No authors found for this category yet.")
        else:
            bar_chart(filtered, x="display_name", y="paper_count", horizontal=True)

    st.divider()
    st.markdown("**Publication count distribution**")
    counts_df = get_author_publication_counts()
    histogram(counts_df, x="paper_count", nbins=20)
