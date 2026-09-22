"""
ingestion/semantic_scholar.py

Connector for the Semantic Scholar Academic Graph API
(https://api.semanticscholar.org/api-docs/graph). Free, public, no API
key strictly required -- but unauthenticated requests share one global
pool with every other anonymous caller worldwide, so 429 (rate limited)
responses are common during busy periods even at a conservative request
rate. A free API key (https://www.semanticscholar.org/product/api#Get-Started)
gives a dedicated (if modest) rate instead; set SEMANTIC_SCHOLAR_API_KEY
in .env to use one.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List

import requests

from config.loader import get_intensity_preset, load_categories
from database.models import NormalizedPaper, SearchConfig, SourceResult
from ingestion.base import PaperSource, RetryableHTTPError

logger = logging.getLogger(__name__)

BASE_URL = "https://api.semanticscholar.org/graph/v1/paper/search"

FIELDS = (
    "title,abstract,authors,year,publicationDate,externalIds,venue,"
    "publicationVenue,citationCount,openAccessPdf,fieldsOfStudy,url,journal"
)

_RATE_LIMIT_HINT = (
    "Semantic Scholar's shared, unauthenticated pool is rate-limiting requests "
    "right now. This is common during busy periods and isn't specific to your "
    "setup. A free API key gives you a dedicated rate instead -- get one at "
    "https://www.semanticscholar.org/product/api#Get-Started and set "
    "SEMANTIC_SCHOLAR_API_KEY in your .env, then restart the app. Otherwise, "
    "just try again shortly; the pipeline continues with the other sources "
    "in the meantime."
)


class SemanticScholarSource(PaperSource):
    name = "semantic_scholar"

    def _build_query(self, config: SearchConfig) -> str:
        parts: List[str] = list(config.keywords)
        if config.title_filter:
            parts.append(config.title_filter)
        if config.authors:
            parts.extend(config.authors)
        return " ".join(parts) if parts else "research"

    def _fields_of_study(self, config: SearchConfig) -> List[str]:
        if not config.categories:
            return []
        cat_defs = {c["id"]: c for c in load_categories().get("categories", [])}
        fields: List[str] = []
        for cat_id in config.categories:
            fields.extend(cat_defs.get(cat_id, {}).get("semantic_scholar_fields", []))
        return sorted(set(fields))

    def search(self, config: SearchConfig) -> SourceResult:
        preset = get_intensity_preset(config.intensity)
        max_results = preset["max_results_per_source"]
        limit = min(preset["page_size"], 100)
        max_pages = preset["max_pages"]

        params: Dict[str, Any] = {
            "query": self._build_query(config),
            "fields": FIELDS,
            "limit": limit,
        }
        if config.start_date or config.end_date:
            start_year = config.start_date.year if config.start_date else 1900
            end_year = config.end_date.year if config.end_date else 2100
            params["year"] = f"{start_year}-{end_year}"

        fields_of_study = self._fields_of_study(config)
        if fields_of_study:
            params["fieldsOfStudy"] = ",".join(fields_of_study)

        api_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY")
        headers = {"x-api-key": api_key} if api_key else {}

        papers: List[NormalizedPaper] = []
        offset = 0
        for _page in range(max_pages):
            if len(papers) >= max_results:
                break
            params["offset"] = offset
            try:
                resp = self._get(BASE_URL, params=params, headers=headers)
            except RetryableHTTPError as exc:
                if "429" in str(exc):
                    raise RuntimeError(_RATE_LIMIT_HINT) from exc
                raise
            except requests.HTTPError as exc:
                status = exc.response.status_code if exc.response is not None else None
                if status == 429:
                    raise RuntimeError(_RATE_LIMIT_HINT) from exc
                raise
            data = resp.json()
            results = data.get("data", [])
            if not results:
                break
            for item in results:
                try:
                    papers.append(self._parse_paper(item))
                except Exception:  # noqa: BLE001
                    logger.exception("semantic_scholar: failed to parse one paper, skipping")
            offset += limit
            if len(results) < limit:
                break

        return SourceResult(source=self.name, success=True, papers=papers[:max_results])

    def _parse_paper(self, item: Dict[str, Any]) -> NormalizedPaper:
        external_ids = item.get("externalIds") or {}
        paper_id = item.get("paperId") or external_ids.get("DOI") or item.get("url", "")
        title = (item.get("title") or "").strip()

        authors = [a.get("name", "") for a in item.get("authors", []) or []]
        authors = [a for a in authors if a]

        pub_date = None
        pd = item.get("publicationDate")
        if pd:
            try:
                from datetime import datetime as _dt

                pub_date = _dt.strptime(pd, "%Y-%m-%d").date()
            except ValueError:
                year = item.get("year")
                if year:
                    from datetime import date as _date

                    pub_date = _date(int(year), 1, 1)

        journal = (item.get("journal") or {}).get("name")
        pdf_info = item.get("openAccessPdf") or {}

        return NormalizedPaper(
            external_id=str(paper_id),
            title=title or "(untitled)",
            source=self.name,
            abstract=item.get("abstract"),
            authors=authors,
            publication_date=pub_date,
            categories=item.get("fieldsOfStudy") or [],
            doi=external_ids.get("DOI"),
            url=item.get("url"),
            citation_count=item.get("citationCount", 0) or 0,
            journal=journal,
            venue=item.get("venue"),
            pdf_url=pdf_info.get("url"),
            raw_source_data=item,
        )
