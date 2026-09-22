-- One row per (paper, source) with fields needed for source-overlap analytics.
select
    ps.paper_id,
    ps.source_id,
    s.source_name,
    ps.external_id,
    p.publication_date,
    p.is_possible_duplicate
from {{ source('raw', 'paper_sources') }} ps
join {{ ref('stg_sources') }} s on s.source_id = ps.source_id
join {{ ref('stg_papers') }} p on p.paper_id = ps.paper_id
