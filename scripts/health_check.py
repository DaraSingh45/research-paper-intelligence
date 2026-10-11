"""
scripts/health_check.py

Checks every moving part of the system (Section 41) and reports simple
pass/fail + a human-readable message for each. Used by:
  - `python scripts/health_check.py` (CLI / Docker healthcheck)
  - app/views/settings.py (Settings & Health page)

Every individual check is wrapped so one failing check never crashes the
others.
"""
from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path
from typing import Callable, List, NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests  # noqa: E402

from database.connection import check_connection  # noqa: E402
from llm.ollama_client import OllamaClient  # noqa: E402

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class HealthResult(NamedTuple):
    name: str
    healthy: bool
    optional: bool
    message: str


def _safe_check(name: str, fn: Callable[[], tuple], optional: bool = False) -> HealthResult:
    try:
        healthy, message = fn()
        return HealthResult(name, healthy, optional, message)
    except Exception as exc:  # noqa: BLE001
        return HealthResult(name, False, optional, f"Check raised an exception: {exc}")


def check_application() -> tuple:
    return True, "Application code is loaded and running."


def check_postgres() -> tuple:
    return check_connection()


def check_dbt() -> tuple:
    try:
        result = subprocess.run(["dbt", "--version"], capture_output=True, text=True, timeout=15)
        if result.returncode == 0:
            return True, "dbt is installed."
        return False, "dbt is installed but returned a non-zero exit code."
    except FileNotFoundError:
        return False, "dbt is not installed in this environment."
    except subprocess.TimeoutExpired:
        return False, "Checking dbt timed out."


def check_airflow() -> tuple:
    try:
        resp = requests.get("http://airflow-webserver:8080/health", timeout=3)
        if resp.status_code == 200:
            return True, "Airflow webserver is reachable."
        return False, f"Airflow webserver returned status {resp.status_code}."
    except requests.RequestException:
        try:
            resp = requests.get("http://localhost:8080/health", timeout=3)
            if resp.status_code == 200:
                return True, "Airflow webserver is reachable."
        except requests.RequestException:
            pass
        return False, "Airflow is not running (this is optional -- see README Airflow setup)."


def _check_http_source(url: str, name: str) -> tuple:
    try:
        resp = requests.get(url, timeout=8)
        if resp.status_code < 500:
            return True, f"{name} API is reachable."
        return False, f"{name} API returned status {resp.status_code}."
    except requests.RequestException as exc:
        return False, f"{name} API is not reachable: {exc}"


def check_openalex() -> tuple:
    """OpenAlex is the only paper source. Uses the configured API key so the
    check reflects what a real search will experience."""
    from ingestion.openalex import get_openalex_api_key

    api_key = get_openalex_api_key()
    params = {"per-page": 1}
    if api_key:
        params["api_key"] = api_key
    try:
        resp = requests.get("https://api.openalex.org/works", params=params, timeout=8)
    except requests.Timeout:
        return False, "OpenAlex API did not respond within 8 seconds. Check your internet connection."
    except requests.RequestException as exc:
        return False, f"OpenAlex API is not reachable ({type(exc).__name__}). Check your internet connection."

    if resp.status_code in (401, 403):
        if api_key:
            return False, f"OpenAlex rejected the API key (HTTP {resp.status_code}). Check OPENALEX_API_KEY in .env."
        return False, "OpenAlex requires an API key. Set OPENALEX_API_KEY in .env (free at openalex.org/settings/api)."
    if resp.status_code >= 400:
        return False, f"OpenAlex API returned status {resp.status_code}."
    if api_key:
        return True, "OpenAlex API is reachable and the API key is configured."
    return True, "OpenAlex API is reachable, but no API key is set, so only a small test quota is available."


def check_ollama() -> tuple:
    return OllamaClient().is_available()


def run_all_checks() -> List[HealthResult]:
    checks = [
        ("Application", check_application, False),
        ("PostgreSQL", check_postgres, False),
        ("dbt", check_dbt, False),
        ("Airflow", check_airflow, True),
        ("OpenAlex", check_openalex, False),
        ("Ollama", check_ollama, True),
    ]
    return [_safe_check(name, fn, optional) for name, fn, optional in checks]


def main() -> int:
    results = run_all_checks()
    all_required_ok = True
    for r in results:
        status = "OK" if r.healthy else ("OPTIONAL" if r.optional else "FAIL")
        print(f"[{status:>8}] {r.name}: {r.message}")
        if not r.healthy and not r.optional:
            all_required_ok = False
    return 0 if all_required_ok else 1


if __name__ == "__main__":
    sys.exit(main())
