-- Most frequent authors, plus a breakdown of the categories/topics they
-- publish in (Section 23: "authors by category", "authors by topic").
with author_categories as (
    select
        ipa.author_id,
        ipa.display_name,
        ipc.category_label,
        count(distinct ipa.paper_id) as papers_in_category
    from {{ ref('int_paper_authors') }} ipa
    join {{ ref('int_paper_categories') }} ipc on ipc.paper_id = ipa.paper_id
    where not ipa.is_possible_duplicate
    group by ipa.author_id, ipa.display_name, ipc.category_label
)
select
    a.author_id,
    a.display_name,
    a.paper_count,
    a.total_citations,
    a.avg_citations,
    a.rank_by_paper_count,
    (
        select array_agg(distinct ac.category_label)
        from author_categories ac
        where ac.author_id = a.author_id
    ) as categories,
    (
        select ac.category_label
        from author_categories ac
        where ac.author_id = a.author_id
        order by ac.papers_in_category desc
        limit 1
    ) as top_category
from {{ ref('dim_authors') }} a
order by a.paper_count desc, a.total_citations desc
