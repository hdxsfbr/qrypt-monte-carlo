Qrypt is a hard dependency for new jobs: an outage, a revoked token or an exhausted quota makes POST /jobs fail with 502/503 (by design there is no fallback). Replays and reads keep working.
