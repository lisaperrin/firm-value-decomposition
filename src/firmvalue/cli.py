"""Command-line interface. Run ``firmvalue --help``."""

from __future__ import annotations

import functools
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any

import pandas as pd
import typer
from rich.console import Console, RenderableType
from rich.text import Text

from firmvalue import __version__
from firmvalue.compustat import from_compustat
from firmvalue.errors import FirmValueError, InputFileError
from firmvalue.estimation import estimate_by_group
from firmvalue.io import (
    decompose_by_group,
    markdown_table,
    read_panel,
    read_parameters,
    results_to_dict,
    share_table,
    write_parameters,
)
from firmvalue.live import LiveOptions, fetch_and_decompose
from firmvalue.model import Parameters
from firmvalue.plotting import plot_share_panels
from firmvalue.reference import CITATION, GROUPS, published_shares
from firmvalue.report import estimation_view, live_view, shares_view
from firmvalue.simulate import SimulationDesign, simulate_panel

app = typer.Typer(
    name="firmvalue",
    help="Decompose firm value into physical, labor, knowledge and brand capital.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()
error_console = Console(stderr=True)


@dataclass
class State:
    """Global options shared by every command."""

    as_json: bool = False


state = State()


def _version(value: bool) -> None:
    if value:
        console.print(f"firmvalue {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    as_json: Annotated[
        bool, typer.Option("--json", help="Print machine-readable JSON instead of tables.")
    ] = False,
    _: Annotated[
        bool | None,
        typer.Option("--version", callback=_version, is_eager=True, help="Show the version."),
    ] = None,
) -> None:
    """Structural decomposition of firm value."""
    state.as_json = as_json


def _handle_errors[**P, R](func: Callable[P, R]) -> Callable[P, R]:
    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return func(*args, **kwargs)
        except FirmValueError as exc:
            error_console.print(Text(f"error: {exc}"))
            raise typer.Exit(code=1) from exc

    return wrapper


def _emit(payload: dict[str, Any], *renderables: RenderableType | str) -> None:
    if state.as_json:
        typer.echo(json.dumps(payload, indent=2))
        return
    for item in renderables:
        console.print(Text(item) if isinstance(item, str) else item)


def _panel_summary(panel: pd.DataFrame, path: Path) -> dict[str, Any]:
    return {
        "path": str(path),
        "firm_years": len(panel),
        "firms": int(panel["firm"].nunique()),
        "years": [int(panel["year"].min()), int(panel["year"].max())],
    }


def _panels(decomposition: pd.DataFrame) -> list[tuple[str, pd.DataFrame]]:
    labels = sorted(decomposition["group"].unique(), key=_group_order)
    return [
        (label.replace("_", " ").capitalize(), decomposition[decomposition["group"] == label])
        for label in labels
    ]


def _group_order(label: str) -> tuple[int, str]:
    return (GROUPS.index(label) if label in GROUPS else len(GROUPS), label)


@app.command()
@_handle_errors
def simulate(
    out: Annotated[Path, typer.Option(help="Destination CSV.")] = Path("panel.csv"),
    firms: Annotated[int, typer.Option(min=1, help="Firms per group.")] = 400,
    seed: Annotated[int, typer.Option(help="Random seed.")] = 0,
) -> None:
    """Draw a synthetic firm-year panel from the demonstration design."""
    panel = simulate_panel(SimulationDesign.demo(firms), seed=seed)
    panel.to_csv(out, index=False)
    _emit(_panel_summary(panel, out), f"wrote {len(panel)} firm-years to {out}")


@app.command()
@_handle_errors
def prepare(
    funda: Annotated[Path, typer.Argument(help="Compustat Fundamentals Annual CSV.")],
    out: Annotated[Path, typer.Option(help="Destination CSV.")] = Path("panel.csv"),
    net_of_cash: Annotated[bool, typer.Option(help="Subtract cash from market value.")] = False,
) -> None:
    """Convert a Compustat extract into the estimation panel."""
    if not funda.is_file():
        raise InputFileError(f"fundamentals file not found: {funda}")
    try:
        panel = from_compustat(pd.read_csv(funda), net_of_cash=net_of_cash)
    except ValueError as exc:
        raise InputFileError(str(exc)) from exc
    panel.to_csv(out, index=False)
    _emit(_panel_summary(panel, out), f"wrote {len(panel)} firm-years to {out}")


@app.command()
@_handle_errors
def estimate(
    panel: Annotated[Path, typer.Argument(help="Panel CSV.")],
    out: Annotated[Path, typer.Option(help="Destination JSON.")] = Path("parameters.json"),
    curvature: Annotated[bool, typer.Option(help="Estimate cost curvature too.")] = False,
) -> None:
    """Estimate adjustment cost parameters, pooled and by group."""
    results = estimate_by_group(read_panel(panel), estimate_curvature=curvature)
    write_parameters(results, out)
    _emit(results_to_dict(results), estimation_view(results), f"wrote {out}")


@app.command()
@_handle_errors
def shares(
    panel: Annotated[Path, typer.Argument(help="Panel CSV.")],
    parameters: Annotated[Path, typer.Argument(help="Parameters JSON from `estimate`.")],
    out: Annotated[Path | None, typer.Option(help="Firm-year decomposition CSV.")] = None,
) -> None:
    """Decompose firm value and report average book and market value shares."""
    decomposition = decompose_by_group(read_panel(panel), read_parameters(parameters))
    if out is not None:
        decomposition.to_csv(out, index=False)
    table = share_table(decomposition)
    _emit({"shares": table.to_dict(orient="records"), "units": "percent"}, shares_view(table))


