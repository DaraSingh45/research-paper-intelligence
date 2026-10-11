"""
scripts/check_openalex.py

Quick diagnostic: sends one real search to OpenAlex exactly the way the app
does, and prints what came back. Your API key is never printed.

Run it inside the app container (while the app is running):

    docker compose exec app python scripts/check_openalex.py
    docker compose exec app python scripts/check_openalex.py "graph neural networks"
    docker compose exec app python scripts/check_openalex.py "llm" --title "agents" --category machine_learning --days 365

Exit code is 0 when OpenAlex accepted the query, 1 otherwise.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests  # noqa: E402

from database.models import SearchConfig  # noqa: E402
from ingestion.base import redact_secrets  # noqa: E402
from ingestion.openalex import BASE_URL, OpenAlexSource, get_openalex_api_key  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Send one test search to OpenAlex.")
    parser.add_argument("keywords", nargs="?", default="machine learning",
                        help="comma-separated keywords (default: machine learning)")
    parser.add_argument("--title", default=None, help="title must contain this")
    parser.add_argument("--author", default=None, help="author name")
    parser.add_argument("--category", action="append", default=[],
                        help="category id from config/categories.yaml (repeatable)")
    parser.add_argument("--days", type=int, default=365, help="look back this many days (default 365)")
    args = parser.parse_args()

    key = get_openalex_api_key()
    print(f"API key: {'found (ends with ...' + key[-4:] + ')' if key else 'NOT FOUND - check OPENALEX_API_KEY in .env'}")

    cfg = SearchConfig(
        keywords=[k.strip() for k in args.keywords.split(",") if k.strip()],
        title_filter=args.title,
        authors=[args.author] if args.author else [],
        categories=args.category,
        start_date=date.today() - timedelta(days=args.days),
        end_date=date.today(),
        intensity="quick",
    )
    params = OpenAlexSource()._build_params(cfg, per_page=5)
    print("Query parameters sent:")
    for k, v in params.items():
        print(f"  {k} = {v}")

    send = dict(params)
    headers = {}
    if key:
        send["api_key"] = key
        headers["Authorization"] = f"Bearer {key}"

    try:
        resp = requests.get(BASE_URL, params=send, headers=headers, timeout=30)
    except requests.RequestException as exc:
        print(f"\nFAILED: could not reach OpenAlex: {redact_secrets(exc)}")
        return 1

    print(f"\nHTTP status: {resp.status_code}")
    try:
        body = resp.json()
    except ValueError:
        print(redact_secrets(resp.text[:500]))
        return 1

    if resp.status_code != 200:
        print("FAILED. OpenAlex said:")
        print("  error:  ", redact_secrets(body.get("error", "")))
        print("  message:", redact_secrets(body.get("message", "")))
        return 1

    meta = body.get("meta", {})
    print(f"OK - OpenAlex accepted the query. Matching works: {meta.get('count', '?'):,}")
    for i, work in enumerate(body.get("results", [])[:5], 1):
        print(f"  {i}. [{work.get('publication_date', '?')}] {work.get('display_name', '(untitled)')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
