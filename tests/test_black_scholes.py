import math

import pytest

from qmc.black_scholes import call_price, norm_cdf


def test_brief_reference_case():
    # S0=100, K=100, r=5%, sigma=20%, T=1 year: the widely published value 10.4506.
    assert call_price(100, 100, 0.05, 0.2, 1) == pytest.approx(10.450583572185565, abs=1e-12)


def test_hull_textbook_example():
    # Hull, "Options, Futures, and Other Derivatives", example 15.6: c = 4.76.
    assert round(call_price(42, 40, 0.10, 0.20, 0.5), 2) == 4.76


def test_norm_cdf_values():
    assert norm_cdf(0) == 0.5
    assert norm_cdf(1.959963984540054) == pytest.approx(0.975, abs=1e-12)
    assert norm_cdf(-8) < 1e-14


def test_deep_in_the_money_tends_to_forward_intrinsic_value():
    S0, K, r, T = 200.0, 50.0, 0.03, 1.0
    assert call_price(S0, K, r, 0.01, T) == pytest.approx(S0 - K * math.exp(-r * T), rel=1e-9)


@pytest.mark.parametrize("bad", [dict(S0=0), dict(K=-1), dict(sigma=0), dict(T=0)])
def test_rejects_non_positive_inputs(bad):
    args = dict(S0=100, K=100, r=0.05, sigma=0.2, T=1) | bad
    with pytest.raises(ValueError):
        call_price(**args)
