"""United States statutory federal corporate income tax rates (top bracket)."""

from __future__ import annotations

import numpy as np
import pandas as pd

_RATE_CHANGES: tuple[tuple[int, float], ...] = (
    (1951, 0.52),
    (1964, 0.50),
    (1965, 0.48),
    (1979, 0.46),
    (1987, 0.40),
    (1988, 0.34),
    (1993, 0.35),
    (2018, 0.21),
)


def statutory_rate(year: int) -> float:
    """Top federal corporate rate in force for fiscal ``year``."""
    rate = _RATE_CHANGES[0][1]
    for start, value in _RATE_CHANGES:
        if year >= start:
            rate = value
    return rate


def statutory_rates(years: pd.Series) -> pd.Series:
    """Vectorised :func:`statutory_rate` for a Series of fiscal years."""
    starts = np.array([start for start, _ in _RATE_CHANGES])
    values = np.array([value for _, value in _RATE_CHANGES])
    idx = np.searchsorted(starts, years.to_numpy(), side="right") - 1
    return pd.Series(values[np.clip(idx, 0, len(values) - 1)], index=years.index, name="tax_rate")
