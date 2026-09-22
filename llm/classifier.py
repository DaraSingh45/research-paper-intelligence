"""
llm/classifier.py

The LLM already returns a free-text `research_area` field as part of the
single combined enrichment call (see llm/summarizer.py + Section 25).
This module maps that free-text label onto the internal category
vocabulary (config/categories.yaml) for filtering/analytics purposes,
without requiring a second LLM call.
"""
from __future__ import annotations

import difflib
from typing import Optional

from config.loader import get_category_labels, load_categories


def map_research_area_to_category(research_area: Optional[str]) -> Optional[str]:
    """Best-effort match of a free-text research_area string to one of the
    internal category ids. Returns None if nothing matches reasonably well
    (the raw research_area text is still stored as-is in llm_enrichments;
    this mapping is only used for grouping/filtering in the UI)."""
    if not research_area:
        return None

    text = research_area.strip().lower()
    labels = get_category_labels()  # id -> label

    # Exact / substring match first
    for cat_id, label in labels.items():
        if text == label.lower() or label.lower() in text or text in label.lower():
            return cat_id

    # Keyword hints from categories.yaml
    for cat in load_categories().get("categories", []):
        for kw in cat.get("keywords", []):
            if kw.lower() in text:
                return cat["id"]

    # Fuzzy fallback
    best_id, best_ratio = None, 0.0
    for cat_id, label in labels.items():
        ratio = difflib.SequenceMatcher(None, text, label.lower()).ratio()
        if ratio > best_ratio:
            best_ratio, best_id = ratio, cat_id
    return best_id if best_ratio >= 0.6 else None
