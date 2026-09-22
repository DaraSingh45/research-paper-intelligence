"""
tests/test_deduplication.py

Tests processing/deduplicator.py's tiered matching logic. The database
layer is mocked so these tests run without a live PostgreSQL instance.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database.models import NormalizedPaper  # noqa: E402
from processing.deduplicator import DedupOutcome, Deduplicator  # noqa: E402
from processing.normalizer import normalize_paper  # noqa: E402


def make_paper(**overrides) -> NormalizedPaper:
    defaults = dict(
        external_id="1",
        title="Attention Is All You Need Again",
        source="arxiv",
        abstract="An abstract.",
        authors=["Alice Author"],
        publication_date=date(2023, 1, 1),
        categories=["cs.LG"],
        doi="10.1234/attn",
        url="https://example.com/1",
        citation_count=1,
    )
    defaults.update(overrides)
    paper = NormalizedPaper(**defaults)
    return normalize_paper(paper)


class TestDeduplicatorTiers:
    @patch("processing.deduplicator.PaperRepository")
    @patch("processing.deduplicator.AuthorRepository")
    def test_same_doi_is_duplicate(self, mock_authors, mock_papers):
        mock_papers.find_by_doi.return_value = {"id": "existing-paper-id"}
        dedup = Deduplicator(dedup_strategy="full", enable_fuzzy=False)
        outcome = dedup.process_paper(make_paper(), job_id="job1")
        assert outcome == DedupOutcome.DUPLICATE_DOI
        mock_papers.link_source.assert_called_once()
        mock_papers.insert_paper.assert_not_called()

    @patch("processing.deduplicator.PaperRepository")
    @patch("processing.deduplicator.AuthorRepository")
    def test_same_external_id_is_duplicate(self, mock_authors, mock_papers):
        mock_papers.find_by_doi.return_value = None
        mock_papers.find_by_external_id.return_value = {"id": "existing-paper-id"}
        dedup = Deduplicator(dedup_strategy="full", enable_fuzzy=False)
        outcome = dedup.process_paper(make_paper(doi=None), job_id="job1")
        assert outcome == DedupOutcome.DUPLICATE_EXTERNAL_ID
        mock_papers.insert_paper.assert_not_called()

    @patch("processing.deduplicator.PaperRepository")
    @patch("processing.deduplicator.AuthorRepository")
    def test_same_normalized_title_is_duplicate(self, mock_authors, mock_papers):
        mock_papers.find_by_doi.return_value = None
        mock_papers.find_by_external_id.return_value = None
        mock_papers.find_by_normalized_title.return_value = {"id": "existing-paper-id"}
        dedup = Deduplicator(dedup_strategy="full", enable_fuzzy=False)
        outcome = dedup.process_paper(make_paper(doi=None), job_id="job1")
        assert outcome == DedupOutcome.DUPLICATE_TITLE
        mock_papers.insert_paper.assert_not_called()

    @patch("processing.deduplicator.PaperRepository")
    @patch("processing.deduplicator.AuthorRepository")
    def test_different_source_ids_but_no_match_creates_new(self, mock_authors, mock_papers):
        mock_papers.find_by_doi.return_value = None
        mock_papers.find_by_external_id.return_value = None
        mock_papers.find_by_normalized_title.return_value = None
        mock_papers.insert_paper.return_value = "new-paper-id"
        mock_authors.upsert_author.return_value = "author-id"

        dedup = Deduplicator(dedup_strategy="full", enable_fuzzy=False)
        outcome = dedup.process_paper(make_paper(doi=None, external_id="openalex-1", source="openalex"), job_id="job1")
        assert outcome == DedupOutcome.NEW
        mock_papers.insert_paper.assert_called_once()
        mock_papers.link_source.assert_called_once()

    @patch("processing.deduplicator.PaperRepository")
    @patch("processing.deduplicator.AuthorRepository")
    def test_fuzzy_match_flags_but_does_not_merge(self, mock_authors, mock_papers):
        mock_papers.find_by_doi.return_value = None
        mock_papers.find_by_external_id.return_value = None
        mock_papers.find_by_normalized_title.return_value = None
        mock_papers.insert_paper.return_value = "new-paper-id"
        mock_papers.find_candidates_for_fuzzy_match.return_value = [
            {"id": "similar-paper-id", "title": "Attention Is All You Need", "title_normalized": "attention is all you need"}
        ]
        mock_authors.upsert_author.return_value = "author-id"

        dedup = Deduplicator(dedup_strategy="strict", enable_fuzzy=True, fuzzy_threshold=0.8)
        outcome = dedup.process_paper(make_paper(doi=None), job_id="job1")

        # Fuzzy matches are flagged for review, not auto-merged: the paper is
        # still inserted as its own row.
        assert outcome == DedupOutcome.POSSIBLE_DUPLICATE
        mock_papers.insert_paper.assert_called_once()
        mock_papers.flag_possible_duplicate.assert_called_once_with("new-paper-id", "similar-paper-id")

    @patch("processing.deduplicator.PaperRepository")
    @patch("processing.deduplicator.AuthorRepository")
    def test_batch_summary_counts(self, mock_authors, mock_papers):
        mock_papers.find_by_doi.side_effect = [None, {"id": "existing"}]
        mock_papers.find_by_external_id.return_value = None
        mock_papers.find_by_normalized_title.return_value = None
        mock_papers.insert_paper.return_value = "new-id"
        mock_authors.upsert_author.return_value = "author-id"

        dedup = Deduplicator(dedup_strategy="basic", enable_fuzzy=False)
        papers = [make_paper(external_id="1", doi="10.1/a"), make_paper(external_id="2", doi="10.1/b")]
        summary = dedup.process_batch(papers, job_id="job1")

        assert summary.total == 2
        assert summary.new == 1
        assert summary.duplicates == 1
