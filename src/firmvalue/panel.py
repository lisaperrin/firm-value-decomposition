"""Schema of the firm-year panel consumed by the estimator and decomposition."""

from __future__ import annotations

import pandas as pd

from firmvalue.inputs import FLOW_COLUMN, INPUTS, Input

ID_COLUMNS: tuple[str, ...] = ("firm", "year")
STOCK_COLUMNS: tuple[str, ...] = tuple(str(name) for name in INPUTS)
FLOW_COLUMNS: tuple[str, ...] = tuple(FLOW_COLUMN[name] for name in INPUTS)
REQUIRED_COLUMNS: tuple[str, ...] = (
    *ID_COLUMNS,
    "market_value",
    "tax_rate",
    *STOCK_COLUMNS,
    *FLOW_COLUMNS,
)
OPTIONAL_COLUMNS: tuple[str, ...] = ("group",)


def stock_column(name: Input) -> str:
    """Column holding the end-of-year installed stock of ``name``."""
    return str(name)


def flow_column(name: Input) -> str:
    """Column holding the within-year expenditure (or hiring) flow of ``name``."""
    return FLOW_COLUMN[name]


class PanelError(ValueError):
    """The panel violates the schema."""


def validate_panel(frame: pd.DataFrame) -> pd.DataFrame:
    """Check columns, types and positivity; return a sorted copy.

    Stocks are measured at the end of the fiscal year, after that year's
    investment, so that market value at the same date can be written as a
    linear combination of them. Physical capital must be strictly positive;
    the other stocks may be zero for firms that never hire, research or
    advertise.
    """
    missing = [c for c in REQUIRED_COLUMNS if c not in frame.columns]
    if missing:
        raise PanelError(f"panel is missing required columns: {missing}")

    panel = frame.copy()
    numeric = [c for c in REQUIRED_COLUMNS if c != "firm"]
    for column in numeric:
        panel[column] = pd.to_numeric(panel[column], errors="raise")

    if panel[list(REQUIRED_COLUMNS)].isna().any().any():
        bad = panel[list(REQUIRED_COLUMNS)].isna().any()
        raise PanelError(f"panel has missing values in: {list(bad[bad].index)}")
    if panel.duplicated(list(ID_COLUMNS)).any():
        raise PanelError("panel has duplicate (firm, year) rows")

    if (panel[stock_column(Input.PHYSICAL)] <= 0).any():
        raise PanelError("physical capital must be strictly positive")
    others = [stock_column(name) for name in INPUTS if name != Input.PHYSICAL]
    if (panel[others] < 0).any().any():
        raise PanelError("labor, knowledge and brand stocks must be non-negative")
    if (panel["market_value"] <= 0).any():
        raise PanelError("market value must be strictly positive")
    if ((panel["tax_rate"] < 0) | (panel["tax_rate"] >= 1)).any():
        raise PanelError("tax rate must lie in [0, 1)")

    if "group" not in panel.columns:
        panel["group"] = "all"
    panel["group"] = panel["group"].astype(str)
    return panel.sort_values(list(ID_COLUMNS)).reset_index(drop=True)
