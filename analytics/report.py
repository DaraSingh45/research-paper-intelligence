"""
analytics/report.py

Generates a per-job PDF research report (Section 33): search
configuration, paper counts, main topics, publication trend, top authors,
important (highly cited) papers, and summary statistics. Scoped to a
single research job's results (unlike analytics/trends.py etc., which
report across the whole library).

Uses reportlab only (already a dependency) -- no extra chart-rendering
libraries, to keep the install light on constrained machines.
"""
from __future__ import annotations

import io
from collections import Counter
from typing import Any, Dict, List

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from database.connection import get_cursor
from database.repositories import JobRepository, PaperRepository, QualityCheckRepository


def _job_top_topics(job_id: str, limit: int = 10) -> List[tuple]:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT le.topics FROM papers p
            JOIN llm_enrichments le ON le.paper_id = p.id
            WHERE p.research_job_id = %s AND le.status = 'VALID'
            """,
            (job_id,),
        )
        rows = cur.fetchall()
    counter: Counter = Counter()
    for row in rows:
        for topic in row["topics"] or []:
            counter[topic] += 1
    return counter.most_common(limit)


def _job_top_authors(job_id: str, limit: int = 10) -> List[Dict[str, Any]]:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT a.display_name, COUNT(DISTINCT pa.paper_id) AS paper_count
            FROM paper_authors pa
            JOIN authors a ON a.id = pa.author_id
            JOIN papers p ON p.id = pa.paper_id
            WHERE p.research_job_id = %s
            GROUP BY a.display_name
            ORDER BY paper_count DESC
            LIMIT %s
            """,
            (job_id, limit),
        )
        return cur.fetchall()


def _job_publication_trend(job_id: str) -> List[Dict[str, Any]]:
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT date_trunc('month', publication_date)::date AS month, COUNT(*) AS paper_count
            FROM papers
            WHERE research_job_id = %s AND publication_date IS NOT NULL
            GROUP BY 1 ORDER BY 1
            """,
            (job_id,),
        )
        return cur.fetchall()


def generate_pdf_report(job_id: str) -> bytes:
    job = JobRepository.get_job(job_id)
    if not job:
        raise ValueError(f"Job {job_id} not found")

    papers = PaperRepository.list_papers_for_job(job_id)
    top_topics = _job_top_topics(job_id)
    top_authors = _job_top_authors(job_id)
    trend = _job_publication_trend(job_id)
    quality_checks = QualityCheckRepository.for_job(job_id)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, title=f"Research Report - {job_id}")
    styles = getSampleStyleSheet()
    story = []

    story.append(Paragraph("Research Paper Intelligence — Report", styles["Title"]))
    story.append(Paragraph(f"Job ID: {job_id}", styles["Normal"]))
    story.append(Paragraph(f"Generated: {job.get('completed_at') or job.get('created_at')}", styles["Normal"]))
    story.append(Spacer(1, 0.25 * inch))

    story.append(Paragraph("Search Configuration", styles["Heading2"]))
    config_rows = [
        ["Keywords", ", ".join(job.get("keywords") or []) or "—"],
        ["Title filter", job.get("title_filter") or "—"],
        ["Authors", ", ".join(job.get("authors") or []) or "—"],
        ["Categories", ", ".join(job.get("categories") or []) or "—"],
        ["Date range", f"{job.get('start_date') or '—'} to {job.get('end_date') or '—'}"],
        ["Intensity", job.get("intensity", "—")],
        ["AI Enrichment", "Enabled" if job.get("llm_enabled") else "Disabled"],
    ]
    story.append(_make_table([["Field", "Value"]] + config_rows))
    story.append(Spacer(1, 0.25 * inch))

    story.append(Paragraph("Summary Statistics", styles["Heading2"]))
    stats_rows = [
        ["Total found", str(job.get("total_found", 0))],
        ["Unique papers", str(job.get("total_unique", 0))],
        ["Duplicates removed", str(job.get("total_duplicates", 0))],
        ["Rejected (validation)", str(job.get("total_failed", 0))],
    ]
    story.append(_make_table([["Metric", "Value"]] + stats_rows))
    story.append(Spacer(1, 0.25 * inch))

    if quality_checks:
        story.append(Paragraph("Quality Checks", styles["Heading2"]))
        qc_rows = [[qc["check_name"], "PASS" if qc["passed"] else "REVIEW", str(qc["details"])[:80]] for qc in quality_checks]
        story.append(_make_table([["Check", "Result", "Details"]] + qc_rows))
        story.append(Spacer(1, 0.25 * inch))

    if trend:
        story.append(Paragraph("Publication Trend (by month)", styles["Heading2"]))
        trend_rows = [[str(r["month"]), str(r["paper_count"])] for r in trend]
        story.append(_make_table([["Month", "Papers"]] + trend_rows))
        story.append(Spacer(1, 0.25 * inch))

    if top_topics:
        story.append(Paragraph("Main Topics", styles["Heading2"]))
        topic_rows = [[topic, str(count)] for topic, count in top_topics]
        story.append(_make_table([["Topic", "Paper Count"]] + topic_rows))
        story.append(Spacer(1, 0.25 * inch))

    if top_authors:
        story.append(Paragraph("Top Authors", styles["Heading2"]))
        author_rows = [[a["display_name"], str(a["paper_count"])] for a in top_authors]
        story.append(_make_table([["Author", "Papers"]] + author_rows))
        story.append(Spacer(1, 0.25 * inch))

    important_papers = sorted(papers, key=lambda p: p.get("citation_count") or 0, reverse=True)[:10]
    if important_papers:
        story.append(Paragraph("Important Papers (most cited)", styles["Heading2"]))
        for p in important_papers:
            story.append(Paragraph(f"<b>{p['title']}</b>", styles["Normal"]))
            story.append(
                Paragraph(
                    f"Citations: {p.get('citation_count', 0)} | Authors: {p.get('authors') or '—'} | "
                    f"Published: {p.get('publication_date') or 'Unknown'}",
                    styles["Normal"],
                )
            )
            story.append(Spacer(1, 0.1 * inch))

    doc.build(story)
    return buffer.getvalue()


def _make_table(rows: List[List[str]]) -> Table:
    table = Table(rows, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1B1E29")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]
        )
    )
    return table
