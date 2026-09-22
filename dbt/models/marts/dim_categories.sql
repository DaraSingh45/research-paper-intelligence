-- Category dimension: aggregated publication/citation stats per category.
select
    category_id,
    category_label,
    count(distinct paper_id)                               as paper_count,
    coalesce(sum(citation_count), 0)                        as total_citations,
    round(coalesce(avg(citation_count), 0)::numeric, 2)     as avg_citations,
    round(
        100.0 * count(distinct paper_id) / nullif(sum(count(distinct paper_id)) over (), 0), 2
    ) as pct_of_all_papers
from {{ ref('int_paper_categories') }}
where not is_possible_duplicate
group by category_id, category_label
