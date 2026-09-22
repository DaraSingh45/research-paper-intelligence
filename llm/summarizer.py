"""
llm/summarizer.py

Generates the combined summary/topics/research_area/confidence enrichment
for a single paper (Section 25 asks for one JSON object covering all of
these, produced in a single call -- this keeps LLM usage efficient, which
matters on constrained hardware).

Retries on validation failure (Section 26): if the LLM's output fails
validation, the request is retried up to `max_retries` times before the
paper is marked FAILED_REVIEW.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional

from llm.ollama_client import OllamaClient
from llm.prompts import SYSTEM_PROMPT, build_enrichment_prompt
from llm.validator import LLMValidationResult, validate_enrichment

logger = logging.getLogger(__name__)


@dataclass
class EnrichmentAttemptResult:
    validation: LLMValidationResult
    raw_response: str
    attempt_count: int


def generate_enrichment(
    client: OllamaClient,
    title: str,
    abstract: Optional[str],
    allowed_categories: List[str],
    max_retries: int = 2,
) -> EnrichmentAttemptResult:
    prompt = build_enrichment_prompt(title, abstract or "", allowed_categories)

    last_validation = LLMValidationResult(valid=False, errors=["LLM was not called."])
    last_raw = ""
    attempts = 0

    for attempt in range(1, max_retries + 2):  # first try + retries
        attempts = attempt
        response = client.generate(prompt, system=SYSTEM_PROMPT)
        if not response.success:
            last_validation = LLMValidationResult(valid=False, errors=[response.error or "Unknown Ollama error"])
            last_raw = ""
            continue

        last_raw = response.text
        last_validation = validate_enrichment(response.text)
        if last_validation.valid:
            break
        logger.info(
            "LLM enrichment attempt %s/%s failed validation for '%s...': %s",
            attempt,
            max_retries + 1,
            title[:60],
            last_validation.errors,
        )

    return EnrichmentAttemptResult(validation=last_validation, raw_response=last_raw, attempt_count=attempts)
