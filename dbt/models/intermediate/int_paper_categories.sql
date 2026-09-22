-- One row per (paper, category) with fields needed for category/topic analytics.
select
    pc.paper_id,
    pc.category_id,
    c.category_label,
    p.publication_date,
    p.citation_count,
    p.is_possible_duplicate
from {{ source('raw', 'paper_categories') }} pc
join {{ ref('stg_categories') }} c on c.category_id = pc.category_id
join {{ ref('stg_papers') }} p on p.paper_id = pc.paper_id
