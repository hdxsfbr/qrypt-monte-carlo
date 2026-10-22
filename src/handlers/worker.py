"""Worker Lambda: simulate one shard per SQS message and record it; the last shard finishes the job.

Flow for one message ``{"job_id", "shard_index", "shard_count", "paths"}``:
1. Read the job (parameters, master seed, algorithm version).
2. Simulate the shard (``qmc.pipeline.run_shard``).
3. Record the result and add 1 to the job's ``completed`` count in one transaction. A repeated delivery
   is refused by the transaction and changes nothing (EC-2).
4. If every shard is now recorded, combine them in shard-index order and mark the job COMPLETE, or
   PARTIAL if any shard failed (EC-3).

On an error the message is retried (up to ``MAX_RECEIVE_COUNT`` deliveries, then SQS moves it to the
dead-letter queue, a holding queue for messages that keep failing). The worker shortens the wait before
each retry to 2, 4 and 8 seconds. On the last attempt it records the shard as FAILED first, so the job
ends PARTIAL instead of waiting forever.
"""

from __future__ import annotations

import json
import logging
import math
import time

from handlers import store
from handlers.common import client, emit_metrics, fault_injection_enabled, log_event, number, setting, utc_now
from qmc.aggregate import errors_from_reference
from qmc.black_scholes import call_price
from qmc.pipeline import ShardTask, aggregate, run_shard
from qmc.simulate import ShardResult


class InjectedFailure(RuntimeError):
    """Raised on purpose for shards listed in ``fail_shards`` (only when fault injection is switched on)."""


def handler(event, context):
    for record in event.get("Records", []):
        process(record)
    return {"processed": len(event.get("Records", []))}


def process(record: dict) -> None:
    msg = json.loads(record["body"])
    job_id, index = msg["job_id"], int(msg["shard_index"])
    attempt = int(record.get("attributes", {}).get("ApproximateReceiveCount", "1"))
    max_attempts = int(setting("MAX_RECEIVE_COUNT", "3"))

    job = store.get_job(job_id)
    if job is None:
        log_event("shard for unknown job dropped", logging.WARNING, job_id=job_id, shard=index)
        return
    if job["status"] in store.FINISHED:
        log_event("shard for finished job ignored", job_id=job_id, shard=index)
        return

    try:
        run(job, msg, attempt)
    except Exception as exc:
        log_event(
            "shard failed",
            logging.ERROR,
            job_id=job_id,
            shard=index,
            attempt=attempt,
            error=type(exc).__name__,
        )
        if attempt >= max_attempts:
            if store.record_shard(
                job_id,
                index,
                {"state": "FAILED", "error": f"{type(exc).__name__}: {exc}"[:300], "attempts": attempt},
                "failed",
            ):
                emit_metrics({"ShardFailures": 1}, job_id=job_id, shard=index)
            maybe_finish(job_id)
        retry_soon(record, attempt)
        raise


def run(job: dict, msg: dict, attempt: int) -> None:
    job_id, index = job["job_id"], int(msg["shard_index"])
    if fault_injection_enabled() and index in [int(i) for i in job.get("fail_shards", [])]:
        raise InjectedFailure(f"fault injection requested for shard {index}")
    params = store.params_of(job)
    task = ShardTask(index, int(msg["shard_count"]), int(msg["paths"]))
    start = time.perf_counter()
    result = run_shard(params, bytes.fromhex(job["master_seed_hex"]), task, job["algo_version"])
    duration_ms = (time.perf_counter() - start) * 1000
    fields = {
        "state": "DONE",
        # Exact binary values (float.hex) are what the job total is built from; the plain numbers are
        # for people reading the table.
        "sum_hex": result.sum.hex(),
        "sum_sq_hex": result.sum_sq.hex(),
        "sum": number(result.sum),
        "n": result.n,
        "duration_ms": number(round(duration_ms, 3)),
        "attempts": attempt,
    }
    if store.record_shard(job_id, index, fields, "completed"):
        emit_metrics({"PathsSimulated": result.n, "ShardDurationMs": duration_ms}, job_id=job_id, shard=index)
        log_event("shard done", job_id=job_id, shard=index, paths=result.n, duration_ms=round(duration_ms, 1))
    else:
        log_event("duplicate shard delivery ignored", job_id=job_id, shard=index)
    maybe_finish(job_id)


def retry_soon(record: dict, attempt: int) -> None:
    """Make the message visible again after 2, 4, 8 ... seconds instead of the queue's long default."""
    try:
        client("sqs").change_message_visibility(
            QueueUrl=setting("QUEUE_URL"),
            ReceiptHandle=record["receiptHandle"],
            VisibilityTimeout=min(2**attempt, 300),
        )
    except Exception as exc:  # the retry still happens, just later; never hide the original error
        log_event("could not shorten retry wait", logging.WARNING, error=type(exc).__name__)


def maybe_finish(job_id: str) -> None:
    job = store.get_job(job_id)
    if job is None or job["status"] != "QUEUED":
        return
    shards = int(job["shards"])
    if int(job.get("completed", 0)) + int(job.get("failed", 0)) < shards:
        return
    items = store.shard_items(job_id)
    _, finished_at = utc_now()
    failed = sorted(int(i["shard_index"]) for i in items if i["state"] == "FAILED")
    if failed:
        fields = {"status": "PARTIAL", "failed_shards": failed, "finished_at": finished_at}
    else:
        fields = {"status": "COMPLETE", "finished_at": finished_at, **result_fields(job, items)}
    if store.finish_job(job_id, fields):
        log_event("job finished", job_id=job_id, status=fields["status"])


def result_fields(job: dict, items: list[dict]) -> dict:
    params = store.params_of(job)
    by_index = {
        int(i["shard_index"]): ShardResult(
            float.fromhex(i["sum_hex"]), float.fromhex(i["sum_sq_hex"]), int(i["n"])
        )
        for i in items
    }
    est = aggregate(params, by_index)
    reference = call_price(params.S0, params.K, params.r, params.sigma, params.T)
    fields = {
        "result": {
            "estimate": number(est.estimate),
            "std_error": number(est.std_error),
            "ci95_low": number(est.ci95_low),
            "ci95_high": number(est.ci95_high),
            "n": est.n,
            "estimate_hex": est.estimate_hex,
        },
        "black_scholes": number(reference),
    }
    distance = errors_from_reference(est, reference)
    if math.isfinite(distance):  # infinite only if every path paid the same, so there is no spread
        fields["result"]["std_errors_from_black_scholes"] = number(round(distance, 4))
    original_id = job.get("replay_of")
    if original_id:
        original = store.get_job(original_id)
        original_hex = (original or {}).get("result", {}).get("estimate_hex")
        fields["replay_check"] = {
            "original_job_id": original_id,
            "original_estimate_hex": original_hex,
            "bit_identical": original_hex == est.estimate_hex,
        }
    return fields
