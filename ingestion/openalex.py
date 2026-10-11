"""
ingestion/openalex.py

Connector for the OpenAlex "works" API (https://docs.openalex.org).

As of February 2026, OpenAlex requires a free API key for reliable access
(https://openalex.org/settings/api -- free, takes under a minute). Without
a key you get a small daily test quota and may see errors once it's used
up. The old `mailto=` "polite pool" parameter was retired at the same
time, so it is no longer sent.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from config.loader import get_intensity_preset, load_categories
from database.models import NormalizedPaper, SearchConfig, SourceResult
from ingestion.base import PaperSource, RateLimitExhaustedError, RetryableHTTPError, redact_secrets

logger = logging.getLogger(__name__)

BASE_URL = "https://api.openalex.org/works"

_API_KEY_HINT = (
    "OpenAlex needs a free API key. Get one at https://openalex.org/settings/api "
    "and set OPENALEX_API_KEY=your_key in the .env file in the project folder."
)

_PLACEHOLDER_KEYS = {"", "your_api_key", "your-api-key", "your_key_here", "changeme", "change_me"}

# The project's .env file. In Docker the whole project folder is mounted at
# /app, so this is the same file you edit on your computer.
DOTENV_PATH = Path(__file__).resolve().parent.parent / ".env"

_dotenv_cache: Dict[str, Any] = {"mtime": None, "value": None}


def _clean_key(raw: Optional[str]) -> Optional[str]:
    value = (raw or "").strip().strip('"').strip("'").strip()
    if value.lower() in _PLACEHOLDER_KEYS:
        return None
    return value


def _read_dotenv_key() -> Optional[str]:
    """Reads OPENALEX_API_KEY straight from the project's .env file.
    Re-read whenever the file changes, so editing .env takes effect on the
    next search without restarting anything."""
    try:
        mtime = DOTENV_PATH.stat().st_mtime
    except OSError:
        return None
    if _dotenv_cache["mtime"] != mtime:
        value = None
        try:
            from dotenv import dotenv_values

            value = dotenv_values(DOTENV_PATH).get("OPENALEX_API_KEY")
        except Exception:  # noqa: BLE001 - fall back to a tiny manual parser
            try:
                for line in DOTENV_PATH.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line.startswith("OPENALEX_API_KEY") and "=" in line:
                        value = line.split("=", 1)[1].split(" #", 1)[0]
            except OSError:
                value = None
        _dotenv_cache.update(mtime=mtime, value=_clean_key(value))
    return _dotenv_cache["value"]


def get_openalex_api_key() -> Optional[str]:
    """Returns the OpenAlex API key, or None if none is configured.

    Order of precedence:
      1. OPENALEX_API_KEY in the project's .env file (read live).
      2. The OPENALEX_API_KEY environment variable.

    The .env file wins so that a stale value baked into a running Docker
    container can never silently override the key you just saved. Blank
    values and the placeholder from .env.example count as "not set"."""
    return _read_dotenv_key() or _clean_key(os.getenv("OPENALEX_API_KEY"))


def _describe_rate_limit(api_key: Optional[str], retry_after: Optional[int]) -> str:
    when = ""
    if retry_after:
        hours, minutes = divmod(int(retry_after) // 60, 60)
        when = f" It resets in about {hours}h {minutes}m (midnight UTC)."
    if not api_key:
        return (
            "OpenAlex's shared free quota for requests without an API key is used up." + when + " "
            + _API_KEY_HINT
        )
    return (
        "Your OpenAlex API key's daily budget is used up." + when
        + " Try a smaller search depth (Quick) after it resets."
    )


def _reconstruct_abstract(inverted_index: Optional[Dict[str, List[int]]]) -> Optional[str]:
    """OpenAlex returns abstracts as an inverted index (word -> positions)
    instead of plain text, for copyright reasons. Rebuild the plain text."""
    if not inverted_index:
        return None
    position_to_word: Dict[int, str] = {}
    for word, positions in inverted_index.items():
        for pos in positions:
            position_to_word[pos] = word
    if not position_to_word:
        return None
    max_pos = max(position_to_word.keys())
    return " ".join(position_to_word.get(i, "") for i in range(max_pos + 1)).strip()


class OpenAlexSource(PaperSource):
    name = "openalex"

    # ------------------------------------------------------------------
    # Query building (OpenAlex API syntax as documented in 2026:
    # https://help.openalex.org/api/searching/ and /api/filtering/)
    # ------------------------------------------------------------------
    @staticmethod
    def _clean_term(text: str) -> str:
        """Commas separate filters and double quotes delimit phrases, so
        neither may appear inside a single search term."""
        return " ".join(text.replace(",", " ").replace('"', " ").split())

    @classmethod
    def _or_phrases(cls, terms: List[str]) -> Optional[str]:
        """Lucene-style OR of quoted phrases: "a b" OR "c". Duplicates and
        empty terms are dropped; order is preserved."""
        seen: List[str] = []
        for term in terms:
            cleaned = cls._clean_term(term)
            if cleaned and cleaned.lower() not in (s.lower() for s in seen):
                seen.append(cleaned)
        if not seen:
            return None
        return " OR ".join(f'"{t}"' for t in seen)

    @classmethod
    def _keyword_query(cls, keywords: List[str]) -> Optional[str]:
        terms = [cls._clean_term(k) for k in keywords if cls._clean_term(k)]
        if not terms:
            return None
        if len(terms) == 1:
            return terms[0]  # unquoted: lets OpenAlex stem / match words anywhere
        return cls._or_phrases(terms)  # comma-separated keywords mean "any of these"

    @staticmethod
    def _category_terms(category_ids: List[str]) -> List[str]:
        cat_defs = {c["id"]: c for c in load_categories().get("categories", [])}
        terms: List[str] = []
        for cat_id in category_ids:
            cat = cat_defs.get(cat_id, {})
            terms.append(cat.get("label", ""))
            terms.extend(cat.get("keywords", []))
        return [t for t in terms if t and len(t.strip()) >= 3]

    def _build_filters(self, config: SearchConfig, include_categories: bool = True,
                       include_authors: bool = True) -> List[str]:
        filters: List[str] = []

        if config.start_date:
            filters.append(f"from_publication_date:{config.start_date.isoformat()}")
        if config.end_date:
            filters.append(f"to_publication_date:{config.end_date.isoformat()}")

        if include_authors and config.authors:
            authors = self._or_phrases(config.authors)
            if authors:
                filters.append(f"raw_author_name.search:{authors}")

        if include_categories and config.categories:
            phrases = self._or_phrases(self._category_terms(config.categories))
            if phrases:
                filters.append(f"title_abstract_keywords.search:{phrases}")

        return filters

    def _build_params(self, config: SearchConfig, per_page: int, *, sort: bool = True,
                      include_categories: bool = True, include_authors: bool = True,
                      include_title: bool = True) -> Dict[str, Any]:
        params: Dict[str, Any] = {"per-page": per_page}
        if sort:
            params["sort"] = "publication_date:desc"
        keyword_query = self._keyword_query(config.keywords or [])
        if keyword_query:
            params["search"] = keyword_query
        if include_title and config.title_filter and self._clean_term(config.title_filter):
            params["search.title"] = self._clean_term(config.title_filter)
        filters = self._build_filters(config, include_categories, include_authors)
        if filters:
            params["filter"] = ",".join(filters)
        return params

    def _query_variants(self, config: SearchConfig, per_page: int) -> List[tuple]:
        """The full query first, then progressively simpler fallbacks used
        only if OpenAlex rejects the request (HTTP 400). Each entry is
        (description of what was dropped, params)."""
        variants = [("", self._build_params(config, per_page))]
        variants.append(("newest-first sorting", self._build_params(config, per_page, sort=False)))
        if config.categories:
            variants.append(("the category filter", self._build_params(
                config, per_page, sort=False, include_categories=False)))
        if config.authors:
            variants.append(("the category and author filters", self._build_params(
                config, per_page, sort=False, include_categories=False, include_authors=False)))
        if config.title_filter and (config.keywords or config.categories or config.authors):
            variants.append(("the category, author and title filters", self._build_params(
                config, per_page, sort=False, include_categories=False, include_authors=False,
                include_title=False)))
        # Remove exact duplicates while keeping order.
        unique, seen = [], set()
        for desc, params in variants:
            key = tuple(sorted(params.items()))
            if key not in seen:
                seen.add(key)
                unique.append((desc, params))
        return unique

    @staticmethod
    def _error_detail(exc: requests.HTTPError) -> str:
        resp = exc.response
        if resp is None:
            return redact_secrets(str(exc))
        try:
            body = resp.json()
            detail = body.get("message") or body.get("error") or ""
        except Exception:  # noqa: BLE001
            detail = (getattr(resp, "text", "") or "")[:300]
        return redact_secrets(f"HTTP {resp.status_code}: {detail}".strip().rstrip(":"))

    def search(self, config: SearchConfig) -> SourceResult:
        preset = get_intensity_preset(config.intensity)
        max_results = preset["max_results_per_source"]
        per_page = min(preset["page_size"], 200)
        max_pages = preset["max_pages"]

        contact_email = os.getenv("CONTACT_EMAIL")
        api_key = get_openalex_api_key()
        headers: Dict[str, str] = {}
        auth_params: Dict[str, Any] = {}
        if api_key:
            # OpenAlex accepts the key as a query parameter or a Bearer token;
            # send both so either form is honoured. Error messages are always
            # passed through redact_secrets() so the key is never displayed.
            auth_params["api_key"] = api_key
            headers["Authorization"] = f"Bearer {api_key}"
        elif contact_email:
            # Retired Feb 2026, but harmless to include.
            auth_params["mailto"] = contact_email
        logger.info("openalex: searching %s an API key", "with" if api_key else "WITHOUT")

        warnings: List[str] = []
        papers: List[NormalizedPaper] = []
        variants = self._query_variants(config, per_page)
        variant_index = 0
        params = dict(variants[0][1], **auth_params)

        page = 1
        while page <= max_pages and len(papers) < max_results:
            params["page"] = page
            try:
                resp = self._get(BASE_URL, params=params, headers=headers or None)
            except RateLimitExhaustedError as exc:
                logger.warning("openalex: rate limit exhausted (has_key=%s)", bool(api_key))
                return SourceResult(
                    source=self.name, success=False,
                    error_message=_describe_rate_limit(api_key, exc.retry_after_seconds),
                    papers=papers[:max_results], warnings=warnings,
                )
            except RetryableHTTPError as exc:
                if exc.status_code == 429:
                    logger.warning("openalex: HTTP 429 after retries (has_key=%s)", bool(api_key))
                    return SourceResult(
                        source=self.name, success=False, error_message=_describe_rate_limit(api_key, None),
                        papers=papers[:max_results], warnings=warnings,
                    )
                raise
            except requests.HTTPError as exc:
                status = exc.response.status_code if exc.response is not None else None
                if status in (401, 403) or (status in (400, 409) and not api_key and not papers):
                    if not api_key:
                        return SourceResult(source=self.name, success=False,
                                            error_message=f"{_API_KEY_HINT} ({self._error_detail(exc)})")
                    return SourceResult(source=self.name, success=False, error_message=(
                        "OpenAlex rejected your API key. Check OPENALEX_API_KEY in .env "
                        f"({self._error_detail(exc)})."))
                if status == 400 and page == 1 and variant_index + 1 < len(variants):
                    variant_index += 1
                    dropped, simpler = variants[variant_index]
                    note = (f"OpenAlex rejected the query ({self._error_detail(exc)}); "
                            f"retried without {dropped}.")
                    logger.warning("openalex: %s", note)
                    warnings.append(note)
                    params = dict(simpler, **auth_params)
                    continue
                return SourceResult(source=self.name, success=False, papers=papers[:max_results],
                                    warnings=warnings,
                                    error_message=f"OpenAlex rejected the search ({self._error_detail(exc)}).")

            data = resp.json()
            results = data.get("results", [])
            if not results:
                break
            for work in results:
                try:
                    papers.append(self._parse_work(work))
                except Exception:  # noqa: BLE001 - skip malformed record, don't fail the batch
                    logger.exception("openalex: failed to parse one work, skipping")
            if len(results) < per_page:
                break
            page += 1

        return SourceResult(source=self.name, success=True, papers=papers[:max_results], warnings=warnings)

    def _parse_work(self, work: Dict[str, Any]) -> NormalizedPaper:
        openalex_id = (work.get("id") or "").rsplit("/", 1)[-1]
        title = (work.get("display_name") or work.get("title") or "").strip()
        abstract = _reconstruct_abstract(work.get("abstract_inverted_index"))

        authors = [
            (a.get("author", {}) or {}).get("display_name", "")
            for a in work.get("authorships", []) or []
        ]
        authors = [a for a in authors if a]

        pub_date = None
        pd = work.get("publication_date")
        if pd:
            try:
                from datetime import datetime as _dt

                pub_date = _dt.strptime(pd, "%Y-%m-%d").date()
            except ValueError:
                pub_date = None

        concepts = [c.get("display_name", "") for c in work.get("concepts", []) or [] if c.get("display_name")]

        doi = work.get("doi")
        if doi:
            doi = doi.replace("https://doi.org/", "").strip()

        primary_location = work.get("primary_location") or {}
        source_info = primary_location.get("source") or {}
        venue = source_info.get("display_name")
        publisher = source_info.get("host_organization_name")

        open_access = work.get("open_access") or {}
        pdf_url = primary_location.get("pdf_url") or open_access.get("oa_url")

        # Human-friendly "paper page": the publisher's landing page, else the
        # DOI. The OpenAlex ID URL is only a last resort, because openalex.org
        # pages load data in the visitor's browser without an API key and fail
        # once the network's shared free quota is used up.
        landing = primary_location.get("landing_page_url")
        paper_url = landing or (f"https://doi.org/{doi}" if doi else None) or work.get("id")

        return NormalizedPaper(
            external_id=openalex_id,
            title=title or "(untitled)",
            source=self.name,
            abstract=abstract,
            authors=authors,
            publication_date=pub_date,
            categories=concepts,
            doi=doi,
            url=paper_url,
            citation_count=work.get("cited_by_count", 0) or 0,
            venue=venue,
            publisher=publisher,
            pdf_url=pdf_url,
            language=work.get("language"),
            raw_source_data=work,
        )
