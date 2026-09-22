"""
llm/ollama_client.py

Thin client for a locally running Ollama server (https://ollama.com).
No paid API, no external service -- everything happens on localhost (or
wherever OLLAMA_HOST points, e.g. host.docker.internal in Docker).
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Optional

import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


@dataclass
class OllamaResponse:
    success: bool
    text: str = ""
    error: Optional[str] = None


class OllamaClient:
    def __init__(self, host: Optional[str] = None, model: Optional[str] = None, timeout: Optional[int] = None):
        self.host = (host or os.getenv("OLLAMA_HOST", "http://localhost:11434")).rstrip("/")
        self.model = model or os.getenv("OLLAMA_MODEL", "llama3.2:3b")
        self.timeout = timeout or int(os.getenv("OLLAMA_TIMEOUT_SECONDS", "120"))

    def is_available(self) -> tuple[bool, str]:
        """Checks whether Ollama is reachable and the configured model is
        installed. Used by the AI Enrichment toggle and the Settings/Health
        page -- must never raise, only report."""
        try:
            resp = requests.get(f"{self.host}/api/tags", timeout=5)
            resp.raise_for_status()
            models = [m.get("name", "") for m in resp.json().get("models", [])]
            if not models:
                return False, "Ollama is running but no models are installed."
            model_installed = any(self.model.split(":")[0] in m for m in models)
            if not model_installed:
                return False, (
                    f"Ollama is running, but model '{self.model}' is not installed. "
                    f"Run: ollama pull {self.model}"
                )
            return True, f"Ollama is available with model '{self.model}'."
        except requests.ConnectionError:
            return False, "Ollama is not running or not reachable at " + self.host
        except Exception as exc:  # noqa: BLE001
            return False, f"Could not check Ollama status: {exc}"

    def generate(self, prompt: str, system: Optional[str] = None) -> OllamaResponse:
        """Sends a single-turn prompt to Ollama's /api/generate endpoint and
        requests JSON-formatted output."""
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.2},
        }
        if system:
            payload["system"] = system
        try:
            resp = requests.post(f"{self.host}/api/generate", json=payload, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
            return OllamaResponse(success=True, text=data.get("response", ""))
        except requests.Timeout:
            return OllamaResponse(success=False, error="Ollama request timed out.")
        except requests.ConnectionError:
            return OllamaResponse(success=False, error="Could not connect to Ollama.")
        except Exception as exc:  # noqa: BLE001
            logger.exception("Ollama generate() failed")
            return OllamaResponse(success=False, error=str(exc))
