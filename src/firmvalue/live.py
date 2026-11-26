"""Decompose a listed firm's value from its published annual statements.

The statements come from MarketLens (``firmvalue[live]``), whose provider
returns a few fiscal years of balance sheet, income statement and cash flow
lines per ticker. This module turns those records into the package's panel
schema, applies a set of adjustment cost parameters and reports the value
shares, together with every proxy and shortcut the construction needed.

Statements are converted to the package's conventional units: millions of
the reporting currency and thousands of employees, so that parameters
estimated on Compustat-style panels apply unchanged.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Protocol

import pandas as pd

from firmvalue.capital import perpetual_inventory
from firmvalue.errors import FirmValueError
from firmvalue.inputs import DEFAULT_SPECS, INPUTS, Input, InputSpec
from firmvalue.model import Parameters, decompose
from firmvalue.panel import flow_column, stock_column, validate_panel
from firmvalue.tax import statutory_rate

MONEY_SCALE = 1e6
HEADCOUNT_SCALE = 1e3


class StatementLike(Protocol):
    """One fiscal year of statement lines, structurally compatible with MarketLens.

    Members are read-only properties so that frozen dataclasses satisfy the protocol.
    """

    @property
    def symbol(self) -> str:
        """Ticker symbol."""

    @property
    def fiscal_year_end(self) -> date:
        """Last day of the fiscal year."""

    @property
    def currency(self) -> str:
        """Reporting currency."""

    @property
    def net_ppe(self) -> float | None:
        """Net property, plant and equipment."""

    @property
    def capex(self) -> float | None:
        """Capital expenditure as a positive outflow."""

    @property
    def rd_expense(self) -> float | None:
        """Research and development expense."""

    @property
    def sga_expense(self) -> float | None:
        """Selling, general and administrative expense."""

    @property
    def total_debt(self) -> float | None:
        """Gross debt."""

    @property
    def cash(self) -> float | None:
        """Cash and equivalents."""

    @property
    def shares_outstanding(self) -> float | None:
        """Shares outstanding at fiscal year end."""

    @property
    def price_at_year_end(self) -> float | None:
        """Share price on or before fiscal year end."""


class LiveDataError(FirmValueError):
    """The statements do not contain enough to build a panel."""


class LiveDependencyError(FirmValueError):
    """MarketLens is not installed."""


ILLUSTRATIVE_PARAMETERS = Parameters.quadratic(
    physical=2.0, labor=1200.0, knowledge=30.0, brand=4.0
)
"""Adjustment cost parameters used when none are supplied.

They are the calibration behind the packaged synthetic demonstration, chosen
so that simulated value shares resemble the averages published by Belo, Gala,
Salomao and Vitorino (2022). They are not estimates on real data, and every
live result built on them says so.
"""


@dataclass(frozen=True, slots=True)
class LiveOptions:
    """Choices made when turning statements into a panel.

    ``brand_share_of_sga`` is the fraction of selling, general and
    administrative expense treated as advertising, since Yahoo publishes no
    advertising line. ``tax_rate`` overrides the United States statutory
    schedule, which is otherwise applied to every filer. ``growth`` is the
    pre-sample growth rate used to initialise the intangible stocks.
    """

    brand_share_of_sga: float = 0.30
    tax_rate: float | None = None
    net_of_cash: bool = False
    growth: float = 0.03
    specs: Mapping[Input, InputSpec] = field(default_factory=lambda: dict(DEFAULT_SPECS))

    def __post_init__(self) -> None:
        if not 0.0 <= self.brand_share_of_sga <= 1.0:
            raise ValueError("brand_share_of_sga must lie in [0, 1]")
        if self.tax_rate is not None and not 0.0 <= self.tax_rate < 1.0:
            raise ValueError("tax_rate must lie in [0, 1)")


@dataclass(frozen=True, slots=True)
class LivePanel:
    """A validated one-firm panel plus the notes explaining how it was built."""

    symbol: str
    currency: str
    panel: pd.DataFrame
    notes: tuple[str, ...]
    years_dropped: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class LiveDecomposition:
    """Value shares of one firm, by fiscal year, under given parameters."""

    symbol: str
    currency: str
    parameters_source: str
    by_year: pd.DataFrame
    notes: tuple[str, ...]

    @property
    def latest(self) -> pd.Series:
        """The most recent fiscal year's row."""
        return self.by_year.iloc[-1]

    def to_dict(self) -> dict[str, Any]:
        """JSON-ready summary with the latest year expanded and all years listed."""
        latest = self.latest
        return {
            "symbol": self.symbol,
            "currency": self.currency,
            "units": "millions of currency; employees in thousands; shares in percent",
            "parameters_source": self.parameters_source,
            "latest_fiscal_year": int(latest["year"]),
            "observed_value": float(latest["observed_value"]),
            "implied_value": float(latest["implied_value"]),
            "book_value": float(latest["book_value"]),
            "observed_ratio": float(latest["observed_ratio"]),
            "implied_ratio": float(latest["implied_ratio"]),
            "inputs": {
                str(name): {
                    "stock": float(latest[stock_column(name)]),
                    "shadow_value": float(latest[f"q_{name}"]),
                    "value": float(latest[f"value_{name}"]),
                    "share": float(100.0 * latest[f"share_{name}"]),
                    "book_share": float(100.0 * latest[f"book_share_{name}"]),
                }
                for name in INPUTS
            },
            "by_year": [
                {
                    "year": int(row["year"]),
                    **{str(name): float(100.0 * row[f"share_{name}"]) for name in INPUTS},
                    "observed_ratio": float(row["observed_ratio"]),
                    "implied_ratio": float(row["implied_ratio"]),
                }
                for _, row in self.by_year.iterrows()
            ],
            "notes": list(self.notes),
        }


