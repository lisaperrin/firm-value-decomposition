import numpy as np
import pandas as pd
import pytest

from firmvalue.capital import perpetual_inventory, perpetual_inventory_by_firm


def test_constant_flow_without_growth_stays_at_steady_state():
    flows = pd.Series([10.0] * 50)
    stock = perpetual_inventory(flows, depreciation=0.2, growth=0.0)
    assert np.allclose(stock, 50.0)


def test_steady_state_initialisation_with_growth():
    g, d = 0.05, 0.15
    flows = pd.Series(10.0 * (1 + g) ** np.arange(40))
    stock = perpetual_inventory(flows, depreciation=d, growth=g)
    ratio = stock.to_numpy() / flows.to_numpy()
    assert np.allclose(ratio, ratio[0])
    assert ratio[0] == pytest.approx((1 + g) / (g + d))


def test_explicit_initial_stock_and_missing_flows():
    flows = pd.Series([5.0, np.nan, 5.0])
    stock = perpetual_inventory(flows, depreciation=0.5, initial=100.0)
    assert stock.tolist() == [55.0, 27.5, 18.75]


def test_invalid_rates_rejected():
    with pytest.raises(ValueError, match="depreciation"):
        perpetual_inventory(pd.Series([1.0]), depreciation=0.0)
    with pytest.raises(ValueError, match="growth"):
        perpetual_inventory(pd.Series([1.0]), depreciation=0.1, growth=-0.2)


def test_by_firm_respects_firm_boundaries_and_original_order():
    frame = pd.DataFrame(
        {
            "firm": ["b", "a", "b", "a"],
            "year": [2001, 2001, 2000, 2000],
            "flow": [1.0, 2.0, 1.0, 2.0],
        }
    )
    stock = perpetual_inventory_by_firm(frame, "flow", depreciation=0.5, growth=0.0)
    expected_first = {"a": 4.0, "b": 2.0}
    assert stock.loc[3] == expected_first["a"]
    assert stock.loc[2] == expected_first["b"]
    assert stock.loc[1] == pytest.approx(0.5 * 4.0 + 2.0)
    assert stock.loc[0] == pytest.approx(0.5 * 2.0 + 1.0)
