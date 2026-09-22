"""
llm/prompts.py

Builds the strict-JSON enrichment prompt (Section 25). Kept in its own
file so prompt wording can be tuned/evaluated (see evaluation/) without
touching the calling code in llm/summarizer.py.
"""
from __future__ import annotations

from typing import List

SYSTEM_PROMPT = (
    "You are a research paper analysis assistant. You ONLY respond with a single, "
    "strictly valid JSON object and nothing else -- no markdown, no explanations, "
    "no text before or after the JSON. If you are unsure about a field, make your "
    "best reasonable estimate rather than leaving it out."
)

RESPONSE_SCHEMA_DESCRIPTION = """
Respond with EXACTLY this JSON shape and nothing else:
{
  "summary": "<a concise 2-4 sentence summary of the paper in plain English>",
  "topics": ["<topic1>", "<topic2>", "<topic3 optional>"],
  "research_area": "<one short research area label>",
  "confidence": <a number between 0.0 and 1.0 indicating your confidence>
}
""".strip()


def build_enrichment_prompt(title: str, abstract: str, allowed_categories: List[str]) -> str:
    abstract_text = abstract.strip() if abstract else "(no abstract available -- infer from the title only)"
    categories_hint = ", ".join(allowed_categories) if allowed_categories else "(no restriction)"

    return f"""
Paper title:
{title}

Paper abstract:
{abstract_text}

Task:
1. Write a concise, accurate summary of what this paper is about (2-4 sentences).
2. List 1-5 topic labels that describe this paper's specific subject matter.
3. Assign ONE overall research_area. Prefer one of these labels if it reasonably
   fits: {categories_hint}. If none fit well, use your own short label.
4. Give a confidence score between 0.0 and 1.0 reflecting how confident you are
   in this classification given the information available.

{RESPONSE_SCHEMA_DESCRIPTION}
""".strip()
