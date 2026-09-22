# Research Paper Intelligence & Analytics Pipeline

A free, fully local, privacy-friendly research-paper search and analytics
tool. Search across arXiv, OpenAlex, Semantic Scholar and Crossref from a
simple dashboard, get deduplicated papers stored in PostgreSQL, explore
dbt-powered analytics, and optionally enrich papers with a locally running
LLM (via Ollama) — all without writing code, touching a config file, or
sending your data anywhere.

Built as a B.Tech final-year project to demonstrate data engineering,
analytics, orchestration and LLM engineering skills, while staying usable
on a modest 8GB RAM laptop.

---

## Table of contents

**For users**
1. [Features](#features)
2. [Requirements](#requirements)
3. [Installation (Docker — recommended)](#installation-docker--recommended)
4. [First run](#first-run)
5. [Academic source API keys (recommended)](#academic-source-api-keys-recommended)
6. [Using the app](#using-the-app)
7. [Local LLM setup (optional)](#local-llm-setup-optional)
8. [Troubleshooting](#troubleshooting)

**For developers**
9. [Architecture](#architecture)
10. [Project structure](#project-structure)
11. [Database architecture](#database-architecture)
12. [dbt architecture](#dbt-architecture)
13. [Airflow setup](#airflow-setup)
14. [Configuration files](#configuration-files)
15. [Testing](#testing)
16. [Running without Docker](#running-without-docker)
17. [Project limitations](#project-limitations)
18. [Future improvements](#future-improvements)
19. [License](#license)

---

## Features

- 🔎 **No-code research configuration** — keywords, title filter, author,
  categories, date range, and a Quick/Standard/Deep intensity level.
- 📡 **Four fixed, free academic sources** — arXiv, OpenAlex, Semantic
  Scholar, Crossref. All free; arXiv and Crossref need no setup, the other
  two work best with a free key (see [Academic source API keys](#academic-source-api-keys-recommended)).
- 🧹 **Cleaning, normalization & 4-tier deduplication** (DOI → external ID →
  exact title → fuzzy title, with fuzzy matches flagged for review, never
  silently merged).
- 🗄️ **PostgreSQL storage** with a fully normalized schema and preserved
  raw source data.
- 🔧 **dbt transformations** producing staging → intermediate → mart models,
  including publication trends, topic growth, author/category/source/
  citation statistics.
- 🤖 **Optional local AI enrichment** via [Ollama](https://ollama.com) —
  summaries, topics, and research area, with strict JSON validation and
  automatic retries. The app works fully without it.
- 📊 **Dashboard, Papers, Topics, Authors, Jobs pages** — all in a clean,
  dark Streamlit UI.
- 📤 **CSV / JSON / PDF export**.
- ⏱️ **Scheduled recurring searches** via Apache Airflow (optional).
- 🐳 **One-command Docker install.**
- 🔒 **100% local** — no cloud database, no hosted backend, no paid APIs.

---

## Requirements

- [Docker](https://www.docker.com/) and Docker Compose (bundled with Docker
  Desktop) — **this is the only hard requirement.**
- ~4GB of free RAM for the default setup (Postgres + app). 8GB total system
  RAM is enough; see the RAM notes below if you also want Airflow and/or a
  local LLM running at the same time.
- (Optional) [Ollama](https://ollama.com) installed natively on your
  machine if you want AI enrichment — this is **not** required to use the
  rest of the app.

> **RAM budget note (8GB machines):** Postgres + the Streamlit app together
> use roughly 1–1.5GB. Airflow (optional, opt-in) adds ~1GB. A local LLM via
> Ollama (e.g. `llama3.2:3b`) needs another ~2–3GB while generating. Running
> all of these plus your OS and browser at once on 8GB is tight but doable
> one-at-a-time; the defaults below only start Postgres + the app so
> everything stays comfortable out of the box.

---

## Installation (Docker — recommended)

```
git clone <repository-url>
cd research-paper-intelligence
cp .env.example .env
docker compose up --build
```

That's it. The first startup automatically creates the database schema —
there is nothing else to configure. Once you see Streamlit's log message
that the app is running, open:

**http://localhost:8501**

## First run

1. Open http://localhost:8501 — you'll land on the **Research** page.
2. Type a keyword (e.g. `large language models`), pick a category or two,
   choose an intensity (start with **Quick** for your first try), and
   click **START RESEARCH**.
3. Watch the live progress bar as it searches each source.
4. When it finishes, open **Dashboard** or **Papers** from the sidebar to
   explore what was found.

No Python, no SQL, no dbt commands, no Airflow UI required for this.

## Academic source API keys (recommended)

arXiv and Crossref need no setup. The other two sources changed their
access terms in 2026 and now work best with a free key:

- **OpenAlex** — as of February 2026, requires a free API key for
  reliable access (without one you get a small daily test quota, then
  errors). Get one at https://openalex.org/settings/api (under a minute,
  no card needed), then set `OPENALEX_API_KEY` in `.env`.
- **Semantic Scholar** — doesn't require a key, but its unauthenticated
  pool is shared with every anonymous caller worldwide and gets
  rate-limited during busy periods. A free key gives you a dedicated
  rate: https://www.semanticscholar.org/product/api#Get-Started, then
  set `SEMANTIC_SCHOLAR_API_KEY` in `.env`.

Restart the app (`docker compose up --build`) after editing `.env` for
either to take effect. Neither is required — the pipeline continues with
whichever sources succeed if one is skipped or fails (see the Research
page's per-source status and **Jobs → Job Logs** for details).

## Using the app

| Page | What it's for |
|---|---|
| **Research** | Configure and launch a new search; results appear inline on this page as soon as it finishes, with a click-through link to each paper's PDF or page. |
| **Dashboard** | Top-level metrics and the 6 key charts (trends, topics, categories, authors, citations, sources). |
| **Papers** | Searchable/filterable table of every paper collected so far, with a direct download/open link per paper; click a row for full details. |
| **Topics** | AI-derived topic analytics (requires AI Enrichment to have been used at least once). |
| **Authors** | Most frequent authors, breakdowns by category, citation stats. |
| **Jobs** | History of every search job, scheduled recurring searches, and CSV/JSON/PDF export. |
| **Settings** | Live health status of every component (Postgres, dbt, Airflow, each source, Ollama). |

## Local LLM setup (optional)

AI enrichment is completely optional — the app is fully useful without it.
To enable it:

1. Install Ollama natively on your host machine: https://ollama.com/download
2. Pull a small model (3B models run comfortably on 8GB RAM machines):
   ```
   ollama pull llama3.2:3b
   ```
3. Make sure `OLLAMA_MODEL` in your `.env` matches the model you pulled
   (it defaults to `llama3.2:3b`, so usually nothing to change).
4. On the **Research** page, toggle **Enable local AI enrichment**. The UI
   will show a green check if Ollama is reachable and the model is
   installed, or a clear message explaining what's missing if not.

Running Ollama natively (not inside Docker) is recommended so it can use
your GPU if you have one, and so its RAM isn't double-counted against the
Docker containers. The app reaches it at `http://host.docker.internal:11434`
by default (already set in `.env.example`). If you'd rather run Ollama
inside Docker too, use `docker compose --profile llm-docker up` and set
`OLLAMA_HOST=http://ollama:11434` in `.env`.

**Privacy:** all collected data, processing, analytics and AI enrichment
run locally. When AI enrichment is enabled, paper content is processed
through your locally installed Ollama model and is never sent to an
external AI service.

## Troubleshooting

- **"The application isn't fully set up yet" on first load.** Postgres is
  still starting. Wait ~10 seconds and refresh, or click the on-screen
  "Try to initialize the database now" button.
- **A source shows a red ✗ on the Research page progress view.** That
  source's API was unreachable or timed out — the pipeline keeps going
  with the other sources. Check **Jobs → open the job → Job Logs** for
  details.
- **AI Enrichment toggle shows a warning.** Ollama isn't running or the
  configured model isn't installed yet — see [Local LLM setup](#local-llm-setup-optional).
  The rest of the pipeline still runs normally.
- **Dashboard/Topics charts are empty right after a search.** Give dbt a
  moment to run (it's part of the pipeline, shown in the job's progress
  and logs). If it still looks empty, check **Settings** to confirm dbt
  is installed inside the app container, and check the job's logs for a
  `dbt run` error.
- **`port is already allocated`.** Postgres doesn't publish a host port by
  default (the app reaches it internally, so this can't collide with
  anything on your machine). If you see this for **8501** (the app itself),
  something else is using that port — stop it, or edit the left-hand
  number in `docker-compose.yml`'s `app` service, e.g. `"8502:8501"`, and
  re-run `docker compose up --build`.
- **Nothing shows a Python traceback** — if you do see one, please open an
  issue; the app is designed to show a friendly message and log the
  details instead (see **Jobs → Job Logs**).

---

# For developers

## Architecture

```
USER
  |
  v
Streamlit UI  (app/)  ---------------------------+
  |                                               |
  v                                               |
Research Config (SearchConfig)                    |
  |                                                |
  v                                                |
pipeline/orchestrator.py  <---- shared by ---->  Airflow DAG (scheduled runs)
  |
  +--> ingestion/*.py   (arXiv, OpenAlex, Semantic Scholar, Crossref)
  +--> processing/cleaner.py, normalizer.py, validator.py
  +--> processing/deduplicator.py  (DOI -> external ID -> title -> fuzzy)
  +--> database/repositories.py  -->  PostgreSQL
  +--> dbt (subprocess)  -->  staging -> intermediate -> marts
  +--> llm/*.py  (Ollama, optional)  -->  llm_enrichments table
  +--> quality_checks

analytics/*.py  <-- reads dbt marts  <-- app/views/dashboard.py, topics.py, authors.py
```

Both the Streamlit "START RESEARCH" button and the Airflow DAG call the
exact same functions in `pipeline/orchestrator.py` — no business logic
lives inside the DAG file itself, and none is duplicated between the two
callers.

## Project structure

```
research-paper-intelligence/
├── app/                  Streamlit UI (pages + reusable components)
├── ingestion/             Fixed source connectors (arXiv, OpenAlex, Semantic Scholar, Crossref)
├── processing/             Cleaning, normalization, deduplication, validation
├── database/              Connection pooling, models, repositories, schema.sql
├── llm/                   Ollama client, prompts, summarizer, classifier, validator
├── analytics/              Reporting queries against dbt marts + PDF report generator
├── pipeline/               Reusable orchestration (used by both Streamlit and Airflow)
├── dbt/                    staging -> intermediate -> marts transformation models
├── airflow/dags/            Thin DAG that calls pipeline/orchestrator.py
├── config/                categories.yaml, intensity.yaml, loader.py
├── scripts/                init_database.py, health_check.py, run_pipeline.py (CLI)
├── evaluation/              Small manually-reviewed LLM evaluation dataset
├── tests/                  pytest suite
├── data/                   Local scratch/export directory (gitignored)
├── Dockerfile / docker-compose.yml / docker-entrypoint.sh
└── requirements.txt / requirements-airflow.txt
```

## Database architecture

See `database/schema.sql` for the full DDL. Key tables:

- `research_jobs` — one row per search run (config, status, counts, progress).
- `job_logs` — structured per-job log lines (surfaced in the UI's "Job Logs").
- `papers` — canonical deduplicated paper records, including a
  `raw_source_data JSONB` column that preserves every source's original
  payload (never overwritten), and a `possible_duplicate_of` column used
  by fuzzy-match flags (never auto-merged).
- `authors`, `paper_authors`, `categories`, `paper_categories`, `sources`,
  `paper_sources` — normalized many-to-many relationships.
- `citations` — point-in-time citation count snapshots.
- `llm_enrichments` — validated (or `FAILED_REVIEW`) LLM output, kept
  strictly separate from the original paper fields.
- `quality_checks` — per-job data quality results.
- `scheduled_searches` — saved configs reused by recurring Airflow runs.

Indexes exist on DOI, normalized title, publication date, and source for
query performance; unique constraints prevent duplicate DOIs and duplicate
`(source, external_id)` pairs.

## dbt architecture

```
staging/      stg_papers, stg_authors, stg_categories, stg_sources
                (renamed/typed 1:1 views over the raw tables)
intermediate/  int_paper_authors, int_paper_categories, int_paper_sources
                (joined, analytics-ready rows)
marts/         dim_papers, dim_authors, dim_categories, fct_citations
                publication_trends, topic_growth, author_statistics,
                category_statistics, source_statistics, citation_statistics
```

Marts are materialized as tables; staging/intermediate as views. Run
manually with:
```
cd dbt
dbt run --profiles-dir .
```
(this happens automatically as part of every pipeline run, via
`pipeline/orchestrator.run_dbt()`).

## Airflow setup

Airflow is optional and off by default. To try it:

```
docker compose --profile airflow up --build
```

Then open **http://localhost:8080** (default login is generated on first
`standalone` boot — check the `rpi_airflow` container logs for the
auto-generated admin password), and look for the `research_pipeline` DAG.

- **Ad-hoc run with a specific config:**
  ```
  docker compose exec airflow airflow dags trigger research_pipeline \
    --conf '{"config": {"keywords": ["ai agents"], "intensity": "standard"}}'
  ```
- **Recurring runs:** create a schedule from the app's **Jobs** page
  (reuses a past job's configuration + Off/Daily/Weekly/Monthly). The DAG's
  own `@daily` schedule checks the `scheduled_searches` table and runs any
  schedule that's due, reusing the exact same `pipeline/orchestrator.py`
  functions as the UI.

Only small metadata (a job id, a config dict) is passed between Airflow
tasks via XCom — large paper lists are never passed through XCom; each
stage persists to PostgreSQL and the next stage reads from there.

## Configuration files

Nothing is hard-coded that a developer might reasonably want to tune:

- `config/categories.yaml` — the 12 predefined categories and how each
  maps onto arXiv codes / OpenAlex concepts / Semantic Scholar fields /
  keyword fallbacks.
- `config/intensity.yaml` — Quick/Standard/Deep presets (max results, page
  size, dedup strategy) and per-source rate limits / timeouts / retries.
- `.env` — database credentials, Ollama host/model, contact email for the
  academic APIs' "polite pool".

Adding a 5th source connector later only requires implementing
`ingestion/<name>.py` (subclassing `PaperSource`) and adding one line to
`SOURCE_REGISTRY` in `ingestion/__init__.py` — this is intentionally not a
user-facing UI option, per the project's fixed-sources constraint.

## Testing

```
pip install -r requirements.txt
pytest
```

- `test_ingestion.py`, `test_processing.py`, `test_deduplication.py`,
  `test_llm.py` run fully offline (no network, no database — everything
  is mocked or uses canned payloads).
- `test_database.py` runs real integration tests against PostgreSQL and
  **auto-skips** if no database is reachable. To run it:
  ```
  docker compose up -d postgres
  python scripts/init_database.py
  pytest tests/test_database.py
  ```

## Running without Docker

```
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env   # edit POSTGRES_HOST to "localhost"
# start your own local Postgres 16, matching the credentials in .env
python scripts/init_database.py
streamlit run app/main.py
```

dbt looks for `dbt/profiles.yml`; copy `dbt/profiles.yml.example` to
`dbt/profiles.yml` (it reads credentials from the same `.env`).

## Project limitations

- Citation counts vary between sources and are not deduplicated/reconciled
  across sources — the `papers.citation_count` column reflects whichever
  source's value was captured first; the `citations` table keeps a
  per-source history if you want to compare.
- Crossref does not provide field-of-study data, so category filtering
  does not narrow Crossref results the way it does for the other three
  sources.
- Fuzzy-title deduplication is a heuristic (`difflib` similarity ratio) and
  intentionally conservative — it flags for review rather than merging, so
  some near-duplicates will remain visible as separate rows until reviewed.
- LLM enrichment quality depends entirely on the local model you choose;
  the bundled `evaluation/` dataset is a small, manually reviewed sanity
  check, not a rigorous benchmark.
- Airflow's `standalone` mode (used here for a light footprint) is not a
  production-grade deployment topology; it's intentionally simple for a
  local, single-user student project.
- The two API keys described in [Academic source API keys](#academic-source-api-keys-recommended)
  reflect each provider's terms as of this writing (late 2026); external
  APIs change their access terms over time, so if a source starts failing
  consistently, check that provider's current API docs for anything new.

## Future improvements

- A 5th+ source connector (e.g. PubMed, IEEE Xplore, CORE).
- Citation graph analysis (who cites whom) using the sources' reference
  lists where available.
- A "merge/dismiss" review UI for `possible_duplicate_of` flags.
- Author name disambiguation beyond simple normalized-name matching (e.g.
  ORCID-based linking where sources provide it).
- Incremental/delta ingestion so scheduled runs only reprocess genuinely
  new papers.

## License

MIT — see [LICENSE](LICENSE).


<img width="1354" height="316" alt="image" src="https://github.com/user-attachments/assets/8ac31e1a-bbd3-4d80-85e2-4735228e0f55" />
<img width="1365" height="265" alt="image" src="https://github.com/user-attachments/assets/34b35671-b98d-4cca-b7dc-56ba660d8213" />

<img width="1048" height="512" alt="image" src="https://github.com/user-attachments/assets/e362db0c-538a-4904-bb63-a77455620469" />

<img width="1096" height="567" alt="image" src="https://github.com/user-attachments/assets/51c24e43-0789-4a26-8d53-d8962f7db990" />

<img width="1087" height="374" alt="image" src="https://github.com/user-attachments/assets/aa735788-3645-4065-8a80-005716dfaf5e" />

<img width="1091" height="378" alt="image" src="https://github.com/user-attachments/assets/0ed22b28-aa38-426a-853a-40cfc128c960" />

<img width="1349" height="554" alt="image" src="https://github.com/user-attachments/assets/82ad9ffa-c2dd-49de-8f9e-5895fe771f80" />

<img width="1126" height="286" alt="image" src="https://github.com/user-attachments/assets/c6f7898b-4aea-4b14-889a-e252092d1d6f" />
