"""
app/views/settings.py

Settings & Health page (Section 41). Shows the status of every moving
part so troubleshooting doesn't require reading logs or code.
"""
from __future__ import annotations

import os

import streamlit as st

from app.components.style import rpi_page_header, rpi_pill
from scripts.health_check import run_all_checks


def render() -> None:
    rpi_page_header("Settings", "System health, configuration, and privacy.")

    if st.button("Re-check now"):
        st.rerun()

    with st.spinner("Checking components..."):
        results = run_all_checks()

    for r in results:
        status_text = "OK" if r.healthy else ("Optional" if r.optional else "Not available")
        col1, col2 = st.columns([1, 4])
        with col1:
            st.markdown(f"**{r.name}**  \n{rpi_pill(status_text, ok=r.healthy or r.optional)}", unsafe_allow_html=True)
        with col2:
            st.caption(r.message)

    st.divider()
    col_config, col_privacy = st.columns(2)
    with col_config:
        st.markdown("**Configuration**")
        st.caption("From your .env file — edit it and restart the app to change these.")
        safe_env = {
            "POSTGRES_HOST": os.getenv("POSTGRES_HOST", "—"),
            "POSTGRES_DB": os.getenv("POSTGRES_DB", "—"),
            "OLLAMA_HOST": os.getenv("OLLAMA_HOST", "—"),
            "OLLAMA_MODEL": os.getenv("OLLAMA_MODEL", "—"),
            "APP_ENV": os.getenv("APP_ENV", "—"),
        }
        st.table(safe_env)

    with col_privacy:
        st.markdown("**Privacy**")
        st.caption(
            "All data, processing, analytics and optional AI enrichment run locally. "
            "When AI enrichment is enabled, paper content is processed through your "
            "locally installed Ollama model and is never sent to an external service."
        )
