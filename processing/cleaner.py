"""
processing/cleaner.py

Cleans a NormalizedPaper produced by a connector. Never mutates the
original raw_source_data -- operates on (and returns) a shallow copy so
the "original data is never overwritten" principle (Section 21) holds.
"""
from __future__ import annotations

import copy
import logging
import re
from datetime import date
from typing import List, Optional
from urllib.parse import urlparse

from database.models import NormalizedPaper

logger = logging.getLogger(__name__)

DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$")
_WHITESPACE_RE = re.compile(r"\s+")


def clean_whitespace(text: Optional[str]) -> Optional[str]:
    if text is None:
        return None
    cleaned = _WHITESPACE_RE.sub(" ", text).strip()
    return cleaned or None


def clean_title(title: Optional[str]) -> Optional[str]:
    title = clean_whitespace(title)
    if not title or title.lower() in {"(untitled)", "untitled", "n/a", "none"}:
        return None
    return title


def clean_abstract(abstract: Optional[str]) -> Optional[str]:
    abstract = clean_whitespace(abstract)
    if abstract and len(abstract) < 20:
        # Too short to be a meaningful abstract (likely a placeholder/junk value)
        return None
    return abstract


def clean_doi(doi: Optional[str]) -> Optional[str]:
    if not doi:
        return None
    doi = doi.strip().lower()
    doi = doi.replace("https://doi.org/", "").replace("http://doi.org/", "").replace("doi:", "")
    doi = doi.strip()
    if not doi or not DOI_RE.match(doi):
        return None
    return doi


def clean_date(value: Optional[date]) -> Optional[date]:
    if value is None:
        return None
    today = date.today()
    # Reject obviously malformed dates (far future, or before academic publishing existed)
    if value.year < 1900 or value > today:
        return None
    return value


def clean_url(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    url = url.strip()
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return None
    return url


def clean_citation_count(value) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return 0
    return n if n >= 0 else 0


def clean_authors(authors: List[str]) -> List[str]:
    seen = set()
    cleaned: List[str] = []
    for author in authors or []:
        name = clean_whitespace(author)
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue  # duplicate author within the same paper
        seen.add(key)
        cleaned.append(name)
    return cleaned


def clean_paper(paper: NormalizedPaper) -> Optional[NormalizedPaper]:
    """Returns a cleaned copy of the paper, or None if the paper fails
    minimum quality bars (e.g. no usable title) and should be dropped."""
    cleaned = copy.deepcopy(paper)

    cleaned.title = clean_title(cleaned.title)
    if not cleaned.title:
        logger.debug("Dropping paper %s/%s: empty/invalid title", paper.source, paper.external_id)
        return None

    cleaned.abstract = clean_abstract(cleaned.abstract)
    cleaned.doi = clean_doi(cleaned.doi)
    cleaned.publication_date = clean_date(cleaned.publication_date)
    cleaned.url = clean_url(cleaned.url)
    cleaned.pdf_url = clean_url(cleaned.pdf_url)
    cleaned.citation_count = clean_citation_count(cleaned.citation_count)
    cleaned.authors = clean_authors(cleaned.authors)
    cleaned.journal = clean_whitespace(cleaned.journal)
    cleaned.venue = clean_whitespace(cleaned.venue)
    cleaned.publisher = clean_whitespace(cleaned.publisher)

    return cleaned


def clean_batch(papers: List[NormalizedPaper]) -> tuple[List[NormalizedPaper], int]:
    """Cleans a batch of papers, returning (cleaned_papers, num_dropped)."""
    cleaned: List[NormalizedPaper] = []
    dropped = 0
    for paper in papers:
        result = clean_paper(paper)
        if result is None:
            dropped += 1
        else:
            cleaned.append(result)
    return cleaned, dropped
