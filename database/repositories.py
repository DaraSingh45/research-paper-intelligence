"""
database/repositories.py

Repository layer: every SQL statement in the application lives here.
Other modules (pipeline, app pages, analytics) should never write raw SQL
themselves for OLTP operations -- they call into these repositories.
(Analytics read queries against dbt marts are the one exception; see
analytics/*.py, since those are reporting queries, not transactional ones.)
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from database.connection import get_cursor
from database.models import JobStatus, NormalizedPaper

logger = logging.getLogger(__name__)


# ======================================================================
# Jobs
# ======================================================================
class JobRepository:
    @staticmethod
    def create_job(job_id: str, config: Dict[str, Any], triggered_by: str = "manual") -> None:
        with get_cursor() as cur:
            cur.execute(
                """
                INSERT INTO research_jobs
                    (id, status, keywords, title_filter, authors, categories,
                     start_date, end_date, intensity, llm_enabled, llm_options,
                     triggered_by)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    job_id,
                    JobStatus.PENDING.value,
                    config.get("keywords", []),
                    config.get("title_filter"),
                    config.get("authors", []),
                    config.get("categories", []),
                    config.get("start_date"),
                    config.get("end_date"),
                    config.get("intensity", "standard"),
                    config.get("llm_enabled", False),
                    json.dumps(
                        {
                            "generate_summary": config.get("llm_generate_summary", True),
                            "generate_topics": config.get("llm_generate_topics", True),
                            "generate_research_area": config.get("llm_generate_research_area", True),
                        }
                    ),
                    triggered_by,
                ),
            )

    @staticmethod
    def set_status(job_id: str, status: JobStatus, error_message: Optional[str] = None) -> None:
        fields = ["status = %s"]
        params: List[Any] = [status.value]
        if status == JobStatus.RUNNING:
            fields.append("started_at = COALESCE(started_at, now())")
        if status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
            fields.append("completed_at = now()")
        if error_message is not None:
            fields.append("error_message = %s")
            params.append(error_message)
        params.append(job_id)
        with get_cursor() as cur:
            cur.execute(f"UPDATE research_jobs SET {', '.join(fields)} WHERE id = %s", params)

    @staticmethod
    def update_progress(job_id: str, step: str, percent: int) -> None:
        with get_cursor() as cur:
            cur.execute(
                "UPDATE research_jobs SET current_step = %s, progress_percent = %s WHERE id = %s",
                (step, max(0, min(100, percent)), job_id),
            )

    @staticmethod
    def update_counts(
        job_id: str,
        total_found: Optional[int] = None,
        total_unique: Optional[int] = None,
        total_duplicates: Optional[int] = None,
        total_failed: Optional[int] = None,
    ) -> None:
        fields, params = [], []
        for name, val in (
            ("total_found", total_found),
            ("total_unique", total_unique),
            ("total_duplicates", total_duplicates),
            ("total_failed", total_failed),
        ):
            if val is not None:
                fields.append(f"{name} = %s")
                params.append(val)
        if not fields:
            return
        params.append(job_id)
        with get_cursor() as cur:
            cur.execute(f"UPDATE research_jobs SET {', '.join(fields)} WHERE id = %s", params)

    @staticmethod
    def update_source_status(job_id: str, source: str, status: str) -> None:
        with get_cursor() as cur:
            cur.execute(
                """
                UPDATE research_jobs
                SET source_status = source_status || jsonb_build_object(%s, %s)
                WHERE id = %s
                """,
                (source, status, job_id),
            )

    @staticmethod
    def get_job(job_id: str) -> Optional[Dict[str, Any]]:
        with get_cursor() as cur:
            cur.execute("SELECT * FROM research_jobs WHERE id = %s", (job_id,))
            return cur.fetchone()

    @staticmethod
    def list_jobs(limit: int = 100) -> List[Dict[str, Any]]:
        with get_cursor() as cur:
            cur.execute(
                "SELECT * FROM research_jobs ORDER BY created_at DESC LIMIT %s", (limit,)
            )
            return cur.fetchall()

    @staticmethod
    def append_log(job_id: str, message: str, level: str = "INFO", source: Optional[str] = None) -> None:
        try:
            with get_cursor() as cur:
                cur.execute(
                    "INSERT INTO job_logs (job_id, level, source, message) VALUES (%s, %s, %s, %s)",
                    (job_id, level, source, message),
                )
        except Exception:  # noqa: BLE001 - logging must never break the pipeline
            logger.exception("Failed to write job log for job_id=%s", job_id)

    @staticmethod
    def get_logs(job_id: str, limit: int = 500) -> List[Dict[str, Any]]:
        with get_cursor() as cur:
            cur.execute(
                "SELECT * FROM job_logs WHERE job_id = %s ORDER BY ts ASC LIMIT %s",
                (job_id, limit),
            )
            return cur.fetchall()


