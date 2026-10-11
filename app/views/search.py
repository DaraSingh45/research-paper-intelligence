"""
app/views/search.py

The Research page. Lets the user configure and launch a search without
touching code, config files, APIs, or the database directly. Papers are
searched exclusively through OpenAlex. Launches the pipeline in a
background thread, polls job progress from PostgreSQL, and shows the
results inline once done (they also remain browsable on the Papers page).
"""
from __future__ import annotations

import threading
import time

import streamlit as st

from app.components.filters import render_category_multiselect, render_date_range_picker
from app.components.progress import render_full_job_progress
from app.components.style import rpi_page_header, rpi_pill, rpi_section
from config.loader import load_intensity_config
from ingestion.openalex import get_openalex_api_key
from llm.ollama_client import OllamaClient


def _start_pipeline_background(job_id: str, config: dict) -> None:
    def _run():
        from pipeline.orchestrator import run_full_pipeline

        try:
            run_full_pipeline(config, triggered_by="manual", existing_job_id=job_id)
        except Exception:
            pass  # already recorded on the job via fail_job() inside the orchestrator

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()


def _source_badge() -> str:
    if get_openalex_api_key():
        return rpi_pill("OpenAlex · API key set", tone="ok")
    return rpi_pill("OpenAlex · no API key", tone="caution")


def _render_intensity_picker() -> str:
    cfg = load_intensity_config()
    intensity_cfg = cfg.get("intensity", {})
    options = list(intensity_cfg.keys())  # quick, standard, deep
    default_key = cfg.get("default_intensity", "standard")
    default_index = options.index(default_key) if default_key in options else 0

    choice = st.radio(
        "Search depth",
        options,
        index=default_index,
        horizontal=True,
        format_func=lambda k: intensity_cfg[k]["label"],
        captions=[f"Up to {intensity_cfg[k]['max_results_per_source']:,} papers" for k in options],
        key="intensity_choice_radio",
        label_visibility="collapsed",
    )
    st.caption(intensity_cfg[choice]["description"])
    return choice


def _render_ai_enrichment_section() -> dict:
    result = {
        "llm_enabled": False,
        "llm_generate_summary": True,
        "llm_generate_topics": True,
        "llm_generate_research_area": True,
    }

    enabled = st.toggle("Enable local AI enrichment", value=False, key="llm_enabled")
    if not enabled:
        st.caption(
            "Optional. Generates a summary, topic labels and a research area for each paper "
            "using a locally running Ollama model."
        )
        return result

    client = OllamaClient()
    available, message = client.is_available()
    if not available:
        st.warning(f"{message} The search will still run without AI enrichment.")
        return result

    st.caption(f"{message} Runs entirely on your machine; paper content is never sent to an external AI service.")
    col1, col2, col3 = st.columns(3)
    with col1:
        gen_summary = st.checkbox("Summaries", value=True, key="llm_gen_summary")
    with col2:
        gen_topics = st.checkbox("Topic labels", value=True, key="llm_gen_topics")
    with col3:
        gen_area = st.checkbox("Research area", value=True, key="llm_gen_area")

    result.update(
        llm_enabled=True,
        llm_generate_summary=gen_summary,
        llm_generate_topics=gen_topics,
        llm_generate_research_area=gen_area,
    )
    return result


def _render_results(job_id: str) -> None:
    from app.views.papers import render_papers_table
    from database.repositories import PaperRepository

    papers = PaperRepository.list_papers_for_job(job_id)
    if not papers:
        st.info(
            "This search completed but found no papers matching your criteria. Try broadening "
            "the keywords, categories, or date range."
        )
        return

    rpi_section(f"Results · {len(papers):,} papers", "Also available any time on the Papers page.")
    render_papers_table(papers, key=f"inline_results_{job_id}")


def _render_active_job(active_job_id: str) -> None:
    job = render_full_job_progress(active_job_id)
    if not job:
        if st.button("Start a new search"):
            st.session_state["active_job_id"] = None
            st.rerun()
        return

    if job.get("status") in ("COMPLETED", "FAILED", "CANCELLED"):
        if st.button("New search", type="secondary"):
            st.session_state["active_job_id"] = None
            st.rerun()
        if job.get("status") == "COMPLETED":
            st.write("")
            _render_results(active_job_id)
    else:
        time.sleep(2)
        st.rerun()


def render() -> None:
    rpi_page_header(
        "New search",
        "Find and analyse research papers from the OpenAlex scholarly catalogue.",
        badge_html=_source_badge(),
    )

    active_job_id = st.session_state.get("active_job_id")
    if active_job_id:
        _render_active_job(active_job_id)
        return

    if not get_openalex_api_key():
        st.warning(
            "No OpenAlex API key found, so searches use OpenAlex's small shared free quota and may fail. "
            "Get a free key at openalex.org/settings/api and add `OPENALEX_API_KEY=your_key` to the "
            "`.env` file in the project folder. No restart needed: the key is picked up on the next search.",
            icon=":material/key:",
        )

    # Note: this page deliberately does NOT use st.form(). The AI enrichment
    # toggle needs an immediate rerun to show live feedback (Ollama
    # availability) -- st.form() only reruns on submit.

    with st.container(border=True):
        rpi_section("What are you looking for?", "Provide at least one of keywords, title, author or category.")
        keywords_raw = st.text_input(
            "Keywords",
            placeholder="e.g. large language models, retrieval augmented generation",
            help="Separate multiple keywords with commas.",
        )
        col1, col2, col3 = st.columns(3)
        with col1:
            title_filter = st.text_input("Title contains", placeholder="e.g. transformer")
        with col2:
            authors_raw = st.text_input("Author", placeholder="e.g. Yoshua Bengio")
        with col3:
            custom_category = st.text_input("Custom topic", placeholder="e.g. federated learning")

    with st.container(border=True):
        rpi_section("Filters")
        col1, col2 = st.columns([3, 2])
        with col1:
            categories = render_category_multiselect("research_categories", label="Categories")
        with col2:
            start_date, end_date = render_date_range_picker("research")

    col_depth, col_ai = st.columns(2)
    with col_depth:
        with st.container(border=True):
            rpi_section("Search depth")
            intensity = _render_intensity_picker()
    with col_ai:
        with st.container(border=True):
            rpi_section("AI enrichment")
            llm_config = _render_ai_enrichment_section()

    st.write("")
    _, col_btn = st.columns([3, 1])
    with col_btn:
        submitted = st.button("Start search", type="primary", use_container_width=True)

    if submitted:
        keywords = [k.strip() for k in keywords_raw.split(",") if k.strip()]
        authors = [a.strip() for a in authors_raw.split(",") if a.strip()]

        if custom_category.strip():
            keywords.append(custom_category.strip())

        if not (keywords or title_filter or authors or categories):
            st.error("Please provide at least one of: keywords, title, author, or category.")
            return
        if start_date is None or end_date is None:
            st.error("Please fix the date range before starting.")
            return

        config = {
            "keywords": keywords,
            "title_filter": title_filter or None,
            "authors": authors,
            "categories": categories,
            "custom_category": custom_category or None,
            "start_date": start_date,
            "end_date": end_date,
            "intensity": intensity,
            **llm_config,
        }

        from pipeline.orchestrator import create_job

        job_id = create_job(config, triggered_by="manual")
        st.session_state["active_job_id"] = job_id
        _start_pipeline_background(job_id, config)
        st.rerun()
