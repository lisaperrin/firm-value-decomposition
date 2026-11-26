---
name: estimate
description: Estimate the adjustment cost parameters of the firm-value decomposition on a firm-year panel CSV and report the fit. Use when the user has a panel (from Compustat via `firmvalue prepare` or from `simulate`) and wants parameter estimates, standard errors or the valuation-ratio fit.
argument-hint: <panel.csv> [parameters.json] [--curvature]
allowed-tools: mcp__plugin_firmvalue_firmvalue__estimate_parameters mcp__plugin_firmvalue_firmvalue__value_shares Bash(uv run firmvalue *)
---

# Estimate the model

Fit the structural model to the panel at **$0** and write the parameters to `$1`
(default `parameters.json`). Pass `--curvature` only when the user asks to estimate the
curvature of the adjustment cost functions instead of fixing it at 2.

## Steps

1. **Check the file exists.** If `$0` is missing, say so and point to `uv run firmvalue
   prepare <compustat.csv>` or `uv run firmvalue simulate` to make one. Stop there.
2. **Estimate.** Call the `estimate_parameters` MCP tool with `panel_path="$0"` and
   `estimate_curvature` as requested. If the MCP server is unavailable, run
   `uv run firmvalue --json estimate $0 --out $1` instead; the JSON is identical. Never fill
   in estimates from memory.
3. **Read the result before writing.** For each group note the four scales with their
   standard errors, whether `converged` is true, and the three fit statistics
   (`pooled_r2`, `time_series_r2`, `cross_section_r2`). A negative R squared means the model
   fits that dimension worse than a constant; say so plainly.
4. **Report** in prose and one table, no more than 250 words:
   - A table of scale estimates with standard errors in parentheses, one row per group.
   - Which inputs carry the highest adjustment costs and how precisely they are pinned
     down (estimate relative to standard error).
   - The fit, naming the weakest of the three statistics.
   - What the user can do next: `value_shares` for the decomposition, `/firmvalue:decompose`
     for a single firm, or re-estimation with `--curvature`.

## Rules

- Labor's scale is in money units per thousand employees; the other scales are
  dimensionless. Say so when comparing magnitudes.
- Parameters are bounded below at zero; an estimate of exactly zero means the bound is
  binding, not that the cost is known to be zero.
- Do not describe the results as a replication of the paper unless the panel is real
  Compustat data, and even then call them "estimates with this package's conventions".
