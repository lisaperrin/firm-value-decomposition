"""Synthetic firm-year panels generated from the structural model.

The generator is used for Monte Carlo checks of the estimator and for the
packaged demonstration, since the Compustat data behind the published
estimates are proprietary. Firms differ in size, in growth and in persistent
and transitory investment rates; market value is the model-implied value
times log-normal noise.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from firmvalue.inputs import CAPITAL_INPUTS, DEFAULT_SPECS, INPUTS, Input, InputSpec
from firmvalue.model import Parameters
from firmvalue.panel import flow_column, stock_column
from firmvalue.tax import statutory_rate


@dataclass(frozen=True, slots=True)
class GroupDesign:
    """Data-generating process for one group of firms.

    ``book_mix`` gives the opening composition of physical, knowledge and
    brand capital; ``employees_per_capital`` the opening labor stock in
    thousands of employees per unit of book capital.

    The investment rate of input ``j`` in year ``t`` is

        rate = depreciation_j + growth + trend_j(t) + g_i + a_ij + u_ijt,

    where ``g_i`` is a firm-level growth effect common to all inputs,
    ``a_ij`` a persistent input-specific deviation and ``u_ijt`` a transitory
    AR(1) deviation, all in rate units. ``rate_trend`` shifts the target
    linearly from zero in the first sample year to the given value in the
    last. Rates are floored at zero.
    """

    name: str
    firms: int
    params: Parameters
    book_mix: Mapping[Input, float]
    employees_per_capital: float = 0.004
    growth: float = 0.03
    rate_trend: Mapping[Input, float] = field(default_factory=dict)
    firm_growth_sd: float = 0.02
    rate_dispersion: float = 0.03
    persistence: float = 0.60
    innovation: float = 0.05
    valuation_noise: float = 0.25

    def __post_init__(self) -> None:
        if abs(sum(self.book_mix[n] for n in CAPITAL_INPUTS) - 1.0) > 1e-9:
            raise ValueError("book_mix must sum to one over the capital inputs")


@dataclass(frozen=True, slots=True)
class SimulationDesign:
    """A set of groups observed over a common sample of fiscal years."""

    groups: tuple[GroupDesign, ...]
    start_year: int = 1975
    end_year: int = 2015
    log_size_mean: float = 6.0
    log_size_sd: float = 1.5
    tax_rate: float | None = None

    @classmethod
    def demo(cls, firms_per_group: int = 400) -> SimulationDesign:
        """Two groups calibrated so that value shares resemble the published ones."""
        specs = dict(DEFAULT_SPECS)
        low = GroupDesign(
            name="low_skill",
            firms=firms_per_group,
            params=Parameters.quadratic(2.0, 900.0, 32.0, 7.0, specs),
            book_mix={Input.PHYSICAL: 0.72, Input.KNOWLEDGE: 0.10, Input.BRAND: 0.18},
            rate_trend={Input.PHYSICAL: -0.02, Input.KNOWLEDGE: 0.03},
        )
        high = GroupDesign(
            name="high_skill",
            firms=firms_per_group,
            params=Parameters.quadratic(2.0, 1500.0, 27.0, 2.0, specs),
            book_mix={Input.PHYSICAL: 0.61, Input.KNOWLEDGE: 0.28, Input.BRAND: 0.11},
            rate_trend={Input.PHYSICAL: -0.03, Input.KNOWLEDGE: 0.04},
        )
        return cls(groups=(low, high))


def _simulate_group(
    group: GroupDesign, design: SimulationDesign, rng: np.random.Generator
) -> pd.DataFrame:
    years = np.arange(design.start_year, design.end_year + 1)
    n_years = years.size
    n = group.firms
    specs = group.params.specs

    size = np.exp(rng.normal(design.log_size_mean, design.log_size_sd, n))
    stocks: dict[Input, np.ndarray] = {name: size * group.book_mix[name] for name in CAPITAL_INPUTS}
    stocks[Input.LABOR] = size * group.employees_per_capital

    firm_growth = rng.normal(0.0, group.firm_growth_sd, n)
    persistent = {name: rng.normal(0.0, group.rate_dispersion, n) for name in INPUTS}
    transitory = {name: np.zeros(n) for name in INPUTS}
    innovation_sd = group.innovation * np.sqrt(1.0 - group.persistence**2)
    progress = (years - years[0]) / max(n_years - 1, 1)
    firm_ids = np.array([f"{group.name}_{i:04d}" for i in range(n)])

    frames = []
    for t, year in enumerate(years):
        tax = statutory_rate(int(year)) if design.tax_rate is None else design.tax_rate
        row: dict[str, np.ndarray | float | int | str] = {
            "firm": firm_ids,
            "year": int(year),
            "group": group.name,
            "tax_rate": tax,
        }
        new_stocks: dict[Input, np.ndarray] = {}
        value = np.zeros(n)
        for name in INPUTS:
            spec: InputSpec = specs[name]
            target = (
                spec.depreciation + group.growth + group.rate_trend.get(name, 0.0) * progress[t]
            )
            transitory[name] = group.persistence * transitory[name] + rng.normal(
                0.0, innovation_sd, n
            )
            rate = np.maximum(target + firm_growth + persistent[name] + transitory[name], 0.0)
            flow = rate * stocks[name]
            new_stocks[name] = (1.0 - spec.depreciation) * stocks[name] + flow
            q = spec.after_tax_price(tax) + (1.0 - tax) * group.params.costs[name].marginal(rate)
            value += np.asarray(q) * new_stocks[name]
            row[flow_column(name)] = flow
            row[stock_column(name)] = new_stocks[name]
        frame = pd.DataFrame(row)
        noise = rng.normal(-0.5 * group.valuation_noise**2, group.valuation_noise, n)
        frame["market_value"] = value * np.exp(noise)
        frames.append(frame)
        stocks = new_stocks
    return pd.concat(frames, ignore_index=True)


def simulate_panel(design: SimulationDesign, seed: int | None = None) -> pd.DataFrame:
    """Draw a firm-year panel following :mod:`firmvalue.panel`."""
    rng = np.random.default_rng(seed)
    frames = [_simulate_group(group, design, rng) for group in design.groups]
    panel = pd.concat(frames, ignore_index=True)
    columns = [
        "firm",
        "year",
        "group",
        "market_value",
        "tax_rate",
        *(stock_column(n) for n in INPUTS),
        *(flow_column(n) for n in INPUTS),
    ]
    return panel[columns].sort_values(["firm", "year"]).reset_index(drop=True)
