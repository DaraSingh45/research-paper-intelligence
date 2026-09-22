"""
app/components/filters.py

Reusable filter widgets shared by the Research, Papers, Topics and
Authors pages, so date-range/category logic is defined exactly once.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import List, Optional, Tuple

import streamlit as st

from config.loader import load_categories

DATE_PRESETS = {
    "Last 7 days": 7,
    "Last 30 days": 30,
    "Last 6 months": 182,
    "Last 1 year": 365,
    "Last 5 years": 365 * 5,
}


def render_category_multiselect(key: str, label: str = "Categories") -> List[str]:
    categories = load_categories().get("categories", [])
    options = {c["label"]: c["id"] for c in categories}
    selected_labels = st.multiselect(label, list(options.keys()), key=key)
    return [options[lbl] for lbl in selected_labels]


def render_category_selectbox(key: str, label: str = "Category", include_all: bool = True) -> Optional[str]:
    categories = load_categories().get("categories", [])
    options = {c["label"]: c["id"] for c in categories}
    labels = (["All categories"] if include_all else []) + list(options.keys())
    choice = st.selectbox(label, labels, key=key)
    if choice == "All categories":
        return None
    return options.get(choice)


def render_date_range_picker(
    key_prefix: str, include_all_time: bool = False, default_preset: str = "Last 30 days"
) -> Tuple[Optional[date], Optional[date]]:
    """The date-range control used on the Research page (Section 9: presets
    + custom range) and, with include_all_time=True, on browsing pages
    like Papers where the sensible default is to show everything rather
    than silently filtering to a recent window."""
    preset_options = (["All time"] if include_all_time else []) + list(DATE_PRESETS.keys()) + ["Custom range"]
    default_choice = "All time" if include_all_time else default_preset
    default_index = preset_options.index(default_choice) if default_choice in preset_options else 0

    preset = st.selectbox("Date range", preset_options, index=default_index, key=f"{key_prefix}_preset")

    today = date.today()

    if preset == "All time":
        return None, None

    if preset == "Custom range":
        col1, col2 = st.columns(2)
        with col1:
            start = st.date_input("Start date", value=today - timedelta(days=30), key=f"{key_prefix}_start")
        with col2:
            end = st.date_input("End date", value=today, key=f"{key_prefix}_end")
        if start > end:
            st.error("Start date must be on or before end date.")
            return None, None
        return start, end

    days = DATE_PRESETS[preset]
    return today - timedelta(days=days), today


def render_source_selectbox(key: str, label: str = "Source", include_all: bool = True) -> Optional[str]:
    sources = {"arXiv": "arxiv", "OpenAlex": "openalex", "Semantic Scholar": "semantic_scholar", "Crossref": "crossref"}
    labels = (["All sources"] if include_all else []) + list(sources.keys())
    choice = st.selectbox(label, labels, key=key)
    if choice == "All sources":
        return None
    return sources.get(choice)
