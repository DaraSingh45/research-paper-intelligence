-- Citation summary stats: average, median, "highly cited" threshold
-- (90th percentile), and citations broken down by category.
with overall as (
    select
        round(avg(citation_count)::numeric, 2)                               as avg_citations,
        percentile_cont(0.5) within group (order by citation_count)          as median_citations,
        percentile_cont(0.9) within group (order by citation_count)          as p90_citations,
        max(citation_count)                                                   as max_citations
    from {{ ref('stg_papers') }}
    where not is_possible_duplicate
),
highly_cited as (
    -- Aggregates can't be referenced inside FILTER (...), so the p90
    -- threshold from `overall` is computed first and joined in here.
    select count(*) as highly_cited_paper_count
    from {{ ref('stg_papers') }} p
    cross join overall o
    where not p.is_possible_duplicate
      and p.citation_count >= o.p90_citations
),
by_category as (
    select
        category_id,
        category_label,
        round(avg(citation_count)::numeric, 2) as avg_citations,
        sum(citation_count)                    as total_citations,
        count(distinct paper_id)               as paper_count
    from {{ ref('int_paper_categories') }}
    where not is_possible_duplicate
    group by category_id, category_label
)
select
    o.avg_citations,
    o.median_citations,
    o.p90_citations                as highly_cited_threshold,
    o.max_citations,
    h.highly_cited_paper_count,
    bc.category_id,
    bc.category_label,
    bc.avg_citations               as category_avg_citations,
    bc.total_citations             as category_total_citations,
    bc.paper_count                 as category_paper_count
from overall o
cross join highly_cited h
cross join by_category bc
order by bc.total_citations desc
