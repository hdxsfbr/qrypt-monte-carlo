"""Black-Scholes closed-form price of a European call option.

The formula gives the exact fair price under the same model the simulation uses, so it is the reference
the Monte Carlo estimate is checked against.
"""

from __future__ import annotations

import math


def norm_cdf(x: float) -> float:
    """Standard normal cumulative distribution: the chance a standard normal number is at most x."""
    return 0.5 * math.erfc(-x / math.sqrt(2.0))


def call_price(S0: float, K: float, r: float, sigma: float, T: float) -> float:
    """C = S0 * N(d1) - K * e^(-rT) * N(d2)."""
    if S0 <= 0 or K <= 0 or sigma <= 0 or T <= 0:
        raise ValueError("S0, K, sigma and T must be positive")
    vol = sigma * math.sqrt(T)
    d1 = (math.log(S0 / K) + (r + 0.5 * sigma * sigma) * T) / vol
    d2 = d1 - vol
    return S0 * norm_cdf(d1) - K * math.exp(-r * T) * norm_cdf(d2)
