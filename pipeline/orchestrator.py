"""
pipeline/orchestrator.py

The single source of truth for how a research job actually runs. Both the
Streamlit "START RESEARCH" button and the Airflow DAG call into these same
functions -- no business logic is duplicated or embedded in either caller.

Design note on Airflow task granularity: ingestion, cleaning, normalization
and deduplication are combined into one function (run_ingestion_and_storage)
because they operate on an in-memory stream of papers per source. Passing
thousands of paper objects between separate Airflow tasks via XCom is not
practical (XCom is meant for small metadata), so each stage instead persists
its results directly to PostgreSQL and downstream stages/tasks read from
there via `job_id`. This keeps the Airflow DAG simple (task = pipeline
stage) while keeping data movement efficient.
"""
from __future__ import annotations

import logging
import subprocess
from datetime import date
from pathlib import Path
from typing import Any, Dict, Optional

from config.loader import get_category_labels, get_intensity_preset, get_llm_batch_settings, load_categories
from database.connection import get_cursor
from database.models import JobStatus, SearchConfig, new_job_id
from database.repositories import (
    CategoryRepository,
    JobRepository,
    LLMRepository,
    QualityCheckRepository,
)
from ingestion import get_all_sources
from llm.ollama_client import OllamaClient
from llm.summarizer import generate_enrichment
from processing.cleaner import clean_batch
from processing.deduplicator import Deduplicator
from processing.normalizer import normalize_batch
from processing.validator import validate_batch

logger = logging.getLogger(__name__)

DBT_PROJECT_DIR = Path(__file__).resolve().parent.parent / "dbt"


# ----------------------------------------------------------------------
# Stage: create job
# ----------------------------------------------------------------------
def create_job(config: Dict[str, Any], triggered_by: str = "manual") -> str:
    job_id = new_job_id()
    CategoryRepository.ensure_categories(load_categories().get("categories", []))
    JobRepository.create_job(job_id, config, triggered_by=triggered_by)
    JobRepository.append_log(job_id, "Research job created.", source="pipeline")
    return job_id


def _build_search_config(job: Dict[str, Any]) -> SearchConfig:
    llm_options = job.get("llm_options") or {}
    return SearchConfig(
        keywords=job.get("keywords") or [],
        title_filter=job.get("title_filter"),
        authors=job.get("authors") or [],
        categories=job.get("categories") or [],
        start_date=job.get("start_date") if isinstance(job.get("start_date"), date) else None,
        end_date=job.get("end_date") if isinstance(job.get("end_date"), date) else None,
        intensity=job.get("intensity", "standard"),
        llm_enabled=bool(job.get("llm_enabled", False)),
        llm_generate_summary=llm_options.get("generate_summary", True),
        llm_generate_topics=llm_options.get("generate_topics", True),
        llm_generate_research_area=llm_options.get("generate_research_area", True),
    )


# ----------------------------------------------------------------------
# Stage: ingestion + cleaning + normalization + deduplication + storage
# ----------------------------------------------------------------------
def run_ingestion_and_storage(job_id: str) -> None:
    job = JobRepository.get_job(job_id)
    if not job:
        raise ValueError(f"Job {job_id} not found")

    JobRepository.set_status(job_id, JobStatus.RUNNING)
    JobRepository.update_progress(job_id, "Preparing search", 2)

    search_config = _build_search_config(job)
    preset = get_intensity_preset(search_config.intensity)
    dedup = Deduplicator(
        dedup_strategy=preset.get("dedup_strategy", "full"),
        enable_fuzzy=preset.get("enable_fuzzy_dedup", True),
        fuzzy_threshold=preset.get("fuzzy_title_threshold", 0.92),
    )

    sources = get_all_sources()
    total_found = total_unique = total_duplicates = total_failed = 0

    for idx, source in enumerate(sources):
        step_pct = 5 + int(50 * idx / max(len(sources), 1))
        JobRepository.update_progress(job_id, f"Collecting papers from {source.name}", step_pct)
        JobRepository.append_log(job_id, f"Searching {source.name}...", source=source.name)

        result = source.safe_search(search_config)

        if not result.success:
            # A single failing source must never crash the pipeline (Section 16).
            JobRepository.update_source_status(job_id, source.name, f"failed: {result.error_message}")
            JobRepository.append_log(
                job_id, f"{source.name} failed: {result.error_message}", level="WARNING", source=source.name
            )
            continue

        JobRepository.update_source_status(job_id, source.name, "ok")
        total_found += len(result.papers)

        cleaned, dropped_in_cleaning = clean_batch(result.papers)
        normalized = normalize_batch(cleaned)
        valid_papers, invalid_papers = validate_batch(normalized)
        total_failed += dropped_in_cleaning + len(invalid_papers)

        for paper, errors in invalid_papers:
            JobRepository.append_log(
                job_id, f"Rejected '{paper.title}': {'; '.join(errors)}", level="WARNING", source=source.name
            )

        dedup_summary = dedup.process_batch(valid_papers, job_id)
        total_unique += dedup_summary.new
        total_duplicates += dedup_summary.duplicates

        JobRepository.append_log(
            job_id,
            (
                f"{source.name}: found={len(result.papers)} new={dedup_summary.new} "
                f"duplicates={dedup_summary.duplicates} possible_duplicates={dedup_summary.possible_duplicates} "
                f"rejected={dropped_in_cleaning + len(invalid_papers)} requests={result.requests_made} "
                f"time={result.elapsed_seconds:.1f}s"
            ),
            source=source.name,
        )

        JobRepository.update_counts(
            job_id,
            total_found=total_found,
            total_unique=total_unique,
            total_duplicates=total_duplicates,
            total_failed=total_failed,
        )

    JobRepository.update_progress(job_id, "Ingestion complete", 55)


