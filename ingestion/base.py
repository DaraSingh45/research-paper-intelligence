"""
ingestion/base.py

Common interface every source connector implements, plus shared helpers
(rate limiting, retries, timeouts) so individual connectors stay short and
only contain source-specific request/parsing logic.

Section 14 of the spec: "Create a common abstract interface... All
connectors must return the same normalized paper object."
"""
from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from typing import TypeVar

import requests
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from config.loader import get_source_settings
from database.models import SearchConfig, SourceResult

logger = logging.getLogger(__name__)

T = TypeVar("T")

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


class RetryableHTTPError(Exception):
    """Raised for HTTP responses that are worth retrying (rate limit / 5xx)."""


class RateLimiter:
    """Very small token-less rate limiter: sleeps just long enough between
    calls to respect requests_per_second. Good enough for a single-process
    student project; not meant for concurrent workers."""

    def __init__(self, requests_per_second: float):
        self.min_interval = 1.0 / max(requests_per_second, 0.01)
        self._last_call = 0.0

    def wait(self) -> None:
        elapsed = time.monotonic() - self._last_call
        remaining = self.min_interval - elapsed
        if remaining > 0:
            time.sleep(remaining)
        self._last_call = time.monotonic()


class PaperSource(ABC):
    """Abstract interface every source connector must implement."""

    name: str = "base"

    def __init__(self):
        settings = get_source_settings(self.name)
        self.timeout = settings.get("timeout_seconds", 30)
        self.max_retries = settings.get("max_retries", 3)
        self.backoff = settings.get("retry_backoff_seconds", 2)
        self.rate_limiter = RateLimiter(settings.get("requests_per_second", 1))
        self.enabled = settings.get("enabled", True)
        self.requests_made = 0

    @abstractmethod
    def search(self, config: SearchConfig) -> SourceResult:
        """Search this source using the given config and return a SourceResult.
        Implementations must never raise -- all errors are caught and reported
        inside the SourceResult so one failing source cannot crash the pipeline."""
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Shared HTTP helper with rate limiting + retries + timeout handling
    # ------------------------------------------------------------------
    def _get(self, url: str, params: dict | None = None, headers: dict | None = None) -> requests.Response:
        @retry(
            reraise=True,
            stop=stop_after_attempt(self.max_retries),
            wait=wait_exponential(multiplier=self.backoff, min=1, max=30),
            retry=retry_if_exception_type((RetryableHTTPError, requests.Timeout, requests.ConnectionError)),
        )
        def _do_request() -> requests.Response:
            self.rate_limiter.wait()
            self.requests_made += 1
            resp = requests.get(url, params=params, headers=headers, timeout=self.timeout)
            if resp.status_code in RETRYABLE_STATUS_CODES:
                raise RetryableHTTPError(f"{self.name}: HTTP {resp.status_code} from {url}")
            resp.raise_for_status()
            return resp

        return _do_request()

    def safe_search(self, config: SearchConfig) -> SourceResult:
        """Wraps search() with a final safety net so a connector bug never
        takes down the whole ingestion stage."""
        if not self.enabled:
            return SourceResult(source=self.name, success=False, error_message="Source disabled in config")
        start = time.monotonic()
        try:
            result = self.search(config)
            result.elapsed_seconds = time.monotonic() - start
            result.requests_made = self.requests_made
            return result
        except Exception as exc:  # noqa: BLE001 - a source must never crash the pipeline
            logger.exception("Unhandled error in %s connector", self.name)
            return SourceResult(
                source=self.name,
                success=False,
                error_message=f"Unexpected error: {exc}",
                requests_made=self.requests_made,
                elapsed_seconds=time.monotonic() - start,
            )
