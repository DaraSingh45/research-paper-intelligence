-- One row per (paper, author) with the fields needed for author analytics.
select
    pa.paper_id,
    pa.author_id,
    pa.author_order,
    a.display_name,
    a.normalized_name,
    p.publication_date,
    p.citation_count,
    p.primary_category_id,
    p.is_possible_duplicate
from {{ source('raw', 'paper_authors') }} pa
join {{ ref('stg_authors') }} a on a.author_id = pa.author_id
join {{ ref('stg_papers') }} p on p.paper_id = pa.paper_id
