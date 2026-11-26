"""Reading and writing panels, parameters and share tables."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pandas as pd

from firmvalue.errors import InputFileError, ParametersError
from firmvalue.estimation import EstimationResult
from firmvalue.inputs import INPUTS
from firmvalue.model import Parameters, decompose
from firmvalue.panel import validate_panel


def read_panel(path: Path) -> pd.DataFrame:
    """Load and validate a panel CSV."""
    if not path.is_file():
        raise InputFileError(f"panel file not found: {path}")
    return validate_panel(pd.read_csv(path))


def results_to_dict(results: Mapping[str, EstimationResult]) -> dict[str, dict[str, Any]]:
    """Convert estimation results into a JSON-ready mapping keyed by group."""
    return {
        group: {
            "parameters": result.params.to_dict(),
            "standard_errors": dict(result.standard_errors),
            "fit": result.fit.to_dict(),
            "converged": result.converged,
        }
        for group, result in results.items()
    }


def write_parameters(results: Mapping[str, EstimationResult], path: Path) -> None:
    """Write estimation results as JSON."""
    path.write_text(json.dumps(results_to_dict(results), indent=2) + "\n")


def parameters_from_payload(payload: Mapping[str, Any]) -> dict[str, Parameters]:
    """Parse the JSON written by :func:`write_parameters` into parameters by group."""
    try:
        return {
            str(group): Parameters.from_dict(entry["parameters"])
            for group, entry in payload.items()
        }
    except (KeyError, TypeError, ValueError) as exc:
        raise ParametersError(f"parameters payload is malformed: {exc}") from exc


def read_parameters(path: Path) -> dict[str, Parameters]:
    """Load parameters by group from a JSON file."""
    if not path.is_file():
        raise InputFileError(f"parameters file not found: {path}")
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ParametersError(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ParametersError(f"{path} must hold an object keyed by group")
    return parameters_from_payload(payload)


def decompose_by_group(panel: pd.DataFrame, params: Mapping[str, Parameters]) -> pd.DataFrame:
    """Decompose each group with its own parameters, falling back to ``"all"``."""
    pieces = []
    for label, frame in panel.groupby("group", sort=True):
        key = str(label) if str(label) in params else "all"
        if key not in params:
            raise ParametersError(f"no parameters for group {label!r} and no 'all' fallback")
        pieces.append(decompose(frame, params[key]))
    return pd.concat(pieces, ignore_index=True)


def share_table(decomposition: pd.DataFrame) -> pd.DataFrame:
    """Average book and market shares in percent, pooled and by group."""
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


def markdown_table(frame: pd.DataFrame, digits: int = 2) -> str:
    """Render a DataFrame as a GitHub-flavoured Markdown table."""
    header = "| " + " | ".join(frame.columns) + " |"
    rule = "|" + "|".join("---" for _ in frame.columns) + "|"
    body = [
        "| " + " | ".join(f"{v:.{digits}f}" if isinstance(v, float) else str(v) for v in row) + " |"
        for row in frame.itertuples(index=False)
    ]
    return "\n".join([header, rule, *body]) + "\n"
