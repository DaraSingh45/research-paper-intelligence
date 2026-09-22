"""
tests/test_database.py

Integration tests against a real PostgreSQL instance (insertion,
constraints, relationships). These are automatically skipped if no
database is reachable, so `pytest` still passes on a machine that hasn't
started Docker/Postgres yet -- run `docker compose up -d postgres` and
`python scripts/init_database.py` first to exercise these.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database.connection import check_connection, get_cursor  # noqa: E402
from database.models import NormalizedPaper  # noqa: E402
from database.repositories import (  # noqa: E402
    AuthorRepository,
    CategoryRepository,
    JobRepository,
    PaperRepository,
)

DB_AVAILABLE, _DB_MESSAGE = check_connection()

pytestmark = pytest.mark.skipif(
    not DB_AVAILABLE, reason="No live PostgreSQL connection available for integration tests."
)


@pytest.fixture(autouse=True)
def _cleanup_test_rows():
    """Removes any rows this test module creates, so tests can be re-run
    without manual cleanup."""
    yield
    with get_cursor() as cur:
        cur.execute("DELETE FROM research_jobs WHERE id LIKE 'TEST-%'")
        cur.execute("DELETE FROM papers WHERE title LIKE 'TEST PAPER%'")
        cur.execute("DELETE FROM authors WHERE normalized_name LIKE 'test-author%'")


class TestJobInsertion:
    def test_create_and_fetch_job(self):
        job_id = "TEST-JOB-001"
        JobRepository.create_job(
            job_id,
            {"keywords": ["test"], "categories": [], "authors": [], "intensity": "quick", "llm_enabled": False},
        )
        job = JobRepository.get_job(job_id)
        assert job is not None
        assert job["keywords"] == ["test"]
        assert job["status"] == "PENDING"

    def test_job_status_transitions(self):
        from database.models import JobStatus

        job_id = "TEST-JOB-002"
        JobRepository.create_job(job_id, {"keywords": ["x"]})
        JobRepository.set_status(job_id, JobStatus.RUNNING)
        job = JobRepository.get_job(job_id)
        assert job["status"] == "RUNNING"
        assert job["started_at"] is not None

    def test_job_logs_are_recorded(self):
        job_id = "TEST-JOB-003"
        JobRepository.create_job(job_id, {"keywords": ["x"]})
        JobRepository.append_log(job_id, "hello world", source="test")
        logs = JobRepository.get_logs(job_id)
        assert any(log["message"] == "hello world" for log in logs)


class TestPaperInsertionAndConstraints:
    def test_insert_paper_and_find_by_doi(self):
        paper = NormalizedPaper(
            external_id="test-1",
            title="TEST PAPER Insertion Check",
            source="arxiv",
            doi="10.9999/test-insertion",
            publication_date=date(2024, 1, 1),
        )
        paper.title_normalized = "test paper insertion check"
        paper.internal_categories = ["uncategorized"]
        paper_id = PaperRepository.insert_paper(paper, job_id=None)
        assert paper_id is not None

        found = PaperRepository.find_by_doi("10.9999/test-insertion")
        assert found is not None
        assert str(found["id"]) == paper_id

    def test_doi_unique_constraint_enforced(self):
        paper1 = NormalizedPaper(
            external_id="test-2",
            title="TEST PAPER Constraint Check A",
            source="arxiv",
            doi="10.9999/test-constraint",
        )
        paper1.title_normalized = "test paper constraint check a"
        paper1.internal_categories = ["uncategorized"]
        PaperRepository.insert_paper(paper1, job_id=None)

        paper2 = NormalizedPaper(
            external_id="test-3",
            title="TEST PAPER Constraint Check B",
            source="openalex",
            doi="10.9999/test-constraint",  # same DOI on purpose
        )
        paper2.title_normalized = "test paper constraint check b"
        paper2.internal_categories = ["uncategorized"]

        with pytest.raises(Exception):
            PaperRepository.insert_paper(paper2, job_id=None)

    def test_author_relationship(self):
        paper = NormalizedPaper(
            external_id="test-4",
            title="TEST PAPER Author Relationship",
            source="arxiv",
            authors=["Test Author One"],
        )
        paper.title_normalized = "test paper author relationship"
        paper.internal_categories = ["uncategorized"]
        paper_id = PaperRepository.insert_paper(paper, job_id=None)

        author_id = AuthorRepository.upsert_author("Test Author One", "test-author-one")
        PaperRepository.link_authors(paper_id, [author_id])

        detail = PaperRepository.get_paper_detail(paper_id)
        assert "Test Author One" in detail["author_names"]


class TestCategorySync:
    def test_ensure_categories_is_idempotent(self):
        categories = [{"id": "test_category_sync", "label": "Test Category Sync"}]
        CategoryRepository.ensure_categories(categories)
        CategoryRepository.ensure_categories(categories)  # should not raise on second call
        all_categories = CategoryRepository.list_categories()
        assert any(c["id"] == "test_category_sync" for c in all_categories)

        with get_cursor() as cur:
            cur.execute("DELETE FROM categories WHERE id = 'test_category_sync'")
