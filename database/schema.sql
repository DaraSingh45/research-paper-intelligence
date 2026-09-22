-- ============================================================
-- Research Paper Intelligence - PostgreSQL schema
-- Applied by scripts/init_database.py on first startup.
-- Raw source data is preserved (raw_source_data JSONB) and is never
-- overwritten by LLM-generated values (those live in llm_enrichments).
-- ============================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;  -- for gen_random_uuid()

-- ----------------------------------------------------------------
-- research_jobs: one row per search run (ad-hoc or scheduled)
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS research_jobs (
    id                  TEXT PRIMARY KEY,               -- e.g. RP-20260914-001
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at          TIMESTAMPTZ,
    completed_at        TIMESTAMPTZ,
    status              TEXT NOT NULL DEFAULT 'PENDING'
                            CHECK (status IN ('PENDING','RUNNING','COMPLETED','FAILED','CANCELLED')),
    keywords            TEXT[] NOT NULL DEFAULT '{}',
    title_filter        TEXT,
    authors             TEXT[] NOT NULL DEFAULT '{}',
    categories          TEXT[] NOT NULL DEFAULT '{}',
    start_date          DATE,
    end_date            DATE,
    intensity           TEXT NOT NULL DEFAULT 'standard'
                            CHECK (intensity IN ('quick','standard','deep')),
    llm_enabled         BOOLEAN NOT NULL DEFAULT false,
    llm_options         JSONB NOT NULL DEFAULT '{}',
    total_found         INTEGER NOT NULL DEFAULT 0,
    total_unique        INTEGER NOT NULL DEFAULT 0,
    total_duplicates    INTEGER NOT NULL DEFAULT 0,
    total_failed        INTEGER NOT NULL DEFAULT 0,
    error_message       TEXT,
    current_step        TEXT,
    progress_percent    INTEGER NOT NULL DEFAULT 0,
    source_status       JSONB NOT NULL DEFAULT '{}',    -- {"arxiv": "ok", "semantic_scholar": "timeout"}
    triggered_by        TEXT NOT NULL DEFAULT 'manual'  -- 'manual' | 'scheduled' | 'airflow'
);

CREATE INDEX IF NOT EXISTS idx_research_jobs_status ON research_jobs(status);
CREATE INDEX IF NOT EXISTS idx_research_jobs_created_at ON research_jobs(created_at);