# ======================================================================
# Sources & Categories (mostly-static reference tables)
# ======================================================================
class SourceRepository:
    _cache: Dict[str, int] = {}

    @classmethod
    def get_source_id(cls, name: str) -> int:
        if name in cls._cache:
            return cls._cache[name]
        with get_cursor() as cur:
            cur.execute("SELECT id FROM sources WHERE name = %s", (name,))
            row = cur.fetchone()
            if row is None:
                cur.execute("INSERT INTO sources (name) VALUES (%s) RETURNING id", (name,))
                row = cur.fetchone()
        cls._cache[name] = row["id"]
        return row["id"]


class CategoryRepository:
    @staticmethod
    def ensure_categories(categories: List[Dict[str, str]]) -> None:
        """Idempotently syncs config/categories.yaml into the categories table."""
        with get_cursor() as cur:
            for c in categories:
                cur.execute(
                    """
                    INSERT INTO categories (id, label) VALUES (%s, %s)
                    ON CONFLICT (id) DO UPDATE SET label = EXCLUDED.label
                    """,
                    (c["id"], c["label"]),
                )

    @staticmethod
    def list_categories() -> List[Dict[str, Any]]:
        with get_cursor() as cur:
            cur.execute("SELECT * FROM categories ORDER BY label")
            return cur.fetchall()


# ======================================================================
# Authors
# ======================================================================
class AuthorRepository:
    @staticmethod
    def upsert_author(display_name: str, normalized_name: str) -> str:
        with get_cursor() as cur:
            cur.execute(
                """
                INSERT INTO authors (display_name, normalized_name)
                VALUES (%s, %s)
                ON CONFLICT (normalized_name) DO UPDATE SET display_name = authors.display_name
                RETURNING id
                """,
                (display_name, normalized_name),
            )
            return str(cur.fetchone()["id"])


