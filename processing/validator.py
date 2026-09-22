"""
processing/validator.py

Final validation gate before a paper is written to PostgreSQL. This is
separate from llm/validator.py, which validates LLM output specifically.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from database.models import NormalizedPaper

MIN_TITLE_LENGTH = 3
MAX_TITLE_LENGTH = 1000


@dataclass
class ValidationResult:
    valid: bool
    errors: List[str] = field(default_factory=list)


def validate_paper(paper: NormalizedPaper) -> ValidationResult:
    errors: List[str] = []

    if not paper.title or len(paper.title) < MIN_TITLE_LENGTH:
        errors.append("Title is missing or too short.")
    elif len(paper.title) > MAX_TITLE_LENGTH:
        errors.append("Title is unreasonably long (possible parsing error).")

    if not paper.external_id:
        errors.append("Missing external_id from source.")

    if not paper.source:
        errors.append("Missing source name.")

    if paper.citation_count < 0:
        errors.append("Citation count cannot be negative.")

    if paper.doi and ("/" not in paper.doi):
        errors.append("DOI does not look well-formed.")

    return ValidationResult(valid=not errors, errors=errors)


def validate_batch(papers: List[NormalizedPaper]) -> tuple[List[NormalizedPaper], List[tuple[NormalizedPaper, List[str]]]]:
    """Returns (valid_papers, [(paper, errors), ...] for invalid ones)."""
    valid: List[NormalizedPaper] = []
    invalid: List[tuple[NormalizedPaper, List[str]]] = []
    for paper in papers:
        result = validate_paper(paper)
        if result.valid:
            valid.append(paper)
        else:
            invalid.append((paper, result.errors))
    return valid, invalid
