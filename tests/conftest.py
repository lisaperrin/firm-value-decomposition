import pandas as pd
import pytest

from firmvalue.model import Parameters
from firmvalue.simulate import SimulationDesign, simulate_panel


@pytest.fixture(scope="session")
def demo_panel() -> pd.DataFrame:
    return simulate_panel(SimulationDesign.demo(firms_per_group=60), seed=1)


@pytest.fixture
def small_panel() -> pd.DataFrame:
    rows = []
    for firm, scale in (("a", 1.0), ("b", 3.0)):
        for i, year in enumerate(range(2000, 2005)):
            growth = 1.03**i
            rows.append(
                {
                    "firm": firm,
                    "year": year,
                    "group": "g1" if firm == "a" else "g2",
                    "market_value": 2500.0 * scale * growth,
                    "tax_rate": 0.35,
                    "physical": 1000.0 * scale * growth,
                    "labor": 4.0 * scale * growth,
                    "knowledge": 300.0 * scale * growth,
                    "brand": 100.0 * scale * growth,
                    "capex": 130.0 * scale * growth,
                    "hires": 0.5 * scale * growth,
                    "rd": 55.0 * scale * growth,
                    "advertising": 52.0 * scale * growth,
                }
            )
    return pd.DataFrame(rows)


@pytest.fixture
def params() -> Parameters:
    return Parameters.quadratic(physical=2.0, labor=900.0, knowledge=30.0, brand=6.0)
