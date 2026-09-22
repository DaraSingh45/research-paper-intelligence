select
    id              as author_id,
    display_name,
    normalized_name
from {{ source('raw', 'authors') }}
