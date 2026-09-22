"""
processing/deduplicator.py

Implements the 4-tier duplicate detection strategy from Section 19:
  1. DOI match
  2. Source-specific external ID match
  3. Exact normalized title match
  4. Fuzzy title match (same year + high similarity) -- flagged for
     manual review via papers.possible_duplicate_of, NEVER auto-merged.

When an exact duplicate (tiers 1-3) is found, the incoming paper is not
inserted as a new row -- instead its source is linked onto the existing
paper (paper_sources) and its raw payload is merged in additively, so the
"Original paper -> arXiv ID / OpenAlex ID / DOI" relationship in Section 19
is preserved.
"""
from __future__ import annotations

import difflib
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

from database.models import NormalizedPaper
from database.repositories import AuthorRepository, PaperRepository
from processing.normalizer import normalize_author_name

logger = logging.getLogger(__name__)


class DedupOutcome(str, Enum):
    NEW = "new"
    DUPLICATE_DOI = "duplicate_doi"
    DUPLICATE_EXTERNAL_ID = "duplicate_external_id"
    DUPLICATE_TITLE = "duplicate_title"
    POSSIBLE_DUPLICATE = "possible_duplicate"


@dataclass
class DedupSummary:
    total: int = 0
    new: int = 0
    duplicates: int = 0
    possible_duplicates: int = 0
    outcomes: List[DedupOutcome] = field(default_factory=list)


class Deduplicator:
    def __init__(self, dedup_strategy: str = "full", enable_fuzzy: bool = True, fuzzy_threshold: float = 0.92):
        self.dedup_strategy = dedup_strategy
        self.enable_fuzzy = enable_fuzzy and dedup_strategy in ("full", "strict")
        self.fuzzy_threshold = fuzzy_threshold

    def _store_authors_and_categories(self, paper_id: str, paper: NormalizedPaper) -> None:
        author_ids = []
        for author_name in paper.authors:
            norm = normalize_author_name(author_name)
            if not norm:
                continue
            author_ids.append(AuthorRepository.upsert_author(author_name, norm))
        if author_ids:
            PaperRepository.link_authors(paper_id, author_ids)
        if paper.internal_categories:
            PaperRepository.link_categories(paper_id, paper.internal_categories)

    def _find_fuzzy_match(self, paper: NormalizedPaper) -> Optional[str]:
        year = paper.publication_date.year if paper.publication_date else None
        candidates = PaperRepository.find_candidates_for_fuzzy_match(year)
        best_id, best_ratio = None, 0.0
        for cand in candidates:
            ratio = difflib.SequenceMatcher(None, paper.title_normalized, cand["title_normalized"]).ratio()
            if ratio > best_ratio:
                best_ratio, best_id = ratio, str(cand["id"])
        if best_id and best_ratio >= self.fuzzy_threshold:
            return best_id
        return None

    def process_paper(self, paper: NormalizedPaper, job_id: Optional[str]) -> DedupOutcome:
        # Tier 1: DOI
        if paper.doi:
            existing = PaperRepository.find_by_doi(paper.doi)
            if existing:
                PaperRepository.link_source(str(existing["id"]), paper.source, paper.external_id, paper.url)
                PaperRepository.merge_raw_source_data(str(existing["id"]), paper.source, paper.raw_source_data)
                return DedupOutcome.DUPLICATE_DOI

        # Tier 2: source-specific external id (already ingested from this exact source before)
        existing = PaperRepository.find_by_external_id(paper.source, paper.external_id)
        if existing:
            PaperRepository.merge_raw_source_data(str(existing["id"]), paper.source, paper.raw_source_data)
            return DedupOutcome.DUPLICATE_EXTERNAL_ID

        # Tier 3: exact normalized title match
        if self.dedup_strategy in ("basic", "full", "strict"):
            existing = PaperRepository.find_by_normalized_title(paper.title_normalized)
            if existing:
                PaperRepository.link_source(str(existing["id"]), paper.source, paper.external_id, paper.url)
                PaperRepository.merge_raw_source_data(str(existing["id"]), paper.source, paper.raw_source_data)
                return DedupOutcome.DUPLICATE_TITLE

        # Tier 4: fuzzy title match (flag only -- insert as its own row)
        possible_duplicate_of = self._find_fuzzy_match(paper) if self.enable_fuzzy else None

        paper_id = PaperRepository.insert_paper(paper, job_id)
        PaperRepository.link_source(paper_id, paper.source, paper.external_id, paper.url)
        self._store_authors_and_categories(paper_id, paper)

        if possible_duplicate_of:
            PaperRepository.flag_possible_duplicate(paper_id, possible_duplicate_of)
            return DedupOutcome.POSSIBLE_DUPLICATE

        return DedupOutcome.NEW

    def process_batch(self, papers: List[NormalizedPaper], job_id: Optional[str]) -> DedupSummary:
        summary = DedupSummary(total=len(papers))
        for paper in papers:
            try:
                outcome = self.process_paper(paper, job_id)
            except Exception:  # noqa: BLE001 - one bad paper should not stop the batch
                logger.exception(
                    "Deduplication failed for paper external_id=%s source=%s", paper.external_id, paper.source
                )
                continue
            summary.outcomes.append(outcome)
            if outcome == DedupOutcome.NEW:
                summary.new += 1
            elif outcome == DedupOutcome.POSSIBLE_DUPLICATE:
                summary.possible_duplicates += 1
                summary.new += 1  # it IS a new row, just flagged for review
            else:
                summary.duplicates += 1
        return summary
