"""Ingestion package: OpenAlex is the only active paper source.

Papers are searched exclusively through the OpenAlex "works" API
(https://docs.openalex.org). The older connectors (arXiv, Semantic Scholar,
Crossref) are still in this folder so existing tests and historical data
keep working, but they are NOT registered below and are therefore never
called by the pipeline.

To re-enable another source in the future, import its class here and add
one line to SOURCE_REGISTRY.
"""
from typing import List

from ingestion.base import PaperSource
from ingestion.openalex import OpenAlexSource

# Developer-controlled registry of active sources. OpenAlex only.
SOURCE_REGISTRY = {
    "openalex": OpenAlexSource,
}


def get_all_sources() -> List[PaperSource]:
    """Instantiate every registered (active) source connector."""
    return [cls() for cls in SOURCE_REGISTRY.values()]
