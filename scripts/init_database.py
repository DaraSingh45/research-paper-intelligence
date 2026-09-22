"""
scripts/init_database.py

Applies database/schema.sql to PostgreSQL and syncs config/categories.yaml
into the categories table. Safe to run multiple times (everything uses
IF NOT EXISTS / ON CONFLICT).

Usage:
    python scripts/init_database.py
"""
from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database.connection import check_connection, get_connection  # noqa: E402
from database.repositories import CategoryRepository  # noqa: E402
from config.loader import load_categories  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

SCHEMA_PATH = Path(__file__).resolve().parent.parent / "database" / "schema.sql"


def wait_for_postgres(max_attempts: int = 20, delay_seconds: float = 2.0) -> None:
    for attempt in range(1, max_attempts + 1):
        ok, message = check_connection()
        if ok:
            logger.info("PostgreSQL is reachable.")
            return
        logger.info("Waiting for PostgreSQL (%s/%s): %s", attempt, max_attempts, message)
        time.sleep(delay_seconds)
    raise RuntimeError("PostgreSQL did not become reachable in time. Check your .env and docker compose services.")


def apply_schema() -> None:
    sql = SCHEMA_PATH.read_text(encoding="utf-8")
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
    logger.info("Schema applied from %s", SCHEMA_PATH)


def sync_categories() -> None:
    categories = load_categories().get("categories", [])
    CategoryRepository.ensure_categories(categories)
    logger.info("Synced %s categories from config/categories.yaml", len(categories))


def main() -> None:
    wait_for_postgres()
    apply_schema()
    sync_categories()
    logger.info("Database initialization complete.")


if __name__ == "__main__":
    main()
