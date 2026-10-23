If SendMessageBatch partially fails, the API returns 503 but the job item already exists; it remains QUEUED with missing shards until a GET after 10 minutes marks it PARTIAL.
