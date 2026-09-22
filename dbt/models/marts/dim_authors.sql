-- Author dimension: aggregated publication/citation stats per author.
select
    author_id,
    display_name,
    count(distinct paper_id)                              as paper_count,
    coalesce(sum(citation_count), 0)                       as total_citations,
    round(coalesce(avg(citation_count), 0)::numeric, 2)    as avg_citations,
    array_agg(distinct primary_category_id)                as category_ids,
    min(publication_date)                                  as first_publication_date,
    max(publication_date)                                  as latest_publication_date,
    row_number() over (order by count(distinct paper_id) desc, sum(citation_count) desc) as rank_by_paper_count
from {{ ref('int_paper_authors') }}
where not is_possible_duplicate
group by author_id, display_name
