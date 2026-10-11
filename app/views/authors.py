"""
app/views/authors.py

Author analytics: top authors, authors by category, and
publication/citation statistics.
"""
from __future__ import annotations

import streamlit as st

from analytics.authors import get_author_publication_counts, get_authors_by_category, get_top_authors
from app.components.charts import bar_chart, histogram
from app.components.filters import render_category_selectbox
from app.components.style import rpi_page_header, rpi_section


def render() -> None:
    rpi_page_header("Authors", "Who is publishing, how often, and in which categories.")

    top_authors = get_top_authors(limit=50)
    if top_authors.empty:
        st.info("No author data yet. Run a search first.")
        return

    with st.container(border=True):
        rpi_section("Top authors", "By number of papers in your collection")
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
            column_config={"Avg citations": st.column_config.NumberColumn(format="%.1f")},
        )

    col1, col2 = st.columns(2, gap="medium")
    with col1:
        with st.container(border=True):
            rpi_section("Authors by category")
            category_id = render_category_selectbox("authors_category", include_all=False)
            if category_id:
                from config.loader import get_category_labels

                label = get_category_labels().get(category_id)
                filtered = get_authors_by_category(label, limit=20) if label else top_authors.iloc[0:0]
                if filtered.empty:
                    st.caption("No authors found for this category yet.")
                else:
                    bar_chart(filtered, x="display_name", y="paper_count", horizontal=True)

    with col2:
        with st.container(border=True):
            rpi_section("Publication count distribution", "Papers per author")
            histogram(get_author_publication_counts(), x="paper_count", nbins=20)
