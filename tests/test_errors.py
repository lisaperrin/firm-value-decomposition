import json
from pathlib import Path

import pytest

from firmvalue.errors import FirmValueError, InputFileError, PanelError, ParametersError
from firmvalue.io import parameters_from_payload, read_panel, read_parameters


def test_hierarchy() -> None:
    for cls in (PanelError, ParametersError, InputFileError):
        assert issubclass(cls, FirmValueError)
        assert issubclass(cls, Exception)


def test_missing_files_name_the_path(tmp_path: Path) -> None:
    with pytest.raises(InputFileError, match=r"panel\.csv"):
        read_panel(tmp_path / "panel.csv")
    with pytest.raises(InputFileError, match=r"parameters\.json"):
        read_parameters(tmp_path / "parameters.json")


def test_malformed_parameters(tmp_path: Path) -> None:
    path = tmp_path / "parameters.json"
    path.write_text("not json")
    with pytest.raises(ParametersError, match="valid JSON"):
        read_parameters(path)
    path.write_text(json.dumps([1, 2]))
    with pytest.raises(ParametersError, match="keyed by group"):
        read_parameters(path)
    with pytest.raises(ParametersError, match="malformed"):
        parameters_from_payload({"all": {"parameters": {"physical": {"scale": 1.0}}}})
    with pytest.raises(ParametersError, match="malformed"):
        parameters_from_payload({"all": {}})
