"""
app/components/metrics.py

Renders a row of stat cards (see app/components/style.py). Used by the
Dashboard page's top metrics (Total Papers, Unique Papers, Duplicates,
Authors, Categories, Citations) and reused wherever else a quick numeric
summary is useful.
"""
from __future__ import annotations

from typing import List, Tuple

from app.components.style import rpi_stat_row


def render_metric_row(metrics: List[Tuple[str, object]], help_text: dict | None = None) -> None:
    """metrics: list of (label, value) pairs."""
    if not metrics:
        return
    rpi_stat_row([(str(value), label) for label, value in metrics])


def render_paper_counts(counts: dict) -> None:
    """Convenience wrapper for the shape returned by PaperRepository.count_papers()."""
    render_metric_row(
        [
            ("Unique papers", f"{counts.get('unique_papers', 0):,}"),
            ("Possible duplicates", f"{counts.get('possible_duplicates', 0):,}"),
            ("Authors", f"{counts.get('authors', 0):,}"),
            ("Categories", f"{counts.get('categories', 0):,}"),
            ("Total citations", f"{counts.get('total_citations', 0):,}"),
        ]
    )
