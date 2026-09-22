"""
app/views/jobs.py

Jobs page (Section 32): shows all previous jobs, lets the user open one,
manage recurring scheduled searches (Section 35), and export results
(Section 33).
"""
from __future__ import annotations

import json

import pandas as pd
import streamlit as st

from app.components.progress import render_full_job_progress
from app.components.style import rpi_page_header
from database.repositories import JobRepository, PaperRepository, ScheduledSearchRepository


def _render_export_buttons(job_id: str) -> None:
    papers = PaperRepository.list_papers_for_job(job_id)
    if not papers:
        st.caption("No papers to export for this job.")
        return

    df = pd.DataFrame(papers)
    csv_bytes = df.to_csv(index=False).encode("utf-8")
    json_bytes = json.dumps(papers, indent=2, default=str).encode("utf-8")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.download_button("⬇ CSV", csv_bytes, file_name=f"{job_id}_papers.csv", mime="text/csv", use_container_width=True)
    with col2:
        st.download_button("⬇ JSON", json_bytes, file_name=f"{job_id}_papers.json", mime="application/json", use_container_width=True)
    with col3:
        if st.button("Generate PDF report", use_container_width=True):
            with st.spinner("Building report..."):
                from analytics.report import generate_pdf_report

                pdf_bytes = generate_pdf_report(job_id)
            st.download_button(
                "⬇ Download PDF report", pdf_bytes, file_name=f"{job_id}_report.pdf", mime="application/pdf"
            )


def _render_scheduling_section() -> None:
    st.caption("A scheduled job reuses a saved configuration and runs automatically via Airflow.")

    schedules = ScheduledSearchRepository.list_all()
    if schedules:
        for s in schedules:
            with st.expander(f"{s['name']} — {s['frequency'].capitalize()} {'(active)' if s['active'] else '(paused)'}"):
                st.json(s["config"])
                col1, col2 = st.columns(2)
                with col1:
                    st.caption(f"Last run: {s.get('last_run_at') or 'never'}")
                with col2:
                    if s["active"]:
                        if st.button("Pause", key=f"pause_{s['id']}"):
                            ScheduledSearchRepository.set_active(s["id"], False)
                            st.rerun()
                    else:
                        if st.button("Resume", key=f"resume_{s['id']}"):
                            ScheduledSearchRepository.set_active(s["id"], True)
                            st.rerun()
    else:
        st.caption("No scheduled searches yet.")

    with st.expander("Create a scheduled search from a past job"):
        jobs = JobRepository.list_jobs(limit=50)
        completed_jobs = [j for j in jobs if j["status"] == "COMPLETED"]
        if not completed_jobs:
            st.caption("Complete at least one search on the Research page first, then reuse its configuration here.")
        else:
            options = {f"{j['id']} — {', '.join(j.get('keywords') or []) or j.get('title_filter') or '(no keywords)'}": j for j in completed_jobs}
            choice = st.selectbox("Base configuration on job", list(options.keys()), key="sched_base_job")
            name = st.text_input("Schedule name", value=f"Recurring: {choice.split(' — ')[0]}", key="sched_name")
            frequency = st.selectbox("Frequency", ["off", "daily", "weekly", "monthly"], index=1, key="sched_freq")
            if st.button("Create schedule"):
                base_job = options[choice]
                config = {
                    "keywords": base_job.get("keywords") or [],
                    "title_filter": base_job.get("title_filter"),
                    "authors": base_job.get("authors") or [],
                    "categories": base_job.get("categories") or [],
                    "start_date": None,
                    "end_date": None,
                    "intensity": base_job.get("intensity", "standard"),
                    "llm_enabled": base_job.get("llm_enabled", False),
                }
                ScheduledSearchRepository.create(name, config, frequency)
                st.success("Scheduled search created.")
                st.rerun()


def _render_history() -> None:
    jobs = JobRepository.list_jobs(limit=100)
    if not jobs:
        st.info("No jobs yet. Run a search on the Research page first.")
        return

    table_df = pd.DataFrame(
        [
            {
                "id": j["id"],
                "Job ID": j["id"],
                "Date": j["created_at"],
                "Query": ", ".join(j.get("keywords") or []) or (j.get("title_filter") or "—"),
                "Intensity": j["intensity"],
                "Papers": j.get("total_unique", 0),
                "Status": j["status"],
            }
            for j in jobs
        ]
    )

    event = st.dataframe(
        table_df.drop(columns=["id"]),
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
    )

    selected_rows = event.selection.rows if event and event.selection else []
    if selected_rows:
        st.divider()
        job_id = str(table_df.iloc[selected_rows[0]]["id"])
        job = render_full_job_progress(job_id)
        if job.get("status") == "COMPLETED":
            st.markdown("**Export**")
            _render_export_buttons(job_id)


def render() -> None:
    rpi_page_header("Jobs", "Your search history, plus recurring scheduled searches.")

    tab_history, tab_scheduled = st.tabs(["History", "Scheduled searches"])
    with tab_history:
        _render_history()
    with tab_scheduled:
        _render_scheduling_section()
