"""Validation of job requests.

Every field is checked on the server; a bad request gets a ``ValidationError`` naming the field, which the
API turns into HTTP 400.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

NUMBER_FIELDS = ("S0", "K", "r", "sigma", "T")
INT_FIELDS = ("paths", "shards")
REQUIRED = NUMBER_FIELDS + INT_FIELDS
OPTIONAL = ("fail_shards",)


class ValidationError(ValueError):
    def __init__(self, field: str, message: str):
        super().__init__(f"{field}: {message}")
        self.field = field
        self.message = message


@dataclass(frozen=True)
class Limits:
    max_paths: int = 10_000_000
    max_shards: int = 20
    max_paths_per_shard: int = 500_000
    fault_injection: bool = False  # set only by the deployment (Terraform variable), never by a caller


@dataclass(frozen=True)
class JobParams:
    S0: float
    K: float
    r: float
    sigma: float
    T: float
    paths: int
    shards: int

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class JobRequest:
    params: JobParams
    fail_shards: tuple[int, ...] = ()


def _number(body: dict, name: str) -> float:
    value = body[name]
    # bool is a subclass of int in Python, so reject it explicitly.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValidationError(name, "must be a number")
    value = float(value)
    if not math.isfinite(value):
        raise ValidationError(name, "must be a finite number")
    return value


def _whole(body: dict, name: str) -> int:
    value = body[name]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValidationError(name, "must be a whole number")
    if isinstance(value, float):
        if not value.is_integer():
            raise ValidationError(name, "must be a whole number")
        value = int(value)
    return value


DEFAULT_LIMITS = Limits()


def validate_job_request(body: object, limits: Limits = DEFAULT_LIMITS) -> JobRequest:
    if not isinstance(body, dict):
        raise ValidationError("body", "must be a JSON object")
    unknown = sorted(set(body) - set(REQUIRED) - set(OPTIONAL))
    if unknown:
        raise ValidationError(unknown[0], "unknown field")
    for name in REQUIRED:
        if name not in body:
            raise ValidationError(name, "is required")

    S0, K, r, sigma, T = (_number(body, n) for n in NUMBER_FIELDS)
    paths, shards = (_whole(body, n) for n in INT_FIELDS)

    for name, value in (("S0", S0), ("K", K), ("sigma", sigma), ("T", T)):
        if value <= 0:
            raise ValidationError(name, "must be greater than 0")
    if abs(r) > 1:
        raise ValidationError("r", "must be between -1 and 1 (a yearly rate, e.g. 0.05 for 5%)")
    if sigma > 5:
        raise ValidationError("sigma", "must be at most 5 (500% yearly volatility)")
    if T > 100:
        raise ValidationError("T", "must be at most 100 years")
    if paths < 2:
        raise ValidationError("paths", "must be at least 2")
    if paths > limits.max_paths:
        raise ValidationError("paths", f"must be at most {limits.max_paths}")
    if shards < 1:
        raise ValidationError("shards", "must be at least 1")
    if shards > limits.max_shards:
        raise ValidationError("shards", f"must be at most {limits.max_shards}")
    if shards > paths:
        raise ValidationError("shards", "must not exceed paths")
    if -(-paths // shards) > limits.max_paths_per_shard:
        raise ValidationError(
            "shards", f"too few shards: each shard may run at most {limits.max_paths_per_shard} paths"
        )

    fail_shards: tuple[int, ...] = ()
    if "fail_shards" in body:
        if not limits.fault_injection:
            raise ValidationError("fail_shards", "fault injection is not enabled on this deployment")
        raw = body["fail_shards"]
        if not isinstance(raw, list) or not all(
            isinstance(i, int) and not isinstance(i, bool) and 0 <= i < shards for i in raw
        ):
            raise ValidationError("fail_shards", "must be a list of shard indexes")
        fail_shards = tuple(sorted(set(raw)))

    return JobRequest(JobParams(S0, K, r, sigma, T, paths, shards), fail_shards)
