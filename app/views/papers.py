"""
app/views/papers.py

Searchable papers table (Section 29). Selecting a row shows the full
paper detail, including the validated LLM summary if AI enrichment was
used. Never fabricates missing data -- shows "Not available" instead.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from app.components.filters import render_category_selectbox, render_date_range_picker, render_source_selectbox
from app.components.style import rpi_page_header, rpi_stat_row
from database.repositories import PaperRepository


def _render_detail(paper_id: str) -> None:
    detail = PaperRepository.get_paper_detail(paper_id)
    if not detail:
        st.error("Paper not found.")
        return

    st.markdown(f"### {detail['title']}")
    rpi_stat_row(
        [
            (str(detail.get("citation_count", 0)), "Citations"),
            (detail["publication_date"].isoformat() if detail.get("publication_date") else "Unknown", "Published"),
            (", ".join(detail.get("source_names", [])) or "Unknown", "Sources"),
            (", ".join(detail.get("category_labels", [])) or "Uncategorized", "Categories"),
        ]
    )

    st.write("**Authors:** " + (", ".join(detail.get("author_names", [])) or "Not available"))

    st.write("**Abstract**")
    st.write(detail.get("abstract") or "_Not available from any source._")

    llm = detail.get("llm_enrichment")
    if llm and llm.get("status") == "VALID":
        st.write("**AI summary**")
        st.info(llm.get("summary", ""))
        col1, col2 = st.columns(2)
        with col1:
            st.write("**Topics:** " + (", ".join(llm.get("topics") or []) or "Not available"))
        with col2:
            if llm.get("confidence") is not None:
                st.write(f"**Research area:** {llm.get('research_area') or 'Not available'} "
                         f"(confidence: {llm.get('confidence'):.2f})")
    elif llm and llm.get("status") == "FAILED_REVIEW":
        st.warning("AI enrichment was attempted for this paper but did not pass validation, so no summary is shown.")
    else:
        st.caption("AI enrichment was not run for this paper.")

    link_cols = st.columns(3)
    with link_cols[0]:
        if detail.get("doi"):
            st.link_button("View DOI", f"https://doi.org/{detail['doi']}", use_container_width=True)
    with link_cols[1]:
        if detail.get("url"):
            st.link_button("Paper page", detail["url"], use_container_width=True)
    with link_cols[2]:
        if detail.get("pdf_url"):
            st.link_button("⬇ Download PDF", detail["pdf_url"], use_container_width=True, type="primary")


def render() -> None:
    rpi_page_header("Papers", "Search, filter, and open any paper's details or PDF.")

    with st.expander("Filters", expanded=True):
        col1, col2, col3 = st.columns(3)
        with col1:
            query = st.text_input("Search title/abstract", key="papers_query")
        with col2:
            category_id = render_category_selectbox("papers_category")
        with col3:
            source_name = render_source_selectbox("papers_source")
        start_date, end_date = render_date_range_picker("papers", include_all_time=True)

    results = PaperRepository.search_papers(
        query=query or None,
        category_id=category_id,
        source_name=source_name,
        start_date=start_date,
        end_date=end_date,
        limit=300,
    )

    if not results:
        st.info("No papers match these filters yet.")
        return

    render_papers_table(results, key="papers_table")


def render_papers_table(results: list[dict], key: str) -> None:
    """Shared table renderer: used by this page and reused inline on the
    Research page to show a completed job's results without navigating
    away. Includes a clickable PDF/paper-page link column."""
    df = pd.DataFrame(results)
    display_df = pd.DataFrame(
        {
            "id": df["id"],
            "Title": df["title"],
            "Authors": df["authors"],
            "Date": df["publication_date"],
            "Category": df["primary_category"].fillna("Uncategorized"),
            "Topics": df["llm_topics"].apply(lambda t: ", ".join(t) if isinstance(t, list) else "")
            if "llm_topics" in df.columns
            else "",
            "Citations": df["citation_count"],
            "Source": df["sources"],
            "Link": df.apply(
                lambda r: r.get("pdf_url") or r.get("url") or "", axis=1
            )
            if "pdf_url" in df.columns or "url" in df.columns
            else "",
        }
    )

    st.caption(f"{len(display_df)} paper(s). Click a row for full details, or use the Link column to open the PDF.")
    event = st.dataframe(
        display_df.drop(columns=["id"]),
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        column_config={
            "Link": st.column_config.LinkColumn("PDF / page", display_text="Open ↗", width="small"),
        },
        key=key,
    )

    selected_rows = event.selection.rows if event and event.selection else []
    if selected_rows:
        st.divider()
        selected_id = str(display_df.iloc[selected_rows[0]]["id"])
        _render_detail(selected_id)
