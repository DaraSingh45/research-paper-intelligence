"""
app/components/progress.py

Renders a research job's live progress (Section 12 example: job id,
progress bar, current step) by polling the research_jobs / job_logs
tables. Used by the Research page while a job is running and by the
Jobs page when reopening a past job.
"""
from __future__ import annotations

from typing import Any, Dict

import streamlit as st

from app.components.style import rpi_mono, rpi_pill
from database.repositories import JobRepository

SOURCE_LABELS = {
    "arxiv": "arXiv",
    "openalex": "OpenAlex",
    "semantic_scholar": "Semantic Scholar",
    "crossref": "Crossref",
}

STATUS_ICONS = {
    "PENDING": "○",
    "RUNNING": "◐",
    "COMPLETED": "●",
    "FAILED": "✕",
    "CANCELLED": "–",
}


def render_job_header(job: Dict[str, Any]) -> None:
    icon = STATUS_ICONS.get(job["status"], "")
    st.markdown(f"### {icon} Research job — {rpi_mono(job['id'])}", unsafe_allow_html=True)
    st.caption(f"Status: **{job['status']}** · Intensity: **{job['intensity']}** · Triggered by: {job.get('triggered_by', 'manual')}")


def render_progress_bar(job: Dict[str, Any]) -> None:
    percent = int(job.get("progress_percent") or 0)
    st.progress(percent / 100.0, text=f"{job.get('current_step') or 'Working...'} — {percent}%")


def render_source_status(job: Dict[str, Any]) -> None:
    source_status = job.get("source_status") or {}
    if not source_status:
        return
    parts = []
    for source, status in source_status.items():
        label = SOURCE_LABELS.get(source, source)
        ok = status == "ok"
        text = label if ok else f"{label} — {status}"
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
    with st.expander("Job logs (technical details)", expanded=False):
        for log in logs:
            level = log["level"]
            prefix = {"ERROR": "🔴", "WARNING": "🟡", "INFO": "⚪", "DEBUG": "⚫"}.get(level, "⚪")
            source = f"[{log['source']}] " if log.get("source") else ""
            st.text(f"{prefix} {log['ts']:%H:%M:%S} {source}{log['message']}")


def render_full_job_progress(job_id: str) -> Dict[str, Any]:
    """Renders the whole progress panel and returns the latest job row,
    so the caller can decide whether to keep polling."""
    job = JobRepository.get_job(job_id)
    if not job:
        st.error("Job not found.")
        return {}
    render_job_header(job)
    render_progress_bar(job)
    render_source_status(job)
    render_counts(job)
    if job.get("error_message"):
        st.error(f"Something went wrong: {job['error_message']}")
    render_job_logs(job_id)
    return job
