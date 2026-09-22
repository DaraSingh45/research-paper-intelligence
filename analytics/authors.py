"""
analytics/authors.py

Reporting queries against the dbt author_statistics / dim_authors marts.
"""
from __future__ import annotations

import pandas as pd

from analytics.trends import _safe_read_sql


def get_top_authors(limit: int = 20) -> pd.DataFrame:
    return _safe_read_sql(
        "SELECT * FROM author_statistics ORDER BY paper_count DESC, total_citations DESC LIMIT %s",
        (limit,),
    )


def get_authors_by_category(category_label: str, limit: int = 20) -> pd.DataFrame:
    return _safe_read_sql(
        """
        SELECT * FROM author_statistics
        WHERE %s = ANY(categories)
        ORDER BY paper_count DESC
        LIMIT %s
        """,
        (category_label, limit),
    )


def get_author_publication_counts() -> pd.DataFrame:
    return _safe_read_sql("SELECT paper_count, total_citations, avg_citations FROM dim_authors")
