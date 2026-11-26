"""Command-line interface."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import pandas as pd
import typer

from firmvalue.compustat import from_compustat
from firmvalue.estimation import EstimationResult, estimate_by_group
from firmvalue.inputs import INPUTS
from firmvalue.model import Parameters, decompose
from firmvalue.panel import validate_panel
from firmvalue.plotting import plot_share_panels
from firmvalue.reference import CITATION, GROUPS, published_shares
from firmvalue.simulate import SimulationDesign, simulate_panel

app = typer.Typer(
    help="Decompose firm value into physical, labor, knowledge and brand capital.",
    no_args_is_help=True,
    add_completion=False,
)


def _read_panel(path: Path) -> pd.DataFrame:
    return validate_panel(pd.read_csv(path))


def _write_parameters(results: dict[str, EstimationResult], path: Path) -> None:
    payload = {
        group: {
            "parameters": result.params.to_dict(),
            "standard_errors": dict(result.standard_errors),
            "fit": result.fit.to_dict(),
            "converged": result.converged,
        }
        for group, result in results.items()
    }
    path.write_text(json.dumps(payload, indent=2) + "\n")


def _read_parameters(path: Path) -> dict[str, Parameters]:
    payload = json.loads(path.read_text())
    return {group: Parameters.from_dict(entry["parameters"]) for group, entry in payload.items()}


def _decompose_by_group(panel: pd.DataFrame, params: dict[str, Parameters]) -> pd.DataFrame:
    pieces = []
    for label, frame in panel.groupby("group", sort=True):
        key = str(label) if str(label) in params else "all"
        if key not in params:
            raise typer.BadParameter(f"no parameters for group {label!r} and no 'all' fallback")
        pieces.append(decompose(frame, params[key]))
    return pd.concat(pieces, ignore_index=True)


def _panels(decomposition: pd.DataFrame) -> list[tuple[str, pd.DataFrame]]:
    labels = sorted(decomposition["group"].unique(), key=_group_order)
    return [
        (label.replace("_", " ").capitalize(), decomposition[decomposition["group"] == label])
        for label in labels
    ]


def _group_order(label: str) -> tuple[int, str]:
    return (GROUPS.index(label) if label in GROUPS else len(GROUPS), label)


def _share_table(decomposition: pd.DataFrame) -> pd.DataFrame:
    rows = []
    groups = [("all", decomposition)] + [
        (str(k), g) for k, g in decomposition.groupby("group", sort=True)
    ]
    for label, frame in groups:
        for name in INPUTS:
            rows.append(
                {
                    "group": label,
                    "input": str(name),
                    "book": 100.0 * frame[f"book_share_{name}"].mean(),
                    "market": 100.0 * frame[f"share_{name}"].mean(),
                }
            )
    return pd.DataFrame(rows)


def _markdown(frame: pd.DataFrame, digits: int = 2) -> str:
    header = "| " + " | ".join(frame.columns) + " |"
    rule = "|" + "|".join("---" for _ in frame.columns) + "|"
    body = [
        "| " + " | ".join(f"{v:.{digits}f}" if isinstance(v, float) else str(v) for v in row) + " |"
        for row in frame.itertuples(index=False)
    ]
    return "\n".join([header, rule, *body]) + "\n"


@app.command()
def simulate(
    out: Annotated[Path, typer.Option(help="Destination CSV.")] = Path("panel.csv"),
    firms: Annotated[int, typer.Option(help="Firms per group.")] = 400,
    seed: Annotated[int, typer.Option(help="Random seed.")] = 0,
) -> None:
    """Draw a synthetic firm-year panel from the demonstration design."""
    panel = simulate_panel(SimulationDesign.demo(firms), seed=seed)
    panel.to_csv(out, index=False)
    typer.echo(f"wrote {len(panel)} firm-years to {out}")


@app.command()
def prepare(
    funda: Annotated[Path, typer.Argument(help="Compustat Fundamentals Annual CSV.")],
    out: Annotated[Path, typer.Option(help="Destination CSV.")] = Path("panel.csv"),
    net_of_cash: Annotated[bool, typer.Option(help="Subtract cash from market value.")] = False,
) -> None:
    """Convert a Compustat extract into the estimation panel."""
    panel = from_compustat(pd.read_csv(funda), net_of_cash=net_of_cash)
    panel.to_csv(out, index=False)
    typer.echo(f"wrote {len(panel)} firm-years to {out}")


@app.command()
def estimate(
    panel: Annotated[Path, typer.Argument(help="Panel CSV.")],
    out: Annotated[Path, typer.Option(help="Destination JSON.")] = Path("parameters.json"),
    curvature: Annotated[bool, typer.Option(help="Estimate cost curvature too.")] = False,
) -> None:
    """Estimate adjustment cost parameters, pooled and by group."""
    results = estimate_by_group(_read_panel(panel), estimate_curvature=curvature)
    _write_parameters(results, out)
    summary = pd.concat([r.summary() for r in results.values()], ignore_index=True)
    typer.echo(_markdown(summary, digits=3))
    for group, result in results.items():
        fit = result.fit
        typer.echo(
            f"{group}: pooled R2 {fit.pooled_r2:.3f}, time-series R2 {fit.time_series_r2:.3f}, "
            f"cross-section R2 {fit.cross_section_r2:.3f}"
        )
    typer.echo(f"wrote {out}")


@app.command()
def shares(
    panel: Annotated[Path, typer.Argument(help="Panel CSV.")],
    parameters: Annotated[Path, typer.Argument(help="Parameters JSON from `estimate`.")],
    out: Annotated[Path | None, typer.Option(help="Firm-year decomposition CSV.")] = None,
) -> None:
    """Decompose firm value and report average book and market value shares."""
    decomposition = _decompose_by_group(_read_panel(panel), _read_parameters(parameters))
    if out is not None:
        decomposition.to_csv(out, index=False)
    typer.echo(_markdown(_share_table(decomposition)))


@app.command()
def figure(
    panel: Annotated[Path, typer.Argument(help="Panel CSV.")],
    parameters: Annotated[Path, typer.Argument(help="Parameters JSON from `estimate`.")],
    out: Annotated[Path, typer.Option(help="Destination image.")] = Path("shares.png"),
    weighted: Annotated[bool, typer.Option(help="Value-weight the annual shares.")] = False,
) -> None:
    """Plot the history of value shares, one panel per group."""
    decomposition = _decompose_by_group(_read_panel(panel), _read_parameters(parameters))
    fig = plot_share_panels(_panels(decomposition), weighted=weighted)
    fig.savefig(out, dpi=200, bbox_inches="tight")
    typer.echo(f"wrote {out}")


@app.command()
def demo(
    out_dir: Annotated[Path, typer.Option(help="Output directory.")] = Path("outputs"),
    firms: Annotated[int, typer.Option(help="Firms per group.")] = 400,
    seed: Annotated[int, typer.Option(help="Random seed.")] = 0,
) -> None:
    """Simulate, estimate, decompose and plot in one run."""
    out_dir.mkdir(parents=True, exist_ok=True)
    panel = simulate_panel(SimulationDesign.demo(firms), seed=seed)
    panel.to_csv(out_dir / "panel.csv", index=False)

    results = estimate_by_group(panel)
    _write_parameters(results, out_dir / "parameters.json")
    params = {group: result.params for group, result in results.items()}
    decomposition = _decompose_by_group(panel, params)
    decomposition.to_csv(out_dir / "decomposition.csv", index=False)

    estimated = _share_table(decomposition)
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
            _markdown(summary, digits=3),
            "## Fit of the valuation ratio",
            "",
            _markdown(fits, digits=3),
            "## Average value shares (percent)",
            "",
            "Published columns are from Tables 2 and 4 of the reference below.",
            "",
            _markdown(comparison),
            f"Reference: {CITATION}",
            "",
        ]
    )
    (out_dir / "report.md").write_text(report)

    figure = plot_share_panels(_panels(decomposition))
    figure.savefig(out_dir / "shares.png", dpi=200, bbox_inches="tight")
    typer.echo(report)
    typer.echo(f"wrote outputs to {out_dir}")