def _money(value: float | None) -> float:
    return 0.0 if value is None else float(value) / MONEY_SCALE


def statements_to_panel(
    statements: Sequence[StatementLike],
    employees: int | None,
    options: LiveOptions | None = None,
) -> LivePanel:
    """Build a one-firm panel from annual statements, oldest first.

    A fiscal year is kept when it has net property, plant and equipment, a
    year-end price and a share count; other lines default to zero and are
    recorded in the notes. Employees are carried across all years at the
    latest value because Yahoo publishes no headcount history, so hiring
    equals replacement of separations and the labor share is a rough figure.
    """
    options = options or LiveOptions()
    if not statements:
        raise LiveDataError("no annual statements were provided")
    records = sorted(statements, key=lambda s: s.fiscal_year_end)
    symbol = records[-1].symbol
    currency = records[-1].currency
    notes: list[str] = []
    dropped: list[int] = []

    kept = []
    for record in records:
        year = record.fiscal_year_end.year
        missing = [
            name
            for name, value in (
                ("net_ppe", record.net_ppe),
                ("price_at_year_end", record.price_at_year_end),
                ("shares_outstanding", record.shares_outstanding),
            )
            if value is None
        ]
        if missing or record.net_ppe is None or record.net_ppe <= 0:
            dropped.append(year)
            continue
        kept.append(record)
    if not kept:
        raise LiveDataError(
            f"{symbol}: no fiscal year has net PP&E, a year-end price and a share count"
        )
    if dropped:
        notes.append(f"dropped fiscal years without the required lines: {dropped}")

    years = [r.fiscal_year_end.year for r in kept]
    if len(set(years)) != len(years):
        raise LiveDataError(f"{symbol}: two statements share a fiscal year: {years}")

    for line, label in (("rd_expense", "R&D"), ("sga_expense", "SG&A"), ("total_debt", "debt")):
        if any(getattr(r, line) is None for r in kept):
            notes.append(f"{label} missing in some years and treated as zero")

    frame = pd.DataFrame({"firm": symbol, "year": years, "group": "all"})
    tax = (
        [options.tax_rate] * len(kept)
        if options.tax_rate is not None
        else [statutory_rate(y) for y in years]
    )
    frame["tax_rate"] = tax
    if options.tax_rate is None and currency != "USD":
        notes.append(
            f"United States statutory tax rates applied to a {currency} filer; "
            "pass tax_rate to override"
        )

    market = []
    for record in kept:
        equity = (record.price_at_year_end or 0.0) * (record.shares_outstanding or 0.0)
        value = equity + (record.total_debt or 0.0)
        if options.net_of_cash:
            value -= record.cash or 0.0
        market.append(value / MONEY_SCALE)
    frame["market_value"] = market
    if options.net_of_cash:
        notes.append("market value is net of cash and equivalents")

    frame[stock_column(Input.PHYSICAL)] = [_money(r.net_ppe) for r in kept]
    frame[flow_column(Input.PHYSICAL)] = [_money(r.capex) for r in kept]

    rd = pd.Series([_money(r.rd_expense) for r in kept])
    frame[flow_column(Input.KNOWLEDGE)] = rd.to_numpy()
    frame[stock_column(Input.KNOWLEDGE)] = perpetual_inventory(
        rd, options.specs[Input.KNOWLEDGE].depreciation, options.growth
    ).to_numpy()

    advertising = pd.Series([options.brand_share_of_sga * _money(r.sga_expense) for r in kept])
    frame[flow_column(Input.BRAND)] = advertising.to_numpy()
    frame[stock_column(Input.BRAND)] = perpetual_inventory(
        advertising, options.specs[Input.BRAND].depreciation, options.growth
    ).to_numpy()
    notes.append(
        f"advertising proxied as {options.brand_share_of_sga:.0%} of SG&A; "
        "Yahoo publishes no advertising line"
    )
    notes.append(
        f"knowledge and brand stocks initialised from the first of {len(kept)} observed "
        f"years at {options.growth:.0%} pre-sample growth"
    )

    headcount = 0.0 if employees is None else employees / HEADCOUNT_SCALE
    separation = options.specs[Input.LABOR].depreciation
    frame[stock_column(Input.LABOR)] = headcount
    frame[flow_column(Input.LABOR)] = separation * headcount
    if employees is None:
        notes.append("no headcount available; labor share is zero")
    else:
        notes.append(
            "headcount is the latest value carried across all years; hiring equals "
            "replacement of separations, so the labor share is a rough figure"
        )

    panel = validate_panel(frame)
    return LivePanel(symbol, currency, panel, tuple(notes), tuple(dropped))


