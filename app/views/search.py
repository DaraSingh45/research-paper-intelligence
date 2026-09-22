"""
app/views/search.py

The Research page (Sections 7-13). Lets the user configure and launch a
search without touching code, config files, APIs, or the database
directly. Launches the pipeline in a background thread, polls job
progress from PostgreSQL, and shows the results inline once done (they
also remain browsable anytime on the Papers page).
"""
from __future__ import annotations

import threading
import time

import streamlit as st

from app.components.filters import render_category_multiselect, render_date_range_picker
from app.components.progress import render_full_job_progress
from app.components.style import rpi_page_header
from config.loader import load_intensity_config
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


def _render_intensity_picker() -> str:
    intensity_cfg = load_intensity_config().get("intensity", {})
    options = list(intensity_cfg.keys())  # quick, standard, deep
    default_index = options.index(load_intensity_config().get("default_intensity", "standard"))

    if "intensity_choice" not in st.session_state:
        st.session_state["intensity_choice"] = options[default_index]

    st.markdown("**Search intensity**")
    cols = st.columns(len(options))
    for col, key in zip(cols, options):
        preset = intensity_cfg[key]
        with col:
            selected = st.session_state["intensity_choice"] == key
            card_class = "rpi-choice rpi-choice-selected" if selected else "rpi-choice"
            mark = " · selected" if selected else ""
            st.markdown(
                f"""
                <div class="{card_class}">
                    <div class="rpi-choice-title">{preset['label']}{mark}</div>
                    <div class="rpi-choice-desc">{preset['description']}<br>
                    Up to {preset['max_results_per_source']:,} results per source</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if st.button(
                "Selected ✓" if selected else "Select",
                key=f"intensity_btn_{key}",
                use_container_width=True,
                disabled=selected,
            ):
                st.session_state["intensity_choice"] = key
                st.rerun()

    return st.session_state["intensity_choice"]


def _render_ai_enrichment_section() -> dict:
    enabled = st.toggle("Enable local AI enrichment (optional)", value=False, key="llm_enabled")

    result = {
        "llm_enabled": False,
        "llm_generate_summary": True,
        "llm_generate_topics": True,
        "llm_generate_research_area": True,
    }

    if not enabled:
        st.caption("Works fully without this. Enable it to generate summaries, topics, and a "
                   "research area for each paper using a locally running Ollama model.")
        return result

    client = OllamaClient()
    available, message = client.is_available()
    if not available:
        st.warning(f"⚠️ {message} The rest of the pipeline will still run normally.")
        return result

    st.success(f"✓ {message}")
    col1, col2, col3 = st.columns(3)
    with col1:
        gen_summary = st.checkbox("Summaries", value=True, key="llm_gen_summary")
    with col2:
        gen_topics = st.checkbox("Topic labels", value=True, key="llm_gen_topics")
    with col3:
        gen_area = st.checkbox("Research area", value=True, key="llm_gen_area")

    st.caption(
        "Runs entirely on your machine through Ollama — paper content is never sent to an "
        "external AI service."
    )

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
        st.info("This search completed but found no papers matching your criteria. Try broadening "
                 "the keywords, categories, or date range.")
        return

    st.markdown(f"**Results — {len(papers)} paper(s) found**")
    render_papers_table(papers, key=f"inline_results_{job_id}")
    st.caption("These results are also always available on the **Papers** page.")


def render() -> None:
    rpi_page_header("Research", "Configure a search and run it against arXiv, OpenAlex, Semantic Scholar, and Crossref.")

    active_job_id = st.session_state.get("active_job_id")
    if active_job_id:
        job = render_full_job_progress(active_job_id)
        if job and job.get("status") in ("COMPLETED", "FAILED", "CANCELLED"):
            if st.button("Start a new search"):
                st.session_state["active_job_id"] = None
                st.rerun()
            if job.get("status") == "COMPLETED":
                st.divider()
                _render_results(active_job_id)
        elif job:
            time.sleep(2)
            st.rerun()
        return

    # Note: this page deliberately does NOT use st.form(). The intensity
    # picker (individual buttons) and the AI Enrichment toggle both need an
    # immediate rerun to show live feedback (selected intensity, Ollama
    # availability) -- st.form() only reruns on submit, which would hide
    # that feedback until after the pipeline had already started.

    col1, col2 = st.columns([2, 1])
    with col1:
        keywords_raw = st.text_input(
            "Keywords", placeholder="e.g. large language models, retrieval augmented generation"
        )
        title_filter = st.text_input("Title contains (optional)", placeholder="e.g. transformer")
    with col2:
        authors_raw = st.text_input("Author (optional)", placeholder="e.g. Yoshua Bengio")
        custom_category = st.text_input("Custom category (optional)", placeholder="e.g. federated learning")

    categories = render_category_multiselect("research_categories", label="Categories")
    start_date, end_date = render_date_range_picker("research")

    st.divider()
    intensity = _render_intensity_picker()

    st.divider()
    llm_config = _render_ai_enrichment_section()

    st.divider()
    submitted = st.button("🔍 Start research", type="primary", use_container_width=True)

    if submitted:
        keywords = [k.strip() for k in keywords_raw.split(",") if k.strip()]
        authors = [a.strip() for a in authors_raw.split(",") if a.strip()]

        if custom_category.strip():
            keywords.append(custom_category.strip())

        if not (keywords or title_filter or authors or categories):
            st.error("Please provide at least one of: keywords, title filter, author, or category.")
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