-- ----------------------------------------------------------------
-- job_logs: structured log lines per job (for the Job Logs / Health page)
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS job_logs (
    id           BIGSERIAL PRIMARY KEY,
    job_id       TEXT NOT NULL REFERENCES research_jobs(id) ON DELETE CASCADE,
    ts           TIMESTAMPTZ NOT NULL DEFAULT now(),
    level        TEXT NOT NULL DEFAULT 'INFO' CHECK (level IN ('DEBUG','INFO','WARNING','ERROR')),
    source       TEXT,                                   -- e.g. 'arxiv', 'llm', 'dbt', 'pipeline'
    message      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_job_logs_job_id ON job_logs(job_id);

-- ----------------------------------------------------------------
-- scheduled_searches: saved configs reused by recurring Airflow runs
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS scheduled_searches (
    id              SERIAL PRIMARY KEY,
    name            TEXT NOT NULL,
    config          JSONB NOT NULL,           -- same shape as a research_jobs search config
    frequency       TEXT NOT NULL DEFAULT 'off' CHECK (frequency IN ('off','daily','weekly','monthly')),
    active          BOOLEAN NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_run_at     TIMESTAMPTZ,
    next_run_at     TIMESTAMPTZ
);

-- ----------------------------------------------------------------
-- sources: the 4 fixed, developer-controlled connectors
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sources (
    id      SERIAL PRIMARY KEY,
    name    TEXT NOT NULL UNIQUE   -- 'arxiv' | 'openalex' | 'semantic_scholar' | 'crossref'
);

INSERT INTO sources (name) VALUES
    ('arxiv'), ('openalex'), ('semantic_scholar'), ('crossref')
ON CONFLICT (name) DO NOTHING;

-- ----------------------------------------------------------------
-- categories: internal category vocabulary (mirrors config/categories.yaml)
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS categories (
    id      TEXT PRIMARY KEY,      -- e.g. 'machine_learning'
    label   TEXT NOT NULL
);

-- ----------------------------------------------------------------
-- papers: the canonical, deduplicated paper record
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS papers (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title               TEXT NOT NULL,
    title_normalized    TEXT NOT NULL,          -- lowercased/punctuation-stripped, for dedup matching
    abstract            TEXT,
    publication_date    DATE,
    doi                 TEXT,
    url                 TEXT,
    pdf_url             TEXT,
    journal             TEXT,
    venue               TEXT,
    publisher           TEXT,
    language            TEXT,
    citation_count      INTEGER NOT NULL DEFAULT 0,
    primary_category_id TEXT REFERENCES categories(id),
    research_job_id     TEXT REFERENCES research_jobs(id),
    raw_source_data     JSONB NOT NULL DEFAULT '{}',  -- preserved raw payload(s), never overwritten by LLM
    possible_duplicate_of UUID REFERENCES papers(id),  -- set by fuzzy matching, never auto-merged
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_papers_doi UNIQUE (doi)
);

CREATE INDEX IF NOT EXISTS idx_papers_doi ON papers(doi);
CREATE INDEX IF NOT EXISTS idx_papers_title_normalized ON papers(title_normalized);
CREATE INDEX IF NOT EXISTS idx_papers_publication_date ON papers(publication_date);
CREATE INDEX IF NOT EXISTS idx_papers_primary_category ON papers(primary_category_id);

-- ----------------------------------------------------------------
-- authors + paper_authors (many-to-many)
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS authors (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    display_name    TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    CONSTRAINT uq_authors_normalized_name UNIQUE (normalized_name)
);

CREATE INDEX IF NOT EXISTS idx_authors_normalized_name ON authors(normalized_name);

CREATE TABLE IF NOT EXISTS paper_authors (
    paper_id    UUID NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    author_id   UUID NOT NULL REFERENCES authors(id) ON DELETE CASCADE,
    author_order INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (paper_id, author_id)
);

-- ----------------------------------------------------------------
-- paper_categories (many-to-many, a paper may span multiple categories)
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS paper_categories (
    paper_id    UUID NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    category_id TEXT NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
    PRIMARY KEY (paper_id, category_id)
);

-- ----------------------------------------------------------------
-- paper_sources: which source(s) a paper was found in + its external id
-- (this is how "Original paper -> arXiv ID / OpenAlex ID / DOI" is tracked)
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS paper_sources (
    id              BIGSERIAL PRIMARY KEY,
    paper_id        UUID NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    source_id       INTEGER NOT NULL REFERENCES sources(id),
    external_id     TEXT NOT NULL,
    source_url      TEXT,
    fetched_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_paper_source_external UNIQUE (source_id, external_id)
);

CREATE INDEX IF NOT EXISTS idx_paper_sources_paper_id ON paper_sources(paper_id);
CREATE INDEX IF NOT EXISTS idx_paper_sources_source_id ON paper_sources(source_id);

-- ----------------------------------------------------------------
-- citations: point-in-time citation count snapshots (per source, per fetch)
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS citations (
    id              BIGSERIAL PRIMARY KEY,
    paper_id        UUID NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    source_id       INTEGER REFERENCES sources(id),
    citation_count  INTEGER NOT NULL DEFAULT 0,
    recorded_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_citations_paper_id ON citations(paper_id);

-- ----------------------------------------------------------------
-- llm_enrichments: validated (or failed) LLM output, kept separate from
-- the original paper data per the "never overwrite raw data" principle
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS llm_enrichments (
    id              BIGSERIAL PRIMARY KEY,
    paper_id        UUID NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    model_name      TEXT NOT NULL,
    summary         TEXT,
    topics          TEXT[] NOT NULL DEFAULT '{}',
    research_area   TEXT,
    confidence      REAL,
    status          TEXT NOT NULL DEFAULT 'PENDING'
                        CHECK (status IN ('PENDING','VALID','FAILED_REVIEW')),
    raw_response    TEXT,               -- exact text returned by the LLM, for debugging
    validation_errors TEXT[] NOT NULL DEFAULT '{}',
    attempt_count   INTEGER NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_llm_enrichment_paper UNIQUE (paper_id)
);

CREATE INDEX IF NOT EXISTS idx_llm_enrichments_status ON llm_enrichments(status);

-- ----------------------------------------------------------------
-- quality_checks: pipeline-level data quality results per job
-- ----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS quality_checks (
    id              BIGSERIAL PRIMARY KEY,
    job_id          TEXT NOT NULL REFERENCES research_jobs(id) ON DELETE CASCADE,
    check_name      TEXT NOT NULL,       -- e.g. 'missing_abstract_rate', 'possible_duplicates'
    passed          BOOLEAN NOT NULL DEFAULT true,
    details         JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_quality_checks_job_id ON quality_checks(job_id);

-- ----------------------------------------------------------------
-- Seed categories table from config (kept in sync by scripts/init_database.py,
-- this INSERT is a safety net for a bare `psql -f schema.sql` run)
-- ----------------------------------------------------------------
INSERT INTO categories (id, label) VALUES
    ('artificial_intelligence', 'Artificial Intelligence'),
    ('machine_learning', 'Machine Learning'),
    ('natural_language_processing', 'Natural Language Processing'),
    ('computer_vision', 'Computer Vision'),
    ('cybersecurity', 'Cybersecurity'),
    ('data_science', 'Data Science'),
    ('robotics', 'Robotics'),
    ('cloud_computing', 'Cloud Computing'),
    ('quantum_computing', 'Quantum Computing'),
    ('software_engineering', 'Software Engineering'),
    ('information_retrieval', 'Information Retrieval'),
    ('human_computer_interaction', 'Human Computer Interaction'),
    ('uncategorized', 'Uncategorized')
ON CONFLICT (id) DO NOTHING;
