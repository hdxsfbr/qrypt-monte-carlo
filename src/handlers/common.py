"""Settings, AWS clients, structured logs and metrics shared by both handlers.

Terms
- *Embedded Metric Format (EMF)*: a JSON log line with an ``_aws`` section. CloudWatch reads such lines
  and turns the named fields into metrics, so the functions never call the metrics API.
- *Dimension*: a label attached to a metric. We use one, ``Environment`` (for example ``dev``).
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from decimal import Decimal
from functools import cache

import boto3

from qmc.params import Limits

NAMESPACE = "QMC"
# The six custom metrics (docs/DESIGN.md, section 3) and their CloudWatch units.
METRIC_UNITS = {
    "JobsSubmitted": "Count",
    "PathsSimulated": "Count",
    "EntropyKiB": "Count",
    "ShardFailures": "Count",
    "QryptErrors": "Count",
    "ShardDurationMs": "Milliseconds",
}

log = logging.getLogger("qmc")
log.setLevel(logging.INFO)


def setting(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, default)
    if value is None:
        raise RuntimeError(f"missing setting {name}")
    return value


def limits_from_env() -> Limits:
    defaults = Limits()
    return Limits(
        max_paths=int(setting("MAX_PATHS", str(defaults.max_paths))),
        max_shards=int(setting("MAX_SHARDS", str(defaults.max_shards))),
        max_paths_per_shard=int(setting("MAX_PATHS_PER_SHARD", str(defaults.max_paths_per_shard))),
        fault_injection=fault_injection_enabled(),
    )


def fault_injection_enabled() -> bool:
    return setting("ENABLE_FAULT_INJECTION", "false") == "true"


@cache
def client(service: str):
    """One boto3 client per service per function copy (created on first use, reused afterwards)."""
    return boto3.client(service)


def reset_clients() -> None:
    """Forget cached clients (tests create fresh fake AWS services between cases)."""
    client.cache_clear()


def log_event(message: str, level: int = logging.INFO, **fields) -> None:
    """A structured log line. Lambda's JSON log format adds the extra fields as JSON keys.

    Never pass headers, request bodies or secrets here."""
    log.log(level, message, extra={"qmc": fields})


def emit_metrics(values: dict[str, float], **context) -> None:
    """Write one EMF line. ``context`` fields (job id, shard) are kept in the log line for searching but
    are not dimensions, so they do not create extra metrics."""
    unknown = set(values) - set(METRIC_UNITS)
    if unknown:
        raise ValueError(f"unknown metrics {sorted(unknown)}")
    record = {
        "_aws": {
            "Timestamp": int(time.time() * 1000),
            "CloudWatchMetrics": [
                {
                    "Namespace": NAMESPACE,
                    "Dimensions": [["Environment"]],
                    "Metrics": [{"Name": k, "Unit": METRIC_UNITS[k]} for k in values],
                }
            ],
        },
        "Environment": setting("QMC_ENV", "dev"),
        **context,
        **values,
    }
    # Straight to standard output: Lambda passes a line that is already JSON through unchanged, which is
    # what CloudWatch needs to find the metrics. (Going through ``logging`` would wrap it.)
    sys.stdout.write(json.dumps(record) + "\n")
    sys.stdout.flush()


def plain(value):
    """DynamoDB returns numbers as ``Decimal``; turn them into int or float for JSON output."""
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, dict):
        return {k: plain(v) for k, v in value.items()}
    if isinstance(value, list):
        return [plain(v) for v in value]
    return value


def number(x: float | int) -> Decimal:
    """A float or int as a DynamoDB number. ``repr`` of a float is the shortest text that reads back as
    exactly the same float, so nothing is lost on the way in or out."""
    return Decimal(repr(x)) if isinstance(x, float) else Decimal(x)


def utc_now() -> tuple[float, str]:
    """Current time as (seconds since 1970, ISO 8601 text in UTC with milliseconds)."""
    now = time.time()
    iso = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(now)) + f".{int(now % 1 * 1000):03d}Z"
    return now, iso
