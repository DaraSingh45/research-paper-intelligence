"""
tests/test_processing.py

Covers data cleaning (missing title, invalid date, malformed DOI, etc.),
normalization, and paper/configuration validation.
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.loader import get_intensity_preset  # noqa: E402
from database.models import NormalizedPaper  # noqa: E402
from processing import cleaner, normalizer, validator  # noqa: E402


def make_paper(**overrides) -> NormalizedPaper:
    defaults = dict(
        external_id="1",
        title="  A   Sample   Paper  ",
        source="arxiv",
        abstract="This is a reasonably long abstract about something interesting.",
        authors=["Jane Doe", "jane doe", "John Smith"],
        publication_date=date(2023, 1, 1),
        categories=["cs.AI"],
        doi="10.1234/example",
        url="https://example.com/paper",
        citation_count=5,
    )
    defaults.update(overrides)
    return NormalizedPaper(**defaults)


class TestCleaner:
    def test_missing_title_is_dropped(self):
        paper = make_paper(title="")
        assert cleaner.clean_paper(paper) is None

    def test_whitespace_title_is_cleaned(self):
        paper = make_paper()
        cleaned = cleaner.clean_paper(paper)
        assert cleaned.title == "A Sample Paper"

    def test_invalid_future_date_is_rejected(self):
        paper = make_paper(publication_date=date.today() + timedelta(days=3650))
        cleaned = cleaner.clean_paper(paper)
        assert cleaned.publication_date is None

    def test_malformed_doi_is_rejected(self):
        paper = make_paper(doi="not-a-doi")
        cleaned = cleaner.clean_paper(paper)
        assert cleaned.doi is None

    def test_doi_prefix_is_stripped(self):
        paper = make_paper(doi="https://doi.org/10.1234/example")
        cleaned = cleaner.clean_paper(paper)
        assert cleaned.doi == "10.1234/example"

    def test_missing_abstract_is_none_not_crashing(self):
        paper = make_paper(abstract=None)
        cleaned = cleaner.clean_paper(paper)
        assert cleaned.abstract is None

    def test_short_junk_abstract_is_dropped(self):
        paper = make_paper(abstract="n/a")
        cleaned = cleaner.clean_paper(paper)
        assert cleaned.abstract is None

    def test_duplicate_authors_removed_case_insensitively(self):
        paper = make_paper()
        cleaned = cleaner.clean_paper(paper)
        assert cleaned.authors == ["Jane Doe", "John Smith"]

    def test_invalid_url_rejected(self):
        paper = make_paper(url="not a url")
        cleaned = cleaner.clean_paper(paper)
        assert cleaned.url is None

    def test_negative_citation_count_clamped_to_zero(self):
        paper = make_paper(citation_count=-5)
        cleaned = cleaner.clean_paper(paper)
        assert cleaned.citation_count == 0

    def test_clean_batch_counts_dropped(self):
        papers = [make_paper(external_id="1"), make_paper(external_id="2", title="")]
        cleaned, dropped = cleaner.clean_batch(papers)
        assert len(cleaned) == 1
        assert dropped == 1


class TestNormalizer:
    def test_normalize_title_strips_punctuation_and_case(self):
        assert normalizer.normalize_title("Hello, World!") == "hello world"

    def test_normalize_author_name(self):
        assert normalizer.normalize_author_name("Jane Ann Doe") == "doe, j."

    def test_map_categories_falls_back_to_uncategorized(self):
        result = normalizer.map_categories_to_internal(["totally-unknown-category-xyz"])
        assert result == ["uncategorized"]

    def test_map_categories_matches_arxiv_code(self):
        result = normalizer.map_categories_to_internal(["cs.CV"])
        assert "computer_vision" in result


class TestValidator:
    def test_valid_paper_passes(self):
        paper = make_paper()
        result = validator.validate_paper(paper)
        assert result.valid

    def test_empty_title_fails(self):
        paper = make_paper(title="")
        result = validator.validate_paper(paper)
        assert not result.valid
        assert any("title" in e.lower() for e in result.errors)

    def test_missing_external_id_fails(self):
        paper = make_paper(external_id="")
        result = validator.validate_paper(paper)
        assert not result.valid

    def test_batch_split_valid_invalid(self):
        papers = [make_paper(external_id="1"), make_paper(external_id="2", title="")]
        valid, invalid = validator.validate_batch(papers)
        assert len(valid) == 1
        assert len(invalid) == 1


class TestConfiguration:
    def test_invalid_intensity_raises(self):
        with pytest.raises(ValueError):
            get_intensity_preset("ultra-mega-deep")

    def test_valid_intensities_load(self):
        for name in ("quick", "standard", "deep"):
            preset = get_intensity_preset(name)
            assert preset["max_results_per_source"] > 0

    def test_default_intensity_used_when_none_given(self):
        preset = get_intensity_preset(None)
        assert preset is not None
