"""
analytics/topics.py

Reporting queries covering LLM-derived topics: top topics overall, growth
over time (from the topic_growth mart), and topics broken down by category
(derived from dim_papers, since topics and categories are both attached to
individual papers there).
"""
from __future__ import annotations

import pandas as pd

from analytics.trends import _safe_read_sql


def get_top_topics(limit: int = 20) -> pd.DataFrame:
    return _safe_read_sql(
        """
        SELECT topic, SUM(paper_count) AS total_paper_count
        FROM topic_growth
        GROUP BY topic
        ORDER BY total_paper_count DESC
        LIMIT %s
        """,
        (limit,),
    )


def get_topic_growth(topic: str | None = None) -> pd.DataFrame:
    if topic:
        return _safe_read_sql(
            "SELECT * FROM topic_growth WHERE topic = %s ORDER BY month", (topic,)
        )
    return _safe_read_sql("SELECT * FROM topic_growth ORDER BY topic, month")


def get_topics_by_category(limit_per_category: int = 5) -> pd.DataFrame:
    return _safe_read_sql(
        """
        WITH exploded AS (
            SELECT primary_category_label AS category_label, unnest(llm_topics) AS topic
            FROM dim_papers
            WHERE llm_status = 'VALID' AND NOT is_possible_duplicate
        ),
        counted AS (
            SELECT category_label, topic, COUNT(*) AS paper_count,
                   ROW_NUMBER() OVER (PARTITION BY category_label ORDER BY COUNT(*) DESC) AS rn
            FROM exploded
            GROUP BY category_label, topic
        )
        SELECT category_label, topic, paper_count
        FROM counted
        WHERE rn <= %s
        ORDER BY category_label, paper_count DESC
        """,
        (limit_per_category,),
    )
