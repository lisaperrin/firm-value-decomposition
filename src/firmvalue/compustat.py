"""Build the estimation panel from Compustat Fundamentals Annual.

The input frame uses Compustat's lower-case mnemonics: ``gvkey``, ``fyear``,
``prcc_f``, ``csho``, ``dltt``, ``dlc``, ``ppent``, ``capx``, ``xrd``, ``xad``,
``emp`` and optionally ``che`` and ``sic``. Amounts are in millions of dollars,
employees in thousands.

Physical capital is net property, plant and equipment; knowledge and brand
capital are accumulated from research and development and advertising
expenditure with the perpetual inventory method; the labor stock is reported
employment, and hiring is the change in employment plus separations. Market
value is the market value of equity plus the book value of long-term and
short-term debt, optionally net of cash.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping

import numpy as np
import pandas as pd

from firmvalue.capital import perpetual_inventory_by_firm
from firmvalue.inputs import DEFAULT_SPECS, Input, InputSpec
from firmvalue.panel import REQUIRED_COLUMNS, flow_column, stock_column, validate_panel
from firmvalue.tax import statutory_rates

REQUIRED_FUNDA: tuple[str, ...] = (
    "gvkey",
    "fyear",
    "prcc_f",
    "csho",
    "dltt",
    "dlc",
    "ppent",
    "capx",
    "xrd",
    "xad",
    "emp",
)


def is_regulated(sic: pd.Series) -> pd.Series:
    """Financial firms (SIC 6000-6999) and utilities (SIC 4900-4999)."""
    code = pd.to_numeric(sic, errors="coerce")
    return code.between(6000, 6999) | code.between(4900, 4999)


def from_compustat(
    funda: pd.DataFrame,
    specs: Mapping[Input, InputSpec] | None = None,
    growth: float = 0.03,
    min_years: int = 3,
    net_of_cash: bool = False,
    exclude_regulated: bool = True,
    group: Callable[[pd.DataFrame], pd.Series | np.ndarray] | None = None,
) -> pd.DataFrame:
    """Convert Compustat annual fundamentals into a validated firm-year panel.

    Parameters
    ----------
    funda
        Fundamentals Annual extract with the columns listed in
        :data:`REQUIRED_FUNDA`.
    specs
        Depreciation rates used for the perpetual inventory and for
        separations; defaults to :data:`firmvalue.inputs.DEFAULT_SPECS`.
    growth
        Pre-sample growth rate assumed when initialising intangible stocks.
    min_years
        Minimum number of usable fiscal years per firm.
    net_of_cash
        Subtract cash and short-term investments (``che``) from market value.
    exclude_regulated
        Drop financial firms and utilities when a ``sic`` column is present.
    group
        Optional function assigning each row a group label from the raw data,
        for example a skill classification keyed on industry.

    """
    specs = dict(DEFAULT_SPECS) if specs is None else dict(specs)
    missing = [c for c in REQUIRED_FUNDA if c not in funda.columns]
    if missing:
        raise ValueError(f"fundamentals are missing columns: {missing}")

    data = funda.copy()
    if exclude_regulated and "sic" in data.columns:
        data = data[~is_regulated(data["sic"])]
    data = data.dropna(subset=["gvkey", "fyear", "prcc_f", "csho", "ppent", "emp"])
    data["fyear"] = data["fyear"].astype(int)
    data = data.drop_duplicates(["gvkey", "fyear"], keep="last").sort_values(["gvkey", "fyear"])
    for column in ("xrd", "xad", "capx", "dltt", "dlc"):
        data[column] = pd.to_numeric(data[column], errors="coerce").fillna(0.0)

    panel = pd.DataFrame(
        {
            "firm": data["gvkey"].astype(str).to_numpy(),
            "year": data["fyear"].to_numpy(),
        },
        index=data.index,
    )
    panel["market_value"] = data["prcc_f"].abs() * data["csho"] + data["dltt"] + data["dlc"]
    if net_of_cash and "che" in data.columns:
        panel["market_value"] -= pd.to_numeric(data["che"], errors="coerce").fillna(0.0)
    panel["tax_rate"] = statutory_rates(panel["year"])

    panel[stock_column(Input.PHYSICAL)] = data["ppent"]
    panel[flow_column(Input.PHYSICAL)] = data["capx"]
    panel[stock_column(Input.KNOWLEDGE)] = perpetual_inventory_by_firm(
        data.assign(firm=panel["firm"], year=panel["year"]),
        "xrd",
        specs[Input.KNOWLEDGE].depreciation,
        growth=growth,
    )
    panel[flow_column(Input.KNOWLEDGE)] = data["xrd"]
    panel[stock_column(Input.BRAND)] = perpetual_inventory_by_firm(
        data.assign(firm=panel["firm"], year=panel["year"]),
        "xad",
        specs[Input.BRAND].depreciation,
        growth=growth,
    )
    panel[flow_column(Input.BRAND)] = data["xad"]

    employees = data["emp"]
    previous = employees.groupby(panel["firm"]).shift(1)
    consecutive = panel.groupby("firm")["year"].diff() == 1
    separations = specs[Input.LABOR].depreciation
    panel[stock_column(Input.LABOR)] = employees
    panel[flow_column(Input.LABOR)] = (employees - (1.0 - separations) * previous).where(
        consecutive
    )

    if group is not None:
        panel["group"] = np.asarray(group(data)).astype(str)

    panel = panel.dropna(subset=[flow_column(Input.LABOR)])
    panel = panel[(panel["market_value"] > 0) & (panel[stock_column(Input.PHYSICAL)] > 0)]
    counts = panel.groupby("firm")["year"].transform("size")
    panel = panel[counts >= min_years]
    ordered = [*REQUIRED_COLUMNS, *(["group"] if "group" in panel.columns else [])]
    return validate_panel(panel[ordered].reset_index(drop=True))
