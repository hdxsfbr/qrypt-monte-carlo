"""All reads and writes to the DynamoDB table ``qmc-<env>-jobs``.

Items (docs/DESIGN.md, section 4):
- job: key ``JOB#<id>`` / ``META``;
- shard result: ``JOB#<id>`` / ``SHARD#0007`` (state DONE or FAILED);
- rate-limit window: ``RATE#<10-second window number>`` / ``RATE``, deleted automatically after a minute.

Terms
- *Conditional write*: a write DynamoDB performs only if a stated condition holds (for example "this item
  does not exist yet"); otherwise it refuses, and nothing changes.
- *Transaction*: several writes that DynamoDB applies all together or not at all.
"""

from __future__ import annotations

import base64
import binascii
import json
import math

from boto3.dynamodb.types import TypeDeserializer, TypeSerializer
from botocore.exceptions import ClientError

from handlers.common import client, number, setting
from qmc.params import JobParams

FINISHED = ("COMPLETE", "PARTIAL")
RATE_WINDOW_S = 10
RATE_LIMIT = 25  # Qrypt allows 30 requests per 10 seconds; keep a margin
INDEX = "by_created"

_ser = TypeSerializer()
_de = TypeDeserializer()


def _table() -> str:
    return setting("TABLE_NAME")


def to_item(d: dict) -> dict:
    return {k: _ser.serialize(v) for k, v in d.items()}


def from_item(item: dict) -> dict:
    return {k: _de.deserialize(v) for k, v in item.items()}


def job_key(job_id: str) -> dict:
    return {"pk": {"S": f"JOB#{job_id}"}, "sk": {"S": "META"}}


def shard_sk(index: int) -> str:
    return f"SHARD#{index:04d}"


def is_condition_failure(err: ClientError) -> bool:
    return err.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException"


def params_of(job: dict) -> JobParams:
    p = job["params"]
    return JobParams(
        float(p["S0"]),
        float(p["K"]),
        float(p["r"]),
        float(p["sigma"]),
        float(p["T"]),
        int(p["paths"]),
        int(p["shards"]),
    )


def params_item(params: JobParams) -> dict:
    return {k: number(v) for k, v in params.to_dict().items()}


# ---- jobs -------------------------------------------------------------------------------------------


def put_job(job: dict) -> None:
    """Write a new job; refuses to overwrite an existing id."""
    client("dynamodb").put_item(
        TableName=_table(),
        Item=to_item({"pk": f"JOB#{job['job_id']}", "sk": "META", **job}),
        ConditionExpression="attribute_not_exists(pk)",
    )


def get_job(job_id: str) -> dict | None:
    resp = client("dynamodb").get_item(TableName=_table(), Key=job_key(job_id), ConsistentRead=True)
    return from_item(resp["Item"]) if "Item" in resp else None


def finish_job(job_id: str, fields: dict) -> bool:
    """Set the final fields (status COMPLETE or PARTIAL and the result) only if the job is still QUEUED.

    Returns False when another worker (or a status check) finished it first; that is not an error."""
    names = {f"#f{i}": k for i, k in enumerate(fields)}
    values = {f":v{i}": _ser.serialize(v) for i, v in enumerate(fields.values())}
    values[":queued"] = {"S": "QUEUED"}
    try:
        client("dynamodb").update_item(
            TableName=_table(),
            Key=job_key(job_id),
            UpdateExpression="SET " + ", ".join(f"#f{i} = :v{i}" for i in range(len(fields))),
            ConditionExpression="#status = :queued",
            ExpressionAttributeNames={**names, "#status": "status"},
            ExpressionAttributeValues=values,
        )
    except ClientError as err:
        if is_condition_failure(err):
            return False
        raise
    return True


def encode_page_token(key: dict | None) -> str | None:
    if not key:
        return None
    return base64.urlsafe_b64encode(json.dumps(key, sort_keys=True).encode()).decode()


def decode_page_token(token: str) -> dict:
    """Raises ValueError for anything that is not a token we issued."""
    try:
        key = json.loads(base64.urlsafe_b64decode(token.encode()))
    except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError) as err:
        raise ValueError("bad page token") from err
    expected = {"pk", "sk", "gsi1pk", "gsi1sk"}
    if not isinstance(key, dict) or set(key) != expected:
        raise ValueError("bad page token")
    if not all(isinstance(v, dict) and set(v) == {"S"} and isinstance(v["S"], str) for v in key.values()):
        raise ValueError("bad page token")
    return key


