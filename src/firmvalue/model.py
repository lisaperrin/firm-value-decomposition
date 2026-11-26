"""Structural model: adjustment costs, shadow values and the value identity.

A firm chooses investment in four quasi-fixed inputs to maximise the present
value of after-tax dividends. Operating profit and adjustment costs are both
homogeneous of degree one in stocks and flows, so Hayashi's theorem extends
to every input: ex-dividend market value equals the sum over inputs of the
shadow value of one installed unit times the installed stock,

    V_t = sum_j q_jt X_{j,t+1}.

The shadow value is read off the first-order condition for investment and
equals the full after-tax marginal cost of one more unit,

    q_jt = p_j(tau_t) + (1 - tau_t) * dC_j/dI_j,

where ``p_j`` is the direct after-tax purchase price (1 for physical capital,
``1 - tau`` for expensed intangibles, 0 for labor) and ``C_j`` is the
adjustment cost function.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from firmvalue.inputs import DEFAULT_SPECS, INPUTS, Input, InputSpec
from firmvalue.panel import flow_column, stock_column

ArrayLike = np.ndarray | pd.Series | float


@dataclass(frozen=True, slots=True)
class AdjustmentCost:
    """Homogeneous-of-degree-one adjustment cost ``(theta / nu) |I/X|^nu X``.

    ``curvature`` of 2 gives the familiar quadratic specification. Costs are
    symmetric in the sign of the flow, so disinvestment (or firing) is penalised
    like investment (or hiring).
    """

    scale: float
    curvature: float = 2.0

    def __post_init__(self) -> None:
        if self.scale < 0.0:
            raise ValueError("adjustment cost scale must be non-negative")
        if self.curvature <= 1.0:
            raise ValueError("adjustment cost curvature must exceed 1")

    def total(self, rate: ArrayLike, stock: ArrayLike) -> ArrayLike:
        """Total cost at investment rate ``rate = I / X`` on stock ``stock``."""
        return self.scale / self.curvature * np.abs(rate) ** self.curvature * stock

    def marginal(self, rate: ArrayLike) -> ArrayLike:
        """Marginal cost ``dC/dI = theta sign(I/X) |I/X|^(nu - 1)``."""
        return self.scale * np.sign(rate) * np.abs(rate) ** (self.curvature - 1.0)


@dataclass(frozen=True, slots=True)
class Parameters:
    """Structural parameters: one adjustment cost function per input."""

    costs: Mapping[Input, AdjustmentCost]
    specs: Mapping[Input, InputSpec] = field(default_factory=lambda: dict(DEFAULT_SPECS))

    def __post_init__(self) -> None:
        missing = [name for name in INPUTS if name not in self.costs]
        if missing:
            raise ValueError(f"parameters missing adjustment costs for {missing}")

    @classmethod
    def quadratic(
        cls,
        physical: float,
        labor: float,
        knowledge: float,
        brand: float,
        specs: Mapping[Input, InputSpec] | None = None,
    ) -> Parameters:
        """Quadratic adjustment costs with the given scale parameters."""
        costs = {
            Input.PHYSICAL: AdjustmentCost(physical),
            Input.LABOR: AdjustmentCost(labor),
            Input.KNOWLEDGE: AdjustmentCost(knowledge),
            Input.BRAND: AdjustmentCost(brand),
        }
        return cls(costs, dict(specs) if specs is not None else dict(DEFAULT_SPECS))

    def to_dict(self) -> dict[str, dict[str, float]]:
        """Return the adjustment cost parameters as plain nested dictionaries."""
        return {
            str(name): {"scale": cost.scale, "curvature": cost.curvature}
            for name, cost in self.costs.items()
        }

    @classmethod
    def from_dict(
        cls,
        payload: Mapping[str, Mapping[str, float]],
        specs: Mapping[Input, InputSpec] | None = None,
    ) -> Parameters:
        """Inverse of :meth:`to_dict`."""
        costs = {
            Input(name): AdjustmentCost(values["scale"], values.get("curvature", 2.0))
            for name, values in payload.items()
        }
        return cls(costs, dict(specs) if specs is not None else dict(DEFAULT_SPECS))


def investment_rate(panel: pd.DataFrame, name: Input, spec: InputSpec) -> pd.Series:
    """Flow relative to the stock it was applied to, ``I_t / X_t``.

    The panel stores end-of-year stocks ``X_{t+1}``; the beginning-of-year
    stock is recovered from the law of motion ``X_t = (X_{t+1} - I_t) / (1 - delta)``.
    When that stock is not positive (a firm's first investment of this kind)
    the flow is scaled by the end-of-year stock instead, and a firm with no
    stock at all has a zero rate.
    """
    flow = panel[flow_column(name)].to_numpy(dtype=float)
    end_stock = panel[stock_column(name)].to_numpy(dtype=float)
    survival = 1.0 - spec.depreciation
    start_stock = (end_stock - flow) / survival if survival > 0.0 else end_stock
    base = np.where(start_stock > 0.0, start_stock, end_stock)
    rate = np.divide(flow, base, out=np.zeros_like(flow), where=base > 0.0)
    return pd.Series(rate, index=panel.index, name=f"rate_{name}")


def shadow_values(panel: pd.DataFrame, params: Parameters) -> pd.DataFrame:
    """Shadow value ``q_j`` of one installed unit of each input, per firm-year."""
    tax = panel["tax_rate"].to_numpy(dtype=float)
    out = pd.DataFrame(index=panel.index)
    for name in INPUTS:
        spec = params.specs[name]
        rate = investment_rate(panel, name, spec).to_numpy()
        marginal = np.asarray(params.costs[name].marginal(rate), dtype=float)
        out[f"q_{name}"] = spec.after_tax_prices(tax) + (1.0 - tax) * marginal
    return out


def decompose(panel: pd.DataFrame, params: Parameters) -> pd.DataFrame:
    """Model-implied value of each installed input and its share of the total.

    Returns the panel identifiers together with ``q_<input>``,
    ``value_<input>``, ``share_<input>`` (market-value shares summing to one),
    ``book_share_<input>`` (shares of the book sum of capital stocks, zero for
    labor), ``implied_value`` and ``observed_value``.
    """
    q = shadow_values(panel, params)
    out = panel[["firm", "year", "group"]].copy()
    values = {name: q[f"q_{name}"] * panel[stock_column(name)] for name in INPUTS}
    implied = sum(values.values(), pd.Series(0.0, index=panel.index))
    book = sum(
        (panel[stock_column(n)] for n in INPUTS if params.specs[n].purchased),
        pd.Series(0.0, index=panel.index),
    )
    for name in INPUTS:
        out[f"q_{name}"] = q[f"q_{name}"]
        out[f"value_{name}"] = values[name]
        out[f"share_{name}"] = values[name] / implied
        book_share = panel[stock_column(name)] / book if params.specs[name].purchased else 0.0
        out[f"book_share_{name}"] = book_share
    out["implied_value"] = implied
    out["observed_value"] = panel["market_value"]
    out["book_value"] = book
    return out


def implied_value(panel: pd.DataFrame, params: Parameters) -> pd.Series:
    """Market value implied by the identity ``V = sum_j q_j X_j``."""
    q = shadow_values(panel, params)
    total = pd.Series(0.0, index=panel.index)
    for name in INPUTS:
        total = total + q[f"q_{name}"] * panel[stock_column(name)]
    return total.rename("implied_value")


def book_capital(panel: pd.DataFrame, params: Parameters) -> pd.Series:
    """Sum of purchased (book-valued) capital stocks."""
    total = pd.Series(0.0, index=panel.index)
    for name in INPUTS:
        if params.specs[name].purchased:
            total = total + panel[stock_column(name)]
    return total.rename("book_value")
