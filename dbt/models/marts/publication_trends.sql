-- Publication counts per day / week / month / year, with period-over-period
-- growth computed via a window function (LAG), per granularity.
with by_period as (
    select date_trunc('day', publication_date)::date as period, 'day' as granularity, count(*) as paper_count
    from {{ ref('stg_papers') }}
    where publication_date is not null and not is_possible_duplicate
    group by 1

    union all

    select date_trunc('week', publication_date)::date, 'week', count(*)
    from {{ ref('stg_papers') }}
    where publication_date is not null and not is_possible_duplicate
    group by 1

    union all

    select date_trunc('month', publication_date)::date, 'month', count(*)
    from {{ ref('stg_papers') }}
    where publication_date is not null and not is_possible_duplicate
    group by 1

    union all

    select date_trunc('year', publication_date)::date, 'year', count(*)
    from {{ ref('stg_papers') }}
    where publication_date is not null and not is_possible_duplicate
    group by 1
)
select
    period,
    granularity,
    paper_count,
    lag(paper_count) over (partition by granularity order by period)                as previous_period_count,
    paper_count - lag(paper_count) over (partition by granularity order by period)  as change_abs,
    round(
        100.0 * (paper_count - lag(paper_count) over (partition by granularity order by period))
        / nullif(lag(paper_count) over (partition by granularity order by period), 0), 2
    ) as change_pct
from by_period
order by granularity, period
