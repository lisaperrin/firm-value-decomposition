"""Statement records shaped like MarketLens' ``Statements`` without importing MarketLens."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class Statement:
    symbol: str
    fiscal_year_end: date
    currency: str
    net_ppe: float | None = None
    capex: float | None = None
    rd_expense: float | None = None
    sga_expense: float | None = None
    total_debt: float | None = None
    cash: float | None = None
    shares_outstanding: float | None = None
    price_at_year_end: float | None = None


def make_records(
    symbol: str = "ACME",
    years: int = 4,
    last_year: int = 2025,
    currency: str = "USD",
    month: int = 12,
    day: int = 31,
) -> list[Statement]:
    """Four plausible years in currency units, growing 10 percent a year, oldest first."""
    records = []
    for offset in range(years - 1, -1, -1):
        year = last_year - offset
        g = 1.10 ** (year - last_year)
        records.append(
            Statement(
                symbol=symbol,
                fiscal_year_end=date(year, month, day),
                currency=currency,
                net_ppe=8.0e9 * g,
                capex=1.2e9 * g,
                rd_expense=3.0e9 * g,
                sga_expense=2.0e9 * g,
                total_debt=4.0e9 * g,
                cash=6.0e9 * g,
                shares_outstanding=1.0e9,
                price_at_year_end=50.0 * g,
            )
        )
    return records
