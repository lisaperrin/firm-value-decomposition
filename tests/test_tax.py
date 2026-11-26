import pandas as pd

from firmvalue.tax import statutory_rate, statutory_rates


def test_known_years():
    assert statutory_rate(1975) == 0.48
    assert statutory_rate(1980) == 0.46
    assert statutory_rate(1987) == 0.40
    assert statutory_rate(1990) == 0.34
    assert statutory_rate(2000) == 0.35
    assert statutory_rate(2018) == 0.21


def test_vectorised_matches_scalar():
    years = pd.Series([1940, 1975, 1979, 1988, 1993, 2017, 2018, 2030])
    rates = statutory_rates(years)
    assert rates.tolist() == [statutory_rate(y) for y in years]
    assert rates.name == "tax_rate"
