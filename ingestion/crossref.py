"""
ingestion/crossref.py

Connector for the Crossref REST API (https://api.crossref.org).
Free, public, no API key required. Crossref indexes DOI metadata across
publishers -- it does not offer field-of-study/category filtering, so
category selection is not applied here (categories still get mapped
during processing/normalizer.py where possible, using container title
and subject data if Crossref happens to return any).
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, List, Optional

from config.loader import get_intensity_preset
from database.models import NormalizedPaper, SearchConfig, SourceResult
from ingestion.base import PaperSource

logger = logging.getLogger(__name__)

BASE_URL = "https://api.crossref.org/works"

_TAG_RE = re.compile(r"<[^>]+>")


def _strip_tags(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    return _TAG_RE.sub(" ", text).strip() or None


def _date_from_parts(date_parts_obj: Optional[Dict[str, Any]]):
    if not date_parts_obj:
        return None
    parts = date_parts_obj.get("date-parts")
    if not parts or not parts[0]:
        return None
    p = parts[0]
    year = p[0] if len(p) > 0 else None
    month = p[1] if len(p) > 1 else 1
    day = p[2] if len(p) > 2 else 1
    if not year:
        return None
    try:
        from datetime import date as _date

        return _date(int(year), int(month or 1), int(day or 1))
    except ValueError:
        return None


class CrossrefSource(PaperSource):
    name = "crossref"

    def search(self, config: SearchConfig) -> SourceResult:
        preset = get_intensity_preset(config.intensity)
        max_results = preset["max_results_per_source"]
        rows = min(preset["page_size"], 100)
        max_pages = preset["max_pages"]

        params: Dict[str, Any] = {"rows": rows, "sort": "published", "order": "desc"}
        if config.keywords:
            params["query.bibliographic"] = " ".join(config.keywords)
        if config.title_filter:
            params["query.title"] = config.title_filter
        if config.authors:
            params["query.author"] = " ".join(config.authors)

        filters: List[str] = []
        if config.start_date:
            filters.append(f"from-pub-date:{config.start_date.isoformat()}")
        if config.end_date:
            filters.append(f"until-pub-date:{config.end_date.isoformat()}")
        if filters:
            params["filter"] = ",".join(filters)

        contact_email = os.getenv("CONTACT_EMAIL")
        headers = {"User-Agent": f"research-paper-intelligence (mailto:{contact_email})"} if contact_email else {}

        papers: List[NormalizedPaper] = []
        offset = 0
        for _page in range(max_pages):
            if len(papers) >= max_results:
                break
            params["offset"] = offset
            resp = self._get(BASE_URL, params=params, headers=headers)
            data = resp.json()
            items = (data.get("message") or {}).get("items", [])
            if not items:
                break
            for item in items:
                try:
                    papers.append(self._parse_item(item))
                except Exception:  # noqa: BLE001
                    logger.exception("crossref: failed to parse one item, skipping")
            offset += rows
            if len(items) < rows:
                break

        return SourceResult(source=self.name, success=True, papers=papers[:max_results])

    def _parse_item(self, item: Dict[str, Any]) -> NormalizedPaper:
        doi = item.get("DOI")
        title_list = item.get("title") or []
        title = (title_list[0] if title_list else "").strip()

        authors = []
        for a in item.get("author", []) or []:
            given = a.get("given", "")
            family = a.get("family", "")
            full = f"{given} {family}".strip()
            if full:
                authors.append(full)

        pub_date = (
            _date_from_parts(item.get("published"))
            or _date_from_parts(item.get("published-print"))
            or _date_from_parts(item.get("published-online"))
        )

        container = item.get("container-title") or []
        journal = container[0] if container else None

        pdf_url = None
        for link in item.get("link", []) or []:
            if link.get("content-type") == "application/pdf":
                pdf_url = link.get("URL")
                break

        return NormalizedPaper(
            external_id=doi or item.get("URL", ""),
            title=title or "(untitled)",
            source=self.name,
            abstract=_strip_tags(item.get("abstract")),
            authors=authors,
            publication_date=pub_date,
            categories=item.get("subject", []) or [],
            doi=doi,
            url=item.get("URL"),
            citation_count=item.get("is-referenced-by-count", 0) or 0,
            journal=journal,
            publisher=item.get("publisher"),
            pdf_url=pdf_url,
            language=item.get("language"),
            raw_source_data=item,
        )
