import pandas as pd
import pytest

from firmvalue.inputs import Input
from firmvalue.model import Parameters
from firmvalue.panel import REQUIRED_COLUMNS, validate_panel
from firmvalue.simulate import GroupDesign, SimulationDesign, simulate_panel


def test_demo_panel_matches_schema(demo_panel):
    validated = validate_panel(demo_panel)
    assert set(REQUIRED_COLUMNS) <= set(validated.columns)
    assert validated["year"].min() == 1975
    assert validated["year"].max() == 2015
    assert set(validated["group"]) == {"low_skill", "high_skill"}
    assert validated["firm"].nunique() == 120


def test_seed_makes_simulation_reproducible():
    design = SimulationDesign.demo(firms_per_group=5)
    first = simulate_panel(design, seed=42)
    second = simulate_panel(design, seed=42)
    pd.testing.assert_frame_equal(first, second)
    third = simulate_panel(design, seed=43)
    assert not first["market_value"].equals(third["market_value"])


def test_law_of_motion_holds_in_simulated_data():
    design = SimulationDesign.demo(firms_per_group=3)
    panel = simulate_panel(design, seed=0).sort_values(["firm", "year"])
    one_firm = panel[panel["firm"] == panel["firm"].iloc[0]]
    physical = one_firm["physical"].to_numpy()
    capex = one_firm["capex"].to_numpy()
    assert physical[1] == pytest.approx(0.9 * physical[0] + capex[1])
    brand = one_firm["brand"].to_numpy()
    advertising = one_firm["advertising"].to_numpy()
    assert brand[1] == pytest.approx(0.5 * brand[0] + advertising[1])


def test_group_design_rejects_bad_mix():
    with pytest.raises(ValueError, match="book_mix"):
        GroupDesign(
            name="x",
            firms=1,
            params=Parameters.quadratic(1, 1, 1, 1),
            book_mix={Input.PHYSICAL: 0.5, Input.KNOWLEDGE: 0.2, Input.BRAND: 0.2},
        )
