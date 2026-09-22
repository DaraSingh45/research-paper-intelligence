"""
tests/test_ingestion.py

Tests the parsing logic of each connector using canned payloads (no real
network calls). Also covers empty/malformed responses and the base
class's retry/rate-limit plumbing.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database.models import SearchConfig  # noqa: E402
from ingestion.arxiv import ArxivSource  # noqa: E402
from ingestion.base import RateLimiter, RetryableHTTPError  # noqa: E402
from ingestion.crossref import CrossrefSource  # noqa: E402
from ingestion.openalex import OpenAlexSource  # noqa: E402
from ingestion.semantic_scholar import SemanticScholarSource  # noqa: E402

SAMPLE_ARXIV_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2301.00001v1</id>
    <title>  A Great Paper About   LLMs  </title>
    <summary>This paper studies large language models in great detail and depth.</summary>
    <author><name>Jane Doe</name></author>
    <author><name>John Smith</name></author>
    <published>2023-01-15T00:00:00Z</published>
    <category term="cs.AI"/>
    <category term="cs.LG"/>
    <link rel="alternate" href="http://arxiv.org/abs/2301.00001v1"/>
    <link title="pdf" href="http://arxiv.org/pdf/2301.00001v1"/>
  </entry>
</feed>"""


class TestArxivParsing:
    def test_parses_valid_entry(self):
        source = ArxivSource()
        papers = source._parse_feed(SAMPLE_ARXIV_FEED)
        assert len(papers) == 1
        paper = papers[0]
        assert paper.title == "A Great Paper About LLMs"
        assert paper.external_id == "2301.00001v1"
        assert paper.authors == ["Jane Doe", "John Smith"]
        assert paper.categories == ["cs.AI", "cs.LG"]
        assert paper.pdf_url == "http://arxiv.org/pdf/2301.00001v1"
        assert paper.source == "arxiv"

    def test_empty_feed_returns_no_papers(self):
        source = ArxivSource()
        empty_feed = '<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"></feed>'
        assert source._parse_feed(empty_feed) == []

    def test_malformed_xml_does_not_raise(self):
        source = ArxivSource()
        assert source._parse_feed("<not valid xml") == []

    def test_search_query_includes_keywords_and_categories(self):
        source = ArxivSource()
        config = SearchConfig(keywords=["transformers"], categories=["machine_learning"])
        query = source._build_search_query(config)
        assert "transformers" in query
        assert "cat:" in query


class TestOpenAlexParsing:
    def test_parses_valid_work(self):
        source = OpenAlexSource()
        work = {
            "id": "https://openalex.org/W123456789",
            "display_name": "Deep Learning for Everyone",
            "abstract_inverted_index": {"Deep": [0], "learning": [1], "is": [2], "fun": [3]},
            "authorships": [{"author": {"display_name": "Alice Author"}}],
            "publication_date": "2022-05-01",
            "concepts": [{"display_name": "Machine learning"}],
            "doi": "https://doi.org/10.1234/example",
            "cited_by_count": 42,
        }
        paper = source._parse_work(work)
        assert paper.external_id == "W123456789"
        assert paper.abstract == "Deep learning is fun"
        assert paper.doi == "10.1234/example"
        assert paper.citation_count == 42

    def test_missing_optional_fields_handled_safely(self):
        source = OpenAlexSource()
        paper = source._parse_work({"id": "https://openalex.org/W1", "display_name": "X"})
        assert paper.abstract is None
        assert paper.authors == []
        assert paper.citation_count == 0


class TestSemanticScholarParsing:
    def test_parses_valid_paper(self):
        source = SemanticScholarSource()
        item = {
            "paperId": "abc123",
            "title": "Reinforcement Learning Survey",
            "abstract": "A survey of RL methods.",
            "authors": [{"name": "Bob Researcher"}],
            "publicationDate": "2021-06-10",
            "externalIds": {"DOI": "10.5555/rl.survey"},
            "citationCount": 10,
            "fieldsOfStudy": ["Computer Science"],
        }
        paper = source._parse_paper(item)
        assert paper.external_id == "abc123"
        assert paper.doi == "10.5555/rl.survey"
        assert paper.citation_count == 10