@app.command()
@_handle_errors
def figure(
    panel: Annotated[Path, typer.Argument(help="Panel CSV.")],
    parameters: Annotated[Path, typer.Argument(help="Parameters JSON from `estimate`.")],
    out: Annotated[Path, typer.Option(help="Destination image.")] = Path("shares.png"),
    weighted: Annotated[bool, typer.Option(help="Value-weight the annual shares.")] = False,
) -> None:
    """Plot the history of value shares, one panel per group."""
    decomposition = decompose_by_group(read_panel(panel), read_parameters(parameters))
    fig = plot_share_panels(_panels(decomposition), weighted=weighted)
    fig.savefig(out, dpi=200, bbox_inches="tight")
    _emit({"path": str(out)}, f"wrote {out}")


@app.command()
@_handle_errors
def live(
    symbols: Annotated[list[str], typer.Argument(help="Ticker symbols, Yahoo style.")],
    years: Annotated[int, typer.Option(min=2, help="Fiscal years of statements.")] = 4,
    parameters: Annotated[
        Path | None, typer.Option(help="Parameters JSON from `estimate`; default illustrative.")
    ] = None,
    group: Annotated[str, typer.Option(help="Group key inside the parameters file.")] = "all",
    brand_share: Annotated[
        float, typer.Option(min=0.0, max=1.0, help="Share of SG&A treated as advertising.")
    ] = 0.30,
    tax_rate: Annotated[
        float | None, typer.Option(min=0.0, max=0.99, help="Override the statutory tax rate.")
    ] = None,
    net_of_cash: Annotated[bool, typer.Option(help="Subtract cash from market value.")] = False,
    panel_out: Annotated[Path | None, typer.Option(help="Write the built panels to CSV.")] = None,
) -> None:
    """Decompose listed firms from their annual statements (needs the `live` extra)."""
    params: Parameters | None = None
    source: str | None = None
    if parameters is not None:
        by_group = read_parameters(parameters)
        key = group if group in by_group else "all"
        if key not in by_group:
            raise InputFileError(f"{parameters} has no group {group!r} and no 'all' entry")
        params, source = by_group[key], f"{parameters} [{key}]"
    options = LiveOptions(
        brand_share_of_sga=brand_share, tax_rate=tax_rate, net_of_cash=net_of_cash
    )
    results = [fetch_and_decompose(s, years, params, source, options) for s in symbols]
    if panel_out is not None:
        pd.concat([r.by_year.assign(symbol=r.symbol) for r in results]).to_csv(
            panel_out, index=False
        )
    views: list[RenderableType | str] = []
    for result in results:
        if views:
            views.append("")
        views.append(live_view(result))
    _emit({"results": [r.to_dict() for r in results]}, *views)


@app.command()
@_handle_errors
def demo(
    out_dir: Annotated[Path, typer.Option(help="Output directory.")] = Path("outputs"),
    firms: Annotated[int, typer.Option(min=1, help="Firms per group.")] = 400,
    seed: Annotated[int, typer.Option(help="Random seed.")] = 0,
) -> None:
    """Simulate, estimate, decompose and plot in one run."""
    out_dir.mkdir(parents=True, exist_ok=True)
    panel = simulate_panel(SimulationDesign.demo(firms), seed=seed)
    panel.to_csv(out_dir / "panel.csv", index=False)

    results = estimate_by_group(panel)
    write_parameters(results, out_dir / "parameters.json")
    params = {group: result.params for group, result in results.items()}
    decomposition = decompose_by_group(panel, params)
    decomposition.to_csv(out_dir / "decomposition.csv", index=False)

    estimated = share_table(decomposition)
    published = published_shares().rename(
        columns={"book": "book_published", "market": "market_published"}
    )
    comparison = estimated.merge(published, on=["group", "input"], how="left")
    comparison = comparison[
        ["group", "input", "book", "book_published", "market", "market_published"]
    ]
    summary = pd.concat([r.summary() for r in results.values()], ignore_index=True)
    fits = pd.DataFrame([{"group": g, **r.fit.to_dict()} for g, r in results.items()])

    report = "\n".join(
        [
            "# Demonstration run",
            "",
            f"Synthetic panel, {firms} firms per group, seed {seed}.",
            "",
            "## Adjustment cost estimates",
            "",
            markdown_table(summary, digits=3),
            "## Fit of the valuation ratio",
            "",
            markdown_table(fits, digits=3),
            "## Average value shares (percent)",
            "",
            "Published columns are from Tables 2 and 4 of the reference below.",
            "",
            markdown_table(comparison),
            f"Reference: {CITATION}",
            "",
        ]
    )
    (out_dir / "report.md").write_text(report)
    plot_share_panels(_panels(decomposition)).savefig(
        out_dir / "shares.png", dpi=200, bbox_inches="tight"
    )
    payload = {
        "out_dir": str(out_dir),
        "estimation": results_to_dict(results),
        "shares": comparison.to_dict(orient="records"),
    }
    _emit(
        payload,
        estimation_view(results),
        shares_view(comparison, "Average value shares, percent (paper: Tables 2 and 4)"),
        f"wrote panel, parameters, decomposition, report.md and shares.png to {out_dir}",
    )
