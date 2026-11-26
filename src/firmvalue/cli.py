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

from firmvalue import __version__
from firmvalue.compustat import from_compustat
from firmvalue.errors import FirmValueError, InputFileError
from firmvalue.estimation import EstimationResult, estimate_by_group
from firmvalue.io import (
    decompose_by_group,
    markdown_table,
    read_panel,
    read_parameters,
    results_to_dict,
    share_table,
    write_parameters,
)
from firmvalue.plotting import plot_share_panels
from firmvalue.reference import CITATION, GROUPS, published_shares
from firmvalue.simulate import SimulationDesign, simulate_panel

app = typer.Typer(
    name="firmvalue",
    help="Decompose firm value into physical, labor, knowledge and brand capital.",
    no_args_is_help=True,
    add_completion=False,
)


@dataclass
class State:
    """Global options shared by every command."""

    as_json: bool = False


state = State()


def _version(value: bool) -> None:
    if value:
        typer.echo(f"firmvalue {__version__}")
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
            typer.echo(f"error: {exc}", err=True)
            raise typer.Exit(code=1) from exc

    return wrapper


def _emit(payload: dict[str, Any], text: str) -> None:
    typer.echo(json.dumps(payload, indent=2) if state.as_json else text)


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


def _estimation_text(results: dict[str, EstimationResult]) -> str:
    summary = pd.concat([r.summary() for r in results.values()], ignore_index=True)
    lines = [markdown_table(summary, digits=3)]
    for group, result in results.items():
        fit = result.fit
        lines.append(
            f"{group}: pooled R2 {fit.pooled_r2:.3f}, time-series R2 {fit.time_series_r2:.3f}, "
            f"cross-section R2 {fit.cross_section_r2:.3f}"
        )
    return "\n".join(lines)


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
    _emit(results_to_dict(results), _estimation_text(results) + f"\nwrote {out}")


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
    _emit({"shares": table.to_dict(orient="records"), "units": "percent"}, markdown_table(table))


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
    _emit(payload, report + f"wrote outputs to {out_dir}")
