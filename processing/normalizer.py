"""
processing/normalizer.py

Normalizes cleaned papers into consistent, comparable forms:
- title_normalized: used for exact/fuzzy dedup matching
- author normalized names: used for author-matching across papers
- categories: source-specific category strings mapped to the internal
  vocabulary defined in config/categories.yaml
"""
from __future__ import annotations

import re
from typing import List

from config.loader import load_categories
from database.models import NormalizedPaper

_PUNCT_RE = re.compile(r"[^\w\s]")
_WHITESPACE_RE = re.compile(r"\s+")


def normalize_title(title: str) -> str:
    """Lowercase, strip punctuation/whitespace -- used purely for matching,
    never shown to the user."""
    if not title:
        return ""
    text = title.lower()
    text = _PUNCT_RE.sub(" ", text)
    text = _WHITESPACE_RE.sub(" ", text).strip()
    return text


def normalize_author_name(name: str) -> str:
    """Produces a 'family, f.' style key so 'Jane A. Doe' and 'J. Doe' have
    a reasonable chance of matching, while keeping the original display
    name untouched for presentation."""
    if not name:
        return ""
    parts = [p for p in _WHITESPACE_RE.split(name.strip()) if p]
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0].lower()
    family = parts[-1].lower()
    initial = parts[0][0].lower() if parts[0] else ""
    return f"{family}, {initial}."


def _category_mapping() -> dict:
    """Builds a lookup from every known source-native label/code
    (lower-cased) to the internal category id."""
    mapping: dict[str, str] = {}
    for cat in load_categories().get("categories", []):
        cat_id = cat["id"]
        for code in cat.get("arxiv_codes", []):
            mapping[code.lower()] = cat_id
        for name in cat.get("openalex_concepts", []):
            mapping[name.lower()] = cat_id
        for field in cat.get("semantic_scholar_fields", []):
            mapping.setdefault(field.lower(), cat_id)
        for kw in cat.get("keywords", []):
            mapping[kw.lower()] = cat_id
        mapping[cat["label"].lower()] = cat_id
    return mapping


def map_categories_to_internal(source_categories: List[str]) -> List[str]:
    """Maps a paper's raw source categories to 0+ internal category ids.
    Falls back to 'uncategorized' if nothing matches."""
    mapping = _category_mapping()
    matched: List[str] = []
    for raw in source_categories or []:
        key = (raw or "").strip().lower()
        if not key:
            continue
        if key in mapping:
            internal_id = mapping[key]
            if internal_id not in matched:
                matched.append(internal_id)
            continue
        # Fallback: substring match against keyword hints (cheap, best-effort)
        for hint, internal_id in mapping.items():
            if hint in key or key in hint:
                if internal_id not in matched:
                    matched.append(internal_id)
                break
    return matched or ["uncategorized"]


def normalize_paper(paper: NormalizedPaper) -> NormalizedPaper:
    """Populates the derived normalization fields on a (cleaned) paper."""
    paper.title_normalized = normalize_title(paper.title)
    paper.internal_categories = map_categories_to_internal(paper.categories)
    return paper


def normalize_batch(papers: List[NormalizedPaper]) -> List[NormalizedPaper]:
    return [normalize_paper(p) for p in papers]
