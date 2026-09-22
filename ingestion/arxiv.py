"""
ingestion/arxiv.py

Connector for the arXiv API (https://arxiv.org/help/api).
Free, public, no API key required. Returns an Atom XML feed.
"""
from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import List, Optional

from config.loader import get_intensity_preset
from database.models import NormalizedPaper, SearchConfig, SourceResult
from ingestion.base import PaperSource

logger = logging.getLogger(__name__)

ATOM_NS = "{http://www.w3.org/2005/Atom}"
ARXIV_NS = "{http://arxiv.org/schemas/atom}"
BASE_URL = "http://export.arxiv.org/api/query"


class ArxivSource(PaperSource):
    name = "arxiv"

    def _build_search_query(self, config: SearchConfig) -> str:
        clauses: List[str] = []

        if config.keywords:
            kw_clause = " AND ".join(f'all:"{kw}"' for kw in config.keywords)
            clauses.append(f"({kw_clause})")

        if config.title_filter:
            clauses.append(f'ti:"{config.title_filter}"')

        if config.authors:
            author_clause = " AND ".join(f'au:"{a}"' for a in config.authors)
            clauses.append(f"({author_clause})")

        if config.categories:
            from config.loader import load_categories

            cat_codes: List[str] = []
            cat_defs = {c["id"]: c for c in load_categories().get("categories", [])}
            for cat_id in config.categories:
                cat_codes.extend(cat_defs.get(cat_id, {}).get("arxiv_codes", []))
            if cat_codes:
                cat_clause = " OR ".join(f"cat:{code}" for code in cat_codes)
                clauses.append(f"({cat_clause})")

        if config.start_date or config.end_date:
            start = config.start_date.strftime("%Y%m%d") if config.start_date else "19910101"
            end = config.end_date.strftime("%Y%m%d") if config.end_date else datetime.now().strftime("%Y%m%d")
            clauses.append(f"submittedDate:[{start}0000 TO {end}2359]")

        return " AND ".join(clauses) if clauses else "all:research"

    def search(self, config: SearchConfig) -> SourceResult:
        preset = get_intensity_preset(config.intensity)
        max_results = preset["max_results_per_source"]
        page_size = min(preset["page_size"], 100)  # arXiv caps at 100 per request
        max_pages = preset["max_pages"]

        query = self._build_search_query(config)
        papers: List[NormalizedPaper] = []
        start_index = 0

        for _page in range(max_pages):
            if len(papers) >= max_results:
                break
            params = {
                "search_query": query,
                "start": start_index,
                "max_results": min(page_size, max_results - len(papers)),
                "sortBy": "submittedDate",
                "sortOrder": "descending",
            }
            resp = self._get(BASE_URL, params=params)
            entries = self._parse_feed(resp.text)
            if not entries:
                break
            papers.extend(entries)
            start_index += page_size
            if len(entries) < page_size:
                break  # no more results available

        return SourceResult(source=self.name, success=True, papers=papers[:max_results])

    def _parse_feed(self, xml_text: str) -> List[NormalizedPaper]:
        results: List[NormalizedPaper] = []
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            logger.warning("arxiv: could not parse response as XML")
            return results

        for entry in root.findall(f"{ATOM_NS}entry"):
            try:
                results.append(self._parse_entry(entry))
            except Exception:  # noqa: BLE001 - skip malformed entries, don't fail the batch
                logger.exception("arxiv: failed to parse one entry, skipping")
        return results

    def _parse_entry(self, entry: ET.Element) -> NormalizedPaper:
        raw_id = (entry.findtext(f"{ATOM_NS}id") or "").strip()
        arxiv_id = raw_id.rsplit("/abs/", 1)[-1] if "/abs/" in raw_id else raw_id
        title = " ".join((entry.findtext(f"{ATOM_NS}title") or "").split())
        summary = " ".join((entry.findtext(f"{ATOM_NS}summary") or "").split())

        authors = [
            (a.findtext(f"{ATOM_NS}name") or "").strip()
            for a in entry.findall(f"{ATOM_NS}author")
        ]
        authors = [a for a in authors if a]

        published = entry.findtext(f"{ATOM_NS}published")
        pub_date = None
        if published:
            try:
                pub_date = datetime.strptime(published[:10], "%Y-%m-%d").date()
            except ValueError:
                pub_date = None

        categories = [c.get("term", "") for c in entry.findall(f"{ATOM_NS}category") if c.get("term")]

        doi = entry.findtext(f"{ARXIV_NS}doi")
        journal_ref = entry.findtext(f"{ARXIV_NS}journal_ref")

        pdf_url: Optional[str] = None
        abs_url: Optional[str] = None
        for link in entry.findall(f"{ATOM_NS}link"):
            if link.get("title") == "pdf":
                pdf_url = link.get("href")
            if link.get("rel") == "alternate":
                abs_url = link.get("href")

        citation_count_elem = entry.findtext(f"{ARXIV_NS}comment")  # arXiv has no citation counts
        raw_data = {
            "id": raw_id,
            "title": title,
            "summary": summary,
            "authors": authors,
            "published": published,
            "categories": categories,
            "doi": doi,
            "journal_ref": journal_ref,
            "comment": citation_count_elem,
        }

        return NormalizedPaper(
            external_id=arxiv_id,
            title=title or "(untitled)",
            source=self.name,
            abstract=summary or None,
            authors=authors,
            publication_date=pub_date,
            categories=categories,
            doi=doi.strip() if doi else None,
            url=abs_url or raw_id,
            citation_count=0,  # arXiv does not provide citation counts
            journal=journal_ref,
            pdf_url=pdf_url,
            raw_source_data=raw_data,
        )
