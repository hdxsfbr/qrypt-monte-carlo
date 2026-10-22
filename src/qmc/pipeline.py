"""Run a whole job in one process: the same steps the workers run, in the same order.

Used by tests (closed-form check, replay, idempotency) and by the local ``qmc`` command. The deployed
platform runs ``simulate_shard`` in separate worker Lambdas and ``combine`` when the last shard is in;
the numbers are the same because each step depends only on the master seed, parameters and shard index.
"""

from __future__ import annotations

from dataclasses import dataclass

from qmc import ALGO_VERSION
from qmc.aggregate import Estimate, combine
from qmc.black_scholes import call_price
from qmc.params import JobParams
from qmc.seeds import shard_seed
from qmc.simulate import ShardResult, shard_path_counts, simulate_shard


@dataclass(frozen=True)
class ShardTask:
    """What one SQS message carries for one shard."""

    shard_index: int
    shard_count: int
    paths: int


def plan_shards(params: JobParams) -> list[ShardTask]:
    counts = shard_path_counts(params.paths, params.shards)
    return [ShardTask(i, params.shards, n) for i, n in enumerate(counts)]


def run_shard(params: JobParams, master_seed: bytes, task: ShardTask, version: str = ALGO_VERSION):
    if version != ALGO_VERSION:
        raise ValueError(f"unsupported algorithm version {version!r}")
    seed = shard_seed(master_seed, task.shard_index, task.shard_count, version)
    return simulate_shard(params, seed, task.paths)


def aggregate(params: JobParams, by_index: dict[int, ShardResult]) -> Estimate:
    """Combine results in shard-index order; every shard must be present."""
    missing = [i for i in range(params.shards) if i not in by_index]
    if missing:
        raise ValueError(f"missing shard results: {missing}")
    return combine([by_index[i] for i in range(params.shards)], params.r, params.T)


@dataclass(frozen=True)
class JobOutcome:
    estimate: Estimate
    black_scholes: float
    shards: dict[int, ShardResult]


def run_job(params: JobParams, master_seed: bytes, version: str = ALGO_VERSION) -> JobOutcome:
    shards = {t.shard_index: run_shard(params, master_seed, t, version) for t in plan_shards(params)}
    return JobOutcome(
        aggregate(params, shards),
        call_price(params.S0, params.K, params.r, params.sigma, params.T),
        shards,
    )
