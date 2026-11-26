"""The four productive inputs and their tax treatment."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import numpy as np


class Input(StrEnum):
    """Productive inputs in the order used throughout the package."""

    PHYSICAL = "physical"
    LABOR = "labor"
    KNOWLEDGE = "knowledge"
    BRAND = "brand"


INPUTS: tuple[Input, ...] = tuple(Input)
CAPITAL_INPUTS: tuple[Input, ...] = (Input.PHYSICAL, Input.KNOWLEDGE, Input.BRAND)

FLOW_COLUMN: dict[Input, str] = {
    Input.PHYSICAL: "capex",
    Input.LABOR: "hires",
    Input.KNOWLEDGE: "rd",
    Input.BRAND: "advertising",
}


@dataclass(frozen=True, slots=True)
class InputSpec:
    """Economic treatment of one input.

    ``depreciation`` is the annual rate at which the installed stock decays
    (for labor, the separation rate). ``expensed`` inputs are deducted from
    taxable income when acquired, so one unit costs ``1 - tax_rate`` after tax.
    ``purchased`` is false for labor, whose only acquisition cost is the
    adjustment cost of hiring.
    """

    name: Input
    depreciation: float
    expensed: bool
    purchased: bool

    def after_tax_price(self, tax_rate: float) -> float:
        """Direct after-tax cost of acquiring one unit, before adjustment costs."""
        if not self.purchased:
            return 0.0
        return 1.0 - tax_rate if self.expensed else 1.0

    def after_tax_prices(self, tax_rates: np.ndarray) -> np.ndarray:
        """Vectorised :meth:`after_tax_price` over an array of tax rates."""
        if not self.purchased:
            return np.zeros_like(tax_rates, dtype=float)
        if self.expensed:
            return 1.0 - np.asarray(tax_rates, dtype=float)
        return np.ones_like(tax_rates, dtype=float)


DEFAULT_SPECS: dict[Input, InputSpec] = {
    Input.PHYSICAL: InputSpec(Input.PHYSICAL, depreciation=0.10, expensed=False, purchased=True),
    Input.LABOR: InputSpec(Input.LABOR, depreciation=0.10, expensed=False, purchased=False),
    Input.KNOWLEDGE: InputSpec(Input.KNOWLEDGE, depreciation=0.15, expensed=True, purchased=True),
    Input.BRAND: InputSpec(Input.BRAND, depreciation=0.50, expensed=True, purchased=True),
}
