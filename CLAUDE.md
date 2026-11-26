# firmvalue

Python 3.12+ package implementing the production-function decomposition of firm value
(Belo, Gala, Salomao and Vitorino, 2022), plus the Claude Code plugin in this same
repository (`.claude-plugin/`, `skills/`, `agents/`, `hooks/`, `.mcp.json`).

## Commands

- `uv sync --all-groups --extra live` installs everything, including MarketLens for live mode.
- `uv run pytest -q` runs the suite (a few seconds, no network).
- `uv run ruff check . && uv run ruff format --check . && uv run mypy` is the lint gate.
- `uv run firmvalue --help` is the CLI; `uv run firmvalue-mcp` starts the MCP server.
- `uv run firmvalue demo --out-dir outputs` regenerates the demonstration report and figure.
- `uv run python scripts/validate_plugin.py` checks the plugin files are coherent.

## Architecture (see docs/design.md)

- `inputs.py`: the four inputs with depreciation and tax treatment (`InputSpec`).
- `model.py`: adjustment costs, shadow values, the value identity and `decompose`. The
  identity `implied_value == sum(q_j * X_j)` must hold exactly for any parameters.
- `estimation.py`: nonlinear least squares on the valuation ratio, firm-clustered standard
  errors, fit statistics. Quadratic costs are solved by non-negative least squares.
- `capital.py`, `tax.py`, `compustat.py`: data construction. `simulate.py`: synthetic panels.
- `io.py`: reading and writing panels and parameter files, share tables, Markdown rendering.
- `live.py`: statements from MarketLens (optional extra `live`) to a one-firm panel and its
  decomposition; every proxy is recorded in `notes`. Tests use `tests/live_fixtures.py`, never
  the network, and replace `live.statements_source`.
- `cli.py` and `mcp_server.py` are thin; logic lives in the modules above.

## Conventions

- Panels store end-of-year stocks and the year's flows; see `panel.py` for the schema.
  Capital stocks are in money units, labor in thousands of employees.
- Shares are fractions inside the library and percent in tables and tool output.
- Every formula has a test with a hand-computable expected value; estimator changes must keep
  the Monte Carlo recovery tests passing.
- Errors derive from `FirmValueError`; the CLI exits 1 with one line, MCP raises `ToolError`.
- Frozen dataclasses for parameters and results. Numpy-style docstrings.
- Conventional commit messages (`feat(estimation): ...`, `fix(cli): ...`).
- Hooks in `.claude/settings.json` auto-format Python after edits and block force-pushes and
  `--no-verify`; do not work around them.
