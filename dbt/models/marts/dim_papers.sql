-- Paper dimension: one row per paper, enriched with its primary category
-- label and (optional) validated LLM enrichment. LLM fields are always
-- kept separate from the original title/abstract columns.
select
    p.paper_id,
    p.title,
    p.abstract,
    p.publication_date,
    p.doi,
    p.url,
    p.pdf_url,
    p.journal,
    p.venue,
    p.publisher,
    p.language,
    p.citation_count,
    p.is_possible_duplicate,
    p.primary_category_id,
    c.category_label as primary_category_label,
    le.summary          as llm_summary,
    le.topics           as llm_topics,
    le.research_area    as llm_research_area,
    le.confidence       as llm_confidence,
    le.status           as llm_status
from {{ ref('stg_papers') }} p
left join {{ ref('stg_categories') }} c on c.category_id = p.primary_category_id
left join {{ source('raw', 'llm_enrichments') }} le on le.paper_id = p.paper_id
