"""Terminal rendering of tables and live results with rich."""

from __future__ import annotations

import math
from collections.abc import Mapping

import numpy as np
import pandas as pd
from rich import box
from rich.console import Group, RenderableType
from rich.table import Table
from rich.text import Text

from firmvalue.estimation import EstimationResult
from firmvalue.inputs import INPUTS
from firmvalue.live import LiveDecomposition

DEFAULT_FORMAT = "{:,.2f}"


def _cell(value: object, fmt: str) -> Text:
    if isinstance(value, bool):
        return Text(str(value))
    if isinstance(value, (int, float, np.integer, np.floating)):
        number = float(value)
        return Text("n/a", style="dim") if math.isnan(number) else Text(fmt.format(number))
    return Text(str(value))


def frame_table(
    frame: pd.DataFrame,
    title: str | None = None,
    formats: Mapping[str, str] | None = None,
    labels: Mapping[str, str] | None = None,
) -> Table:
    """Render a DataFrame as a right-aligned numeric table.

    ``formats`` maps column names to ``str.format`` specs; ``labels`` renames
    headers. Numeric columns default to two decimals with thousands separators.
    """
    formats = dict(formats or {})
    labels = dict(labels or {})
    table = Table(title=title, title_justify="left", box=box.SIMPLE_HEAD, pad_edge=False)
    for column in frame.columns:
        numeric = pd.api.types.is_numeric_dtype(frame[column])
        table.add_column(labels.get(column, str(column)), justify="right" if numeric else "left")
    for row in frame.itertuples(index=False):
        table.add_row(
            *(
                _cell(value, formats.get(col, DEFAULT_FORMAT))
                for col, value in zip(frame.columns, row, strict=True)
            )
        )
    return table


def estimation_view(results: Mapping[str, EstimationResult]) -> RenderableType:
    """Parameter estimates with standard errors, then fit statistics, by group."""
    summary = pd.concat([r.summary() for r in results.values()], ignore_index=True)
    fits = pd.DataFrame([{"group": g, **r.fit.to_dict()} for g, r in results.items()])
    return Group(
        frame_table(
            summary,
            "Adjustment cost estimates",
            {"estimate": "{:,.3f}", "std_error": "{:,.3f}"},
            {"std_error": "std. error"},
        ),
        frame_table(
            fits,
            "Fit of the valuation ratio",
            {
                "pooled_r2": "{:.3f}",
                "time_series_r2": "{:.3f}",
                "cross_section_r2": "{:.3f}",
                "rmse": "{:.3f}",
                "observations": "{:,.0f}",
                "firms": "{:,.0f}",
                "years": "{:,.0f}",
            },
            {
                "pooled_r2": "pooled R²",
                "time_series_r2": "time-series R²",
                "cross_section_r2": "cross-section R²",
            },
        ),
    )


def shares_view(table: pd.DataFrame, title: str = "Average value shares, percent") -> Table:
    """Book and market shares by group and input."""
    formats = {c: "{:.1f}" for c in table.columns if c not in ("group", "input")}
    labels = {
        "book": "book",
        "market": "market",
        "book_published": "book (paper)",
        "market_published": "market (paper)",
    }
    return frame_table(table, title, formats, labels)


def live_view(result: LiveDecomposition) -> RenderableType:
    """One firm's latest-year decomposition with its provenance notes."""
    latest = result.latest
    rows = pd.DataFrame(
        [
            {
                "input": str(name),
                "stock": float(latest[str(name)]),
                "q": float(latest[f"q_{name}"]),
                "book_share": 100.0 * float(latest[f"book_share_{name}"]),
                "market_share": 100.0 * float(latest[f"share_{name}"]),
            }
            for name in INPUTS
        ]
    )
    title = (
        f"{result.symbol}  fiscal {int(latest['year'])}  "
        f"millions of {result.currency}, employees in thousands"
    )
    header = Text.assemble(
        ("observed value ", "dim"),
        f"{latest['observed_value']:,.0f}",
        ("   implied ", "dim"),
        f"{latest['implied_value']:,.0f}",
        ("   book ", "dim"),
        f"{latest['book_value']:,.0f}",
        ("   ratio ", "dim"),
        f"{latest['observed_ratio']:.2f} observed, {latest['implied_ratio']:.2f} implied",
    )
    table = frame_table(
        rows,
        None,
        {"stock": "{:,.0f}", "q": "{:.2f}", "book_share": "{:.1f}", "market_share": "{:.1f}"},
        {"book_share": "book %", "market_share": "market %"},
    )
    footer = [Text.assemble(("parameters  ", "dim"), result.parameters_source)]
    footer += [Text.assemble(("note  ", "dim"), note) for note in result.notes]
    return Group(Text(title, style="bold"), header, table, *footer)
