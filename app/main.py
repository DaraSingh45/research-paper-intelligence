"""
app/main.py

Entrypoint for the Streamlit application. Run with:
    streamlit run app/main.py

Sets up page config, sidebar navigation (Section 6), and a friendly
"database not ready yet" screen instead of a crash if PostgreSQL/schema
isn't reachable yet (Section 38: never show a raw traceback to the user).
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make the project root importable (database/, ingestion/, pipeline/, etc.)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

load_dotenv()

st.set_page_config(
    page_title="Research Paper Intelligence",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded",
)


def _database_ready() -> tuple[bool, str]:
    try:
        from database.connection import check_connection

        ok, message = check_connection()
        if not ok:
            return False, message
        from database.connection import get_cursor

        with get_cursor() as cur:
            cur.execute(
                "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'research_jobs')"
            )
            exists = cur.fetchone()["exists"]
        if not exists:
            return False, "Database is reachable, but the schema has not been created yet."
        return True, "OK"
    except Exception as exc:  # noqa: BLE001
        return False, f"Could not check the database: {exc}"


def _render_setup_screen(message: str) -> None:
    from app.components.style import inject_base_styles, rpi_page_header

    inject_base_styles()
    rpi_page_header("Research Paper Intelligence", "Setup")
    st.warning("The application isn't fully set up yet.")
    st.write(message)
    st.markdown(
        "This usually means PostgreSQL isn't running yet, or the database schema hasn't been "
        "created. If you're running via Docker, wait a few seconds for Postgres to finish "
        "starting and refresh this page. Otherwise, run:"
    )
    st.code("python scripts/init_database.py", language=None)

    if st.button("Try to initialize the database now", type="primary"):
        with st.spinner("Initializing database..."):
            try:
                from scripts.init_database import apply_schema, sync_categories, wait_for_postgres

                wait_for_postgres(max_attempts=5, delay_seconds=2)
                apply_schema()
                sync_categories()
                st.success("Database initialized. Reloading...")
                st.rerun()
            except Exception as exc:  # noqa: BLE001
                st.error(f"Initialization failed: {exc}")


def main() -> None:
    from app.components.style import inject_base_styles, rpi_sidebar_brand

    inject_base_styles()

    ready, message = _database_ready()
    if not ready:
        _render_setup_screen(message)
        return

    # Import page render functions only after we know the app can talk to
    # the database (avoids import-time DB calls failing before we can show
    # the friendly setup screen above).
    from app.views import authors, dashboard, jobs, papers, search, settings, topics

    pages = [
        st.Page(search.render, title="Research", icon="🔎", url_path="research", default=True),
        st.Page(dashboard.render, title="Dashboard", icon="📊", url_path="dashboard"),
        st.Page(papers.render, title="Papers", icon="📄", url_path="papers"),
        st.Page(topics.render, title="Topics", icon="🏷️", url_path="topics"),
        st.Page(authors.render, title="Authors", icon="🧑‍🔬", url_path="authors"),
        st.Page(jobs.render, title="Jobs", icon="🗂️", url_path="jobs"),
        st.Page(settings.render, title="Settings", icon="⚙️", url_path="settings"),
    ]

    with st.sidebar:
        rpi_sidebar_brand()

    pg = st.navigation(pages, position="sidebar")
    pg.run()


if __name__ == "__main__":
    main()
