---
name: decompose
description: Split a firm's market value into physical capital, labor, knowledge capital and brand capital. Use when the user asks what share of a company's value comes from its intangibles or workforce, gives stocks and flows for one firm-year, or wants average shares for a panel.
argument-hint: <panel.csv parameters.json | stocks and flows for one firm>
allowed-tools: mcp__plugin_firmvalue_firmvalue__value_shares mcp__plugin_firmvalue_firmvalue__decompose_firm mcp__plugin_firmvalue_firmvalue__published_value_shares Bash(uv run firmvalue *)
---

# Decompose firm value

Produce the value decomposition for **$ARGUMENTS** using the firmvalue tools.

## Which tool

- **A panel and a parameters file** (`panel.csv parameters.json`): call `value_shares` with
  both paths. Without a parameters file, call it with the panel only and it estimates first.
  The CLI equivalent is `uv run firmvalue --json shares <panel> <parameters>`.
- **One firm-year**: call `decompose_firm` with end-of-year stocks (`physical`, `knowledge`,
  `brand` in money units, `labor` in thousands of employees), the year's flows (`capex`,
  `hires`, `rd`, `advertising`), the `tax_rate`, and `scales` mapping each input to its
  adjustment cost scale. Scales come from a previous estimation; if the user has none, ask
  which parameters file to use rather than inventing values.
- **The paper's numbers**: call `published_value_shares` when the user wants the reference
  shares to compare against.

## Steps

1. Collect the inputs. If a stock or flow is missing, ask for it or state the assumption you
   make (for example a zero advertising flow) before calling the tool.
2. Call the tool. Shares in tool output are fractions for `decompose_firm` and percent for
   `value_shares`; convert so the write-up uses percent throughout.
3. Read the numbers. Check that market shares sum to one hundred and that the labor book
   share is zero (labor has no book value).
4. Write the result, no more than 200 words:
   - One sentence with the implied value and, for a panel, the valuation ratio it implies.
   - A four-row table: input, book share, market share, and shadow value `q` for a single
     firm.
   - Two sentences on the gap between book and market shares, which is where the
     adjustment costs and the tax treatment show up.
   - For a panel, how the groups differ.
5. If a parameters file estimated on synthetic data was used, say so.

## Rules

- Never quote shares or parameters from memory; every number comes from a tool call.
- Describe; do not advise on buying, selling or valuing securities.
