import math
import random

import pytest

from qmc import pipeline
from qmc.aggregate import combine, errors_from_reference
from qmc.black_scholes import call_price
from qmc.params import JobParams
from qmc.simulate import ShardResult, generator_for, normals, shard_path_counts, simulate_shard

BRIEF = JobParams(100.0, 100.0, 0.05, 0.2, 1.0, 1_000_000, 10)
MASTER = bytes.fromhex("5a" * 32)


def test_path_split():
    assert shard_path_counts(10, 3) == [4, 3, 3]
    assert shard_path_counts(9, 3) == [3, 3, 3]
    assert sum(shard_path_counts(1_000_003, 20)) == 1_000_003
    with pytest.raises(ValueError):
        shard_path_counts(2, 3)


def test_generator_is_seeded_from_all_256_bits():
    a = generator_for(bytes(32)).random()
    b = generator_for(bytes(31) + b"\x01").random()
    c = generator_for(b"\x01" + bytes(31)).random()
    assert len({a, b, c}) == 3


def test_mersenne_twister_stream_is_pinned():
    # random() is pure integer arithmetic, so this exact value holds on every platform and Python 3 version
    # (the reproducibility promise in the Python docs). If it ever changes, replays would break.
    assert random.Random(12345).random().hex() == "0x1.aa9e665dc8a18p-2"
    assert generator_for((12345).to_bytes(32, "big")).random().hex() == "0x1.aa9e665dc8a18p-2"


def test_normals_count_and_moments():
    zs = list(normals(generator_for(MASTER), 200_001))
    assert len(zs) == 200_001
    mean = math.fsum(zs) / len(zs)
    var = math.fsum((z - mean) ** 2 for z in zs) / (len(zs) - 1)
    assert abs(mean) < 0.01
    assert abs(var - 1) < 0.01


def test_simulate_shard_rejects_empty():
    with pytest.raises(ValueError):
        simulate_shard(BRIEF, MASTER, 0)


def test_one_million_paths_within_three_standard_errors_of_black_scholes():
    # FR-4: the brief's test case at 1,000,000 paths.
    outcome = pipeline.run_job(BRIEF, MASTER)
    bs = call_price(100, 100, 0.05, 0.2, 1)
    assert outcome.black_scholes == bs
    assert outcome.estimate.n == 1_000_000
    assert errors_from_reference(outcome.estimate, bs) < 3
    assert outcome.estimate.ci95_low < outcome.estimate.estimate < outcome.estimate.ci95_high
    # Standard error of this payoff at 1M paths is about 0.0147.
    assert 0.012 < outcome.estimate.std_error < 0.017


@pytest.mark.parametrize("seed_byte", [1, 2, 3])
def test_other_seeds_and_parameters_also_match(seed_byte):
    params = JobParams(42.0, 40.0, 0.10, 0.20, 0.5, 200_000, 4)
    outcome = pipeline.run_job(params, bytes([seed_byte]) * 32)
    assert errors_from_reference(outcome.estimate, call_price(42, 40, 0.10, 0.20, 0.5)) < 4


def test_shard_results_round_trip():
    r = ShardResult(1.5, 2.25, 3)
    assert ShardResult.from_dict(r.to_dict()) == r


def test_combine_matches_single_pass_formula():
    payoffs = [0.0, 1.0, 2.5, 0.0, 7.25, 3.0]
    shards = [ShardResult(sum(p), sum(x * x for x in p), len(p)) for p in (payoffs[:2], payoffs[2:])]
    est = combine(shards, 0.05, 1.0)
    n = len(payoffs)
    mean = sum(payoffs) / n
    var = sum((x - mean) ** 2 for x in payoffs) / (n - 1)
    d = math.exp(-0.05)
    assert est.estimate == pytest.approx(d * mean, rel=1e-15)
    assert est.std_error == pytest.approx(d * math.sqrt(var / n), rel=1e-12)
    assert est.ci95_high - est.estimate == pytest.approx(1.96 * est.std_error)


def test_combine_edge_cases():
    with pytest.raises(ValueError):
        combine([], 0.05, 1)
    with pytest.raises(ValueError):
        combine([ShardResult(1.0, 1.0, 1)], 0.05, 1)
    zero = combine([ShardResult(0.0, 0.0, 10)], 0.05, 1)
    assert zero.estimate == 0.0
    assert zero.std_error == 0.0
    assert errors_from_reference(zero, 0.0) == 0.0
    assert errors_from_reference(zero, 1.0) == math.inf
