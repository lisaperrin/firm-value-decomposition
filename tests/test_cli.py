import json

import pandas as pd
from typer.testing import CliRunner

from firmvalue.cli import app

runner = CliRunner()


def test_pipeline_commands(tmp_path):
    panel = tmp_path / "panel.csv"
    params = tmp_path / "parameters.json"
    figure = tmp_path / "shares.png"
    decomposition = tmp_path / "decomposition.csv"

    assert runner.invoke(app, ["simulate", "--out", str(panel), "--firms", "40"]).exit_code == 0
    assert runner.invoke(app, ["estimate", str(panel), "--out", str(params)]).exit_code == 0
    payload = json.loads(params.read_text())
    assert set(payload) == {"all", "low_skill", "high_skill"}
    assert set(payload["all"]["parameters"]) == {"physical", "labor", "knowledge", "brand"}

    result = runner.invoke(app, ["shares", str(panel), str(params), "--out", str(decomposition)])
    assert result.exit_code == 0
    assert "| group | input | book | market |" in result.output
    frame = pd.read_csv(decomposition)
    assert {"share_physical", "share_labor", "share_knowledge", "share_brand"} <= set(frame)

    assert (
        runner.invoke(app, ["figure", str(panel), str(params), "--out", str(figure)]).exit_code == 0
    )
    assert figure.stat().st_size > 0


def test_demo_writes_report(tmp_path):
    out = tmp_path / "outputs"
    result = runner.invoke(app, ["demo", "--out-dir", str(out), "--firms", "30"])
    assert result.exit_code == 0, result.output
    for name in ("panel.csv", "parameters.json", "decomposition.csv", "report.md", "shares.png"):
        assert (out / name).exists()
    report = (out / "report.md").read_text()
    assert "market_published" in report
    assert "Belo" in report


def test_prepare_from_compustat(tmp_path):
    rows = []
    for gvkey in (1, 2):
        for i, fyear in enumerate(range(2000, 2006)):
            rows.append(
                {
                    "gvkey": gvkey,
                    "fyear": fyear,
                    "prcc_f": 10.0,
                    "csho": 10.0,
                    "dltt": 5.0,
                    "dlc": 1.0,
                    "ppent": 100.0 + i,
                    "capx": 15.0,
                    "xrd": 4.0,
                    "xad": 2.0,
                    "emp": 1.0 + 0.05 * i,
                }
            )
    funda = tmp_path / "funda.csv"
    pd.DataFrame(rows).to_csv(funda, index=False)
    out = tmp_path / "panel.csv"
    result = runner.invoke(app, ["prepare", str(funda), "--out", str(out)])
    assert result.exit_code == 0, result.output
    assert len(pd.read_csv(out)) == 10
