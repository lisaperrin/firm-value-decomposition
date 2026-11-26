import numpy as np
import pandas as pd
import pytest

from firmvalue.inputs import DEFAULT_SPECS, INPUTS, Input
from firmvalue.model import (
    AdjustmentCost,
    Parameters,
    decompose,
    implied_value,
    investment_rate,
    shadow_values,
)
from firmvalue.panel import PanelError, validate_panel


@pytest.mark.parametrize("curvature", [2.0, 1.5, 3.0])
def test_marginal_cost_is_derivative_of_total(curvature):
    cost = AdjustmentCost(scale=4.0, curvature=curvature)
    stock = 10.0
    for rate in (0.05, 0.2, -0.1):
        h = 1e-6
        flow = rate * stock
        numeric = (
            cost.total((flow + h) / stock, stock) - cost.total((flow - h) / stock, stock)
        ) / (2 * h)
        assert numeric == pytest.approx(cost.marginal(rate), rel=1e-5)


def test_adjustment_cost_validation():
    with pytest.raises(ValueError, match="scale"):
        AdjustmentCost(-1.0)
    with pytest.raises(ValueError, match="curvature"):
        AdjustmentCost(1.0, curvature=1.0)


def test_parameters_round_trip(params):
    restored = Parameters.from_dict(params.to_dict())
    assert restored.to_dict() == params.to_dict()
    with pytest.raises(ValueError, match="missing"):
        Parameters({Input.PHYSICAL: AdjustmentCost(1.0)})


def test_investment_rate_recovers_opening_stock(small_panel):
    panel = validate_panel(small_panel)
    row = panel.iloc[0]
    rate = investment_rate(panel, Input.PHYSICAL, DEFAULT_SPECS[Input.PHYSICAL]).iloc[0]
    opening = (row["physical"] - row["capex"]) / 0.9
    assert rate == pytest.approx(row["capex"] / opening)


def test_investment_rate_handles_zero_stock(small_panel):
    panel = validate_panel(small_panel)
    panel.loc[0, ["knowledge", "rd"]] = 0.0
    panel.loc[1, ["knowledge", "rd"]] = [20.0, 20.0]
    rate = investment_rate(panel, Input.KNOWLEDGE, DEFAULT_SPECS[Input.KNOWLEDGE])
    assert rate.iloc[0] == 0.0
    assert rate.iloc[1] == pytest.approx(1.0)


def test_shadow_value_formulas(small_panel, params):
    panel = validate_panel(small_panel)
    q = shadow_values(panel, params)
    tau = 0.35
    rates = {n: investment_rate(panel, n, DEFAULT_SPECS[n]) for n in INPUTS}
    expected = {
        Input.PHYSICAL: 1 + (1 - tau) * 2.0 * rates[Input.PHYSICAL],
        Input.LABOR: (1 - tau) * 900.0 * rates[Input.LABOR],
        Input.KNOWLEDGE: (1 - tau) * (1 + 30.0 * rates[Input.KNOWLEDGE]),
        Input.BRAND: (1 - tau) * (1 + 6.0 * rates[Input.BRAND]),
    }
    for name in INPUTS:
        assert np.allclose(q[f"q_{name}"], expected[name])


def test_decomposition_identity_and_shares(small_panel, params):
    panel = validate_panel(small_panel)
    out = decompose(panel, params)
    shares = out[[f"share_{n}" for n in INPUTS]].sum(axis=1)
    assert np.allclose(shares, 1.0)
    book = out[[f"book_share_{n}" for n in INPUTS]].sum(axis=1)
    assert np.allclose(book, 1.0)
    assert (out["book_share_labor"] == 0).all()
    total = sum(out[f"value_{n}"] for n in INPUTS)
    assert np.allclose(total, out["implied_value"])
    assert np.allclose(out["implied_value"], implied_value(panel, params))
    assert np.allclose(out["book_value"], panel[["physical", "knowledge", "brand"]].sum(axis=1))


def test_validate_panel_errors(small_panel):
    with pytest.raises(PanelError, match="missing required"):
        validate_panel(small_panel.drop(columns=["capex"]))
    bad = small_panel.copy()
    bad.loc[0, "physical"] = 0.0
    with pytest.raises(PanelError, match="physical"):
        validate_panel(bad)
    duplicated = pd.concat([small_panel, small_panel.iloc[[0]]])
    with pytest.raises(PanelError, match="duplicate"):
        validate_panel(duplicated)
    without_group = validate_panel(small_panel.drop(columns=["group"]))
    assert (without_group["group"] == "all").all()
