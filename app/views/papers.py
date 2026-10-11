"""
app/views/papers.py

Searchable papers table. Selecting a row shows the full paper detail,
including the validated LLM summary if AI enrichment was used. Never
fabricates missing data -- shows "Not available" instead.
"""
from __future__ import annotations

import html

import pandas as pd
import streamlit as st

from app.components.filters import render_category_selectbox, render_date_range_picker
from app.components.style import rpi_page_header, rpi_pill, rpi_section, rpi_stat_row
from database.repositories import PaperRepository


def _esc(text: object) -> str:
    return html.escape(str(text), quote=True)


def _is_openalex_url(url: str | None) -> bool:
    return bool(url) and "openalex.org" in url


def best_paper_link(paper: dict) -> str:
    """Best link to open a paper: PDF, then publisher page, then DOI, and only
    then OpenAlex. openalex.org pages call the OpenAlex API from your browser
    without your API key, so they fail once your network's shared free quota
    is used up."""
    def _str(key: str) -> str | None:
        value = paper.get(key)
        return value if isinstance(value, str) and value.strip() else None  # skips None/NaN

    pdf, url, doi = _str("pdf_url"), _str("url"), _str("doi")
    if pdf:
        return pdf
    if url and not _is_openalex_url(url):
        return url
    if doi:
        return f"https://doi.org/{doi}"
    return url or ""


def _render_detail(paper_id: str) -> None:
    detail = PaperRepository.get_paper_detail(paper_id)
    if not detail:
        st.error("Paper not found.")
        return

    with st.container(border=True):
        st.markdown(f"### {detail['title']}")
        authors = ", ".join(detail.get("author_names", [])) or "Authors not available"
        st.caption(authors)

        rpi_stat_row(
            [
                (f"{detail.get('citation_count', 0) or 0:,}", "Citations"),
                (detail["publication_date"].isoformat() if detail.get("publication_date") else "Unknown", "Published"),
                (detail.get("venue") or detail.get("journal") or "Not available", "Venue"),
                (", ".join(detail.get("category_labels", [])) or "Uncategorized", "Category"),
            ]
        )

        rpi_section("Abstract")
        abstract = detail.get("abstract")
        if abstract:
            st.markdown(f'<div class="rpi-abstract">{_esc(abstract)}</div>', unsafe_allow_html=True)
        else:
            st.caption("No abstract is available for this paper in OpenAlex.")

        llm = detail.get("llm_enrichment")
        if llm and llm.get("status") == "VALID":
            st.write("")
            rpi_section("AI summary", "Generated locally with Ollama.")
            st.info(llm.get("summary", ""))
            topics = llm.get("topics") or []
            if topics:
                st.markdown(" ".join(rpi_pill(t, tone="info") for t in topics), unsafe_allow_html=True)
            if llm.get("research_area"):
                conf = llm.get("confidence")
                conf_text = f" (confidence {conf:.2f})" if conf is not None else ""
                st.caption(f"Research area: {llm.get('research_area')}{conf_text}")
        elif llm and llm.get("status") == "FAILED_REVIEW":
            st.caption("AI enrichment was attempted but did not pass validation, so no summary is shown.")

        st.write("")
        doi_url = f"https://doi.org/{detail['doi']}" if detail.get("doi") else None
        page_url = detail.get("url") if detail.get("url") and not _is_openalex_url(detail.get("url")) else None
        links = []
        if detail.get("pdf_url"):
            links.append(("Open PDF", detail["pdf_url"], "primary"))
        if page_url and page_url != doi_url:
            links.append(("Publisher page", page_url, "secondary"))
        if doi_url:
            links.append(("View DOI", doi_url, "secondary"))
        if not links and detail.get("url"):
            links.append(("OpenAlex record", detail["url"], "secondary"))
        if links:
            for col, (label, url, kind) in zip(st.columns(3), links):
                with col:
                    st.link_button(label, url, use_container_width=True, type=kind)
        else:
            st.caption("No link is available for this paper.")


def render() -> None:
    rpi_page_header("Papers", "Browse, filter and open every paper collected so far.")

    with st.container(border=True):
        col1, col2, col3 = st.columns([2, 1, 1])
        with col1:
            query = st.text_input(
                "Search", placeholder="Search titles and abstracts", key="papers_query",
            )
        with col2:
            category_id = render_category_selectbox("papers_category")
        with col3:
            start_date, end_date = render_date_range_picker("papers", include_all_time=True)

    results = PaperRepository.search_papers(
        query=query or None,
        category_id=category_id,
        source_name=None,
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
    has_links = "pdf_url" in df.columns or "url" in df.columns
    display_df = pd.DataFrame(
        {
            "id": df["id"],
            "Title": df["title"],
            "Authors": df["authors"],
            "Published": df["publication_date"],
            "Category": df["primary_category"].fillna("Uncategorized"),
            "Topics": df["llm_topics"].apply(lambda t: ", ".join(t) if isinstance(t, list) else "")
            if "llm_topics" in df.columns
            else "",
            "Citations": df["citation_count"],
            "Link": df.apply(lambda r: best_paper_link(r.to_dict()), axis=1) if has_links else "",
        }
    )
    # Hide the Topics column entirely when no paper has AI topics.
    if not display_df["Topics"].astype(bool).any():
        display_df = display_df.drop(columns=["Topics"])

    st.caption(f"{len(display_df):,} papers · select a row to see details")
    event = st.dataframe(
        display_df.drop(columns=["id"]),
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        column_config={
            "Title": st.column_config.TextColumn("Title", width="large"),
            "Authors": st.column_config.TextColumn("Authors", width="medium"),
            "Published": st.column_config.DateColumn("Published", format="YYYY-MM-DD", width="small"),
            "Citations": st.column_config.NumberColumn("Citations", format="%d", width="small"),
            "Link": st.column_config.LinkColumn("Link", display_text="Open", width="small"),
        },
        key=key,
    )

    selected_rows = event.selection.rows if event and event.selection else []
    if selected_rows:
        st.write("")
        selected_id = str(display_df.iloc[selected_rows[0]]["id"])
        _render_detail(selected_id)