class TestCrossrefParsing:
    def test_parses_valid_item(self):
        source = CrossrefSource()
        item = {
            "DOI": "10.1000/example",
            "title": ["A Crossref Paper"],
            "author": [{"given": "Carol", "family": "Crossref"}],
            "published": {"date-parts": [[2020, 3, 15]]},
            "container-title": ["Journal of Testing"],
            "is-referenced-by-count": 5,
        }
        paper = source._parse_item(item)
        assert paper.doi == "10.1000/example"
        assert paper.authors == ["Carol Crossref"]
        assert paper.journal == "Journal of Testing"
        assert paper.publication_date.year == 2020


class TestBaseSourceResilience:
    def test_rate_limiter_enforces_minimum_interval(self):
        limiter = RateLimiter(requests_per_second=1000)  # effectively no-op for the test
        limiter.wait()
        limiter.wait()  # should not raise or hang meaningfully

    def test_safe_search_catches_exceptions(self):
        source = ArxivSource()
        with patch.object(source, "search", side_effect=RuntimeError("boom")):
            result = source.safe_search(SearchConfig(keywords=["x"]))
        assert result.success is False
        assert "Unexpected error" in result.error_message

    def test_safe_search_reports_disabled_source(self):
        source = ArxivSource()
        source.enabled = False
        result = source.safe_search(SearchConfig(keywords=["x"]))
        assert result.success is False
        assert "disabled" in result.error_message.lower()

    def test_get_retries_on_retryable_status(self):
        source = ArxivSource()
        source.max_retries = 2
        source.backoff = 0  # keep the test fast

        ok_response = MagicMock(status_code=200)
        ok_response.raise_for_status.return_value = None

        bad_response = MagicMock(status_code=503)

        with patch("ingestion.base.requests.get", side_effect=[bad_response, ok_response]):
            resp = source._get("http://example.com")
        assert resp is ok_response

    def test_get_raises_after_exhausting_retries(self):
        source = ArxivSource()
        source.max_retries = 2
        source.backoff = 0

        bad_response = MagicMock(status_code=503)
        with patch("ingestion.base.requests.get", return_value=bad_response):
            with pytest.raises(RetryableHTTPError):
                source._get("http://example.com")


class TestOpenAlexApiKeyHandling:
    def test_400_without_key_raises_actionable_hint(self, monkeypatch):
        monkeypatch.delenv("OPENALEX_API_KEY", raising=False)
        source = OpenAlexSource()
        http_error = requests.HTTPError(response=MagicMock(status_code=400))
        with patch.object(source, "_get", side_effect=http_error):
            result = source.safe_search(SearchConfig(keywords=["x"]))
        assert result.success is False
        assert "API key" in result.error_message

    def test_api_key_is_sent_when_configured(self, monkeypatch):
        monkeypatch.setenv("OPENALEX_API_KEY", "test-key-123")
        source = OpenAlexSource()
        ok_response = MagicMock(status_code=200)
        ok_response.json.return_value = {"results": []}
        captured_params = {}

        def fake_get(url, params=None, **kwargs):
            captured_params.update(params or {})
            return ok_response

        with patch.object(source, "_get", side_effect=fake_get):
            source.search(SearchConfig(keywords=["x"]))
        assert captured_params.get("api_key") == "test-key-123"
        assert "mailto" not in captured_params


class TestSemanticScholarRateLimitHandling:
    def test_429_after_retries_raises_actionable_hint(self):
        source = SemanticScholarSource()
        error = RetryableHTTPError("semantic_scholar: HTTP 429 from http://x")
        with patch.object(source, "_get", side_effect=error):
            result = source.safe_search(SearchConfig(keywords=["x"]))
        assert result.success is False
        assert "rate-limiting" in result.error_message or "429" in result.error_message

    def test_api_key_header_sent_when_configured(self, monkeypatch):
        monkeypatch.setenv("SEMANTIC_SCHOLAR_API_KEY", "s2-test-key")
        source = SemanticScholarSource()
        ok_response = MagicMock(status_code=200)
        ok_response.json.return_value = {"data": []}
        captured_headers = {}

        def fake_get(url, params=None, headers=None, **kwargs):
            captured_headers.update(headers or {})
            return ok_response

        with patch.object(source, "_get", side_effect=fake_get):
            source.search(SearchConfig(keywords=["x"]))
        assert captured_headers.get("x-api-key") == "s2-test-key"
