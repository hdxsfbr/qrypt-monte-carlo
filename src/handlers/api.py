"""API Lambda behind the Function URL (an HTTPS address AWS gives a function directly).

Routes (docs/DESIGN.md, section 2):
- ``POST /jobs``: check the input and our rate limit, fetch 1 KiB from Qrypt, store the job, queue one
  message per shard. 202 with the job id.
- ``GET /jobs``: recent jobs, newest first, in pages.
- ``GET /jobs/{id}``: status, progress, result and the Black-Scholes reference price.
- ``POST /jobs/{id}/replay``: a new job with the same seed and inputs (no Qrypt call).
- ``GET /health``: can the function reach DynamoDB and SSM Parameter Store?

Every route needs ``Authorization: Bearer <API key>`` unless the deployment uses AWS_IAM (signed AWS
requests, checked by AWS before the function runs). Any unexpected error becomes a plain 500 with the
request id; details go to the log, never to the caller.
"""

from __future__ import annotations

import base64
import binascii
import hmac
import json
import logging
import re
import time
import uuid

from botocore.exceptions import BotoCoreError, ClientError

from handlers import store
from handlers.common import (
    client,
    emit_metrics,
    limits_from_env,
    log_event,
    number,
    plain,
    setting,
    utc_now,
)
from qmc import ALGO_VERSION
from qmc.black_scholes import call_price
from qmc.entropy import EntropyError, EntropySource, QryptEntropySource
from qmc.params import JobParams, ValidationError, validate_job_request
from qmc.pipeline import plan_shards
from qmc.seeds import block_fingerprint, master_seed_from_block

MAX_BODY_BYTES = 4096
SECRET_CACHE_S = 300  # keys read from SSM are reused for 5 minutes per function copy
STALE_AFTER_S = 600  # a job still missing shards after 10 minutes is shown as PARTIAL
RUNTIME = "python3.13"
JOB_PATH = re.compile(r"^/jobs/([0-9a-f-]{36})(/replay)?$")

log = logging.getLogger("qmc")
_secrets: dict[str, tuple[float, str]] = {}


def read_secret(name: str) -> str:
    """A SecureString from SSM Parameter Store, cached briefly. Never logged."""
    cached = _secrets.get(name)
    if cached and time.monotonic() - cached[0] < SECRET_CACHE_S:
        return cached[1]
    value = client("ssm").get_parameter(Name=name, WithDecryption=True)["Parameter"]["Value"]
    _secrets[name] = (time.monotonic(), value)
    return value


def default_entropy() -> EntropySource:
    return QryptEntropySource(read_secret(setting("QRYPT_PARAM_NAME")))


# Tests and local runs replace this with a function returning a MockEntropySource.
entropy_factory = default_entropy


class HttpError(Exception):
    def __init__(self, status: int, body: dict, headers: dict | None = None):
        super().__init__(body.get("error"))
        self.status, self.body, self.headers = status, body, headers or {}


def response(status: int, body: dict, headers: dict | None = None) -> dict:
    return {
        "statusCode": status,
        "headers": {"content-type": "application/json", "cache-control": "no-store", **(headers or {})},
        "body": json.dumps(plain(body)),
    }


def handler(event, context):
    request_id = getattr(context, "aws_request_id", "local")
    try:
        return route(event, request_id)
    except HttpError as err:
        return response(err.status, err.body, err.headers)
    except Exception:
        log.exception("unhandled error", extra={"qmc": {"request_id": request_id}})
        return response(500, {"error": "internal error", "request_id": request_id})


def route(event: dict, request_id: str) -> dict:
    http = event.get("requestContext", {}).get("http", {})
    method, path = http.get("method", "GET").upper(), event.get("rawPath", "/").rstrip("/") or "/"
    authorize(event)
    if path == "/health":
        return only(method, "GET") or health()
    if path == "/jobs":
        if method == "GET":
            return list_jobs(event.get("queryStringParameters") or {})
        return only(method, "POST") or submit(read_body(event), request_id)
    match = JOB_PATH.match(path)
    if match and _valid_uuid(match.group(1)):
        job_id, replay = match.group(1), bool(match.group(2))
        if replay:
            return only(method, "POST") or replay_job(job_id, request_id)
        return only(method, "GET") or get_job(job_id)
    if path.startswith("/jobs/"):
        return response(404, {"error": "job not found", "job_id": path.removeprefix("/jobs/").split("/")[0]})
    return response(404, {"error": "no such route"})


def only(method: str, allowed: str) -> dict | None:
    if method != allowed:
        return response(405, {"error": f"use {allowed}"}, {"allow": allowed})
    return None


def _valid_uuid(text: str) -> bool:
    try:
        return str(uuid.UUID(text)) == text
    except ValueError:
        return False


# ---- auth and input ---------------------------------------------------------------------------------


