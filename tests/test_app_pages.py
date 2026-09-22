"""
tests/test_app_pages.py

Smoke tests for the Streamlit pages themselves, using Streamlit's official
AppTest framework (runs a page exactly as a real session would, without a
browser). These are integration tests against a real PostgreSQL instance
and are skipped automatically if no database is reachable -- same pattern
as tests/test_database.py.

This file exists because a purely backend-level test suite (ingestion,
processing, database) previously gave zero coverage of the UI layer, and
a real bug shipped there silently: the Papers page defaulted to filtering
to "last 30 days", which hid the entire collection for anyone whose
papers were older than that. test_papers_page_shows_all_papers_by_default
guards against that regressing.
"""
from __future__ import annotations

import sys
from pathlib import Path
from tempfile import NamedTemporaryFile

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database.connection import check_connection  # noqa: E402
from database.models import NormalizedPaper  # noqa: E402
from database.repositories import CategoryRepository, JobRepository  # noqa: E402
from processing.deduplicator import Deduplicator  # noqa: E402
from processing.normalizer import normalize_paper  # noqa: E402
from config.loader import load_categories  # noqa: E402

DB_AVAILABLE, _ = check_connection()
pytestmark = pytest.mark.skipif(
    not DB_AVAILABLE, reason="No live PostgreSQL connection available for page tests."
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PAGE_NAMES = ["dashboard", "papers", "topics", "authors", "jobs", "settings", "search"]


def _make_stub(page_name: str) -> str:
    """Writes a tiny script that renders one page, and returns its path.
    AppTest.from_file needs a real file (it uses inspect.getsourcelines
    internally), so this can't be done with an in-memory string/lambda."""
    stub = NamedTemporaryFile(mode="w", suffix=f"_{page_name}.py", delete=False)
    stub.write(
        f"""
import sys
sys.path.insert(0, {str(PROJECT_ROOT)!r})
from app.components.style import inject_base_styles
inject_base_styles()
from app.views.{page_name} import render
render()
"""
    )
    stub.close()
    return stub.name


@pytest.fixture(scope="module")
def seeded_job():
    """Creates one job with a handful of papers whose publication dates
    are older than 30 days, specifically to exercise the Papers page's
    default-filter behavior."""
    from datetime import date, timedelta

    CategoryRepository.ensure_categories(load_categories().get("categories", []))
    job_id = "TEST-PAGES-JOB"
    JobRepository.create_job(job_id, {"keywords": ["test"], "intensity": "quick"})

    dedup = Deduplicator(dedup_strategy="basic", enable_fuzzy=False)
    old_date = date.today() - timedelta(days=400)  # well outside "last 30 days"
    for i in range(3):
        paper = NormalizedPaper(
            external_id=f"pagetest-{i}",
            title=f"TEST PAGE PAPER {i} Old Enough To Be Filtered",
            source="arxiv",
            abstract="An abstract long enough to pass validation for this test paper.",
            authors=["Test Author"],
            publication_date=old_date,
            categories=["cs.AI"],
            doi=f"10.9999/pagetest-{i}",
            citation_count=i,
        )
        normalize_paper(paper)
        dedup.process_paper(paper, job_id)

    yield job_id

    from database.connection import get_cursor

    with get_cursor() as cur:
        cur.execute("DELETE FROM papers WHERE title LIKE 'TEST PAGE PAPER%'")
        cur.execute("DELETE FROM research_jobs WHERE id = %s", (job_id,))


class TestAllPagesRenderWithoutError:
    @pytest.mark.parametrize("page_name", PAGE_NAMES)
    def test_page_renders_with_zero_exceptions(self, page_name, seeded_job):
        from streamlit.testing.v1 import AppTest

        stub_path = _make_stub(page_name)
        at = AppTest.from_file(stub_path, default_timeout=30)
        at.run()
        assert len(at.exception) == 0, [str(e.value) for e in at.exception]


class TestPapersPageDefaultFilter:
    def test_papers_page_shows_all_papers_by_default(self, seeded_job):
        """Regression test: the Papers page must show the whole collection
        by default, not silently filter to a recent date window."""
        from streamlit.testing.v1 import AppTest

        stub_path = _make_stub("papers")
        at = AppTest.from_file(stub_path, default_timeout=30)
        at.run()
        assert len(at.exception) == 0

        assert len(at.dataframe) > 0, "Papers page should render a results table"
        df = at.dataframe[0].value
        titles = df["Title"].tolist()
        assert any("TEST PAGE PAPER" in t for t in titles), (
            "A paper older than 30 days was not shown by default -- the date "
            "filter is silently hiding the collection again."
        )
