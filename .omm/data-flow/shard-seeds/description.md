32-byte per-shard seeds from HKDF-SHA256 (seeds.shard_seed): salt = ALGO_VERSION, info = "shard" || index (4 bytes BE) || count (4 bytes BE). Computed inside the worker on demand; never stored.
