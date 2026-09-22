"""
analytics/trends.py

Reporting queries against the dbt marts (publication_trends, dim_categories,
fct_citations, source_statistics, citation_statistics). These are read-only
and safe to call directly from Streamlit pages.
"""
from __future__ import annotations

import logging
import warnings

import pandas as pd

from database.connection import get_connection

logger = logging.getLogger(__name__)


def _safe_read_sql(query: str, params: tuple = ()) -> pd.DataFrame:
    """Runs a query and returns a DataFrame, or an empty DataFrame (with a
    logged warning) if the underlying dbt mart doesn't exist yet -- this
    happens the first time a user opens the dashboard before any pipeline
    run has executed `dbt run`."""
    try:
        with get_connection() as conn:
            with warnings.catch_warnings():
                # pandas warns that psycopg2 connections aren't SQLAlchemy
                # engines; expected and harmless since we use psycopg2
                # directly throughout. Scoped to this call (rather than a
                # module-level filterwarnings) so it can't be undone by
                # something else resetting the global filter list, e.g.
                # pytest's per-test warning capture.
                warnings.filterwarnings("ignore", message="pandas only supports SQLAlchemy")
                return pd.read_sql(query, conn, params=params)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Analytics query failed (has `dbt run` been executed yet?): %s", exc)
        return pd.DataFrame()


def get_publication_trends(granularity: str = "month") -> pd.DataFrame:
    return _safe_read_sql(
        "SELECT * FROM publication_trends WHERE granularity = %s ORDER BY period",
        (granularity,),
    )


def get_category_distribution() -> pd.DataFrame:
    return _safe_read_sql(
        "SELECT * FROM dim_categories ORDER BY paper_count DESC"
    )

def get_source_distribution() -> pd.DataFrame:
    return _safe_read_sql("SELECT * FROM source_statistics ORDER BY paper_count DESC")


def get_citation_statistics() -> pd.DataFrame:
    return _safe_read_sql("SELECT * FROM citation_statistics ORDER BY category_total_citations DESC")


def get_citation_distribution(limit: int = 500) -> pd.DataFrame:
    """Raw per-paper citation counts (for a histogram), capped for performance."""
    return _safe_read_sql(
        "SELECT citation_count FROM fct_citations ORDER BY citation_count DESC LIMIT %s",
        (limit,),
    )


def get_highly_cited_papers(limit: int = 20) -> pd.DataFrame:
    return _safe_read_sql(
        """
        SELECT dp.title, dp.citation_count, dp.publication_date, dp.primary_category_label, dp.url
        FROM dim_papers dp
        WHERE NOT dp.is_possible_duplicate
        ORDER BY dp.citation_count DESC
        LIMIT %s
        """,
        (limit,),
    )
