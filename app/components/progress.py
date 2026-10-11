"""
app/components/progress.py

Renders a research job's live progress (job id, progress bar, current
step, counts) by polling the research_jobs / job_logs tables. Used by the
Research page while a job is running and by the Jobs page when reopening a
past job.
"""
from __future__ import annotations

import html
from typing import Any, Dict

import streamlit as st

from app.components.style import rpi_mono, rpi_pill, rpi_status_pill
from database.repositories import JobRepository

SOURCE_LABELS = {
    "openalex": "OpenAlex",
    # Legacy sources -- only appear on jobs created before the switch to OpenAlex-only.
    "arxiv": "arXiv",
    "semantic_scholar": "Semantic Scholar",
    "crossref": "Crossref",
}


def _esc(text: object) -> str:
    return html.escape(str(text), quote=True)


def render_job_header(job: Dict[str, Any]) -> None:
    keywords = ", ".join(job.get("keywords") or []) or job.get("title_filter") or "Research job"
    meta = (
        f"Job {rpi_mono(job['id'])} &nbsp;·&nbsp; {_esc(str(job.get('intensity', '')).capitalize())} search"
        f" &nbsp;·&nbsp; Triggered {_esc(job.get('triggered_by', 'manual'))}"
    )
    st.markdown(
        '<div style="display:flex;align-items:center;justify-content:space-between;gap:1rem;flex-wrap:wrap;">'
        f'<div style="font-weight:600;font-size:1.05rem;">{_esc(keywords)}</div>'
        f'{rpi_status_pill(job.get("status", ""))}</div>'
        f'<div style="color:var(--rpi-text-muted);font-size:0.84rem;margin:0.35rem 0 0.9rem 0;">{meta}</div>',
        unsafe_allow_html=True,
    )


def render_progress_bar(job: Dict[str, Any]) -> None:
    percent = int(job.get("progress_percent") or 0)
    st.progress(percent / 100.0, text=f"{job.get('current_step') or 'Working...'} · {percent}%")


def render_source_status(job: Dict[str, Any]) -> None:
    source_status = job.get("source_status") or {}
    if not source_status:
        return
    parts = []
    for source, status in source_status.items():
        label = SOURCE_LABELS.get(source, source)
        ok = status == "ok"
        text = f"{label} connected" if ok else f"{label}: {status}"
        parts.append(rpi_pill(text, ok=ok))
    st.markdown(" ".join(parts), unsafe_allow_html=True)


def render_counts(job: Dict[str, Any]) -> None:
    from app.components.metrics import render_metric_row

    render_metric_row(
        [
            ("Found", f"{job.get('total_found', 0):,}"),
            ("Unique", f"{job.get('total_unique', 0):,}"),
            ("Duplicates", f"{job.get('total_duplicates', 0):,}"),
            ("Rejected", f"{job.get('total_failed', 0):,}"),
        ]
    )


def render_job_logs(job_id: str, limit: int = 200) -> None:
    logs = JobRepository.get_logs(job_id, limit=limit)
    if not logs:
        st.caption("No log entries yet.")
        return
    with st.expander("Technical log", expanded=False):
        lines = []
        for log in logs:
            level = log["level"]
            source = f"[{log['source']}] " if log.get("source") else ""
            lines.append(f"{log['ts']:%H:%M:%S}  {level:<7} {source}{log['message']}")
        st.code("\n".join(lines), language=None)


def render_full_job_progress(job_id: str) -> Dict[str, Any]:
    """Renders the whole progress panel and returns the latest job row,
    so the caller can decide whether to keep polling."""
    job = JobRepository.get_job(job_id)
    if not job:
        st.error("Job not found.")
        return {}
    with st.container(border=True):
        render_job_header(job)
        render_progress_bar(job)
        render_source_status(job)
        st.write("")
        render_counts(job)
        if job.get("error_message"):
            st.error(f"Something went wrong: {job['error_message']}")
        render_job_logs(job_id)
    return job
