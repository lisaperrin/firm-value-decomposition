# firmvalue

Structural decomposition of a firm's market value into the contributions of
four productive inputs: physical capital, the installed labor force, knowledge
capital and brand capital. The package implements the production-function
approach of Belo, Gala, Salomao and Vitorino (2022), estimates its adjustment
cost parameters by nonlinear least squares on valuation ratios, and reports
book-value and market-value shares by group and over time.

![Value shares over time, synthetic demonstration](docs/figures/shares.png)

The figure comes from the packaged demonstration: a synthetic panel of 800
firms over 1975 to 2015 drawn from the model, re-estimated from scratch, and
decomposed. Compustat, the data behind the published estimates, is
proprietary; the `prepare` command turns a Compustat extract into the panel
this package expects so that the same pipeline runs on real data.

## What it does

- Builds knowledge and brand capital stocks from R&D and advertising flows with
  the perpetual inventory method.
- Computes the shadow value of each installed input from investment rates and
  the statutory corporate tax rate.
- Estimates the adjustment cost parameters by minimising the squared error of
  the valuation ratio, with firm-clustered standard errors and fit statistics at
  the firm-year, portfolio and aggregate time-series level.
- Decomposes firm value into input values and shares, and plots their history.
- Simulates panels from the model for Monte Carlo checks of the estimator.

## The model

Firms choose investment in four inputs to maximise the present value of
after-tax dividends. Each stock follows

$$X_{j,t+1} = (1-\delta_j)\,X_{j,t} + I_{j,t}, \qquad j \in \{K, L, N, B\},$$

with physical capital $K$, labor $L$ (hires as the flow, separations as
depreciation), knowledge capital $N$ (R&D) and brand capital $B$ (advertising).
Adjusting an input is costly:

$$C_j(I_j, X_j) = \frac{\theta_j}{\nu_j}\left|\frac{I_j}{X_j}\right|^{\nu_j} X_j,$$

which is quadratic for $\nu_j = 2$. Operating profit and adjustment costs are
homogeneous of degree one in stocks and flows, so Hayashi's theorem extends to
every input and ex-dividend market value is exactly linear in the installed
stocks:

$$V_t = \sum_j q_{j,t}\,X_{j,t+1}.$$

The shadow value $q_j$ equals the full after-tax marginal cost of one more
unit. R&D and advertising are expensed, so a unit costs $1-\tau$; physical
investment is capitalised and costs $1$; labor has no purchase price:

$$q_K = 1 + (1-\tau)\,\theta_K \left(\tfrac{I_K}{K}\right)^{\nu_K-1}, \quad
q_N = (1-\tau)\Big[1 + \theta_N \left(\tfrac{I_N}{N}\right)^{\nu_N-1}\Big],$$

$$q_B = (1-\tau)\Big[1 + \theta_B \left(\tfrac{I_B}{B}\right)^{\nu_B-1}\Big], \quad
q_L = (1-\tau)\,\theta_L \left(\tfrac{H}{L}\right)^{\nu_L-1}.$$

The market-value share of input $j$ is $\mu_j = q_j X_j / V$. Book-value shares
divide each capital stock by the sum of physical, knowledge and brand capital;
labor has no book value.

### Estimation

The target is the valuation ratio, market value over the book sum of the three
capital stocks. The model-implied ratio is

$$\hat v_{it}(\theta) = \frac{\sum_j q_{j,it}(\theta)\,X_{j,it}}{K_{it}+N_{it}+B_{it}},$$

and the estimator minimises $\sum_{it}\big(v_{it} - \hat v_{it}(\theta)\big)^2$
subject to $\theta_j \ge 0$. With quadratic costs the problem is linear in
$\theta$ and solved exactly by non-negative least squares; that solution also
seeds the trust-region solver when the curvatures $\nu_j$ are estimated too.
Standard errors are clustered by firm.

Three fit statistics are reported, each as $1 - SSR/SST$:

| statistic | compares |
|---|---|
| pooled | observed and implied ratios across all firm-years |
| time series | the annual aggregate ratio (total value over total book capital) and its model counterpart |
| cross section | average ratios of ten portfolios formed each year on the previous year's observed ratio |

The lagged sort keeps the portfolio statistic from mechanically favouring the
model.

## Quick start

```bash
uv sync
uv run firmvalue demo --out-dir outputs
```

The demonstration simulates, estimates, decomposes and plots in a few seconds
and writes `panel.csv`, `parameters.json`, `decomposition.csv`, `shares.png`
and `report.md`. The individual steps are also commands:

```bash
uv run firmvalue simulate --out panel.csv --firms 400 --seed 0
uv run firmvalue estimate panel.csv --out parameters.json
uv run firmvalue shares panel.csv parameters.json --out decomposition.csv
uv run firmvalue figure panel.csv parameters.json --out shares.png
```

From Python:

