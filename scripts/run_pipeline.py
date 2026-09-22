"""
scripts/run_pipeline.py

Thin CLI wrapper around pipeline/orchestrator.run_full_pipeline(). The
Streamlit app calls the orchestrator directly (in a background thread);
this script exists so the same pipeline can be triggered from a terminal,
a cron job, or for debugging without opening the UI.

Usage examples:
    python scripts/run_pipeline.py --keywords "large language models" --intensity quick
    python scripts/run_pipeline.py --keywords "robotics" "reinforcement learning" \\
        --categories robotics machine_learning --intensity standard --llm
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.orchestrator import run_full_pipeline  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a research paper search pipeline from the CLI.")
    parser.add_argument("--keywords", nargs="*", default=[], help="Search keywords")
    parser.add_argument("--title", dest="title_filter", default=None, help="Title contains filter")
    parser.add_argument("--authors", nargs="*", default=[], help="Author name filters")
    parser.add_argument("--categories", nargs="*", default=[], help="Internal category ids")
    parser.add_argument("--start-date", default=None, help="YYYY-MM-DD")
    parser.add_argument("--end-date", default=None, help="YYYY-MM-DD")
    parser.add_argument("--intensity", choices=["quick", "standard", "deep"], default="standard")
    parser.add_argument("--llm", action="store_true", help="Enable local LLM enrichment")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    config = {
        "keywords": args.keywords,
        "title_filter": args.title_filter,
        "authors": args.authors,
        "categories": args.categories,
        "start_date": datetime.strptime(args.start_date, "%Y-%m-%d").date() if args.start_date else None,
        "end_date": datetime.strptime(args.end_date, "%Y-%m-%d").date() if args.end_date else None,
        "intensity": args.intensity,
        "llm_enabled": args.llm,
    }

    logger.info("Starting pipeline with config: %s", config)
    job_id = run_full_pipeline(config, triggered_by="cli")
    logger.info("Pipeline finished. Job ID: %s", job_id)


if __name__ == "__main__":
    main()
