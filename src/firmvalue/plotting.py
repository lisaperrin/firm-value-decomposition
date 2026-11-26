"""Figures: the history of value shares as stacked areas."""

from __future__ import annotations

from collections.abc import Sequence

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.axes import Axes
from matplotlib.figure import Figure

from firmvalue.inputs import INPUTS, Input

LABELS: dict[Input, str] = {
    Input.PHYSICAL: "physical capital",
    Input.LABOR: "labor",
    Input.KNOWLEDGE: "knowledge capital",
    Input.BRAND: "brand capital",
}

FILLS: dict[Input, str] = {
    Input.PHYSICAL: "#1d3557",
    Input.LABOR: "#3d7ea6",
    Input.KNOWLEDGE: "#7fb7be",
    Input.BRAND: "#e9c46a",
}


def annual_shares(decomposition: pd.DataFrame, weighted: bool = False) -> pd.DataFrame:
    """Average market-value share of each input by year, in percent.

    Equal-weighted by default; ``weighted`` averages by implied firm value so
    that the result is the aggregate share.
    """
    columns = [f"share_{name}" for name in INPUTS]
    if weighted:
        values = decomposition[[f"value_{name}" for name in INPUTS]]
        totals = values.groupby(decomposition["year"]).sum()
        shares = totals.div(totals.sum(axis=1), axis=0)
        shares.columns = columns
    else:
        shares = decomposition.groupby("year")[columns].mean()
    return (shares * 100.0).rename(columns=lambda c: c.removeprefix("share_"))


def plot_share_history(
    shares: pd.DataFrame,
    ax: Axes | None = None,
    title: str | None = None,
) -> Axes:
    """Stacked-area chart of annual shares (physical capital at the bottom)."""
    if ax is None:
        _, ax = plt.subplots(figsize=(6.0, 4.0))
    years = shares.index.to_numpy()
    series = [shares[str(name)].to_numpy() for name in INPUTS]
    ax.stackplot(
        years,
        *series,
        labels=[LABELS[name] for name in INPUTS],
        colors=[FILLS[name] for name in INPUTS],
        edgecolor="white",
        linewidth=0.6,
    )
    ax.set_xlim(years.min(), years.max())
    ax.set_ylim(0, 100)
    ax.set_ylabel("share of firm value, %")
    ax.set_xlabel("year")
    ax.grid(axis="y", color="#d9d9d9", linewidth=0.5)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    if title:
        ax.set_title(title, loc="left", fontsize=11)
    return ax


def plot_share_panels(
    decompositions: Sequence[tuple[str, pd.DataFrame]],
    weighted: bool = False,
) -> Figure:
    """One stacked-area panel per (title, decomposition) pair, shared legend."""
    n = len(decompositions)
    fig, axes = plt.subplots(1, n, figsize=(6.0 * n, 4.4), sharey=True, squeeze=False)
    for ax, (title, frame) in zip(axes[0], decompositions, strict=True):
        plot_share_history(annual_shares(frame, weighted), ax=ax, title=title)
    for ax in axes[0][1:]:
        ax.set_ylabel("")
    handles, labels = axes[0][0].get_legend_handles_labels()
    fig.legend(
        handles[::-1],
        labels[::-1],
        loc="lower center",
        ncol=len(labels),
        frameon=False,
        bbox_to_anchor=(0.5, -0.02),
    )
    fig.tight_layout(rect=(0.0, 0.06, 1.0, 1.0))
    return fig
