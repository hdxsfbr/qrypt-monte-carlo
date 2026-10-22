#!/usr/bin/env python3
"""Job wall-clock benchmark (NFR-2): N jobs of 1,000,000 paths in 10 shards, one after another.

Each run is timed on the client from sending `POST /jobs` until the first `COMPLETE` seen while polling
every 0.5 s, and also on the server from the job's `created_at` to `finished_at`.
Each job uses 1 KiB of Qrypt entropy, so the default run uses 5 KiB.

Reads QMC_URL and API_KEY from the environment or `.env` (never printed).
Usage: python3 scripts/bench_job.py [--runs 5] [--out results.json]
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
from qmc.cli import request  # noqa: E402

BODY = {"S0": 100, "K": 100, "r": 0.05, "sigma": 0.2, "T": 1, "paths": 1_000_000, "shards": 10}
FINISHED = {"COMPLETE", "PARTIAL"}


def parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def one_run(timeout_s: float) -> dict:
    start = time.perf_counter()
    _, sub = request("POST", "/jobs", BODY)
    job_id = sub["job_id"]
    while True:
        _, job = request("GET", f"/jobs/{job_id}")
        if job["status"] in FINISHED:
            break
        if time.perf_counter() - start > timeout_s:
            raise SystemExit(f"job {job_id} still {job['status']} after {timeout_s} s")
        time.sleep(0.5)
    client_s = time.perf_counter() - start
    res = job.get("result", {})
    se = res.get("std_error") or res.get("se")
    est = res.get("estimate") or res.get("price")
    bs = job.get("black_scholes")
    return {
        "job_id": job_id,
        "status": job["status"],
        "client_s": round(client_s, 2),
        "server_s": round((parse_ts(job["finished_at"]) - parse_ts(job["created_at"])).total_seconds(), 3),
        "estimate": est,
        "std_error": se,
        "black_scholes": bs,
        "error_in_se": round((est - bs) / se, 3) if None not in (est, se, bs) else None,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--timeout", type=float, default=120)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()

    started = datetime.now(UTC).isoformat(timespec="seconds")
    runs = []
    for i in range(args.runs):
        r = one_run(args.timeout)
        line = f"run {i + 1}: {r['status']}, client {r['client_s']} s, server {r['server_s']} s"
        print(line, file=sys.stderr)
        runs.append(r)
        time.sleep(1)
    client = [r["client_s"] for r in runs]
    summary = {
        "benchmark": "NFR-2 job wall-clock, 1,000,000 paths in 10 shards",
        "started_utc": started,
        "job": BODY,
        "runs": runs,
        "client_median_s": statistics.median(client),
        "client_worst_s": max(client),
        "server_median_s": statistics.median(r["server_s"] for r in runs),
        "server_worst_s": max(r["server_s"] for r in runs),
        "all_complete": all(r["status"] == "COMPLETE" for r in runs),
        "qrypt_kib_used": len(runs),
    }
    text = json.dumps(summary, indent=2)
    if args.out:
        args.out.write_text(text + "\n")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
