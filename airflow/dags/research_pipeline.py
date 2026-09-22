"""
airflow/dags/research_pipeline.py

Orchestrates the research pipeline (Section 34). ALL business logic lives
in pipeline/orchestrator.py -- this file only wires reusable functions into
an Airflow task graph, per the project rule that DAGs must not contain
business logic.

Two ways this DAG runs:

1) Ad-hoc / on-demand (triggered with a specific search config):
       airflow dags trigger research_pipeline --conf '{"config": {"keywords": ["llm agents"], "intensity": "standard"}}'
   -> runs the full granular task chain: create_job -> ingestion -> dbt ->
      llm_enrichment -> quality_checks -> complete_job.

2) Recurring / scheduled (the DAG's own daily schedule_interval, no conf):
   -> a single task checks the `scheduled_searches` table (populated from
      the Jobs page's "Off / Daily / Weekly / Monthly" option) for any
      schedule that is due, and runs the SAME reusable pipeline function
      once per due schedule, reusing its saved configuration (Section 35).

Only PostgreSQL-backed state (job_id, small config dicts) crosses task
boundaries via XCom -- never large in-memory paper lists.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

# Make the project root importable inside the Airflow container.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from airflow import DAG  # noqa: E402
from airflow.operators.python import BranchPythonOperator, PythonOperator  # noqa: E402
from airflow.operators.empty import EmptyOperator  # noqa: E402

default_args = {
    "owner": "research-paper-intelligence",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "execution_timeout": timedelta(hours=2),
}


def _decide_path(**context):
    conf = context["dag_run"].conf or {}
    return "create_job" if conf.get("config") else "dispatch_scheduled_searches"


def _create_job(**context):
    from pipeline.orchestrator import create_job

    conf = context["dag_run"].conf or {}
    config = conf["config"]
    job_id = create_job(config, triggered_by="airflow")
    context["ti"].xcom_push(key="job_id", value=job_id)


def _run_ingestion(**context):
    from pipeline.orchestrator import run_ingestion_and_storage

    job_id = context["ti"].xcom_pull(key="job_id", task_ids="create_job")
    run_ingestion_and_storage(job_id)


def _run_dbt(**context):
    from pipeline.orchestrator import run_dbt

    job_id = context["ti"].xcom_pull(key="job_id", task_ids="create_job")
    run_dbt(job_id)


def _run_llm_enrichment(**context):
    from pipeline.orchestrator import run_llm_enrichment

    job_id = context["ti"].xcom_pull(key="job_id", task_ids="create_job")
    run_llm_enrichment(job_id)


def _run_quality_checks(**context):
    from pipeline.orchestrator import run_quality_checks

    job_id = context["ti"].xcom_pull(key="job_id", task_ids="create_job")
    run_quality_checks(job_id)


def _complete_job(**context):
    from pipeline.orchestrator import complete_job

    job_id = context["ti"].xcom_pull(key="job_id", task_ids="create_job")
    complete_job(job_id)


def _on_pipeline_failure(context):
    """Marks the job FAILED in the database if any task in the chain raises,
    so the Jobs page reflects reality instead of showing RUNNING forever."""
    try:
        from pipeline.orchestrator import fail_job

        job_id = context["ti"].xcom_pull(key="job_id", task_ids="create_job")
        if job_id:
            fail_job(job_id, str(context.get("exception")))
    except Exception:
        pass  # best-effort; never let the failure callback itself raise


def _dispatch_scheduled_searches(**context):
    from datetime import datetime as _dt

    from database.repositories import ScheduledSearchRepository
    from pipeline.orchestrator import run_full_pipeline

    due = ScheduledSearchRepository.list_due()
    for schedule in due:
        config = schedule["config"]
        run_full_pipeline(config, triggered_by="scheduled")

        if schedule["frequency"] == "daily":
            next_run = _dt.utcnow() + timedelta(days=1)
        elif schedule["frequency"] == "weekly":
            next_run = _dt.utcnow() + timedelta(weeks=1)
        elif schedule["frequency"] == "monthly":
            next_run = _dt.utcnow() + timedelta(days=30)
        else:
            next_run = _dt.utcnow() + timedelta(days=3650)  # effectively "off"

        ScheduledSearchRepository.mark_run(schedule["id"], next_run)


with DAG(
    dag_id="research_pipeline",
    description="Research Paper Intelligence pipeline (ad-hoc + scheduled runs)",
    default_args=default_args,
    schedule_interval="@daily",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["research-paper-intelligence"],
    on_failure_callback=_on_pipeline_failure,
) as dag:

    branch = BranchPythonOperator(
        task_id="branch_on_trigger_type",
        python_callable=_decide_path,
    )

    dispatch_scheduled_searches = PythonOperator(
        task_id="dispatch_scheduled_searches",
        python_callable=_dispatch_scheduled_searches,
    )

    create_job = PythonOperator(
        task_id="create_job",
        python_callable=_create_job,
    )

    ingestion = PythonOperator(
        task_id="ingestion_cleaning_dedup_storage",
        python_callable=_run_ingestion,
    )

    dbt_transform = PythonOperator(
        task_id="dbt_transform",
        python_callable=_run_dbt,
    )

    llm_enrichment = PythonOperator(
        task_id="llm_enrichment",
        python_callable=_run_llm_enrichment,
    )

    quality_checks = PythonOperator(
        task_id="quality_checks",
        python_callable=_run_quality_checks,
    )

    complete_job = PythonOperator(
        task_id="complete_job",
        python_callable=_complete_job,
    )

    end = EmptyOperator(task_id="end", trigger_rule="none_failed_min_one_success")

    branch >> [dispatch_scheduled_searches, create_job]
    create_job >> ingestion >> dbt_transform >> llm_enrichment >> quality_checks >> complete_job >> end
    dispatch_scheduled_searches >> end
