---
name: live
description: Decompose a listed company's market value into physical capital, labor, knowledge capital and brand capital from its published annual statements. Use when the user names a ticker and asks what share of the company's value is its workforce, R&D, brand or plant, or wants two or three companies compared on that basis.
argument-hint: <TICKER> [TICKER ...] [years]
allowed-tools: mcp__plugin_firmvalue_firmvalue__decompose_live mcp__plugin_firmvalue_firmvalue__published_value_shares Bash(uv run firmvalue *)
---

# Live decomposition

Decompose **$ARGUMENTS** from live statements. The optional trailing number is how many
fiscal years to pull (default 4, minimum 2).

## Steps

1. **Fetch and decompose.** Call `decompose_live` once per ticker with `symbol` and
   `years`. If the MCP server is unavailable, run `uv run firmvalue --json live <TICKERS>`
   instead; the JSON is identical. If the tool reports that MarketLens is missing, tell the
   user to install the extra (`uv sync --extra live`) and stop. Never fill in numbers from
   memory.
2. **Parameters.** If the user has a parameters file from `/firmvalue:estimate`, pass it as
   `parameters_path` and the group key. Otherwise the tool applies an illustrative
   calibration and `parameters_source` says so; repeat that sentence in the write-up.
3. **Read before writing.** Note the latest fiscal year, the currency, the observed and
   implied valuation ratios (a large gap means the parameters do not price this firm), the
   four market shares, and every entry under `notes`.
4. **Write the result**, no more than 250 words for one ticker, a shared table for several:
   - One line: company, fiscal year, observed value and implied value in millions of the
     reporting currency, and the two ratios.
   - A table with one row per input: book share, market share, shadow value `q`.
   - For several tickers, one table with a column per ticker and a sentence on the
     biggest difference.
   - The proxies, verbatim from `notes`: advertising as a share of SG&A, headcount carried
     back, intangible stocks initialised from the first year, tax schedule if non-US.
   - One sentence on what the parameters are and are not.
5. **Close** with: "Model-implied shares under the stated parameters; delayed data, not
   investment advice."

## Rules

- Shares in the tool output are already in percent; stocks and values are in millions.
- A labor share of zero with a "no headcount" note is a data gap, not a finding.
- Describe; do not advise on buying, selling or valuing securities.
- If `decompose_live` reports an unknown symbol, say so and suggest likely tickers.
