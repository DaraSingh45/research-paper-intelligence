"""
config/loader.py

Small shared helper for loading the YAML configuration files.
Every other module (ingestion, processing, pipeline, app) should load
categories/intensity settings through this file instead of hard-coding
values or re-implementing YAML loading.
"""
from __future__ import annotations

import functools
from pathlib import Path
from typing import Any, Dict

import yaml

CONFIG_DIR = Path(__file__).resolve().parent


def _load_yaml(filename: str) -> Dict[str, Any]:
    path = CONFIG_DIR / filename
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


@functools.lru_cache(maxsize=1)
def load_categories() -> Dict[str, Any]:
    """Returns the parsed contents of categories.yaml (cached)."""
    return _load_yaml("categories.yaml")


@functools.lru_cache(maxsize=1)
def load_intensity_config() -> Dict[str, Any]:
    """Returns the parsed contents of intensity.yaml (cached)."""
    return _load_yaml("intensity.yaml")


def get_intensity_preset(name: str) -> Dict[str, Any]:
    """Return the settings block for a given intensity name (quick/standard/deep)."""
    cfg = load_intensity_config()
    presets = cfg.get("intensity", {})
    name = (name or cfg.get("default_intensity", "standard")).lower()
    if name not in presets:
        raise ValueError(
            f"Unknown search intensity '{name}'. Valid options: {list(presets.keys())}"
        )
    return presets[name]


def get_source_settings(source_name: str) -> Dict[str, Any]:
    cfg = load_intensity_config()
    sources = cfg.get("sources", {})
    if source_name not in sources:
        raise ValueError(f"No rate-limit settings configured for source '{source_name}'")
    return sources[source_name]


def get_llm_batch_settings() -> Dict[str, Any]:
    cfg = load_intensity_config()
    return cfg.get("llm", {"batch_size": 5, "max_retries_per_paper": 2, "request_timeout_seconds": 120})


def get_category_ids() -> list:
    """List of all internal category ids, e.g. ['artificial_intelligence', ...]."""
    return [c["id"] for c in load_categories().get("categories", [])]


def get_category_labels() -> Dict[str, str]:
    """Mapping of category id -> human readable label."""
    return {c["id"]: c["label"] for c in load_categories().get("categories", [])}


def clear_cache() -> None:
    """Useful in tests when config files change between test cases."""
    load_categories.cache_clear()
    load_intensity_config.cache_clear()
