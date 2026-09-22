-- Growth of LLM-derived topics over time (monthly buckets), using unnest()
-- on the topics array plus a LAG window function per topic.
with paper_topics as (
    select
        p.paper_id,
        p.publication_date,
        unnest(le.topics) as topic
    from {{ ref('stg_papers') }} p
    join {{ source('raw', 'llm_enrichments') }} le on le.paper_id = p.paper_id
    where le.status = 'VALID'
      and not p.is_possible_duplicate
      and p.publication_date is not null
),
monthly as (
    select
        date_trunc('month', publication_date)::date as month,
        topic,
        count(distinct paper_id) as paper_count
    from paper_topics
    group by 1, 2
)
select
    month,
    topic,
    paper_count,
    lag(paper_count) over (partition by topic order by month) as previous_month_count,
    round(
        100.0 * (paper_count - lag(paper_count) over (partition by topic order by month))
        / nullif(lag(paper_count) over (partition by topic order by month), 0), 2
    ) as growth_pct
from monthly
order by topic, month
