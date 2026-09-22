"""Ingestion package: fixed source connectors (arXiv, OpenAlex, Semantic Scholar, Crossref).

Sources are intentionally fixed and NOT user-configurable in the UI (per
project constraints). A developer wanting to add a 5th connector in the
future only needs to: implement a new ingestion/<name>.py subclassing
PaperSource, then add one line to SOURCE_REGISTRY below.
"""
from typing import List

from ingestion.arxiv import ArxivSource
from ingestion.base import PaperSource
from ingestion.crossref import CrossrefSource
from ingestion.openalex import OpenAlexSource
from ingestion.semantic_scholar import SemanticScholarSource

# Developer-controlled registry of supported sources (Section 14).
SOURCE_REGISTRY = {
    "arxiv": ArxivSource,
    "openalex": OpenAlexSource,
    "semantic_scholar": SemanticScholarSource,
    "crossref": CrossrefSource,
}


def get_all_sources() -> List[PaperSource]:
    """Instantiate every registered source connector."""
    return [cls() for cls in SOURCE_REGISTRY.values()]