def authorize(event: dict) -> None:
    if setting("AUTH_TYPE", "BEARER") == "AWS_IAM":
        return  # AWS already checked the request signature before invoking us
    header = (event.get("headers") or {}).get("authorization", "")
    scheme, _, supplied = header.partition(" ")
    expected = read_secret(setting("API_KEY_PARAM_NAME"))
    # compare_digest takes the same time whether the first or the last character differs, so the key
    # cannot be guessed by timing responses.
    if scheme.lower() != "bearer" or not hmac.compare_digest(supplied.encode(), expected.encode()):
        raise HttpError(401, {"error": "unauthorized"})


def read_body(event: dict) -> object:
    raw = event.get("body") or ""
    if event.get("isBase64Encoded"):
        try:
            data = base64.b64decode(raw, validate=True)
        except (binascii.Error, ValueError) as err:
            raise HttpError(400, {"error": "body: must be valid JSON", "field": "body"}) from err
    else:
        data = raw.encode()
    if len(data) > MAX_BODY_BYTES:
        raise HttpError(400, {"error": f"body: must be at most {MAX_BODY_BYTES} bytes", "field": "body"})
    try:
        return json.loads(data)
    except (json.JSONDecodeError, UnicodeDecodeError) as err:
        raise HttpError(400, {"error": "body: must be valid JSON", "field": "body"}) from err


# ---- routes -----------------------------------------------------------------------------------------


def submit(body: object, request_id: str) -> dict:
    try:
        req = validate_job_request(body, limits_from_env())
    except ValidationError as err:
        return response(400, {"error": str(err), "field": err.field})
    now, fetched_at = utc_now()
    allowed, wait = store.take_rate_slot(now)
    if not allowed:
        return response(
            429,
            {"error": "too many new jobs; try again shortly", "retry_after_s": wait},
            {"retry-after": str(wait)},
        )
    started = time.perf_counter()
    try:
        block = entropy_factory().fetch()
    except EntropyError as err:
        emit_metrics({"QryptErrors": 1}, cause=err.cause, request_id=request_id)
        log_event("qrypt fetch failed", logging.WARNING, cause=err.cause, request_id=request_id)
        return response(err.client_status, {"error": err.message, "cause": err.cause})
    qrypt_ms = round((time.perf_counter() - started) * 1000, 1)
    seed_source = {
        "provider": "qrypt",
        "kib": 1,
        "block_sha256": block_fingerprint(block),
        "fetched_at": fetched_at,
    }
    job = create_job(req.params, master_seed_from_block(block), seed_source, list(req.fail_shards))
    emit_metrics({"JobsSubmitted": 1, "EntropyKiB": 1}, job_id=job["job_id"], request_id=request_id)
    log_event("job submitted", job_id=job["job_id"], request_id=request_id, qrypt_ms=qrypt_ms)
    return accepted(job)


def replay_job(job_id: str, request_id: str) -> dict:
    original = store.get_job(job_id)
    if original is None:
        return response(404, {"error": "job not found", "job_id": job_id})
    if original["status"] != "COMPLETE":
        return response(
            409,
            {"error": "only a COMPLETE job can be replayed", "job_id": job_id, "status": original["status"]},
        )
    job = create_job(
        store.params_of(original),
        bytes.fromhex(original["master_seed_hex"]),
        {"replay_of": job_id},
        [],
        replay_of=job_id,
        algo_version=original["algo_version"],
    )
    emit_metrics({"JobsSubmitted": 1, "EntropyKiB": 0}, job_id=job["job_id"], request_id=request_id)
    log_event("replay submitted", job_id=job["job_id"], replay_of=job_id, request_id=request_id)
    return accepted(job)


def accepted(job: dict) -> dict:
    return response(
        202,
        {
            "job_id": job["job_id"],
            "status": "QUEUED",
            "shards": job["shards"],
            "replay_of": job.get("replay_of"),
            "links": {"self": f"/jobs/{job['job_id']}"},
        },
    )


def create_job(
    params: JobParams,
    master_seed: bytes,
    seed_source: dict,
    fail_shards: list[int],
    replay_of: str | None = None,
    algo_version: str = ALGO_VERSION,
) -> dict:
    job_id = str(uuid.uuid4())
    _, created_at = utc_now()
    job = {
        "job_id": job_id,
        "status": "QUEUED",
        "params": store.params_item(params),
        "shards": params.shards,
        "completed": 0,
        "failed": 0,
        "master_seed_hex": master_seed.hex(),
        "seed_source": seed_source,
        "algo_version": algo_version,
        "runtime": RUNTIME,
        "created_at": created_at,
        "created_ts": number(round(time.time(), 3)),
        "gsi1pk": "JOBS",
        "gsi1sk": f"{created_at}#{job_id}",
    }
    if fail_shards:
        job["fail_shards"] = fail_shards
    if replay_of:
        job["replay_of"] = replay_of
    store.put_job(job)
    enqueue(job_id, params)
    return job


