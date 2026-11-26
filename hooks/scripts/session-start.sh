#!/bin/sh
# SessionStart hook: tell Claude what the firmvalue plugin offers. Plain stdout becomes
# session context. Never fails: a non-zero exit would only add noise to the user's session.
set -u
cat <<'TEXT'
firmvalue plugin is active. The `firmvalue` MCP server decomposes firm value into physical
capital, labor, knowledge capital and brand capital (Belo, Gala, Salomao and Vitorino, 2022).
Tools: estimate_parameters (fit a firm-year panel CSV), value_shares (average shares by
group), decompose_firm (one firm-year from stocks, flows, tax rate and parameters),
decompose_live (a listed company from its published statements, needs the live extra),
simulate_demo_panel (synthetic panel) and published_value_shares (the paper's tables).
Skills: /firmvalue:estimate, /firmvalue:decompose, /firmvalue:live, /firmvalue:explain-model.
Prefer the tools over computing shares by hand; never quote parameter values from memory.
TEXT
exit 0
