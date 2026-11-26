import asyncio
import json
from pathlib import Path
from typing import Any

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from firmvalue import mcp_server
from firmvalue.simulate import SimulationDesign, simulate_panel

EXPECTED_TOOLS = {
    "estimate_parameters",
    "value_shares",
    "decompose_firm",
    "simulate_demo_panel",
    "published_value_shares",
}

SCALES = {"physical": 2.0, "labor": 900.0, "knowledge": 30.0, "brand": 6.0}


def call(tool: str, **arguments: Any) -> dict[str, Any]:
    result = asyncio.run(mcp_server.server.call_tool(tool, arguments))
    assert result.structured_content is not None
    assert json.loads(result.content[0].text) == result.structured_content
    return dict(result.structured_content)


@pytest.fixture(scope="module")
def panel_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("panel") / "panel.csv"
    simulate_panel(SimulationDesign.demo(firms_per_group=30), seed=5).to_csv(path, index=False)
    return path


def test_server_exposes_the_five_tools() -> None:
    names = {tool.name for tool in asyncio.run(mcp_server.server.list_tools())}
    assert names == EXPECTED_TOOLS


def test_every_tool_has_a_description() -> None:
    for tool in asyncio.run(mcp_server.server.list_tools()):
        assert tool.description, tool.name


def test_estimate_parameters_returns_groups_with_fit(panel_path: Path) -> None:
    data = call("estimate_parameters", panel_path=str(panel_path))
    assert set(data) == {"all", "low_skill", "high_skill"}
    low = data["low_skill"]
    assert set(low["parameters"]) == set(SCALES)
    assert low["parameters"]["brand"]["curvature"] == 2.0
    assert set(low["fit"]) >= {"pooled_r2", "time_series_r2", "cross_section_r2"}
    assert low["converged"] is True


def test_value_shares_estimates_when_no_parameters_given(panel_path: Path) -> None:
    data = call("value_shares", panel_path=str(panel_path))
    assert data["units"] == "percent"
    rows = data["shares"]
    assert {r["group"] for r in rows} == {"all", "low_skill", "high_skill"}
    market = sum(r["market"] for r in rows if r["group"] == "all")
    assert market == pytest.approx(100.0)
    labor = next(r for r in rows if r["group"] == "all" and r["input"] == "labor")
    assert labor["book"] == 0.0


def test_value_shares_reads_parameters_file(panel_path: Path, tmp_path: Path) -> None:
    params = tmp_path / "parameters.json"
    params.write_text(
        json.dumps({"all": {"parameters": {k: {"scale": v} for k, v in SCALES.items()}}})
    )
    data = call("value_shares", panel_path=str(panel_path), parameters_path=str(params))
    assert len(data["shares"]) == 12


def test_missing_panel_is_a_tool_error() -> None:
    with pytest.raises(ToolError, match="not found"):
        call("estimate_parameters", panel_path="/definitely/missing.csv")


def test_decompose_firm_matches_the_formulas() -> None:
    data = call(
        "decompose_firm",
        physical=1000.0,
        labor=4.0,
        knowledge=300.0,
        brand=100.0,
        capex=130.0,
        hires=0.5,
        rd=55.0,
        advertising=52.0,
        tax_rate=0.35,
        scales=SCALES,
    )
    inputs = data["inputs"]
    rate_physical = 130.0 / ((1000.0 - 130.0) / 0.9)
    assert inputs["physical"]["shadow_value"] == pytest.approx(1 + 0.65 * 2.0 * rate_physical)
    rate_labor = 0.5 / ((4.0 - 0.5) / 0.9)
    assert inputs["labor"]["shadow_value"] == pytest.approx(0.65 * 900.0 * rate_labor)
    assert sum(v["share"] for v in inputs.values()) == pytest.approx(1.0)
    assert inputs["labor"]["book_share"] == 0.0
    assert data["book_value"] == 1400.0
    assert data["implied_value"] == pytest.approx(sum(v["value"] for v in inputs.values()))


def test_decompose_firm_requires_every_scale() -> None:
    with pytest.raises(ToolError, match="missing"):
        call(
            "decompose_firm",
            physical=1.0,
            labor=0.0,
            knowledge=0.0,
            brand=0.0,
            capex=0.1,
            hires=0.0,
            rd=0.0,
            advertising=0.0,
            tax_rate=0.3,
            scales={"physical": 1.0},
        )


def test_decompose_firm_rejects_negative_scale() -> None:
    with pytest.raises(ToolError, match="non-negative"):
        call(
            "decompose_firm",
            physical=1.0,
            labor=0.0,
            knowledge=0.0,
            brand=0.0,
            capex=0.1,
            hires=0.0,
            rd=0.0,
            advertising=0.0,
            tax_rate=0.3,
            scales={**SCALES, "brand": -1.0},
        )


def test_simulate_demo_panel_writes_csv(tmp_path: Path) -> None:
    out = tmp_path / "sim.csv"
    data = call("simulate_demo_panel", out_path=str(out), firms_per_group=3, seed=1)
    assert out.is_file()
    assert data["firms"] == 6
    assert data["years"] == [1975, 2015]
    assert data["groups"] == ["high_skill", "low_skill"]
    with pytest.raises(ToolError, match="at least 1"):
        call("simulate_demo_panel", out_path=str(out), firms_per_group=0)


def test_published_value_shares_cites_the_paper() -> None:
    data = call("published_value_shares")
    assert len(data["shares"]) == 12
    assert "Belo" in data["citation"]


def test_main_is_an_entry_point() -> None:
    assert callable(mcp_server.main)