def decompose_live(
    statements: Sequence[StatementLike],
    employees: int | None,
    params: Parameters | None = None,
    parameters_source: str | None = None,
    options: LiveOptions | None = None,
) -> LiveDecomposition:
    """Apply ``params`` to a firm's statements and return its value shares by year."""
    if params is None:
        params = ILLUSTRATIVE_PARAMETERS
        parameters_source = "illustrative calibration, not estimated on real data"
    elif parameters_source is None:
        parameters_source = "user-supplied parameters"
    live = statements_to_panel(statements, employees, options)
    out = decompose(live.panel, params)
    out["observed_ratio"] = out["observed_value"] / out["book_value"]
    out["implied_ratio"] = out["implied_value"] / out["book_value"]
    for name in INPUTS:
        out[stock_column(name)] = live.panel[stock_column(name)].to_numpy()
    return LiveDecomposition(
        symbol=live.symbol,
        currency=live.currency,
        parameters_source=parameters_source,
        by_year=out.reset_index(drop=True),
        notes=live.notes,
    )


StatementsSource = Callable[[str, int], tuple[list[StatementLike], int | None]]
"""Returns ``(statements oldest first, latest headcount)`` for a ticker."""


def _marketlens_source(symbol: str, years: int) -> tuple[list[StatementLike], int | None]:
    try:
        from marketlens.data.cache import CachedProvider
        from marketlens.data.yfinance_provider import YFinanceProvider
        from marketlens.errors import MarketLensError
    except ImportError as exc:
        raise LiveDependencyError(
            "live mode needs MarketLens; install the extra with `uv sync --extra live` "
            "or `pip install 'firmvalue[live]'`"
        ) from exc
    provider = CachedProvider(YFinanceProvider())
    try:
        statements = provider.get_statements(symbol, years)
        employees = provider.get_fundamentals(symbol).employees
    except MarketLensError as exc:
        raise LiveDataError(str(exc)) from exc
    return list(statements), employees


statements_source: StatementsSource = _marketlens_source
"""Source of statements used by the CLI and MCP server; tests replace it."""


def fetch_and_decompose(
    symbol: str,
    years: int = 4,
    params: Parameters | None = None,
    parameters_source: str | None = None,
    options: LiveOptions | None = None,
) -> LiveDecomposition:
    """Fetch a ticker's statements through the configured source and decompose them."""
    if years < 2:
        raise LiveDataError("years must be at least 2")
    statements, employees = statements_source(symbol, years)
    return decompose_live(statements, employees, params, parameters_source, options)
