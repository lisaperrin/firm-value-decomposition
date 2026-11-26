# Design notes

## Intent

Turn the production-function decomposition of firm value from Belo, Gala,
Salomao and Vitorino (2022) into a reusable, tested implementation: a model
layer that states the value identity, an estimator that fits the adjustment
cost parameters to valuation ratios, a data layer that builds the required
panel from Compustat, and a simulation layer that makes the whole pipeline
runnable and testable without proprietary data.

## Goals

- Exact value identity: implied value equals the sum of shadow values times
  stocks for any parameter vector, and shares sum to one.
- Estimation that reduces to a closed-form linear problem in the quadratic case
  and extends to estimated curvature without changing the interface.
- Honest fit reporting at three aggregation levels, with firm-clustered
  standard errors.
- A demonstration that runs in seconds and reproduces the shape of the
  published tables and figure from synthetic data.
- Every empirical convention (depreciation, tax treatment, market value
  definition, sample filters) visible in one place and overridable.

## Non-goals

- Replicating the paper's point estimates. The data are proprietary and the
  paper's moment conditions are not reproduced verbatim.
- A general dynamic-programming solver. The value identity makes the firm's
  problem unnecessary to solve; only first-order conditions are used.
- Industry classification into skill groups. Users supply a grouping.

## Approaches considered

**Language.** Python with `uv` was chosen over Rust. The workload is panel
algebra, a small nonlinear least-squares problem and plotting; NumPy, pandas,
SciPy and Matplotlib cover it, estimation runs in under a second on tens of
thousands of firm-years, and the audience (finance researchers and analysts)
reads Python. Rust would add build complexity without a performance need.

**Estimation.** Three options were weighed.

1. Nonlinear least squares on the valuation ratio (chosen). Transparent,
   fast, and with quadratic costs the problem is linear so the non-negative
   least-squares solution is exact and serves as a starting point when
   curvature is estimated.
2. GMM on portfolio-level moments, closer to the structural-estimation
   literature. More machinery (weighting matrix, moment selection) for the
   same identifying variation; left as a possible extension on top of the
   same `_Design` arrays.
3. Simulated method of moments with a full solution of the firm's problem.
   Unnecessary because the value identity gives closed-form implied values.

**Adjustment costs.** A power-form cost `(theta/nu)|I/X|^nu X` nests the
quadratic case and keeps homogeneity of degree one, which the value identity
requires. Asymmetric or fixed costs were rejected because they break the
identity.

**Panel timing.** Stocks are stored at fiscal year end, after the year's
investment, so market value at the same date is a linear combination of
them. The investment rate uses the opening stock recovered from the law of
motion, falling back to the closing stock in a firm's first year of a given
flow.

**Synthetic data.** Investment rates are the target rate plus additive firm
growth, persistent input-specific and transitory AR(1) deviations. An earlier
log-normal multiplicative design made high-depreciation stocks compound away
from the intended composition over four decades; additive shocks keep the
cross-sectional composition stable while leaving enough rate variation to
identify the parameters.

## Decisions left to users

- Depreciation and separation rates (`InputSpec`).
- Whether market value is net of cash.
- Group definitions for separate estimation.
- Whether to estimate cost curvature.
- Number of portfolios in the cross-sectional fit statistic.
