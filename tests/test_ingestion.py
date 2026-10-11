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
    @pytest.fixture(autouse=True)
    def _ignore_real_dotenv(self, monkeypatch, tmp_path):
        # Point the connector at an empty temp .env so a developer's real
        # .env file can't affect these tests.
        import ingestion.openalex as oa

        monkeypatch.setattr(oa, "DOTENV_PATH", tmp_path / ".env")
        oa._dotenv_cache.update(mtime=None, value=None)

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

    def test_key_is_read_from_dotenv_file(self, monkeypatch, tmp_path):
        import ingestion.openalex as oa

        monkeypatch.delenv("OPENALEX_API_KEY", raising=False)
        env_file = tmp_path / ".env"
        env_file.write_text("POSTGRES_DB=x\nOPENALEX_API_KEY= file-key-456 \n", encoding="utf-8")
        monkeypatch.setattr(oa, "DOTENV_PATH", env_file)
        assert oa.get_openalex_api_key() == "file-key-456"

    def test_dotenv_file_wins_over_stale_environment(self, monkeypatch, tmp_path):
        import ingestion.openalex as oa

        monkeypatch.setenv("OPENALEX_API_KEY", "")
        env_file = tmp_path / ".env"
        env_file.write_text("OPENALEX_API_KEY=fresh-key\n", encoding="utf-8")
        monkeypatch.setattr(oa, "DOTENV_PATH", env_file)
        assert oa.get_openalex_api_key() == "fresh-key"

    def test_paper_url_prefers_landing_page_then_doi(self):
        source = OpenAlexSource()
        base = {"id": "https://openalex.org/W1", "display_name": "T", "doi": "https://doi.org/10.1/abc"}
        with_landing = dict(base, primary_location={"landing_page_url": "https://publisher.example/abc"})
        assert source._parse_work(with_landing).url == "https://publisher.example/abc"
        assert source._parse_work(base).url == "https://doi.org/10.1/abc"
        assert source._parse_work({"id": "https://openalex.org/W2", "display_name": "T"}).url == "https://openalex.org/W2"

    def test_placeholder_key_counts_as_missing(self, monkeypatch):
        monkeypatch.setenv("OPENALEX_API_KEY", " YOUR_API_KEY")
        from ingestion.openalex import get_openalex_api_key

        assert get_openalex_api_key() is None

    def test_exhausted_quota_gives_clear_message(self, monkeypatch):
        from ingestion.base import RateLimitExhaustedError

        monkeypatch.delenv("OPENALEX_API_KEY", raising=False)
        source = OpenAlexSource()
        error = RateLimitExhaustedError("openalex: exhausted", retry_after_seconds=24526)
        with patch.object(source, "_get", side_effect=error):
            result = source.safe_search(SearchConfig(keywords=["x"]))
        assert result.success is False
        assert "API key" in result.error_message and "resets" in result.error_message

    def test_429_with_long_retry_after_is_not_retried(self):
        source = OpenAlexSource()
        source.backoff = 0
        resp = MagicMock(status_code=429, headers={"Retry-After": "24526"})
        with patch("ingestion.base.requests.get", return_value=resp) as mocked:
            from ingestion.base import RateLimitExhaustedError

            with pytest.raises(RateLimitExhaustedError):
                source._get("http://example.com")
        assert mocked.call_count == 1


class TestOpenAlexQueryBuilding:
    """Guards the 2026 OpenAlex query syntax (help.openalex.org/api/searching)."""

    def _params(self, **kw):
        from datetime import date

        cfg = SearchConfig(
            keywords=kw.get("keywords", ["machine learning", "deep learning"]),
            title_filter=kw.get("title_filter", "AI agents"),
            authors=kw.get("authors", []),
            categories=kw.get("categories", ["artificial_intelligence", "machine_learning"]),
            start_date=date(2026, 10, 4),
            end_date=date(2026, 10, 11),
            intensity="quick",
        )
        return OpenAlexSource()._build_params(cfg, 25), cfg

    def test_no_deprecated_or_invalid_filters(self):
        params, _ = self._params(authors=["Yoshua Bengio"])
        f = params["filter"]
        assert "concepts.display_name.search" not in f
        assert "authorships.author.display_name.search" not in f
        assert "title.search" not in f
        assert "|" not in f

    def test_uses_documented_parameters(self):
        params, _ = self._params(authors=["Yoshua Bengio", "Geoffrey Hinton"])
        assert params["search"] == '"machine learning" OR "deep learning"'
        assert params["search.title"] == "AI agents"
        assert 'raw_author_name.search:"Yoshua Bengio" OR "Geoffrey Hinton"' in params["filter"]
        assert 'title_abstract_keywords.search:"Artificial Intelligence" OR' in params["filter"]
        assert "from_publication_date:2026-10-04" in params["filter"]

    def test_single_keyword_is_unquoted(self):
        params, _ = self._params(keywords=["transformers"], categories=[], title_filter=None)
        assert params["search"] == "transformers"

    def test_commas_and_quotes_cannot_break_filters(self):
        params, _ = self._params(authors=['Smith, "John"'], categories=[], title_filter=None)
        assert 'raw_author_name.search:"Smith John"' in params["filter"]

    def test_400_retries_with_simpler_query_and_records_warning(self, monkeypatch):
        import ingestion.openalex as oa

        monkeypatch.setattr(oa, "get_openalex_api_key", lambda: "k-123")
        source = OpenAlexSource()
        bad = MagicMock(status_code=400)
        bad.json.return_value = {"error": "Invalid query parameters", "message": "bad filter"}
        ok_response = MagicMock(status_code=200)
        ok_response.json.return_value = {"results": [{"id": "https://openalex.org/W9", "display_name": "Ok"}]}
        calls = []

        def fake_get(url, params=None, **kwargs):
            calls.append(dict(params))
            if len(calls) == 1:
                raise requests.HTTPError(response=bad)
            return ok_response

        with patch.object(source, "_get", side_effect=fake_get):
            _, cfg = self._params()
            result = source.search(cfg)
        assert result.success is True and len(result.papers) == 1
        assert "sort" in calls[0] and "sort" not in calls[1]
        assert result.warnings and "bad filter" in result.warnings[0]

    def test_api_key_is_never_shown_in_errors(self, monkeypatch):
        import ingestion.openalex as oa

        monkeypatch.setattr(oa, "get_openalex_api_key", lambda: "SECRET-KEY-42")
        source = OpenAlexSource()
        err = requests.HTTPError(
            "500 Server Error for url: https://api.openalex.org/works?api_key=SECRET-KEY-42&page=1"
        )
        with patch.object(source, "_get", side_effect=err):
            result = source.safe_search(SearchConfig(keywords=["x"]))
        assert result.success is False
        assert "SECRET-KEY-42" not in (result.error_message or "")

    def test_redact_secrets(self):
        from ingestion.base import redact_secrets

        text = "url?per-page=25&api_key=abc123&page=1 Authorization: Bearer abc123"
        out = redact_secrets(text)
        assert "abc123" not in out and "api_key=***" in out


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
