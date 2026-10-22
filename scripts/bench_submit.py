#!/usr/bin/env python3
"""Submit-latency benchmark (NFR-1): 1 warm-up call, then N timed `POST /jobs` calls.

Each job is small (10,000 paths, 1 shard) so compute stays tiny; calls are paced (default one every 2 s),
under the API rate limit (25 jobs per 10 s) and the Qrypt limit (documented as 30 requests per 10 s;
a faster first attempt at 2 calls per second was rejected by Qrypt on its third call).
Each submitted job uses 1 KiB of Qrypt entropy, so the default run uses 51 KiB.

Reads QMC_URL and API_KEY from the environment or `.env` (never printed).
Usage: python3 scripts/bench_submit.py [--count 50] [--out results.json]
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from qmc.cli import CliError, request  # noqa: E402

BODY = {"S0": 100, "K": 100, "r": 0.05, "sigma": 0.2, "T": 1, "paths": 10_000, "shards": 1}


def percentile(values: list[float], p: float) -> float:
    """Nearest-rank percentile: the smallest value with at least p% of values at or below it."""
    ordered = sorted(values)
    rank = max(1, -(-len(ordered) * p // 100))  # ceiling
    return ordered[int(rank) - 1]


def timed_submit() -> tuple[float, str, int | str]:
    """One timed call. A rejected call is recorded with its error text instead of stopping the run."""
    start = time.perf_counter()
    try:
        status, data = request("POST", "/jobs", BODY)
    except CliError as err:
        return (time.perf_counter() - start) * 1000, "", str(err)
    return (time.perf_counter() - start) * 1000, data.get("job_id", ""), status


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--count", type=int, default=50)
    ap.add_argument("--interval", type=float, default=2.0, help="seconds between call starts")
    ap.add_argument("--max-rejects", type=int, default=5, help="stop after this many rejected calls")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()

    started = datetime.now(UTC).isoformat(timespec="seconds")
    warm_ms, warm_id, _ = timed_submit()
    print(f"warm-up: {warm_ms:.0f} ms (not counted)", file=sys.stderr)
    calls = []
    for i in range(args.count):
        t0 = time.monotonic()
        ms, job_id, status = timed_submit()
        calls.append({"n": i + 1, "ms": round(ms, 1), "http": status, "job_id": job_id})
        if sum(c["http"] != 202 for c in calls) >= args.max_rejects:
            print(f"stopping: {args.max_rejects} rejected calls", file=sys.stderr)
            break
        time.sleep(max(0.0, args.interval - (time.monotonic() - t0)))
    ok = [c for c in calls if c["http"] == 202]
    times = [c["ms"] for c in ok]
    summary = {
        "benchmark": "NFR-1 submit latency (client side, warm)",
        "started_utc": started,
        "job": BODY,
        "interval_s": args.interval,
        "count_attempted": len(calls),
        "count": len(times),
        "rejected": [c for c in calls if c["http"] != 202],
        "warmup_ms": round(warm_ms, 1),
        "warmup_job_id": warm_id,
        "p50_ms": round(statistics.median(times), 1),
        "p95_ms": round(percentile(times, 95), 1),
        "min_ms": min(times),
        "max_ms": max(times),
        "mean_ms": round(statistics.fmean(times), 1),
        "all_http_202": len(ok) == len(calls),
        "qrypt_kib_used": len(times) + (1 if warm_id else 0),
        "calls": calls,
    }
    text = json.dumps(summary, indent=2)
    if args.out:
        args.out.write_text(text + "\n")
    print(json.dumps({k: v for k, v in summary.items() if k != "calls"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
