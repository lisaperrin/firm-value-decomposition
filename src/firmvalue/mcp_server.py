"""A Model Context Protocol server exposing the decomposition to Claude and other clients.

Run it over stdio with ``firmvalue-mcp`` (or ``uvx --from <this repo> firmvalue-mcp``).
Tools return JSON-compatible dicts; package errors surface as tool errors carrying the
message rather than as opaque server failures.
"""

from __future__ import annotations

import functools
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import pandas as pd
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from firmvalue import __version__
from firmvalue.errors import FirmValueError, ParametersError
from firmvalue.estimation import estimate_by_group
from firmvalue.inputs import INPUTS, Input
from firmvalue.io import (
    decompose_by_group,
    read_panel,
    read_parameters,
    results_to_dict,
    share_table,
)
from firmvalue.model import AdjustmentCost, Parameters, decompose
from firmvalue.panel import flow_column, stock_column
from firmvalue.reference import CITATION, published_shares
from firmvalue.simulate import SimulationDesign, simulate_panel

server = MCPServer(
    name="firmvalue",
    version=__version__,
    instructions=(
        "Structural decomposition of firm value into physical capital, labor, knowledge "
        "capital and brand capital (Belo, Gala, Salomao and Vitorino, 2022). Use "
        "estimate_parameters on a firm-year panel CSV, value_shares for average shares, "
        "decompose_firm for one firm-year given parameters, simulate_demo_panel to create a "
        "synthetic panel, and published_value_shares for the paper's tables."
    ),
)


def _tool_errors[**P, R](func: Callable[P, R]) -> Callable[P, R]:
    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return func(*args, **kwargs)
        except FirmValueError as exc:
            raise ToolError(str(exc)) from exc

    return wrapper


def _parameters(scales: Mapping[str, float], curvatures: Mapping[str, float] | None) -> Parameters:
    missing = [str(name) for name in INPUTS if str(name) not in scales]
    if missing:
        raise ToolError(f"scales must include every input; missing {missing}")
    curvatures = curvatures or {}
    try:
        costs = {
            name: AdjustmentCost(float(scales[str(name)]), float(curvatures.get(str(name), 2.0)))
            for name in INPUTS
        }
    except ValueError as exc:
        raise ToolError(str(exc)) from exc
    return Parameters(costs)


@server.tool()
@_tool_errors
def estimate_parameters(panel_path: str, estimate_curvature: bool = False) -> dict[str, Any]:
    """Estimate adjustment cost parameters from a firm-year panel CSV, pooled and by group.

    Returns, per group, the parameters, firm-clustered standard errors and fit statistics
    (pooled, time-series and cross-sectional R squared of the valuation ratio).
    """
    panel = read_panel(Path(panel_path).expanduser())
    return results_to_dict(estimate_by_group(panel, estimate_curvature=estimate_curvature))


@server.tool()
@_tool_errors
def value_shares(panel_path: str, parameters_path: str | None = None) -> dict[str, Any]:
    """Average book-value and market-value shares of the four inputs, pooled and by group.

    ``parameters_path`` is the JSON written by the ``estimate`` command or
    ``estimate_parameters``; when omitted the parameters are estimated first.
    """
    panel = read_panel(Path(panel_path).expanduser())
    if parameters_path is None:
        params = {g: r.params for g, r in estimate_by_group(panel).items()}
    else:
        params = read_parameters(Path(parameters_path).expanduser())
    table = share_table(decompose_by_group(panel, params))
    return {"shares": table.to_dict(orient="records"), "units": "percent"}


@server.tool()
@_tool_errors
def decompose_firm(
    physical: float,
    labor: float,
    knowledge: float,
    brand: float,
    capex: float,
    hires: float,
    rd: float,
    advertising: float,
    tax_rate: float,
    scales: dict[str, float],
    curvatures: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Decompose one firm-year given its stocks, flows, tax rate and cost parameters.

    Stocks are end-of-year values (capital in money units, labor in thousands of
    employees); flows are the year's capital expenditure, net hires, R&D and advertising.
    ``scales`` maps physical, labor, knowledge and brand to adjustment cost scales;
    ``curvatures`` optionally overrides the quadratic default of 2.
    """
    params = _parameters(scales, curvatures)
    row: dict[str, Any] = {
        "firm": "firm",
        "year": 0,
        "group": "all",
        "market_value": 1.0,
        "tax_rate": tax_rate,
    }
    values = {
        Input.PHYSICAL: (physical, capex),
        Input.LABOR: (labor, hires),
        Input.KNOWLEDGE: (knowledge, rd),
        Input.BRAND: (brand, advertising),
    }
    for name, (stock, flow) in values.items():
        row[stock_column(name)] = stock
        row[flow_column(name)] = flow
    try:
        out = decompose(pd.DataFrame([row]), params).iloc[0]
    except (ValueError, ParametersError) as exc:
        raise ToolError(str(exc)) from exc
    return {
        "implied_value": float(out["implied_value"]),
        "book_value": float(out["book_value"]),
        "inputs": {
            str(name): {
                "shadow_value": float(out[f"q_{name}"]),
                "value": float(out[f"value_{name}"]),
                "share": float(out[f"share_{name}"]),
                "book_share": float(out[f"book_share_{name}"]),
            }
            for name in INPUTS
        },
    }


@server.tool()
@_tool_errors
def simulate_demo_panel(out_path: str, firms_per_group: int = 400, seed: int = 0) -> dict[str, Any]:
    """Write a synthetic firm-year panel CSV drawn from the demonstration design."""
    if firms_per_group < 1:
        raise ToolError("firms_per_group must be at least 1")
    panel = simulate_panel(SimulationDesign.demo(firms_per_group), seed=seed)
    path = Path(out_path).expanduser()
    panel.to_csv(path, index=False)
    return {
        "path": str(path),
        "firm_years": len(panel),
        "firms": int(panel["firm"].nunique()),
        "groups": sorted(panel["group"].unique().tolist()),
        "years": [int(panel["year"].min()), int(panel["year"].max())],
    }


@server.tool()
def published_value_shares() -> dict[str, Any]:
    """Average book and market value shares reported in Tables 2 and 4 of the paper."""
    return {"shares": published_shares().to_dict(orient="records"), "citation": CITATION}


def main() -> None:
    """Entry point for the ``firmvalue-mcp`` script: serve over stdio."""
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
