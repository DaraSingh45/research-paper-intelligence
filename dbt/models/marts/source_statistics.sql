-- Papers per source, source overlap (papers found in more than one source),
-- and an estimated duplicate rate.
with per_source as (
    select source_name, count(distinct paper_id) as paper_count
    from {{ ref('int_paper_sources') }}
    where not is_possible_duplicate
    group by source_name
),
per_paper_source_count as (
    select paper_id, count(distinct source_id) as source_count
    from {{ ref('int_paper_sources') }}
    where not is_possible_duplicate
    group by paper_id
),
overlap as (
    select count(*) as papers_in_multiple_sources
    from per_paper_source_count
    where source_count > 1
),
totals as (
    select count(*) as total_unique_papers from {{ ref('stg_papers') }} where not is_possible_duplicate
),
possible_dupes as (
    select count(*) as possible_duplicate_count from {{ ref('stg_papers') }} where is_possible_duplicate
)
select
    ps.source_name,
    ps.paper_count,
    o.papers_in_multiple_sources,
    t.total_unique_papers,
    pd.possible_duplicate_count,
    round(100.0 * o.papers_in_multiple_sources / nullif(t.total_unique_papers, 0), 2) as source_overlap_pct,
    round(100.0 * pd.possible_duplicate_count / nullif(t.total_unique_papers + pd.possible_duplicate_count, 0), 2) as possible_duplicate_rate_pct
from per_source ps
cross join overlap o
cross join totals t
cross join possible_dupes pd
order by ps.paper_count desc
