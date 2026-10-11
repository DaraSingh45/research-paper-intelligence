"""
app/views/settings.py

Settings & Health page. Shows the status of every moving part so
troubleshooting doesn't require reading logs or code.
"""
from __future__ import annotations

import html
import os

import streamlit as st

from app.components.style import rpi_page_header, rpi_pill, rpi_section
from ingestion.openalex import get_openalex_api_key
from scripts.health_check import run_all_checks


def _esc(text: object) -> str:
    return html.escape(str(text), quote=True)


def _mask(secret: str | None) -> str:
    if not secret:
        return "Not set"
    if len(secret) <= 6:
        return "Configured"
    return f"Configured (…{secret[-4:]})"


def render() -> None:
    rpi_page_header("Settings", "System health, configuration and privacy.")

    with st.container(border=True):
        head, btn = st.columns([4, 1])
        with head:
            rpi_section("System health")
        with btn:
            if st.button("Re-check", use_container_width=True):
                st.rerun()

        with st.spinner("Checking components..."):
            results = run_all_checks()

        rows = []
        for r in results:
            if r.healthy:
                pill = rpi_pill("OK", tone="ok")
            elif r.optional:
                pill = rpi_pill("Optional", tone="neutral")
            else:
                pill = rpi_pill("Unavailable", tone="warn")
            rows.append(
                f'<div class="rpi-health"><div><div class="rpi-health-name">{_esc(r.name)}</div>'
                f'<div class="rpi-health-msg">{_esc(r.message)}</div></div><div>{pill}</div></div>'
            )
        st.markdown("".join(rows), unsafe_allow_html=True)

    col_config, col_privacy = st.columns(2, gap="medium")
    with col_config:
        with st.container(border=True):
            rpi_section("Configuration", "From your .env file. The OpenAlex key is read live; other changes need `docker compose up -d`.")
            safe_env = {
                "Paper source": "OpenAlex",
                "OPENALEX_API_KEY": _mask(get_openalex_api_key()),
                "POSTGRES_HOST": os.getenv("POSTGRES_HOST", "—"),
                "POSTGRES_DB": os.getenv("POSTGRES_DB", "—"),
                "OLLAMA_HOST": os.getenv("OLLAMA_HOST", "—"),
                "OLLAMA_MODEL": os.getenv("OLLAMA_MODEL", "—"),
                "APP_ENV": os.getenv("APP_ENV", "—"),
            }
            items = "".join(
                f'<div class="rpi-kv-key">{_esc(k)}</div><div class="rpi-kv-val">{_esc(v)}</div>'
                for k, v in safe_env.items()
            )
            st.markdown(f'<div class="rpi-kv">{items}</div>', unsafe_allow_html=True)

    with col_privacy:
        with st.container(border=True):
            rpi_section("Privacy")
            st.markdown(
                "Your search criteria are sent only to the OpenAlex API to find papers. "
                "Everything else (storage, processing, analytics and optional AI enrichment) "
                "runs locally. When AI enrichment is enabled, paper content is processed by "
                "your locally installed Ollama model and is never sent to an external AI service."
            )
