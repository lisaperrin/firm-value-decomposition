import numpy as np
import pandas as pd
import pytest

from firmvalue.compustat import from_compustat, is_regulated


def _funda() -> pd.DataFrame:
    rows = []
    for gvkey, sic in ((1001, 3571), (1002, 2834), (1003, 6020)):
        for i, fyear in enumerate(range(2000, 2006)):
            rows.append(
                {
                    "gvkey": gvkey,
                    "fyear": fyear,
                    "sic": sic,
                    "prcc_f": 20.0 + i,
                    "csho": 50.0,
                    "dltt": 100.0,
                    "dlc": 10.0,
                    "che": 30.0,
                    "ppent": 400.0 + 10 * i,
                    "capx": 60.0,
                    "xrd": 30.0 if gvkey != 1001 else np.nan,
                    "xad": 12.0,
                    "emp": 2.0 + 0.1 * i,
                }
            )
    return pd.DataFrame(rows)


def test_regulated_filter():
    assert is_regulated(pd.Series([6020, 4911, 3571, None])).tolist() == [True, True, False, False]


def test_panel_construction():
    panel = from_compustat(_funda())
    assert set(panel["firm"]) == {"1001", "1002"}
    assert panel["year"].min() == 2001
    first = panel[(panel["firm"] == "1002") & (panel["year"] == 2001)].iloc[0]
    assert first["market_value"] == pytest.approx(21.0 * 50.0 + 110.0)
    assert first["physical"] == 410.0
    assert first["capex"] == 60.0
    assert first["hires"] == pytest.approx(2.1 - 0.9 * 2.0)
    assert first["tax_rate"] == 0.35
    assert first["knowledge"] > 0
    assert first["brand"] > 0
    no_rd = panel[panel["firm"] == "1001"]
    assert (no_rd["knowledge"] == 0).all()
    assert (no_rd["rd"] == 0).all()


def test_options_and_grouping():
    panel = from_compustat(
        _funda(),
        net_of_cash=True,
        exclude_regulated=False,
        group=lambda d: np.where(d["sic"] == 2834, "high_skill", "low_skill"),
    )
    assert set(panel["firm"]) == {"1001", "1002", "1003"}
    assert set(panel["group"]) == {"high_skill", "low_skill"}
    row = panel[(panel["firm"] == "1002") & (panel["year"] == 2001)].iloc[0]
    assert row["market_value"] == pytest.approx(21.0 * 50.0 + 110.0 - 30.0)


def test_min_years_and_missing_columns():
    short = _funda()
    short = short[~((short["gvkey"] == 1002) & (short["fyear"] > 2002))]
    panel = from_compustat(short, min_years=3)
    assert set(panel["firm"]) == {"1001"}
    with pytest.raises(ValueError, match="missing columns"):
        from_compustat(short.drop(columns=["emp"]))
