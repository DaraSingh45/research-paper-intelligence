"""
llm/validator.py

Validates raw LLM output against the strict JSON schema from Section 25.
Never assumes the LLM is correct (Section 26): checks JSON syntax,
required fields, data types, summary length, topic count and confidence
range before anything is trusted.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

MAX_SUMMARY_WORDS = 120
MIN_SUMMARY_WORDS = 3
MAX_TOPICS = 5
MIN_TOPICS = 1


@dataclass
class LLMValidationResult:
    valid: bool
    data: Optional[Dict[str, Any]] = None
    errors: List[str] = field(default_factory=list)


def _extract_json_object(text: str) -> Optional[str]:
    """Some local models wrap JSON in markdown fences or add stray text
    despite instructions. Try to isolate the first {...} block."""
    text = text.strip()
    if text.startswith("{") and text.endswith("}"):
        return text
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return None


def validate_enrichment(raw_text: str) -> LLMValidationResult:
    errors: List[str] = []

    candidate = _extract_json_object(raw_text or "")
    if candidate is None:
        return LLMValidationResult(valid=False, errors=["Response did not contain a JSON object."])

    try:
        data = json.loads(candidate)
    except json.JSONDecodeError as exc:
        return LLMValidationResult(valid=False, errors=[f"Invalid JSON syntax: {exc}"])

    if not isinstance(data, dict):
        return LLMValidationResult(valid=False, errors=["Top-level JSON value must be an object."])

    # --- summary ---
    summary = data.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        errors.append("Missing or empty 'summary' field.")
    else:
        word_count = len(summary.split())
        if word_count < MIN_SUMMARY_WORDS:
            errors.append("Summary is too short to be meaningful.")
        elif word_count > MAX_SUMMARY_WORDS:
            errors.append(f"Summary exceeds {MAX_SUMMARY_WORDS} words.")

    # --- topics ---
    topics = data.get("topics")
    if not isinstance(topics, list) or not all(isinstance(t, str) for t in topics):
        errors.append("'topics' must be a list of strings.")
    else:
        topics = [t.strip() for t in topics if t and t.strip()]
        if not (MIN_TOPICS <= len(topics) <= MAX_TOPICS):
            errors.append(f"'topics' must contain between {MIN_TOPICS} and {MAX_TOPICS} items.")
        data["topics"] = topics

    # --- research_area ---
    research_area = data.get("research_area")
    if not isinstance(research_area, str) or not research_area.strip():
        errors.append("Missing or empty 'research_area' field.")

    # --- confidence ---
    confidence = data.get("confidence")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        errors.append("'confidence' must be a number.")
    elif not (0.0 <= float(confidence) <= 1.0):
        errors.append("'confidence' must be between 0.0 and 1.0.")
    else:
        data["confidence"] = float(confidence)

    return LLMValidationResult(valid=not errors, data=data if not errors else None, errors=errors)
