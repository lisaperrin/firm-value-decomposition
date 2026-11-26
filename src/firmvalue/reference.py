"""Published value shares from Belo, Gala, Salomao and Vitorino (2022).

Average shares in percent, Table 2 (book values) and Table 4 (market values),
for all firms and for firms in low- and high-skill industries. Labor has no
book value, hence its zero book share.
"""

from __future__ import annotations

import pandas as pd

from firmvalue.inputs import INPUTS

GROUPS: tuple[str, ...] = ("all", "low_skill", "high_skill")

BOOK_SHARES: dict[str, dict[str, float]] = {
    "all": {"physical": 64.33, "labor": 0.0, "knowledge": 22.78, "brand": 12.89},
    "low_skill": {"physical": 71.66, "labor": 0.0, "knowledge": 10.11, "brand": 18.23},
    "high_skill": {"physical": 61.49, "labor": 0.0, "knowledge": 27.62, "brand": 10.89},
}

MARKET_SHARES: dict[str, dict[str, float]] = {
    "all": {"physical": 30.36, "labor": 22.53, "knowledge": 38.28, "brand": 8.83},
    "low_skill": {"physical": 40.16, "labor": 14.33, "knowledge": 20.34, "brand": 25.17},
    "high_skill": {"physical": 29.91, "labor": 20.85, "knowledge": 43.23, "brand": 6.02},
}

CITATION = (
    "Belo, F., Gala, V. D., Salomao, J., and Vitorino, M. A. (2022). "
    "Decomposing firm value. Journal of Financial Economics, 143(2), 619-639."
)


def published_shares() -> pd.DataFrame:
    """Long table of the published shares with columns group, input, book, market."""
    rows = [
        {
            "group": group,
            "input": str(name),
            "book": BOOK_SHARES[group][str(name)],
            "market": MARKET_SHARES[group][str(name)],
        }
        for group in GROUPS
        for name in INPUTS
    ]
    return pd.DataFrame(rows)
