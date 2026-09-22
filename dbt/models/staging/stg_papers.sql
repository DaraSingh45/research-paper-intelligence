-- Staging: one row per paper, lightly renamed/typed, raw JSON dropped
-- (raw data stays queryable directly in the source "papers" table).
select
    id                      as paper_id,
    title,
    title_normalized,
    abstract,
    publication_date,
    doi,
    url,
    pdf_url,
    journal,
    venue,
    publisher,
    language,
    citation_count,
    primary_category_id,
    research_job_id,
    (possible_duplicate_of is not null) as is_possible_duplicate,
    created_at
from {{ source('raw', 'papers') }}
