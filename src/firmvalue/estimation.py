"""Nonlinear least-squares estimation of the adjustment cost parameters.

The model is fitted to the valuation ratio: market value divided by the book
sum of the purchased capital stocks (physical, knowledge and brand capital).
Given the value identity the model-implied ratio is

    v_hat(theta) = sum_j q_j(theta) X_j / (K + N + B),

and the estimator minimises the sum of squared differences between observed
and implied ratios across firm-years. With quadratic adjustment costs the
problem is linear in the scale parameters and the non-negative least-squares
solution is exact; it also seeds the general nonlinear problem when the
curvature of the cost functions is estimated as well.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.optimize import least_squares, nnls

from firmvalue.inputs import DEFAULT_SPECS, INPUTS, Input, InputSpec
from firmvalue.model import AdjustmentCost, Parameters, book_capital, investment_rate
from firmvalue.panel import stock_column, validate_panel

CURVATURE_BOUNDS: tuple[float, float] = (1.05, 6.0)


@dataclass(frozen=True, slots=True)
class FitStatistics:
    """Goodness of fit of the valuation ratio at three levels of aggregation.

    ``pooled_r2`` uses every firm-year. ``time_series_r2`` compares the annual
    aggregate ratio (total market value over total book capital) with its
    model counterpart across years. ``cross_section_r2`` compares average
    ratios across portfolios of firms sorted each year on the previous year's
    observed ratio, so that the sort does not mechanically favour the model.
    All three are ``1 - SSR / SST`` and may be negative for a poor fit.
    """

    pooled_r2: float
    time_series_r2: float
    cross_section_r2: float
    rmse: float
    observations: int
    firms: int
    years: int

    def to_dict(self) -> dict[str, float]:
        """Plain mapping for serialisation."""
        return {
            "pooled_r2": self.pooled_r2,
            "time_series_r2": self.time_series_r2,
            "cross_section_r2": self.cross_section_r2,
            "rmse": self.rmse,
            "observations": float(self.observations),
            "firms": float(self.firms),
            "years": float(self.years),
        }


@dataclass(frozen=True, slots=True)
class EstimationResult:
    """Estimated parameters, firm-clustered standard errors and fit."""

    group: str
    params: Parameters
    standard_errors: Mapping[str, float]
    fit: FitStatistics
    fitted: pd.DataFrame
    converged: bool

    def summary(self) -> pd.DataFrame:
        """One row per estimated parameter with estimate and standard error."""
        rows = []
        for name, cost in self.params.costs.items():
            rows.append(
                {
                    "group": self.group,
                    "input": str(name),
                    "parameter": "scale",
                    "estimate": cost.scale,
                    "std_error": self.standard_errors.get(f"scale_{name}", float("nan")),
                }
            )
            if f"curvature_{name}" in self.standard_errors:
                rows.append(
                    {
                        "group": self.group,
                        "input": str(name),
                        "parameter": "curvature",
                        "estimate": cost.curvature,
                        "std_error": self.standard_errors[f"curvature_{name}"],
                    }
                )
        return pd.DataFrame(rows)


@dataclass(frozen=True, slots=True)
class _Design:
    """Pre-computed arrays entering the implied valuation ratio."""

    observed: np.ndarray
    price_terms: np.ndarray
    after_tax: np.ndarray
    rates: np.ndarray
    weights: np.ndarray

    def implied(self, scales: np.ndarray, curvatures: np.ndarray) -> np.ndarray:
        marginal = (
            scales[None, :]
            * np.sign(self.rates)
            * np.abs(self.rates) ** (curvatures[None, :] - 1.0)
        )
        total = self.price_terms + (self.after_tax[:, None] * marginal * self.weights).sum(axis=1)
        return np.asarray(total, dtype=float)


def _design(panel: pd.DataFrame, specs: Mapping[Input, InputSpec]) -> _Design:
    book = book_capital(panel, Parameters.quadratic(0, 0, 0, 0, specs)).to_numpy()
    tax = panel["tax_rate"].to_numpy(dtype=float)
    rates = np.column_stack([investment_rate(panel, n, specs[n]).to_numpy() for n in INPUTS])
    stocks = np.column_stack([panel[stock_column(n)].to_numpy(dtype=float) for n in INPUTS])
    prices = np.column_stack([specs[n].after_tax_prices(tax) for n in INPUTS])
    return _Design(
        observed=panel["market_value"].to_numpy(dtype=float) / book,
        price_terms=(prices * stocks).sum(axis=1) / book,
        after_tax=1.0 - tax,
        rates=rates,
        weights=stocks / book[:, None],
    )


def _linear_solution(design: _Design) -> np.ndarray:
    regressors = design.after_tax[:, None] * design.rates * design.weights
    target = design.observed - design.price_terms
    solution, _ = nnls(regressors, target)
    return np.asarray(solution, dtype=float)


def _cluster_robust_se(jac: np.ndarray, resid: np.ndarray, clusters: np.ndarray) -> np.ndarray:
    n, k = jac.shape
    bread = np.linalg.pinv(jac.T @ jac)
    scores = jac * resid[:, None]
    groups, inverse = np.unique(clusters, return_inverse=True)
    summed = np.zeros((groups.size, k))
    np.add.at(summed, inverse, scores)
    meat = summed.T @ summed
    g = groups.size
    correction = (g / max(g - 1, 1)) * ((n - 1) / max(n - k, 1))
    cov = correction * bread @ meat @ bread
    return np.asarray(np.sqrt(np.clip(np.diag(cov), 0.0, None)), dtype=float)


def _r2(observed: np.ndarray, fitted: np.ndarray) -> float:
    if observed.size < 2:
        return float("nan")
    sst = float(((observed - observed.mean()) ** 2).sum())
    if sst == 0.0:
        return float("nan")
    return 1.0 - float(((observed - fitted) ** 2).sum()) / sst


def fit_statistics(fitted: pd.DataFrame, portfolios: int = 10) -> FitStatistics:
    """Compute :class:`FitStatistics` from a frame of observed and implied ratios.

    ``fitted`` needs columns ``firm``, ``year``, ``observed_ratio``,
    ``implied_ratio`` and ``book_value``.
    """
    observed = fitted["observed_ratio"].to_numpy()
    implied = fitted["implied_ratio"].to_numpy()
    pooled = _r2(observed, implied)
    rmse = float(np.sqrt(np.mean((observed - implied) ** 2)))

    weighted = fitted.assign(
        obs_value=fitted["observed_ratio"] * fitted["book_value"],
        imp_value=fitted["implied_ratio"] * fitted["book_value"],
    )
    annual = weighted.groupby("year")[["obs_value", "imp_value", "book_value"]].sum()
    time_series = _r2(
        (annual["obs_value"] / annual["book_value"]).to_numpy(),
        (annual["imp_value"] / annual["book_value"]).to_numpy(),
    )

    ordered = fitted.sort_values(["firm", "year"])
    lagged = ordered.groupby("firm")["observed_ratio"].shift(1)
    same_firm_prev_year = ordered.groupby("firm")["year"].diff() == 1
    sortable = ordered.assign(lagged=lagged.where(same_firm_prev_year)).dropna(subset=["lagged"])
    cross_section = float("nan")
    if len(sortable) >= 2 * portfolios:
        ranks = sortable.groupby("year")["lagged"].rank(method="first", pct=True)
        bins = np.minimum((ranks * portfolios).to_numpy().astype(int), portfolios - 1)
        by_portfolio = sortable.groupby(bins)[["observed_ratio", "implied_ratio"]].mean()
        cross_section = _r2(
            by_portfolio["observed_ratio"].to_numpy(), by_portfolio["implied_ratio"].to_numpy()
        )

    return FitStatistics(
        pooled_r2=pooled,
        time_series_r2=time_series,
        cross_section_r2=cross_section,
        rmse=rmse,
        observations=len(fitted),
        firms=int(fitted["firm"].nunique()),
        years=int(fitted["year"].nunique()),
    )


def estimate(
    panel: pd.DataFrame,
    specs: Mapping[Input, InputSpec] | None = None,
    estimate_curvature: bool = False,
    group: str = "all",
    portfolios: int = 10,
) -> EstimationResult:
    """Estimate adjustment cost parameters on a validated firm-year panel.

    Parameters
    ----------
    panel
        Firm-year panel following :mod:`firmvalue.panel`.
    specs
        Depreciation and tax treatment of each input; defaults to
        :data:`firmvalue.inputs.DEFAULT_SPECS`.
    estimate_curvature
        Also estimate the curvature of every adjustment cost function
        instead of fixing it at 2 (quadratic costs).
    group
        Label stored on the result.
    portfolios
        Number of portfolios used for the cross-sectional fit statistic.

    """
    specs = dict(DEFAULT_SPECS) if specs is None else dict(specs)
    panel = validate_panel(panel)
    design = _design(panel, specs)
    k = len(INPUTS)
    scales0 = _linear_solution(design)
    base_curvature = np.full(k, 2.0)

    if estimate_curvature:
        x0 = np.concatenate([scales0, base_curvature])
        lower = np.concatenate([np.zeros(k), np.full(k, CURVATURE_BOUNDS[0])])
        upper = np.concatenate([np.full(k, np.inf), np.full(k, CURVATURE_BOUNDS[1])])

        def residuals(x: np.ndarray) -> np.ndarray:
            return np.asarray(design.implied(x[:k], x[k:]) - design.observed)

    else:
        x0 = scales0
        lower = np.zeros(k)
        upper = np.full(k, np.inf)

        def residuals(x: np.ndarray) -> np.ndarray:
            return np.asarray(design.implied(x, base_curvature) - design.observed)

    solution = least_squares(
        residuals, x0, bounds=(lower, upper), method="trf", x_scale="jac", max_nfev=2000
    )
    estimates = np.asarray(solution.x, dtype=float)
    scales = estimates[:k]
    curvatures = estimates[k:] if estimate_curvature else base_curvature

    clusters = panel["firm"].to_numpy()
    errors = _cluster_robust_se(np.asarray(solution.jac), np.asarray(solution.fun), clusters)
    labels = [f"scale_{n}" for n in INPUTS]
    if estimate_curvature:
        labels += [f"curvature_{n}" for n in INPUTS]
    standard_errors = dict(zip(labels, errors.tolist(), strict=True))

    params = Parameters(
        {
            n: AdjustmentCost(float(s), float(c))
            for n, s, c in zip(INPUTS, scales, curvatures, strict=True)
        },
        specs,
    )
    fitted = panel[["firm", "year", "group"]].copy()
    fitted["book_value"] = book_capital(panel, params)
    fitted["observed_ratio"] = design.observed
    fitted["implied_ratio"] = design.implied(scales, curvatures)
    fitted["residual"] = fitted["observed_ratio"] - fitted["implied_ratio"]

    return EstimationResult(
        group=group,
        params=params,
        standard_errors=standard_errors,
        fit=fit_statistics(fitted, portfolios),
        fitted=fitted,
        converged=bool(solution.success),
    )


def estimate_by_group(
    panel: pd.DataFrame,
    specs: Mapping[Input, InputSpec] | None = None,
    estimate_curvature: bool = False,
    include_all: bool = True,
    portfolios: int = 10,
) -> dict[str, EstimationResult]:
    """Estimate separately for every value of the panel's ``group`` column.

    When ``include_all`` is true the pooled estimate is stored under ``"all"``.
    """
    panel = validate_panel(panel)
    results: dict[str, EstimationResult] = {}
    if include_all:
        results["all"] = estimate(panel, specs, estimate_curvature, "all", portfolios)
    for label, frame in panel.groupby("group", sort=True):
        key = str(label)
        if key == "all" and include_all:
            continue
        results[key] = estimate(frame, specs, estimate_curvature, key, portfolios)
    return results
