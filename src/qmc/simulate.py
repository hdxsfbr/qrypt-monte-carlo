"""Monte Carlo simulation of one shard of a European call pricing job.

Each simulated path draws one standard normal number ``Z`` and computes the stock price at expiry
``S_T = S0 * exp((r - sigma^2 / 2) * T + sigma * sqrt(T) * Z)`` (the same model Black-Scholes assumes).
The payoff is ``max(S_T - K, 0)``. A shard returns only three numbers: the sum of payoffs, the sum of
squared payoffs and the path count, which is all that is needed to combine shards later.

Random numbers: ``random.Random`` (the Mersenne Twister generator) seeded with the shard's 256-bit seed.
Python documents that ``random()`` gives the same sequence for the same integer seed across versions.
Normal numbers come from our own Box-Muller step (two uniform numbers in, two normal numbers out) instead
of ``random.gauss``, which has no such promise.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from qmc.params import JobParams

TWO_PI = 2.0 * math.pi


@dataclass(frozen=True)
class ShardResult:
    sum: float
    sum_sq: float
    n: int

    def to_dict(self) -> dict:
        return {"sum": self.sum, "sum_sq": self.sum_sq, "n": self.n}

    @classmethod
    def from_dict(cls, d: dict) -> ShardResult:
        return cls(float(d["sum"]), float(d["sum_sq"]), int(d["n"]))


def shard_path_counts(paths: int, shards: int) -> list[int]:
    """Split paths over shards as evenly as possible; the first ``paths % shards`` shards get one extra."""
    if shards < 1 or paths < shards:
        raise ValueError("need 1 <= shards <= paths")
    base, extra = divmod(paths, shards)
    return [base + (1 if i < extra else 0) for i in range(shards)]


def generator_for(seed: bytes) -> random.Random:
    return random.Random(int.from_bytes(seed, "big"))


def normals(rng: random.Random, n: int):
    """Yield n standard normal numbers using the Box-Muller transform, both outputs of each pair."""
    rand = rng.random
    log, sqrt, cos, sin = math.log, math.sqrt, math.cos, math.sin
    produced = 0
    while produced < n:
        u1 = 1.0 - rand()  # in (0, 1], so log(u1) is defined
        u2 = rand()
        radius = sqrt(-2.0 * log(u1))
        angle = TWO_PI * u2
        yield radius * cos(angle)
        produced += 1
        if produced < n:
            yield radius * sin(angle)
            produced += 1


def simulate_shard(params: JobParams, seed: bytes, n: int) -> ShardResult:
    if n < 1:
        raise ValueError("a shard needs at least one path")
    drift = (params.r - 0.5 * params.sigma * params.sigma) * params.T
    vol = params.sigma * math.sqrt(params.T)
    S0, K = params.S0, params.K
    exp = math.exp
    total = 0.0
    total_sq = 0.0
    for z in normals(generator_for(seed), n):
        payoff = S0 * exp(drift + vol * z) - K
        if payoff > 0.0:
            total += payoff
            total_sq += payoff * payoff
    return ShardResult(total, total_sq, n)
