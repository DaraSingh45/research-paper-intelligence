"""
tests/test_llm.py

Tests llm/validator.py (JSON syntax, required fields, types, ranges),
llm/classifier.py, and llm/summarizer.py's retry behavior -- all without
calling a real Ollama server.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from llm.classifier import map_research_area_to_category  # noqa: E402
from llm.ollama_client import OllamaResponse  # noqa: E402
from llm.summarizer import generate_enrichment  # noqa: E402
from llm.validator import validate_enrichment  # noqa: E402

VALID_JSON = json.dumps(
    {
        "summary": "This paper introduces a new method for training language models efficiently.",
        "topics": ["language models", "efficient training"],
        "research_area": "Natural Language Processing",
        "confidence": 0.85,
    }
)


class TestLLMValidator:
    def test_valid_json_passes(self):
        result = validate_enrichment(VALID_JSON)
        assert result.valid
        assert result.data["confidence"] == 0.85

    def test_invalid_json_syntax_fails(self):
        result = validate_enrichment("{not valid json,,,")
        assert not result.valid
        assert any("json" in e.lower() for e in result.errors)

    def test_missing_required_field_fails(self):
        payload = json.loads(VALID_JSON)
        del payload["summary"]
        result = validate_enrichment(json.dumps(payload))
        assert not result.valid
        assert any("summary" in e.lower() for e in result.errors)

    def test_invalid_confidence_range_fails(self):
        payload = json.loads(VALID_JSON)
        payload["confidence"] = 1.5
        result = validate_enrichment(json.dumps(payload))
        assert not result.valid
        assert any("confidence" in e.lower() for e in result.errors)

    def test_confidence_wrong_type_fails(self):
        payload = json.loads(VALID_JSON)
        payload["confidence"] = "high"
        result = validate_enrichment(json.dumps(payload))
        assert not result.valid

    def test_topics_not_a_list_fails(self):
        payload = json.loads(VALID_JSON)
        payload["topics"] = "language models"
        result = validate_enrichment(json.dumps(payload))
        assert not result.valid

    def test_too_many_topics_fails(self):
        payload = json.loads(VALID_JSON)
        payload["topics"] = [f"topic{i}" for i in range(10)]
        result = validate_enrichment(json.dumps(payload))
        assert not result.valid

    def test_extracts_json_from_surrounding_text(self):
        wrapped = f"Sure! Here is the JSON:\n{VALID_JSON}\nHope that helps."
        result = validate_enrichment(wrapped)
        assert result.valid

    def test_empty_response_fails(self):
        result = validate_enrichment("")
        assert not result.valid


class TestClassifier:
    def test_matches_known_label(self):
        assert map_research_area_to_category("Machine Learning") == "machine_learning"

    def test_matches_via_keyword(self):
        assert map_research_area_to_category("deep learning research") == "machine_learning"

    def test_unrelated_text_may_return_none_or_fuzzy(self):
        result = map_research_area_to_category("underwater basket weaving")
        assert result is None or isinstance(result, str)

    def test_none_input_returns_none(self):
        assert map_research_area_to_category(None) is None


class TestSummarizerRetry:
    def test_retries_until_valid(self):
        client = MagicMock()
        client.generate.side_effect = [
            OllamaResponse(success=True, text="not json at all"),
            OllamaResponse(success=True, text=VALID_JSON),
        ]
        result = generate_enrichment(client, "Title", "Abstract", ["Machine Learning"], max_retries=2)
        assert result.validation.valid
        assert result.attempt_count == 2

    def test_gives_up_after_max_retries(self):
        client = MagicMock()
        client.generate.return_value = OllamaResponse(success=True, text="still not json")
        result = generate_enrichment(client, "Title", "Abstract", [], max_retries=1)
        assert not result.validation.valid
        assert result.attempt_count == 2  # first try + 1 retry

    def test_handles_ollama_failure_gracefully(self):
        client = MagicMock()
        client.generate.return_value = OllamaResponse(success=False, error="connection refused")
        result = generate_enrichment(client, "Title", "Abstract", [], max_retries=0)
        assert not result.validation.valid