def list_jobs(limit: int, start: dict | None = None) -> tuple[list[dict], dict | None]:
    """Newest first, through the ``by_created`` index."""
    kwargs = {
        "TableName": _table(),
        "IndexName": INDEX,
        "KeyConditionExpression": "gsi1pk = :jobs",
        "ExpressionAttributeValues": {":jobs": {"S": "JOBS"}},
        "ScanIndexForward": False,
        "Limit": limit,
    }
    if start:
        kwargs["ExclusiveStartKey"] = start
    resp = client("dynamodb").query(**kwargs)
    return [from_item(i) for i in resp.get("Items", [])], resp.get("LastEvaluatedKey")


# ---- shards -----------------------------------------------------------------------------------------


def record_shard(job_id: str, index: int, fields: dict, counter: str) -> bool:
    """Store one shard's outcome and add 1 to the job's ``completed`` or ``failed`` count, together.

    The shard item is written only if it does not exist yet. If SQS delivers the same message twice,
    the second transaction is refused, nothing is counted twice, and this returns False."""
    if counter not in ("completed", "failed"):
        raise ValueError(counter)
    item = {"pk": f"JOB#{job_id}", "sk": shard_sk(index), "shard_index": index, **fields}
    try:
        client("dynamodb").transact_write_items(
            TransactItems=[
                {
                    "Put": {
                        "TableName": _table(),
                        "Item": to_item(item),
                        "ConditionExpression": "attribute_not_exists(pk)",
                    }
                },
                {
                    "Update": {
                        "TableName": _table(),
                        "Key": job_key(job_id),
                        "UpdateExpression": "ADD #c :one",
                        "ConditionExpression": "attribute_exists(pk)",
                        "ExpressionAttributeNames": {"#c": counter},
                        "ExpressionAttributeValues": {":one": {"N": "1"}},
                    }
                },
            ]
        )
    except ClientError as err:
        if err.response.get("Error", {}).get("Code") != "TransactionCanceledException":
            raise
        reasons = err.response.get("CancellationReasons") or []
        if reasons and reasons[0].get("Code") == "ConditionalCheckFailed":
            return False  # duplicate delivery: this shard is already recorded
        raise
    return True


def shard_items(job_id: str) -> list[dict]:
    """Every recorded shard of a job, in shard-index order."""
    items: list[dict] = []
    kwargs = {
        "TableName": _table(),
        "KeyConditionExpression": "pk = :pk AND begins_with(sk, :shard)",
        "ExpressionAttributeValues": {":pk": {"S": f"JOB#{job_id}"}, ":shard": {"S": "SHARD#"}},
        "ConsistentRead": True,
    }
    while True:
        resp = client("dynamodb").query(**kwargs)
        items.extend(from_item(i) for i in resp.get("Items", []))
        if "LastEvaluatedKey" not in resp:
            return items
        kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]


# ---- rate limit -------------------------------------------------------------------------------------


def take_rate_slot(now: float) -> tuple[bool, int]:
    """Count one Qrypt call in the current 10-second window. Returns (allowed, seconds to wait)."""
    window = int(now // RATE_WINDOW_S)
    try:
        client("dynamodb").update_item(
            TableName=_table(),
            Key={"pk": {"S": f"RATE#{window}"}, "sk": {"S": "RATE"}},
            UpdateExpression="ADD #c :one SET #ttl = :ttl",
            ConditionExpression="attribute_not_exists(#c) OR #c < :limit",
            ExpressionAttributeNames={"#c": "count", "#ttl": "ttl"},
            ExpressionAttributeValues={
                ":one": {"N": "1"},
                ":limit": {"N": str(RATE_LIMIT)},
                ":ttl": {"N": str((window + 6) * RATE_WINDOW_S)},
            },
        )
    except ClientError as err:
        if is_condition_failure(err):
            return False, max(1, math.ceil((window + 1) * RATE_WINDOW_S - now))
        raise
    return True, 0


# ---- health -----------------------------------------------------------------------------------------


def table_reachable() -> bool:
    status = client("dynamodb").describe_table(TableName=_table())["Table"]["TableStatus"]
    return status == "ACTIVE"