# ======================================================================
# Papers (the core write path used by the pipeline)
# ======================================================================
class PaperRepository:
    @staticmethod
    def find_by_doi(doi: str) -> Optional[Dict[str, Any]]:
        if not doi:
            return None
        with get_cursor() as cur:
            cur.execute("SELECT * FROM papers WHERE doi = %s", (doi,))
            return cur.fetchone()

    @staticmethod
    def find_by_external_id(source_name: str, external_id: str) -> Optional[Dict[str, Any]]:
        with get_cursor() as cur:
            cur.execute(
                """
                SELECT p.* FROM papers p
                JOIN paper_sources ps ON ps.paper_id = p.id
                JOIN sources s ON s.id = ps.source_id
                WHERE s.name = %s AND ps.external_id = %s
                """,
                (source_name, external_id),
            )
            return cur.fetchone()

    @staticmethod
    def find_by_normalized_title(title_normalized: str) -> Optional[Dict[str, Any]]:
        with get_cursor() as cur:
            cur.execute(
                "SELECT * FROM papers WHERE title_normalized = %s LIMIT 1", (title_normalized,)
            )
            return cur.fetchone()

    @staticmethod
    def find_candidates_for_fuzzy_match(publication_year: Optional[int]) -> List[Dict[str, Any]]:
        """Small candidate pool (same year) for fuzzy title comparison, so we
        never scan the whole table for a similarity check."""
        with get_cursor() as cur:
            if publication_year:
                cur.execute(
                    """
                    SELECT id, title, title_normalized FROM papers
                    WHERE EXTRACT(YEAR FROM publication_date) = %s
                    """,
                    (publication_year,),
                )
            else:
                cur.execute(
                    "SELECT id, title, title_normalized FROM papers ORDER BY created_at DESC LIMIT 500"
                )
            return cur.fetchall()

    @staticmethod
    def insert_paper(paper: NormalizedPaper, job_id: Optional[str]) -> str:
        with get_cursor() as cur:
            cur.execute(
                """
                INSERT INTO papers
                    (title, title_normalized, abstract, publication_date, doi, url,
                     pdf_url, journal, venue, publisher, language, citation_count,
                     primary_category_id, research_job_id, raw_source_data)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    paper.title,
                    paper.title_normalized,
                    paper.abstract,
                    paper.publication_date,
                    paper.doi,
                    paper.url,
                    paper.pdf_url,
                    paper.journal,
                    paper.venue,
                    paper.publisher,
                    paper.language,
                    paper.citation_count,
                    paper.internal_categories[0] if paper.internal_categories else "uncategorized",
                    job_id,
                    json.dumps({paper.source: paper.raw_source_data}, default=str),
                ),
            )
            return str(cur.fetchone()["id"])

    @staticmethod
    def merge_raw_source_data(paper_id: str, source: str, raw_data: Dict[str, Any]) -> None:
        """Adds another source's raw payload onto an existing paper, without
        touching any already-stored value (raw data is additive, never overwritten)."""
        with get_cursor() as cur:
            cur.execute(
                """
                UPDATE papers
                SET raw_source_data = raw_source_data || jsonb_build_object(%s, %s::jsonb),
                    updated_at = now()
                WHERE id = %s
                """,
                (source, json.dumps(raw_data, default=str), paper_id),
            )

    @staticmethod
    def link_source(paper_id: str, source_name: str, external_id: str, source_url: Optional[str]) -> None:
        source_id = SourceRepository.get_source_id(source_name)
        with get_cursor() as cur:
            cur.execute(
                """
                INSERT INTO paper_sources (paper_id, source_id, external_id, source_url)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (source_id, external_id) DO NOTHING
                """,
                (paper_id, source_id, external_id, source_url),
            )

    @staticmethod
    def link_authors(paper_id: str, author_ids_in_order: List[str]) -> None:
        with get_cursor() as cur:
            for order, author_id in enumerate(author_ids_in_order):
                cur.execute(
                    """
                    INSERT INTO paper_authors (paper_id, author_id, author_order)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (paper_id, author_id) DO NOTHING
                    """,
                    (paper_id, author_id, order),
                )

    @staticmethod
    def link_categories(paper_id: str, category_ids: List[str]) -> None:
        with get_cursor() as cur:
            for cat_id in category_ids:
                cur.execute(
                    """
                    INSERT INTO paper_categories (paper_id, category_id)
                    VALUES (%s, %s)
                    ON CONFLICT DO NOTHING
                    """,
                    (paper_id, cat_id),
                )

    @staticmethod
    def flag_possible_duplicate(paper_id: str, of_paper_id: str) -> None:
        with get_cursor() as cur:
            cur.execute(
                "UPDATE papers SET possible_duplicate_of = %s WHERE id = %s",
                (of_paper_id, paper_id),
            )

    @staticmethod
    def get_paper_detail(paper_id: str) -> Optional[Dict[str, Any]]:
        with get_cursor() as cur:
            cur.execute("SELECT * FROM papers WHERE id = %s", (paper_id,))
            paper = cur.fetchone()
            if not paper:
                return None
            cur.execute(
                """
                SELECT a.display_name FROM authors a
                JOIN paper_authors pa ON pa.author_id = a.id
                WHERE pa.paper_id = %s ORDER BY pa.author_order
                """,
                (paper_id,),
            )
            paper["author_names"] = [r["display_name"] for r in cur.fetchall()]

            cur.execute(
                """
                SELECT s.name FROM sources s
                JOIN paper_sources ps ON ps.source_id = s.id
                WHERE ps.paper_id = %s
                """,
                (paper_id,),
            )
            paper["source_names"] = [r["name"] for r in cur.fetchall()]

            cur.execute(
                """
                SELECT c.label FROM categories c
                JOIN paper_categories pc ON pc.category_id = c.id
                WHERE pc.paper_id = %s
                """,
                (paper_id,),
            )
            paper["category_labels"] = [r["label"] for r in cur.fetchall()]

            cur.execute("SELECT * FROM llm_enrichments WHERE paper_id = %s", (paper_id,))
            paper["llm_enrichment"] = cur.fetchone()
            return paper

    @staticmethod
    def search_papers(
        query: Optional[str] = None,
        category_id: Optional[str] = None,
        source_name: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        limit: int = 200,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        clauses = ["1 = 1"]
        params: List[Any] = []

        if query:
            clauses.append("(p.title ILIKE %s OR p.abstract ILIKE %s)")
            params.extend([f"%{query}%", f"%{query}%"])
        if category_id:
            clauses.append(
                "EXISTS (SELECT 1 FROM paper_categories pc WHERE pc.paper_id = p.id AND pc.category_id = %s)"
            )
            params.append(category_id)
        if source_name:
            clauses.append(
                """EXISTS (
                    SELECT 1 FROM paper_sources ps JOIN sources s ON s.id = ps.source_id
                    WHERE ps.paper_id = p.id AND s.name = %s
                )"""
            )
            params.append(source_name)
        if start_date:
            clauses.append("p.publication_date >= %s")
            params.append(start_date)
        if end_date:
            clauses.append("p.publication_date <= %s")
            params.append(end_date)

        sql = f"""
            SELECT p.id, p.title, p.publication_date, p.citation_count, p.doi, p.url, p.pdf_url,
                   c.label AS primary_category,
                   COALESCE(
                       (SELECT string_agg(a.display_name, ', ' ORDER BY pa.author_order)
                        FROM paper_authors pa JOIN authors a ON a.id = pa.author_id
                        WHERE pa.paper_id = p.id), ''
                   ) AS authors,
                   COALESCE(
                       (SELECT string_agg(s.name, ', ')
                        FROM paper_sources ps JOIN sources s ON s.id = ps.source_id
                        WHERE ps.paper_id = p.id), ''
                   ) AS sources,
                   le.topics AS llm_topics
            FROM papers p
            LEFT JOIN categories c ON c.id = p.primary_category_id
            LEFT JOIN llm_enrichments le ON le.paper_id = p.id
            WHERE {' AND '.join(clauses)}
            ORDER BY p.publication_date DESC NULLS LAST
            LIMIT %s OFFSET %s
        """
        params.extend([limit, offset])
        with get_cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()

    @staticmethod
    def list_papers_for_job(job_id: str) -> List[Dict[str, Any]]:
        """Returns every paper collected by a specific job, with denormalized
        authors/categories/sources -- used for CSV/JSON export (Section 33)."""
        with get_cursor() as cur:
            cur.execute(
                """
                SELECT
                    p.id, p.title, p.abstract, p.publication_date, p.doi, p.url, p.pdf_url,
                    p.journal, p.venue, p.publisher, p.citation_count, p.possible_duplicate_of,
                    c.label AS primary_category,
                    COALESCE(
                        (SELECT string_agg(a.display_name, '; ' ORDER BY pa.author_order)
                         FROM paper_authors pa JOIN authors a ON a.id = pa.author_id
                         WHERE pa.paper_id = p.id), ''
                    ) AS authors,
                    COALESCE(
                        (SELECT string_agg(s.name, '; ')
                         FROM paper_sources ps JOIN sources s ON s.id = ps.source_id
                         WHERE ps.paper_id = p.id), ''
                    ) AS sources,
                    le.summary AS llm_summary,
                    le.topics AS llm_topics,
                    le.research_area AS llm_research_area
                FROM papers p
                LEFT JOIN categories c ON c.id = p.primary_category_id
                LEFT JOIN llm_enrichments le ON le.paper_id = p.id
                WHERE p.research_job_id = %s
                ORDER BY p.publication_date DESC NULLS LAST
                """,
                (job_id,),
            )
            return cur.fetchall()

    @staticmethod
    def count_papers() -> Dict[str, int]:
        with get_cursor() as cur:
            cur.execute("SELECT COUNT(*) AS n FROM papers WHERE possible_duplicate_of IS NULL")
            unique = cur.fetchone()["n"]
            cur.execute("SELECT COUNT(*) AS n FROM papers WHERE possible_duplicate_of IS NOT NULL")
            possible_dupes = cur.fetchone()["n"]
            cur.execute("SELECT COUNT(*) AS n FROM authors")
            authors = cur.fetchone()["n"]
            cur.execute("SELECT COUNT(*) AS n FROM categories")
            categories = cur.fetchone()["n"]
            cur.execute("SELECT COALESCE(SUM(citation_count), 0) AS n FROM papers")
            citations = cur.fetchone()["n"]
            return {
                "unique_papers": unique,
                "possible_duplicates": possible_dupes,
                "authors": authors,
                "categories": categories,
                "total_citations": citations,
            }


# ======================================================================
# Citations
# ======================================================================
class CitationRepository:
    @staticmethod
    def record_snapshot(paper_id: str, source_name: Optional[str], citation_count: int) -> None:
        source_id = SourceRepository.get_source_id(source_name) if source_name else None
        with get_cursor() as cur:
            cur.execute(
                "INSERT INTO citations (paper_id, source_id, citation_count) VALUES (%s, %s, %s)",
                (paper_id, source_id, citation_count),
            )


# ======================================================================
# LLM enrichments
# ======================================================================
class LLMRepository:
    @staticmethod
    def upsert_enrichment(
        paper_id: str,
        model_name: str,
        summary: Optional[str],
        topics: List[str],
        research_area: Optional[str],
        confidence: Optional[float],
        status: str,
        raw_response: Optional[str],
        validation_errors: List[str],
        attempt_count: int,
    ) -> None:
        with get_cursor() as cur:
            cur.execute(
                """
                INSERT INTO llm_enrichments
                    (paper_id, model_name, summary, topics, research_area, confidence,
                     status, raw_response, validation_errors, attempt_count)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (paper_id) DO UPDATE SET
                    model_name = EXCLUDED.model_name,
                    summary = EXCLUDED.summary,
                    topics = EXCLUDED.topics,
                    research_area = EXCLUDED.research_area,
                    confidence = EXCLUDED.confidence,
                    status = EXCLUDED.status,
                    raw_response = EXCLUDED.raw_response,
                    validation_errors = EXCLUDED.validation_errors,
                    attempt_count = EXCLUDED.attempt_count
                """,
                (
                    paper_id,
                    model_name,
                    summary,
                    topics,
                    research_area,
                    confidence,
                    status,
                    raw_response,
                    validation_errors,
                    attempt_count,
                ),
            )

    @staticmethod
    def papers_missing_enrichment(job_id: str, limit: int = 5000) -> List[Dict[str, Any]]:
        with get_cursor() as cur:
            cur.execute(
                """
                SELECT p.id, p.title, p.abstract FROM papers p
                LEFT JOIN llm_enrichments le ON le.paper_id = p.id
                WHERE p.research_job_id = %s AND le.id IS NULL AND p.possible_duplicate_of IS NULL
                LIMIT %s
                """,
                (job_id, limit),
            )
            return cur.fetchall()


# ======================================================================
# Quality checks
# ======================================================================
class QualityCheckRepository:
    @staticmethod
    def record(job_id: str, check_name: str, passed: bool, details: Dict[str, Any]) -> None:
        with get_cursor() as cur:
            cur.execute(
                "INSERT INTO quality_checks (job_id, check_name, passed, details) VALUES (%s, %s, %s, %s)",
                (job_id, check_name, passed, json.dumps(details, default=str)),
            )

    @staticmethod
    def for_job(job_id: str) -> List[Dict[str, Any]]:
        with get_cursor() as cur:
            cur.execute("SELECT * FROM quality_checks WHERE job_id = %s ORDER BY created_at", (job_id,))
            return cur.fetchall()


# ======================================================================
# Scheduled searches (used by the Jobs page + Airflow DAG)
# ======================================================================
class ScheduledSearchRepository:
    @staticmethod
    def create(name: str, config: Dict[str, Any], frequency: str) -> int:
        with get_cursor() as cur:
            cur.execute(
                """
                INSERT INTO scheduled_searches (name, config, frequency, active)
                VALUES (%s, %s, %s, %s) RETURNING id
                """,
                (name, json.dumps(config, default=str), frequency, frequency != "off"),
            )
            return cur.fetchone()["id"]

    @staticmethod
    def list_all() -> List[Dict[str, Any]]:
        with get_cursor() as cur:
            cur.execute("SELECT * FROM scheduled_searches ORDER BY created_at DESC")
            return cur.fetchall()

    @staticmethod
    def list_due(as_of: Optional[datetime] = None) -> List[Dict[str, Any]]:
        as_of = as_of or datetime.utcnow()
        with get_cursor() as cur:
            cur.execute(
                """
                SELECT * FROM scheduled_searches
                WHERE active = true AND (next_run_at IS NULL OR next_run_at <= %s)
                """,
                (as_of,),
            )
            return cur.fetchall()

    @staticmethod
    def mark_run(schedule_id: int, next_run_at: datetime) -> None:
        with get_cursor() as cur:
            cur.execute(
                "UPDATE scheduled_searches SET last_run_at = now(), next_run_at = %s WHERE id = %s",
                (next_run_at, schedule_id),
            )

    @staticmethod
    def set_active(schedule_id: int, active: bool) -> None:
        with get_cursor() as cur:
            cur.execute("UPDATE scheduled_searches SET active = %s WHERE id = %s", (active, schedule_id))
