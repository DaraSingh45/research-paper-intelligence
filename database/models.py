"""
database/models.py

Plain dataclasses shared across the whole project (ingestion, processing,
database, LLM, app). Deliberately not a full ORM -- kept simple and
readable, per the project's "understandable for a student developer" goal.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class JobStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class Intensity(str, Enum):
    QUICK = "quick"
    STANDARD = "standard"
    DEEP = "deep"


@dataclass
class SearchConfig:
    """The user's Research-page configuration. Passed into every connector
    and into the processing/LLM stages so nothing needs to be re-derived."""

    keywords: List[str] = field(default_factory=list)
    title_filter: Optional[str] = None
    authors: List[str] = field(default_factory=list)
    categories: List[str] = field(default_factory=list)      # internal category ids
    custom_category: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    intensity: str = "standard"
    llm_enabled: bool = False
    llm_generate_summary: bool = True
    llm_generate_topics: bool = True
    llm_generate_research_area: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "keywords": self.keywords,
            "title_filter": self.title_filter,
            "authors": self.authors,
            "categories": self.categories,
            "custom_category": self.custom_category,
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "intensity": self.intensity,
            "llm_enabled": self.llm_enabled,
            "llm_generate_summary": self.llm_generate_summary,
            "llm_generate_topics": self.llm_generate_topics,
            "llm_generate_research_area": self.llm_generate_research_area,
        }

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> "SearchConfig":
        def _parse_date(v):
            if not v:
                return None
            if isinstance(v, date):
                return v
            return datetime.fromisoformat(v).date()

        return SearchConfig(
            keywords=data.get("keywords", []),
            title_filter=data.get("title_filter"),
            authors=data.get("authors", []),
            categories=data.get("categories", []),
            custom_category=data.get("custom_category"),
            start_date=_parse_date(data.get("start_date")),
            end_date=_parse_date(data.get("end_date")),
            intensity=data.get("intensity", "standard"),
            llm_enabled=data.get("llm_enabled", False),
            llm_generate_summary=data.get("llm_generate_summary", True),
            llm_generate_topics=data.get("llm_generate_topics", True),
            llm_generate_research_area=data.get("llm_generate_research_area", True),
        )


@dataclass
class NormalizedPaper:
    """The common schema every source connector must return (Section 15)."""

    external_id: str
    title: str
    source: str                                    # 'arxiv' | 'openalex' | 'semantic_scholar' | 'crossref'
    abstract: Optional[str] = None
    authors: List[str] = field(default_factory=list)
    publication_date: Optional[date] = None
    categories: List[str] = field(default_factory=list)   # source-native category strings
    doi: Optional[str] = None
    url: Optional[str] = None
    citation_count: int = 0

    # Optional fields
    journal: Optional[str] = None
    venue: Optional[str] = None
    publisher: Optional[str] = None
    pdf_url: Optional[str] = None
    language: Optional[str] = None

    # Preserved raw payload from the source API (never mutated downstream)
    raw_source_data: Dict[str, Any] = field(default_factory=dict)

    # Populated during processing (not by the connector)
    title_normalized: Optional[str] = None
    internal_categories: List[str] = field(default_factory=list)  # mapped internal category ids


@dataclass
class SourceResult:
    """Returned by every PaperSource.search() call."""

    source: str
    success: bool
    papers: List[NormalizedPaper] = field(default_factory=list)
    error_message: Optional[str] = None
    requests_made: int = 0
    elapsed_seconds: float = 0.0


@dataclass
class LLMEnrichmentResult:
    paper_id: str
    model_name: str
    summary: Optional[str] = None
    topics: List[str] = field(default_factory=list)
    research_area: Optional[str] = None
    confidence: Optional[float] = None
    status: str = "PENDING"          # PENDING | VALID | FAILED_REVIEW
    raw_response: Optional[str] = None
    validation_errors: List[str] = field(default_factory=list)
    attempt_count: int = 0


def new_job_id() -> str:
    """Generates a human-readable job id, e.g. RP-20260914-0f3a."""
    return f"RP-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6]}"
