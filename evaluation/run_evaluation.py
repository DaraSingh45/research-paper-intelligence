"""
evaluation/run_evaluation.py

Runs the local LLM enrichment against evaluation/sample_papers.json and
compares against evaluation/expected_labels.json. This is a small,
manually reviewed sanity check -- NOT a rigorous benchmark. Results here
should never be used to claim the model is broadly "accurate" (Section 27
explicitly warns against that); they only show whether structured output
stays valid and roughly on-topic for a handful of well-understood papers.

Usage:
    python evaluation/run_evaluation.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from llm.classifier import map_research_area_to_category  # noqa: E402
from llm.ollama_client import OllamaClient  # noqa: E402
from llm.summarizer import generate_enrichment  # noqa: E402
from config.loader import get_category_labels  # noqa: E402

EVAL_DIR = Path(__file__).resolve().parent


def load_dataset():
    papers = json.loads((EVAL_DIR / "sample_papers.json").read_text())
    labels = {l["id"]: l for l in json.loads((EVAL_DIR / "expected_labels.json").read_text())}
    return papers, labels


def topic_overlap(actual: list, expected: list) -> float:
    if not expected:
        return 0.0
    actual_lower = {t.lower() for t in actual}
    expected_lower = {t.lower() for t in expected}
    overlap = sum(1 for e in expected_lower if any(e in a or a in e for a in actual_lower))
    return overlap / len(expected_lower)


def main() -> None:
    client = OllamaClient()
    available, message = client.is_available()
    if not available:
        print(f"Ollama is not available: {message}")
        print("Start Ollama and pull the configured model, then re-run this script.")
        return

    papers, labels = load_dataset()
    allowed_categories = list(get_category_labels().values())

    valid_count = 0
    overlap_scores = []

    print(f"Running evaluation on {len(papers)} sample papers using model '{client.model}'...\n")

    for paper in papers:
        expected = labels.get(paper["id"], {})
        result = generate_enrichment(client, paper["title"], paper["abstract"], allowed_categories, max_retries=1)

        status = "VALID" if result.validation.valid else "INVALID"
        if result.validation.valid:
            valid_count += 1
            data = result.validation.data
            overlap = topic_overlap(data.get("topics", []), expected.get("expected_topics", []))
            overlap_scores.append(overlap)
            mapped_area = map_research_area_to_category(data.get("research_area"))
            print(f"[{status}] {paper['title'][:60]}")
            print(f"    research_area: {data.get('research_area')} (mapped: {mapped_area})")
            print(f"    topics: {data.get('topics')}")
            print(f"    topic overlap with expected: {overlap:.0%}")
        else:
            print(f"[{status}] {paper['title'][:60]} -- errors: {result.validation.errors}")
        print()

    print("=" * 60)
    print(f"Structured output validity rate: {valid_count}/{len(papers)} ({100 * valid_count / len(papers):.0f}%)")
    if overlap_scores:
        avg_overlap = sum(overlap_scores) / len(overlap_scores)
        print(f"Average topic overlap with manually reviewed labels: {avg_overlap:.0%}")
    print(
        "\nNote: this is a small, manually reviewed sample. It indicates whether structured "
        "output stays valid and roughly on-topic -- it is not a claim of general model accuracy."
    )


if __name__ == "__main__":
    main()
