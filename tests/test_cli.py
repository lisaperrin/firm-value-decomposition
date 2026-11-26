import json

import pandas as pd
from typer.testing import CliRunner

from firmvalue import __version__, live
from firmvalue.cli import app
from tests.live_fixtures import make_records

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


def test_json_mode_prints_machine_readable_output(tmp_path):
    panel = tmp_path / "panel.csv"
    params = tmp_path / "parameters.json"
    result = runner.invoke(app, ["--json", "simulate", "--out", str(panel), "--firms", "20"])
    assert result.exit_code == 0, result.output
    summary = json.loads(result.output)
    assert summary["firms"] == 40
    assert summary["years"] == [1975, 2015]

    result = runner.invoke(app, ["--json", "estimate", str(panel), "--out", str(params)])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == json.loads(params.read_text())

    result = runner.invoke(app, ["--json", "shares", str(panel), str(params)])
    assert result.exit_code == 0, result.output
    rows = json.loads(result.output)["shares"]
    assert len(rows) == 12


def test_errors_exit_one_with_one_line(tmp_path):
    result = runner.invoke(app, ["estimate", str(tmp_path / "missing.csv")])
    assert result.exit_code == 1
    assert "error: panel file not found" in result.output
    bad = tmp_path / "bad.csv"
    bad.write_text("firm,year\na,2000\n")
    result = runner.invoke(app, ["estimate", str(bad)])
    assert result.exit_code == 1
    assert "missing required columns" in result.output


def test_version_flag():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


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
    result = runner.invoke(app, ["prepare", str(tmp_path / "nope.csv")])
    assert result.exit_code == 1
    assert "not found" in result.output


def test_live_command(monkeypatch, tmp_path):
    monkeypatch.setattr(live, "statements_source", lambda s, y: (make_records(s, y), 30_000))
    result = runner.invoke(app, ["live", "ACME", "BETA", "--years", "3"])
    assert result.exit_code == 0, result.output
    assert "ACME fiscal 2025" in result.output
    assert "BETA fiscal 2025" in result.output
    assert "| input | stock | q | book share | market share |" in result.output
    assert "illustrative" in result.output

    panel_out = tmp_path / "live.csv"
    result = runner.invoke(
        app, ["--json", "live", "ACME", "--brand-share", "0.5", "--panel-out", str(panel_out)]
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)["results"][0]
    assert data["latest_fiscal_year"] == 2025
    assert any("50% of SG&A" in note for note in data["notes"])
    assert len(pd.read_csv(panel_out)) == 4

    result = runner.invoke(app, ["live", "ACME", "--parameters", str(tmp_path / "nope.json")])
    assert result.exit_code == 1
    assert "not found" in result.output
