"""Combine shard results into the job's price estimate.

- *Estimate*: discounted average payoff, ``e^(-rT) * sum / n``.
- *Standard error*: how far the estimate is likely to be from the true price,
  ``e^(-rT) * sqrt(sample variance / n)``.
- *95% confidence interval*: estimate plus or minus 1.96 standard errors.

Shard totals are added in shard-index order with ``math.fsum`` (exact summation, rounded once), so the
result does not depend on which worker finished first.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from qmc.simulate import ShardResult

Z_95 = 1.96


@dataclass(frozen=True)
class Estimate:
    estimate: float
    std_error: float
    ci95_low: float
    ci95_high: float
    n: int

    @property
    def estimate_hex(self) -> str:
        """Exact binary value of the estimate, for bit-identical comparison (``float.hex``)."""
        return self.estimate.hex()

    def to_dict(self) -> dict:
        return {
            "estimate": self.estimate,
            "std_error": self.std_error,
            "ci95_low": self.ci95_low,
            "ci95_high": self.ci95_high,
            "n": self.n,
            "estimate_hex": self.estimate_hex,
        }


def combine(results: Sequence[ShardResult], r: float, T: float) -> Estimate:
    """``results`` must be in shard-index order."""
    if not results:
        raise ValueError("no shard results to combine")
    n = sum(x.n for x in results)
    if n < 2:
        raise ValueError("need at least 2 paths for a standard error")
    total = math.fsum(x.sum for x in results)
    total_sq = math.fsum(x.sum_sq for x in results)
    mean = total / n
    variance = max((total_sq - total * mean) / (n - 1), 0.0)
    discount = math.exp(-r * T)
    estimate = discount * mean
    std_error = discount * math.sqrt(variance / n)
    return Estimate(estimate, std_error, estimate - Z_95 * std_error, estimate + Z_95 * std_error, n)


def errors_from_reference(est: Estimate, reference: float) -> float:
    """How many standard errors the estimate is from the reference price."""
    if est.std_error == 0:
        return 0.0 if est.estimate == reference else math.inf
    return abs(est.estimate - reference) / est.std_error
