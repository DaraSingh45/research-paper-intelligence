#!/bin/sh
# ============================================================
# docker-entrypoint.sh
# Ensures the database is ready and the schema is applied before the
# main process (Streamlit, by default) starts. This is what makes
# `docker compose up --build` "just work" with no manual setup step.
# ============================================================
set -e

# Create dbt/profiles.yml if it doesn't exist yet. Done at startup (not
# build time) so it survives the dev bind-mount in docker-compose.yml.
if [ ! -f "dbt/profiles.yml" ]; then
    cp dbt/profiles.yml.example dbt/profiles.yml
    echo "Created dbt/profiles.yml from the example (reads Postgres credentials from your .env)."
fi

echo "Waiting for PostgreSQL and initializing schema..."
python scripts/init_database.py

echo ""
echo "============================================================"
echo " Setup complete. Streamlit is starting below."
echo " NOTE: Streamlit will print 'http://0.0.0.0:8501' -- that is"
echo " the container's internal bind address, not a browser URL."
echo ""
echo "   >>> Open this in your browser instead: http://localhost:8501"
echo ""
echo "============================================================"
echo ""

echo "Starting: $@"
exec "$@"
