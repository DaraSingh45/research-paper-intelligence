select
    id      as category_id,
    label   as category_label
from {{ source('raw', 'categories') }}
