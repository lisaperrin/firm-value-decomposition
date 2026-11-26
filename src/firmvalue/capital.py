"""Perpetual-inventory construction of capital stocks from expenditure flows."""

from __future__ import annotations

import numpy as np
import pandas as pd


def perpetual_inventory(
    flows: pd.Series,
    depreciation: float,
    growth: float = 0.03,
    initial: float | None = None,
) -> pd.Series:
    """Accumulate a flow series into an end-of-period stock.

    The stock follows ``X[t+1] = (1 - depreciation) * X[t] + flow[t]``. The
    returned series holds ``X[t+1]``, the stock installed at the end of period
    ``t`` and productive in ``t+1``. When ``initial`` is omitted the opening
    stock is the steady-state value implied by the first observed flow growing
    at ``growth``: ``flow[0] / (growth + depreciation)``. Missing flows are
    treated as zero.

    Parameters
    ----------
    flows
        Expenditure flow per period, ordered in time.
    depreciation
        Annual depreciation rate in ``(0, 1]``.
    growth
        Assumed pre-sample growth rate of the flow.
    initial
        Opening stock ``X[0]`` overriding the steady-state assumption.

    """
    if not 0.0 < depreciation <= 1.0:
        raise ValueError("depreciation must lie in (0, 1]")
    if growth + depreciation <= 0.0:
        raise ValueError("growth + depreciation must be positive")

    values = flows.to_numpy(dtype=float)
    values = np.where(np.isnan(values), 0.0, values)
    stock = np.empty_like(values)
    if values.size == 0:
        return pd.Series(stock, index=flows.index, name=flows.name)

    current = values[0] / (growth + depreciation) if initial is None else float(initial)
    survival = 1.0 - depreciation
    for t, flow in enumerate(values):
        current = survival * current + flow
        stock[t] = current
    return pd.Series(stock, index=flows.index, name=flows.name)


def perpetual_inventory_by_firm(
    frame: pd.DataFrame,
    flow: str,
    depreciation: float,
    firm: str = "firm",
    year: str = "year",
    growth: float = 0.03,
) -> pd.Series:
    """Apply :func:`perpetual_inventory` within each firm of a long panel."""
    ordered = frame.sort_values([firm, year])
    stocks = ordered.groupby(firm, sort=False)[flow].transform(
        lambda s: perpetual_inventory(s, depreciation, growth)
    )
    return stocks.reindex(frame.index)