# ----------------------------------------------------------------------
# Stage: dbt transformations
# ----------------------------------------------------------------------
def run_dbt(job_id: str) -> bool:
    JobRepository.update_progress(job_id, "Running dbt transformations", 60)
    JobRepository.append_log(job_id, "Starting dbt run", source="dbt")

    profiles_dir = DBT_PROJECT_DIR if (DBT_PROJECT_DIR / "profiles.yml").exists() else DBT_PROJECT_DIR

    try:
        result = subprocess.run(
            ["dbt", "run", "--project-dir", str(DBT_PROJECT_DIR), "--profiles-dir", str(profiles_dir)],
            capture_output=True,
            text=True,
            timeout=900,
        )
        ok = result.returncode == 0
        tail_out = (result.stdout or "")[-3000:]
        tail_err = (result.stderr or "")[-2000:]
        JobRepository.append_log(
            job_id,
            f"dbt run {'succeeded' if ok else 'FAILED'}.\n{tail_out}\n{tail_err}",
            level="INFO" if ok else "ERROR",
            source="dbt",
        )
        return ok
    except FileNotFoundError:
        JobRepository.append_log(
            job_id,
            "dbt is not installed/available in this environment. Analytics dashboards will be "
            "empty until dbt is set up (see README: dbt setup).",
            level="WARNING",
            source="dbt",
        )
        return False
    except subprocess.TimeoutExpired:
        JobRepository.append_log(job_id, "dbt run timed out after 15 minutes.", level="ERROR", source="dbt")
        return False
    finally:
        JobRepository.update_progress(job_id, "dbt transformations complete", 70)


# ----------------------------------------------------------------------
# Stage: LLM enrichment (optional)
# ----------------------------------------------------------------------
def run_llm_enrichment(job_id: str) -> None:
    job = JobRepository.get_job(job_id)
    if not job or not job.get("llm_enabled"):
        JobRepository.append_log(job_id, "LLM enrichment skipped (not enabled for this job).", source="llm")
        JobRepository.update_progress(job_id, "LLM enrichment skipped", 95)
        return

    client = OllamaClient()
    available, message = client.is_available()
    if not available:
        JobRepository.append_log(job_id, f"LLM enrichment skipped: {message}", level="WARNING", source="llm")
        JobRepository.update_progress(job_id, "LLM enrichment skipped (Ollama unavailable)", 95)
        return

    batch_settings = get_llm_batch_settings()
    max_retries = batch_settings.get("max_retries_per_paper", 2)
    allowed_categories = list(get_category_labels().values())

    papers = LLMRepository.papers_missing_enrichment(job_id)
    total = len(papers)
    JobRepository.append_log(job_id, f"Starting LLM enrichment for {total} paper(s).", source="llm")

    for i, paper in enumerate(papers):
        pct = 70 + int(25 * (i + 1) / max(total, 1))
        JobRepository.update_progress(job_id, f"Enriching paper {i + 1}/{total}", pct)

        attempt = generate_enrichment(
            client, paper["title"], paper.get("abstract"), allowed_categories, max_retries=max_retries
        )

        if attempt.validation.valid and attempt.validation.data:
            data = attempt.validation.data
            LLMRepository.upsert_enrichment(
                paper_id=str(paper["id"]),
                model_name=client.model,
                summary=data.get("summary"),
                topics=data.get("topics", []),
                research_area=data.get("research_area"),
                confidence=data.get("confidence"),
                status="VALID",
                raw_response=attempt.raw_response,
                validation_errors=[],
                attempt_count=attempt.attempt_count,
            )
        else:
            LLMRepository.upsert_enrichment(
                paper_id=str(paper["id"]),
                model_name=client.model,
                summary=None,
                topics=[],
                research_area=None,
                confidence=None,
                status="FAILED_REVIEW",
                raw_response=attempt.raw_response,
                validation_errors=attempt.validation.errors,
                attempt_count=attempt.attempt_count,
            )
            JobRepository.append_log(
                job_id,
                f"LLM enrichment failed validation for '{paper['title'][:60]}': {attempt.validation.errors}",
                level="WARNING",
                source="llm",
            )

    JobRepository.update_progress(job_id, "LLM enrichment complete", 95)


