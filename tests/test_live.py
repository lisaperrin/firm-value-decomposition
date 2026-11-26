import importlib.util
from dataclasses import replace

import numpy as np
import pytest

from firmvalue.inputs import INPUTS
from firmvalue.live import (
    ILLUSTRATIVE_PARAMETERS,
    LiveDataError,
    LiveDependencyError,
    LiveOptions,
    decompose_live,
    fetch_and_decompose,
    statements_to_panel,
)
from firmvalue.model import Parameters, implied_value
from firmvalue.panel import REQUIRED_COLUMNS
from tests.live_fixtures import make_records

EMPLOYEES = 30_000


def test_panel_follows_schema_in_millions_and_thousands():
    live = statements_to_panel(make_records(), EMPLOYEES)
    panel = live.panel
    assert set(REQUIRED_COLUMNS) <= set(panel.columns)
    assert panel["year"].tolist() == [2022, 2023, 2024, 2025]
    last = panel.iloc[-1]
    assert last["physical"] == pytest.approx(8000.0)
    assert last["capex"] == pytest.approx(1200.0)
    assert last["rd"] == pytest.approx(3000.0)
    assert last["advertising"] == pytest.approx(0.30 * 2000.0)
    assert last["labor"] == pytest.approx(30.0)
    assert last["hires"] == pytest.approx(0.10 * 30.0)
    assert last["market_value"] == pytest.approx(50.0 * 1000.0 + 4000.0)
    assert last["tax_rate"] == 0.21
    assert live.currency == "USD"
    assert live.years_dropped == ()


def test_intangible_stocks_accumulate_with_perpetual_inventory():
    panel = statements_to_panel(make_records(), EMPLOYEES).panel
    rd = panel["rd"].to_numpy()
    knowledge = panel["knowledge"].to_numpy()
    assert knowledge[0] == pytest.approx(0.85 * rd[0] / 0.18 + rd[0])
    assert knowledge[1] == pytest.approx(0.85 * knowledge[0] + rd[1])
    brand = panel["brand"].to_numpy()
    advertising = panel["advertising"].to_numpy()
    assert brand[2] == pytest.approx(0.5 * brand[1] + advertising[2])


def test_options_change_construction():
    options = LiveOptions(brand_share_of_sga=0.5, tax_rate=0.30, net_of_cash=True)
    live = statements_to_panel(make_records(currency="EUR"), EMPLOYEES, options)
    last = live.panel.iloc[-1]
    assert last["advertising"] == pytest.approx(1000.0)
    assert last["tax_rate"] == 0.30
    assert last["market_value"] == pytest.approx(50.0 * 1000.0 + 4000.0 - 6000.0)
    assert any("net of cash" in note for note in live.notes)
    assert not any("statutory" in note for note in live.notes)
    with pytest.raises(ValueError, match="brand_share_of_sga"):
        LiveOptions(brand_share_of_sga=1.5)
    with pytest.raises(ValueError, match="tax_rate"):
        LiveOptions(tax_rate=1.0)


def test_non_usd_filer_without_tax_override_is_flagged():
    live = statements_to_panel(make_records(currency="EUR"), EMPLOYEES)
    assert any("EUR filer" in note for note in live.notes)


def test_years_without_required_lines_are_dropped_and_noted():
    records = make_records()
    records[0] = replace(records[0], price_at_year_end=None)
    records[1] = replace(records[1], rd_expense=None, total_debt=None)
    live = statements_to_panel(records, EMPLOYEES)
    assert live.years_dropped == (2022,)
    assert live.panel["year"].tolist() == [2023, 2024, 2025]
    assert live.panel["rd"].iloc[0] == 0.0
    assert any("R&D missing" in note for note in live.notes)
    assert any("debt missing" in note for note in live.notes)


def test_no_usable_year_raises():
    records = [replace(r, shares_outstanding=None) for r in make_records()]
    with pytest.raises(LiveDataError, match="share count"):
        statements_to_panel(records, EMPLOYEES)
    with pytest.raises(LiveDataError, match="no annual statements"):
        statements_to_panel([], EMPLOYEES)
    duplicated = [*make_records(), make_records()[-1]]
    with pytest.raises(LiveDataError, match="share a fiscal year"):
        statements_to_panel(duplicated, EMPLOYEES)


def test_missing_headcount_gives_zero_labor_share():
    result = decompose_live(make_records(), None)
    assert result.latest["share_labor"] == 0.0
    assert any("no headcount" in note for note in result.notes)


def test_decomposition_uses_illustrative_parameters_by_default():
    result = decompose_live(make_records(), EMPLOYEES)
    assert "illustrative" in result.parameters_source
    shares = sum(result.latest[f"share_{name}"] for name in INPUTS)
    assert shares == pytest.approx(1.0)
    panel = statements_to_panel(make_records(), EMPLOYEES).panel
    expected = implied_value(panel, ILLUSTRATIVE_PARAMETERS).iloc[-1]
    assert result.latest["implied_value"] == pytest.approx(expected)
    assert result.latest["observed_ratio"] == pytest.approx(
        result.latest["observed_value"] / result.latest["book_value"]
    )


def test_user_parameters_are_labelled():
    params = Parameters.quadratic(1.0, 500.0, 10.0, 2.0)
    result = decompose_live(make_records(), EMPLOYEES, params)
    assert result.parameters_source == "user-supplied parameters"
    labelled = decompose_live(make_records(), EMPLOYEES, params, "estimates.json")
    assert labelled.parameters_source == "estimates.json"


def test_to_dict_is_json_ready_in_percent():
    data = decompose_live(make_records(), EMPLOYEES).to_dict()
    assert data["symbol"] == "ACME"
    assert data["latest_fiscal_year"] == 2025
    assert sum(v["share"] for v in data["inputs"].values()) == pytest.approx(100.0)
    assert data["inputs"]["labor"]["book_share"] == 0.0
    assert len(data["by_year"]) == 4
    assert all(isinstance(v, float) for v in data["inputs"]["physical"].values())
    assert any("advertising proxied" in note for note in data["notes"])
    assert not np.isnan(data["implied_ratio"])


def test_fetch_uses_the_configured_source(monkeypatch):
    calls = []

    def fake_source(symbol, years):
        calls.append((symbol, years))
        return make_records(symbol), EMPLOYEES

    import firmvalue.live as live

    monkeypatch.setattr(live, "statements_source", fake_source)
    result = fetch_and_decompose("acme", years=3)
    assert calls == [("acme", 3)]
    assert result.symbol == "acme"
    with pytest.raises(LiveDataError, match="at least 2"):
        fetch_and_decompose("acme", years=1)


def test_missing_marketlens_is_a_clear_error(monkeypatch):
    import builtins

    import firmvalue.live as live

    real_import = builtins.__import__

    def no_marketlens(name, *args, **kwargs):
        if name.startswith("marketlens"):
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_marketlens)
    with pytest.raises(LiveDependencyError, match="firmvalue\\[live\\]"):
        live._marketlens_source("ACME", 4)


@pytest.mark.skipif(
    importlib.util.find_spec("marketlens") is None, reason="marketlens extra not installed"
)
def test_marketlens_records_pass_through():
    from marketlens.data import STATEMENT_FIELDS
    from marketlens.data.fake import make_statements

    from tests.live_fixtures import Statement

    assert set(STATEMENT_FIELDS) == set(Statement.__dataclass_fields__)
    result = decompose_live(make_statements("NVDA"), 36_000)
    assert result.symbol == "NVDA"
    assert result.by_year["year"].tolist() == [2022, 2023, 2024, 2025]
