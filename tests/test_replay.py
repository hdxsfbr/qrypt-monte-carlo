"""Replay, ordering and idempotency: the properties the audit story depends on."""

import pytest

from qmc import pipeline
from qmc.params import JobParams

PARAMS = JobParams(100.0, 100.0, 0.05, 0.2, 1.0, 120_000, 7)
MASTER = bytes.fromhex("c3" * 32)


def test_replay_is_bit_identical():
    first = pipeline.run_job(PARAMS, MASTER)
    replay = pipeline.run_job(PARAMS, MASTER)
    assert replay.estimate.estimate_hex == first.estimate.estimate_hex
    assert replay.estimate == first.estimate
    assert replay.shards == first.shards


def test_different_master_seed_gives_different_result():
    other = pipeline.run_job(PARAMS, bytes.fromhex("c4" + "c3" * 31))
    assert other.estimate.estimate_hex != pipeline.run_job(PARAMS, MASTER).estimate.estimate_hex


def test_completion_order_does_not_change_the_bits():
    tasks = pipeline.plan_shards(PARAMS)
    in_order = {t.shard_index: pipeline.run_shard(PARAMS, MASTER, t) for t in tasks}
    reversed_order = {t.shard_index: pipeline.run_shard(PARAMS, MASTER, t) for t in reversed(tasks)}
    assert (
        pipeline.aggregate(PARAMS, reversed_order).estimate_hex
        == pipeline.aggregate(PARAMS, in_order).estimate_hex
    )


def test_duplicate_delivery_does_not_double_count():
    # Simulates SQS delivering every message twice: results are keyed by shard index, written once.
    store: dict[int, object] = {}
    for task in pipeline.plan_shards(PARAMS) * 2:
        result = pipeline.run_shard(PARAMS, MASTER, task)
        store.setdefault(task.shard_index, result)  # the DynamoDB conditional put behaves like this
    est = pipeline.aggregate(PARAMS, store)
    assert est.n == PARAMS.paths
    assert est.estimate_hex == pipeline.run_job(PARAMS, MASTER).estimate.estimate_hex


def test_missing_shard_is_refused():
    shards = pipeline.run_job(PARAMS, MASTER).shards
    del shards[3]
    with pytest.raises(ValueError, match=r"\[3\]"):
        pipeline.aggregate(PARAMS, shards)


def test_shard_paths_add_up():
    assert sum(t.paths for t in pipeline.plan_shards(PARAMS)) == PARAMS.paths


def test_unknown_algorithm_version_is_refused():
    with pytest.raises(ValueError):
        pipeline.run_job(PARAMS, MASTER, version="qmc-v0")
