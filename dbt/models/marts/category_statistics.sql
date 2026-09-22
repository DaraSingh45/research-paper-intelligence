-- Category distribution + month-over-month growth per category.
with monthly as (
    select
        category_id,
        category_label,
        date_trunc('month', publication_date)::date as month,
        count(distinct paper_id) as paper_count
    from {{ ref('int_paper_categories') }}
    where publication_date is not null and not is_possible_duplicate
    group by 1, 2, 3
)
select
    category_id,
    category_label,
    month,
    paper_count,
    lag(paper_count) over (partition by category_id order by month) as previous_month_count,
    round(
        100.0 * (paper_count - lag(paper_count) over (partition by category_id order by month))
        / nullif(lag(paper_count) over (partition by category_id order by month), 0), 2
    ) as growth_pct,
    sum(paper_count) over (partition by category_id order by month) as cumulative_paper_count
from monthly
order by category_label, month
