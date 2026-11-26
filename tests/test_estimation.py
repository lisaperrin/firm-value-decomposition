import math

import numpy as np
import pytest

from firmvalue.estimation import estimate, estimate_by_group, fit_statistics
from firmvalue.inputs import INPUTS, Input
from firmvalue.model import Parameters
from firmvalue.simulate import GroupDesign, SimulationDesign, simulate_panel

TRUE = Parameters.quadratic(physical=2.0, labor=1200.0, knowledge=25.0, brand=4.0)


def _design(noise: float, firms: int = 150) -> SimulationDesign:
    group = GroupDesign(
        name="mc",
        firms=firms,
        params=TRUE,
        book_mix={Input.PHYSICAL: 0.65, Input.KNOWLEDGE: 0.2, Input.BRAND: 0.15},
        valuation_noise=noise,
    )
    return SimulationDesign(groups=(group,), start_year=1990, end_year=2010)


def test_noise_free_panel_is_recovered_exactly():
    panel = simulate_panel(_design(noise=0.0), seed=3)
    result = estimate(panel)
    for name in INPUTS:
        assert result.params.costs[name].scale == pytest.approx(TRUE.costs[name].scale, rel=1e-6)
        assert result.params.costs[name].curvature == 2.0
    assert result.fit.pooled_r2 == pytest.approx(1.0, abs=1e-9)
    assert result.converged


def test_noisy_panel_recovers_within_sampling_error():
    panel = simulate_panel(_design(noise=0.25, firms=300), seed=7)
    result = estimate(panel)
    for name in INPUTS:
        truth = TRUE.costs[name].scale
        estimate_ = result.params.costs[name].scale
        se = result.standard_errors[f"scale_{name}"]
        assert math.isfinite(se)
        assert se > 0
        assert abs(estimate_ - truth) < max(4 * se, 0.1 * truth)
    assert 0.0 < result.fit.pooled_r2 <= 1.0
    assert result.fit.time_series_r2 > 0.5
    assert result.fit.cross_section_r2 > 0.8


def test_curvature_estimation_nests_quadratic_truth():
    panel = simulate_panel(_design(noise=0.05, firms=200), seed=11)
    result = estimate(panel, estimate_curvature=True)
    for name in (Input.PHYSICAL, Input.KNOWLEDGE, Input.BRAND, Input.LABOR):
        assert result.params.costs[name].curvature == pytest.approx(2.0, abs=0.35)
        assert f"curvature_{name}" in result.standard_errors
    assert result.fit.pooled_r2 > 0.9
    assert len(result.summary()) == 2 * len(INPUTS)


def test_estimate_by_group_returns_pooled_and_groups(demo_panel):
    results = estimate_by_group(demo_panel)
    assert set(results) == {"all", "low_skill", "high_skill"}
    assert results["low_skill"].fit.observations < results["all"].fit.observations
    low = results["low_skill"].params.costs
    high = results["high_skill"].params.costs
    assert low[Input.BRAND].scale > high[Input.BRAND].scale
    assert high[Input.LABOR].scale > low[Input.LABOR].scale


def test_fit_statistics_degenerate_inputs(small_panel):
    fitted = small_panel.rename(columns={"market_value": "observed_ratio"})[
        ["firm", "year", "observed_ratio"]
    ].copy()
    fitted["implied_ratio"] = fitted["observed_ratio"]
    fitted["book_value"] = 1.0
    stats = fit_statistics(fitted, portfolios=10)
    assert stats.pooled_r2 == pytest.approx(1.0)
    assert stats.time_series_r2 == pytest.approx(1.0)
    assert np.isnan(stats.cross_section_r2)
    assert stats.observations == len(fitted)
    assert set(stats.to_dict()) >= {"pooled_r2", "rmse", "firms", "years"}