def enqueue(job_id: str, params: JobParams) -> None:
    tasks = plan_shards(params)
    queue = setting("QUEUE_URL")
    for start in range(0, len(tasks), 10):  # SQS takes at most 10 messages per batch
        batch = tasks[start : start + 10]
        resp = client("sqs").send_message_batch(
            QueueUrl=queue,
            Entries=[
                {
                    "Id": str(t.shard_index),
                    "MessageBody": json.dumps(
                        {
                            "job_id": job_id,
                            "shard_index": t.shard_index,
                            "shard_count": t.shard_count,
                            "paths": t.paths,
                        }
                    ),
                }
                for t in batch
            ],
        )
        if resp.get("Failed"):
            # The job stays QUEUED with shards missing; after 10 minutes GET shows it as PARTIAL.
            log_event("could not queue shards", logging.ERROR, job_id=job_id, failed=len(resp["Failed"]))
            raise HttpError(503, {"error": "could not queue all shards; try again", "job_id": job_id})


def get_job(job_id: str) -> dict:
    job = store.get_job(job_id)
    if job is None:
        return response(404, {"error": "job not found", "job_id": job_id})
    if job["status"] == "QUEUED" and time.time() - float(job["created_ts"]) > STALE_AFTER_S:
        job = mark_stale(job)
    return response(200, view(job))


def mark_stale(job: dict) -> dict:
    """A shard whose worker died without recording anything never arrives. After 10 minutes, list the
    missing shards and mark the job PARTIAL, so it never waits forever and is never COMPLETE."""
    shards = int(job["shards"])
    items = store.shard_items(job["job_id"])
    done = {int(i["shard_index"]) for i in items if i["state"] == "DONE"}
    missing = [i for i in range(shards) if i not in done]
    if not missing:
        return job  # all in; the last worker is finishing the job right now
    _, finished_at = utc_now()
    store.finish_job(
        job["job_id"],
        {"status": "PARTIAL", "failed_shards": missing, "finished_at": finished_at, "stale": True},
    )
    return store.get_job(job["job_id"]) or job


def view(job: dict) -> dict:
    params = store.params_of(job)
    done = int(job.get("completed", 0)) + int(job.get("failed", 0))
    status = job["status"]
    if status == "QUEUED" and done > 0:
        status = "RUNNING"  # stored as QUEUED until the end; shown as RUNNING once a shard is in
    out = {
        "job_id": job["job_id"],
        "status": status,
        "progress": {
            "completed": job.get("completed", 0),
            "failed": job.get("failed", 0),
            "shards": job["shards"],
        },
        "params": params.to_dict(),
        "black_scholes": call_price(params.S0, params.K, params.r, params.sigma, params.T),
        "master_seed_hex": job["master_seed_hex"],
        "seed_source": job["seed_source"],
        "algo_version": job["algo_version"],
        "runtime": job["runtime"],
        "created_at": job["created_at"],
    }
    for key in ("finished_at", "result", "failed_shards", "replay_of", "replay_check", "fail_shards"):
        if key in job:
            out[key] = job[key]
    return out


def list_jobs(query: dict) -> dict:
    try:
        limit = int(query.get("limit", "20"))
    except ValueError:
        limit = 0
    if not 1 <= limit <= 100:
        return response(400, {"error": "limit: must be a whole number from 1 to 100", "field": "limit"})
    start = None
    if query.get("next"):
        try:
            start = store.decode_page_token(query["next"])
        except ValueError:
            return response(400, {"error": "next: not a valid page token", "field": "next"})
    items, last = store.list_jobs(limit, start)
    jobs = [
        {
            "job_id": j["job_id"],
            "status": j["status"],
            "created_at": j["created_at"],
            "paths": j["params"]["paths"],
            "shards": j["shards"],
            "estimate": j.get("result", {}).get("estimate"),
            "replay_of": j.get("replay_of"),
        }
        for j in items
    ]
    return response(200, {"jobs": jobs, "next": store.encode_page_token(last)})


def health() -> dict:
    checks = {}
    try:
        checks["dynamodb"] = "ok" if store.table_reachable() else "table not active"
    except (ClientError, BotoCoreError) as err:
        checks["dynamodb"] = f"unreachable ({type(err).__name__})"
    try:
        for name in (setting("QRYPT_PARAM_NAME"), setting("API_KEY_PARAM_NAME")):
            # Without decryption: proves the parameter exists and is readable, without handling the value.
            client("ssm").get_parameter(Name=name, WithDecryption=False)
        checks["ssm"] = "ok"
    except (ClientError, BotoCoreError) as err:
        checks["ssm"] = f"unreachable ({type(err).__name__})"
    healthy = all(v == "ok" for v in checks.values())
    return response(200 if healthy else 503, {"status": "ok" if healthy else "degraded", "checks": checks})
