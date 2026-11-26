---
name: explain-model
description: Explain how the firm-value decomposition works, from the production-function setup to the estimation, at a chosen depth. Use when the user asks why firm value is linear in the installed stocks, what a shadow value is, how the parameters are identified, or what a result means.
argument-hint: [topic] [brief|full]
---

# Explain the model

Explain **$0** (default: the whole model) at depth **$1** (default `brief`: under 300 words;
`full`: as long as needed with the equations). Ground every statement in the repository
rather than general knowledge.

## Sources to read first

- `README.md`, section "The model": the law of motion, adjustment costs, the value identity
  and the four shadow-value formulas.
- `src/firmvalue/model.py`: the implementation of those formulas, including how the
  opening stock is recovered from the law of motion and how zero stocks are handled.
- `src/firmvalue/estimation.py`: the valuation ratio target, why quadratic costs give a
  linear problem, clustered standard errors and the three fit statistics.
- `docs/design.md`: the approaches considered and the choices made.

## Structure

1. **The question**: how much of a firm's market value is attributable to each input.
2. **The mechanism**: constant returns in production and adjustment costs make value linear
   in installed stocks (Hayashi's theorem extended to four inputs). State the identity.
3. **The shadow values**: each `q_j` is the after-tax marginal cost of one more unit;
   explain why expensed intangibles carry `1 - tau` and labor has no purchase price.
4. **Identification**: the parameters are read off how the valuation ratio moves with
   investment rates across firms and years.
5. **What the shares mean**: book versus market shares, and why they differ.
6. **Limits**: what the package assumes (depreciation rates, no tax depreciation
   allowances, equal-weighted shares) and that the demonstration data are synthetic.

## Rules

- Use the package's variable names when pointing at code (`q_knowledge`,
  `share_labor`), and the paper's notation in equations.
- Do not state parameter values or empirical shares unless you read them from a tool
  result, `outputs/report.md`, or `src/firmvalue/reference.py`.
- Keep the economics honest: say "the model implies" rather than "firms are worth".
