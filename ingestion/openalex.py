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
from typing import Any, Dict, List, Optional

import requests

from config.loader import get_intensity_preset, load_categories
from database.models import NormalizedPaper, SearchConfig, SourceResult
from ingestion.base import PaperSource

logger = logging.getLogger(__name__)

BASE_URL = "https://api.openalex.org/works"

_API_KEY_HINT = (
    "OpenAlex requires a free API key for reliable access (since Feb 2026). "
    "Get one at https://openalex.org/settings/api and set OPENALEX_API_KEY in "
    "your .env, then restart the app."
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

    def _build_filters(self, config: SearchConfig) -> List[str]:
        filters: List[str] = []

        if config.start_date:
            filters.append(f"from_publication_date:{config.start_date.isoformat()}")
        if config.end_date:
            filters.append(f"to_publication_date:{config.end_date.isoformat()}")

        if config.title_filter:
            safe = config.title_filter.replace(",", " ")
            filters.append(f"title.search:{safe}")

        if config.authors:
            joined = "|".join(a.replace(",", " ") for a in config.authors)
            filters.append(f"authorships.author.display_name.search:{joined}")

        if config.categories:
            cat_defs = {c["id"]: c for c in load_categories().get("categories", [])}
            concept_names: List[str] = []
            for cat_id in config.categories:
                concept_names.extend(cat_defs.get(cat_id, {}).get("openalex_concepts", []))
            if concept_names:
                joined = "|".join(n.replace(",", " ") for n in concept_names)
                filters.append(f"concepts.display_name.search:{joined}")

        return filters

    def search(self, config: SearchConfig) -> SourceResult:
        preset = get_intensity_preset(config.intensity)
        max_results = preset["max_results_per_source"]
        per_page = min(preset["page_size"], 200)
        max_pages = preset["max_pages"]

        params: Dict[str, Any] = {"per-page": per_page, "sort": "publication_date:desc"}
        if config.keywords:
            params["search"] = " ".join(config.keywords)
        filters = self._build_filters(config)
        if filters:
            params["filter"] = ",".join(filters)

        contact_email = os.getenv("CONTACT_EMAIL")
        api_key = os.getenv("OPENALEX_API_KEY")
        if api_key:
            params["api_key"] = api_key
        elif contact_email:
            # Retired Feb 2026, but harmless to include for older API versions
            # / in case OpenAlex reinstates a lightweight identification path.
            params["mailto"] = contact_email

        papers: List[NormalizedPaper] = []
        for page in range(1, max_pages + 1):
            if len(papers) >= max_results:
                break
            params["page"] = page
            try:
                resp = self._get(BASE_URL, params=params)
            except requests.HTTPError as exc:
                status = exc.response.status_code if exc.response is not None else None
                if status in (400, 401, 403, 409) and not api_key:
                    raise RuntimeError(f"{_API_KEY_HINT} (HTTP {status})") from exc
                raise
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

        return SourceResult(source=self.name, success=True, papers=papers[:max_results])

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
        pdf_url = open_access.get("oa_url") or primary_location.get("pdf_url")

        return NormalizedPaper(
            external_id=openalex_id,
            title=title or "(untitled)",
            source=self.name,
            abstract=abstract,
            authors=authors,
            publication_date=pub_date,
            categories=concepts,
            doi=doi,
            url=work.get("id"),
            citation_count=work.get("cited_by_count", 0) or 0,
            venue=venue,
            publisher=publisher,
            pdf_url=pdf_url,
            language=work.get("language"),
            raw_source_data=work,
        )
