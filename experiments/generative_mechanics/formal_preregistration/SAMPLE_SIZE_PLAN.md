# Sample Size Plan

Status: candidate plan; no formal collection has started.

## Basis

The independent unit is one requested mechanism. Registered execution arms are
repeated measurements, not additional generated samples. The DEV pilot is used
only for engineering validation and supplies no confirmatory effect size.

For a proportion, the worst-case normal-approximation 95% confidence-interval
half-width is

```text
h(N) = 1.96 * sqrt(0.5 * 0.5 / N).
```

The probability of seeing at least one event with true per-mechanism event rate
`p` is

```text
Pr(at least one) = 1 - (1 - p)^N.
```

These are design calculations, not promises about realized interval widths or
power. Confirmatory analyses will use the separately preregistered interval and
testing procedures rather than substituting the approximation below.

## Exact design calculations

| N per model | Worst-case 95% half-width | At least one if p=1% | p=2% | p=5% | p=10% |
|---:|---:|---:|---:|---:|---:|
| 75 | 11.3161 pp | 52.9413% | 78.0236% | 97.8656% | 99.9630% |
| 100 | 9.8000 pp | 63.3968% | 86.7380% | 99.4079% | 99.9973% |
| 150 | 8.0017 pp | 77.8548% | 95.1704% | 99.9544% | 100.0000%* |
| 200 | 6.9296 pp | 86.6020% | 98.2412% | 99.9965% | 100.0000%* |

`*` Rounded to four decimal places; the unrounded probability is below 100%.

## Owner candidates

| Candidate | N/model | Interpretation |
|---|---:|---|
| Economy | 100 | About +/-9.80 pp worst-case precision; weak coverage for 1% events. |
| Balanced | 150 | About +/-8.00 pp; at least 95.17% chance to observe a 2% event once. |
| Precision | 200 | About +/-6.93 pp; higher cost and collection exposure. |

`N=75` is retained as a documented planning reference, not an owner-gate option.
All selected models must receive the same fixed `N`. Expected-valid counts must
not be used to top up invalid outputs or alter `N`.

Costs for each candidate are parameterized in `COLLECTION_COST_PLAN.md` because
current prices, token use, rate limits, validity rates, and runtimes are
`UNVERIFIED`.

```text
OWNER_DECISION_REQUIRED:
sample_size_per_model = null  # choose exactly one of 100, 150, 200
```
