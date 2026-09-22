-- Citation fact table: one row per paper with rank/percentile so the UI
-- can surface "highly cited" papers without recomputing this every time.
select
    paper_id,
    citation_count,
    publication_date,
    primary_category_id,
    rank() over (order by citation_count desc)             as citation_rank,
    percent_rank() over (order by citation_count)           as citation_percentile
from {{ ref('stg_papers') }}
where not is_possible_duplicate
