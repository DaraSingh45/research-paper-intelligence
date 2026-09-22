# ============================================================
# Research Paper Intelligence - Application image
# Contains: Streamlit UI, ingestion/processing pipeline, dbt Core.
# Kept on python:3.11-slim to stay light on constrained (8GB RAM) machines.
# ============================================================
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DEFAULT_TIMEOUT=180 \
    PIP_RETRIES=10

WORKDIR /app

# System deps needed by psycopg2 and dbt-postgres at build time
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# --timeout/--retries make this resilient to a slow or unstable connection to
# PyPI (large wheels like pandas/numpy/pyarrow can otherwise hit pip's short
# default timeout mid-download on a slow network). If this still fails,
# just re-run `docker compose up --build` -- pip resumes from where apt/OS
# layers were already cached, and a second attempt is usually enough.
RUN pip install --no-cache-dir --timeout=180 --retries=10 -r requirements.txt

COPY . .

RUN chmod +x docker-entrypoint.sh

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["streamlit", "run", "app/main.py", "--server.port=8501", "--server.address=0.0.0.0"]
