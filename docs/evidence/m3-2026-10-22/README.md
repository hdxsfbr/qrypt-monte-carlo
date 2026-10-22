# Benchmarks against the live deployment, 22 October 2026

Measured from a Linux workstation on the US West Coast against the deployed Function URL in `us-east-1`
(so every client-side time includes a cross-country network round trip). All times are US Central Time
(CT). Each benchmark was run once with the method in `docs/DESIGN.md` section 7 and is reported as
measured. Nothing was tuned between runs.

Terms used below:

- **p50 / p95:** the time within which 50% / 95% of the calls finished (nearest-rank method).
- **Warm:** the function was already running from an earlier call, so there is no start-up delay.
  The first call of each benchmark is a warm-up and is not counted.
- **Client side:** timed by the script from sending the request until the full reply arrived.
- **Server side:** the run time AWS reports for each function call (`durationMs` in the Lambda
  `platform.report` log line).
- **Shard:** one piece of a job, run by one worker function call.
- **SE (standard error):** how much the estimate would typically move with new randomness.
- **GB-second:** the unit Lambda compute is counted in: memory in GB times run time in seconds.

## NFR-1: submit latency, target under 800 ms at p95 (warm)

Script: `scripts/bench_submit.py` (default settings). One warm-up call, then 50 `POST /jobs` calls, each a
small job (10,000 paths, 1 shard), one call every 2 seconds. Run 5:21:29 to 5:23:09 PM CT.

| Measure | p50 | p95 | min | max |
|---------|-----|-----|-----|-----|
| Client side (50 calls, all HTTP 202) | 396.6 ms | 490.3 ms | 344.2 ms | 659.6 ms |
| Server side, api function (51 calls incl. warm-up) | 137.0 ms | 210.1 ms | | 235.4 ms |

Result: **met** (490 ms p95 client side, against an 800 ms target). Most of the server-side time is the
1 KiB Qrypt request made for every new job.

**Qrypt rate limit finding.** A first attempt at 5:20:33 PM CT paced the calls at 2 per second (the
pace planned in the design). Qrypt accepted two requests within half a second and rejected the third
with HTTP 429, so the API correctly answered 503 "Qrypt rate limit" and the script stopped. That is
stricter in short bursts than the documented 30 requests per 10 seconds. The script was changed to one
call every 2 seconds and to record (not crash on) a rejected call; the counted run had no rejections.

Files: `bench-submit.json` (every call), `lambda-reports.json` (server-side times).

## NFR-2: one job of 1,000,000 paths, target under 60 s from submit to COMPLETE (5 runs)

Script: `scripts/bench_job.py` (default settings). Five jobs one after another, each 1,000,000 paths in
10 shards, polling `GET /jobs/{id}` every 0.5 s. Run 5:23:20 to about 5:23:45 PM CT.

| Run | Client side (submit to COMPLETE seen) | Server side (`created_at` to `finished_at`) | Estimate | Gap to Black-Scholes |
|-----|------|------|----------|-----|
| 1 | 1.45 s | 0.94 s | 10.465275 | +1.00 SE |
| 2 | 3.85 s | 3.11 s | 10.450287 | -0.02 SE |
| 3 | 3.75 s | 3.21 s | 10.469987 | +1.32 SE |
| 4 | 3.01 s | 2.24 s | 10.437973 | -0.86 SE |
| 5 | 3.08 s | 2.21 s | 10.443619 | -0.47 SE |
| **Median / worst** | **3.08 s / 3.85 s** | **2.24 s / 3.21 s** | | all within 3 SE |

Black-Scholes price for these inputs: 10.450583572185565. SE for each run is about 0.0147.

Result: **met** (worst 3.85 s against a 60 s target).

**Shard write conflict finding.** The worker logs show 55 worker calls for 50 shards. In runs 2 to 5,
one or two shards failed their first attempt with `TransactionCanceledException`: two shards of the same
job tried to update the job's shared counter at the same moment, and DynamoDB refuses one of two
overlapping transactions. The refused shard was retried by SQS after the 2-second back-off and
succeeded on its second attempt, so every job finished COMPLETE with the right answer. This is why runs
2 to 5 take about 2 seconds longer than run 1. It is a real weakness: if the same shard lost three such
races in a row it would be marked FAILED and the job would end PARTIAL. The fix (not yet made, because
it changes the deployed code) is to retry a conflicted transaction inside the worker after a short
random pause, and to only treat "this shard is already recorded" as a duplicate.

Files: `bench-job.json` (every run), `lambda-reports.json` (worker times and memory).

## Measured compute per job (input to the cost note)

From `lambda-reports.json` (billed time from AWS, not estimates). That file was built by reading the
`platform.report` lines for each benchmark's time window with `aws logs filter-log-events --profile qmc`.

| Function | Calls | Billed time | Memory | GB-seconds |
|----------|-------|-------------|--------|------------|
| worker, the five 1M-path jobs (incl. 5 retries) | 55 | 6.287 s | 1769 MB | 10.861, so **2.17 per job** |
| api, the five 1M-path jobs (5 submits + 20 status checks) | 25 | 0.939 s | 512 MB | 0.469 |
| api, the 51 small submits | 51 | 7.415 s | 512 MB | 3.708, so **0.073 per submit** |

Peak memory used: worker 91 MB, api 97 MB.

## NFR-4: rebuild time

Not re-run here. The first `terraform apply` into the empty account on 22 October took about 84 seconds
(see `../m2-2026-10-22/README.md`), against a 10-minute target. A full destroy-and-rebuild would take the
graded endpoint offline and change its URL, so it is left for after grading.

## Qrypt usage in these benchmarks

58 KiB in 59 requests: the first, stopped attempt used 2 KiB (plus one request Qrypt rejected, which
returns no data), the counted latency run 51 KiB, and the five 1M-path jobs 5 KiB. Project total so far:
60 KiB of the 10,240 KiB (10 MB) allowance.
