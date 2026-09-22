select
    id      as source_id,
    name    as source_name
from {{ source('raw', 'sources') }}