# ----------------------------------------------------------------------
# Stage: quality checks
# ----------------------------------------------------------------------
def run_quality_checks(job_id: str) -> None:
    JobRepository.update_progress(job_id, "Running quality checks", 97)

    with get_cursor() as cur:
        cur.execute("SELECT COUNT(*) AS n FROM papers WHERE research_job_id = %s", (job_id,))
        total = cur.fetchone()["n"] or 0

        cur.execute(
            "SELECT COUNT(*) AS n FROM papers WHERE research_job_id = %s AND (abstract IS NULL OR abstract = '')",
            (job_id,),
        )
        missing_abstract = cur.fetchone()["n"] or 0

        cur.execute(
            "SELECT COUNT(*) AS n FROM papers WHERE research_job_id = %s AND possible_duplicate_of IS NOT NULL",
            (job_id,),
        )
        possible_dupes = cur.fetchone()["n"] or 0

        cur.execute(
            """
            SELECT COUNT(*) AS n FROM papers p
            LEFT JOIN llm_enrichments le ON le.paper_id = p.id
            WHERE p.research_job_id = %s AND le.status = 'FAILED_REVIEW'
            """,
            (job_id,),
        )
        failed_llm = cur.fetchone()["n"] or 0

    missing_rate = round(100 * missing_abstract / total, 2) if total else 0
    QualityCheckRepository.record(
        job_id,
        "missing_abstract_rate",
        passed=missing_rate < 40,
        details={"missing": missing_abstract, "total": total, "rate_pct": missing_rate},
    )
    QualityCheckRepository.record(
        job_id, "possible_duplicates_flagged", passed=True, details={"count": possible_dupes}
    )
    QualityCheckRepository.record(
        job_id,
        "llm_validation_failures",
        passed=failed_llm == 0,
        details={"failed_review_count": failed_llm},
    )

    JobRepository.update_progress(job_id, "Quality checks complete", 99)


# ----------------------------------------------------------------------
# Stage: completion
# ----------------------------------------------------------------------
def complete_job(job_id: str) -> None:
    JobRepository.set_status(job_id, JobStatus.COMPLETED)
    JobRepository.update_progress(job_id, "Completed", 100)
    JobRepository.append_log(job_id, "Job completed successfully.", source="pipeline")


def fail_job(job_id: str, error_message: str) -> None:
    JobRepository.set_status(job_id, JobStatus.FAILED, error_message=error_message)
    JobRepository.append_log(job_id, f"Job failed: {error_message}", level="ERROR", source="pipeline")


# ----------------------------------------------------------------------
# Convenience: run everything sequentially (used by Streamlit + the CLI
# script + as a fallback single-task option for very small Airflow setups)
# ----------------------------------------------------------------------
def run_full_pipeline(config: Dict[str, Any], triggered_by: str = "manual", existing_job_id: Optional[str] = None) -> str:
    job_id = existing_job_id or create_job(config, triggered_by=triggered_by)
    try:
        run_ingestion_and_storage(job_id)
        run_dbt(job_id)
        run_llm_enrichment(job_id)
        run_quality_checks(job_id)
        complete_job(job_id)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Pipeline failed for job %s", job_id)
        fail_job(job_id, str(exc))
        raise
    return job_id