```python
from firmvalue import SimulationDesign, decompose, estimate_by_group, simulate_panel

panel = simulate_panel(SimulationDesign.demo(), seed=0)
results = estimate_by_group(panel)
low = results["low_skill"]
print(low.summary())
print(low.fit)
shares = decompose(panel[panel["group"] == "low_skill"], low.params)
print(shares.filter(like="share_").mean())
```

## Demonstration results

Averages in percent over all firm-years of the synthetic panel (400 firms per
group, seed 0), next to Tables 2 and 4 of the paper. The synthetic groups are
calibrated to resemble the published composition, so the closeness of the
market shares is a check on the pipeline rather than a replication.

| group | input | book | book (paper) | market | market (paper) |
|---|---|---|---|---|---|
| all | physical | 56.8 | 64.3 | 29.7 | 30.4 |
| all | labor | 0.0 | 0.0 | 17.8 | 22.5 |
| all | knowledge | 25.5 | 22.8 | 36.3 | 38.3 |
| all | brand | 17.7 | 12.9 | 16.3 | 8.8 |
| low skill | physical | 63.0 | 71.7 | 33.9 | 40.2 |
| low skill | labor | 0.0 | 0.0 | 15.8 | 14.3 |
| low skill | knowledge | 14.8 | 10.1 | 24.8 | 20.3 |
| low skill | brand | 22.3 | 18.2 | 25.4 | 25.2 |
| high skill | physical | 50.6 | 61.5 | 25.4 | 29.9 |
| high skill | labor | 0.0 | 0.0 | 19.8 | 20.9 |
| high skill | knowledge | 36.3 | 27.6 | 47.7 | 43.2 |
| high skill | brand | 13.1 | 10.9 | 7.1 | 6.0 |

The estimator recovers the simulated adjustment cost parameters within
sampling error (true values 2 / 900 / 32 / 7 for the low-skill group and
2 / 1500 / 27 / 2 for the high-skill group, in the order physical, labor,
knowledge, brand):

| group | physical | labor | knowledge | brand |
|---|---|---|---|---|
| low skill | 2.11 (0.14) | 845 (29) | 33.5 (0.6) | 7.04 (0.14) |
| high skill | 2.08 (0.16) | 1477 (20) | 26.9 (0.2) | 2.30 (0.17) |

Labor's parameter is in millions of dollars per thousand employees, so a
value of 900 at a hiring rate of 13 percent and a 35 percent tax rate puts
the shadow value of an installed employee at about 76 thousand dollars.

## Using Compustat data

`firmvalue prepare` reads a Fundamentals Annual extract with the lower-case
mnemonics `gvkey, fyear, prcc_f, csho, dltt, dlc, ppent, capx, xrd, xad, emp`
and optionally `che` and `sic`, and writes the estimation panel:

- market value = price times shares outstanding plus long-term debt and debt in
  current liabilities, optionally net of cash;
- physical capital = net property, plant and equipment, flow = capital
  expenditure;
- knowledge and brand capital = perpetual inventory of R&D and advertising
  (missing flows treated as zero) at 15 and 50 percent depreciation, opening
  stock from the first flow at an assumed 3 percent pre-sample growth;
- labor = employees, hires = change in employment plus 10 percent separations;
- tax rate = top statutory federal corporate rate for the fiscal year;
- financials and utilities dropped, firms with fewer than three usable years
  dropped.

Pass a `group` function to `from_compustat` to label firms, for instance by
the skill intensity of their industry, and `estimate` will fit each group
separately as well as pooled.

## Assumptions and limits

- Depreciation rates, tax treatment and the labor separation rate live in
  `InputSpec` objects and can be changed per run; the defaults follow common
  choices in this literature rather than estimated values.
- Tax depreciation allowances and investment tax credits are ignored, so the
  physical capital price is exactly one.
- Shares in tables and figures are equal-weighted averages of firm-level
  shares; `annual_shares(weighted=True)` gives the aggregate share instead.
- The fit statistics are this package's definitions. The paper's moment
  conditions are documented there; the statistics here are designed to answer
  the same question but are not identical.
- The demonstration data are synthetic. Nothing in this repository is an
  empirical result about U.S. firms.

## Project layout

```
src/firmvalue/
  inputs.py      the four inputs, depreciation and tax treatment
  capital.py     perpetual inventory
  tax.py         statutory corporate tax rates
  panel.py       panel schema and validation
  model.py       adjustment costs, shadow values, value identity, decomposition
  estimation.py  nonlinear least squares, clustered standard errors, fit
  simulate.py    synthetic panels from the model
  compustat.py   Compustat adapter
  plotting.py    stacked-area share histories
  reference.py   published shares from the paper
  cli.py         command-line interface
tests/           unit tests and Monte Carlo recovery tests
docs/design.md   design notes and alternatives considered
```

## Development

```bash
uv sync --all-groups
uv run pytest --cov=firmvalue
uv run ruff check . && uv run ruff format --check .
uv run mypy src
```

## Reference

Belo, F., Gala, V. D., Salomao, J., and Vitorino, M. A. (2022). Decomposing
firm value. *Journal of Financial Economics*, 143(2), 619–639.
