"""
database/connection.py

Thin wrapper around psycopg2's connection pool. All other modules should
get connections/cursors through this file rather than calling psycopg2
directly, so there is exactly one place that knows how to reach Postgres.
"""
from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Iterator

import psycopg2
import psycopg2.extras
from psycopg2 import pool as pg_pool
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

_connection_pool: pg_pool.SimpleConnectionPool | None = None


def _build_dsn() -> str:
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    db = os.getenv("POSTGRES_DB", "research_papers")
    user = os.getenv("POSTGRES_USER", "research_user")
    password = os.getenv("POSTGRES_PASSWORD", "")
    return f"host={host} port={port} dbname={db} user={user} password={password}"


def get_pool(minconn: int = 1, maxconn: int = 8) -> pg_pool.SimpleConnectionPool:
    """Lazily create (once) and return the process-wide connection pool.

    maxconn is kept small deliberately -- this app is designed to run
    comfortably on machines with as little as 8GB RAM.
    """
    global _connection_pool
    if _connection_pool is None:
        dsn = _build_dsn()
        _connection_pool = pg_pool.SimpleConnectionPool(minconn, maxconn, dsn)
        logger.info("PostgreSQL connection pool created (min=%s max=%s)", minconn, maxconn)
    return _connection_pool


@contextmanager
def get_connection():
    """Context manager yielding a pooled psycopg2 connection."""
    pool = get_pool()
    conn = pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool.putconn(conn)


@contextmanager
def get_cursor(dict_cursor: bool = True) -> Iterator[psycopg2.extensions.cursor]:
    """Context manager yielding a cursor (RealDictCursor by default so rows
    behave like dicts, which is convenient for building pandas DataFrames
    and JSON responses)."""
    with get_connection() as conn:
        cursor_factory = psycopg2.extras.RealDictCursor if dict_cursor else None
        cur = conn.cursor(cursor_factory=cursor_factory)
        try:
            yield cur
        finally:
            cur.close()


def check_connection() -> tuple[bool, str]:
    """Used by the Settings/Health page and scripts/health_check.py."""
    try:
        with get_cursor() as cur:
            cur.execute("SELECT 1;")
            cur.fetchone()
        return True, "PostgreSQL is reachable."
    except Exception as exc:  # noqa: BLE001 - health check must never raise
        message = str(exc)
        if "could not translate host name" in message.lower():
            host = os.getenv("POSTGRES_HOST", "localhost")
            message += (
                f"\nThe container can't resolve the hostname '{host}'. If you're running via "
                "Docker Compose, this usually means the containers aren't (yet, or anymore) on "
                "the same network -- most often left over from an earlier failed/interrupted "
                "`docker compose up`. Try: `docker compose down -v` then `docker compose up --build` "
                "again for a clean restart."
            )
        return False, f"PostgreSQL is not reachable: {message}"


def close_pool() -> None:
    global _connection_pool
    if _connection_pool is not None:
        _connection_pool.closeall()
        _connection_pool = None
