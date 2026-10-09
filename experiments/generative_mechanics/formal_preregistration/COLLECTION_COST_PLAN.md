# Collection Cost Plan

Status: parameterized estimate only. Current prices, token usage, rate limits,
validity rates, runtimes, and storage sizes are `UNVERIFIED`; no numeric currency,
runtime, or validity promise is made.

## Request-count grid

| Models | N/model=100 | N/model=150 | N/model=200 |
|---:|---:|---:|---:|
| 4 | 400 requests | 600 requests | 800 requests |
| 5 | 500 requests | 750 requests | 1,000 requests |
| 6 | 600 requests | 900 requests | 1,200 requests |

Transport retries do not increase the preregistered mechanism count, but they
can increase provider calls up to three attempts per exact request. The hard
worst-case attempt counts are therefore 3 times the table values.

## Required estimate inputs

For model `m`, verify before owner signoff:

```text
I_m = mean billed input tokens/request
O_m = mean billed output tokens/request
C_in_m = input currency units per 1,000,000 tokens
C_out_m = output currency units per 1,000,000 tokens
q_m = planning execution-valid probability (engineering estimate only)
r_m = expected transport attempts/request, bounded 1 <= r_m <= 3
lambda_m = sustainable request rate/minute
c_m = authorized concurrency
D_req_m, D_resp_m = mean raw request/response bytes
T_eval_m = evaluator runtime per returned mechanism
T_ablate_m = ablation runtime per execution-valid mechanism
```

All currently equal `UNVERIFIED`. Pilot observations may inform engineering
capacity ranges but must not be used as an effect size, directional hypothesis,
or reason to choose N.

For the table below, define matrix aggregates:

```text
Q_k = sum(q_m)                          expected valid mechanisms per one N
I_k = sum(r_m * I_m)                    billed input tokens per one N
O_k = sum(r_m * O_m)                    billed output tokens per one N
C_k = sum(r_m*(I_m*C_in_m+O_m*C_out_m)/1,000,000)
E_k = sum(T_eval_m)                     evaluator time per one N
A_k = sum(q_m*T_ablate_m)               ablation time per one N
D_k = sum(D_req_m+r_m*D_resp_m)         raw bytes per one N
W_k = sum(r_m/lambda_m)                 serial minutes per one N
```

Here `k` is the selected 4-, 5-, or 6-model matrix; every aggregate is
`UNVERIFIED` until its model-level inputs are populated.

| Matrix | N | Requests | Expected valid | Input tokens | Output tokens | Generation cost | Evaluator time | Ablation time | Raw disk | Serial wall time |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 4 | 100 | 400 | `100Q_4` | `100I_4` | `100O_4` | `100C_4` | `100E_4` | `100A_4` | `100D_4` | `100W_4` |
| 4 | 150 | 600 | `150Q_4` | `150I_4` | `150O_4` | `150C_4` | `150E_4` | `150A_4` | `150D_4` | `150W_4` |
| 4 | 200 | 800 | `200Q_4` | `200I_4` | `200O_4` | `200C_4` | `200E_4` | `200A_4` | `200D_4` | `200W_4` |
| 5 | 100 | 500 | `100Q_5` | `100I_5` | `100O_5` | `100C_5` | `100E_5` | `100A_5` | `100D_5` | `100W_5` |
| 5 | 150 | 750 | `150Q_5` | `150I_5` | `150O_5` | `150C_5` | `150E_5` | `150A_5` | `150D_5` | `150W_5` |
| 5 | 200 | 1,000 | `200Q_5` | `200I_5` | `200O_5` | `200C_5` | `200E_5` | `200A_5` | `200D_5` | `200W_5` |
| 6 | 100 | 600 | `100Q_6` | `100I_6` | `100O_6` | `100C_6` | `100E_6` | `100A_6` | `100D_6` | `100W_6` |
| 6 | 150 | 900 | `150Q_6` | `150I_6` | `150O_6` | `150C_6` | `150E_6` | `150A_6` | `150D_6` | `150W_6` |
| 6 | 200 | 1,200 | `200Q_6` | `200I_6` | `200O_6` | `200C_6` | `200E_6` | `200A_6` | `200D_6` | `200W_6` |

## Provisional numeric capacity envelope

For a readable owner comparison before provider verification, the following is
an explicitly nonbinding planning scenario. It is **ESTIMATE / UNVERIFIED**, is
not derived from the DEV pilot, and will not be frozen as an observed fact:

```text
execution-valid planning range: 80%-95% of requested mechanisms
billed input: 2,500-5,000 tokens/request, including expected retry allowance
billed output: 300-1,500 tokens/request, including expected retry allowance
evaluator CPU: 0.25-1.00 minutes/request
ablation CPU: 1-5 minutes/execution-valid mechanism
raw plus derived disk: 0.10-0.50 MB/request
aggregate collection throughput: 2-10 completed requests/minute
```

Let `P_in,k` and `P_out,k` be the verified request-weighted average input and
output prices, in currency units per million tokens, for matrix `k`. They remain
symbolic because unknown provider unit prices must not be guessed. Thus a cell's
currency range is `input_million * P_in,k + output_million * P_out,k`.

| Models x N | Valid mechanisms | Input M tok | Output M tok | Generation cost | Evaluator CPU h | Ablation CPU h | Disk MB | Wall min |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 4 x 100 | 320-380 | 1.000-2.000 | 0.120-0.600 | `1.000P_in,4+0.120P_out,4` to `2.000P_in,4+0.600P_out,4` | 1.67-6.67 | 5.33-31.67 | 40-200 | 40-200 |
| 4 x 150 | 480-570 | 1.500-3.000 | 0.180-0.900 | `1.500P_in,4+0.180P_out,4` to `3.000P_in,4+0.900P_out,4` | 2.50-10.00 | 8.00-47.50 | 60-300 | 60-300 |
| 4 x 200 | 640-760 | 2.000-4.000 | 0.240-1.200 | `2.000P_in,4+0.240P_out,4` to `4.000P_in,4+1.200P_out,4` | 3.33-13.33 | 10.67-63.33 | 80-400 | 80-400 |
| 5 x 100 | 400-475 | 1.250-2.500 | 0.150-0.750 | `1.250P_in,5+0.150P_out,5` to `2.500P_in,5+0.750P_out,5` | 2.08-8.33 | 6.67-39.58 | 50-250 | 50-250 |
| 5 x 150 | 600-713 | 1.875-3.750 | 0.225-1.125 | `1.875P_in,5+0.225P_out,5` to `3.750P_in,5+1.125P_out,5` | 3.13-12.50 | 10.00-59.38 | 75-375 | 75-375 |
| 5 x 200 | 800-950 | 2.500-5.000 | 0.300-1.500 | `2.500P_in,5+0.300P_out,5` to `5.000P_in,5+1.500P_out,5` | 4.17-16.67 | 13.33-79.17 | 100-500 | 100-500 |
| 6 x 100 | 480-570 | 1.500-3.000 | 0.180-0.900 | `1.500P_in,6+0.180P_out,6` to `3.000P_in,6+0.900P_out,6` | 2.50-10.00 | 8.00-47.50 | 60-300 | 60-300 |
| 6 x 150 | 720-855 | 2.250-4.500 | 0.270-1.350 | `2.250P_in,6+0.270P_out,6` to `4.500P_in,6+1.350P_out,6` | 3.75-15.00 | 12.00-71.25 | 90-450 | 90-450 |
| 6 x 200 | 960-1,140 | 3.000-6.000 | 0.360-1.800 | `3.000P_in,6+0.360P_out,6` to `6.000P_in,6+1.800P_out,6` | 5.00-20.00 | 16.00-95.00 | 120-600 | 120-600 |

Ranges combine their respective low and high planning assumptions. They are for
capacity reservation, not inferential inputs and not a promise that every
provider bills retries identically. Replace them with provider-specific measured
ranges before freeze while preserving the formulas and all assumptions.

## Formulas

For equal selected N and selected model set `M`:

```text
requested mechanisms = N * |M|
expected valid mechanisms = N * sum(q_m for m in M)
input tokens = N * sum(r_m * I_m for m in M)
output tokens = N * sum(r_m * O_m for m in M)
generation cost = N * sum(r_m * (I_m*C_in_m + O_m*C_out_m)/1,000,000)
evaluator runtime = N * sum(T_eval_m for m in M)
ablation runtime = N * sum(q_m * T_ablate_m for m in M)
raw disk = N * sum(D_req_m + r_m*D_resp_m for m in M)
```

Add a separately itemized derived-artifact storage factor and fixed manifest/log
overhead after measuring them. Do not hide cached-token pricing, minimum charges,
taxes, egress, serving fees, or retry costs inside a single guessed rate.

For strict serial block execution, a lower-bound collection duration estimate is:

```text
sum(N * r_m / lambda_m for m in M) minutes
```

For provider-parallel execution that still respects recorded within-block launch
order, compute a provider-specific critical path using verified `lambda_m` and
`c_m`. Report both the scheduling assumptions and uncertainty; rate limits and
backend latency make wall-clock time an estimate, not a guarantee.

## Owner cost sheet

Before signoff, populate all nine matrix-by-N cells with:

- currency estimate and explicit price timestamp/source;
- expected input/output tokens and retry assumption;
- expected valid count as a range, not a top-up target;
- evaluator and ablation CPU-hours;
- raw and derived disk requirement;
- serial and authorized-parallel wall-clock range.

The cost sheet may change an owner choice before freeze. After freeze, budget
pressure alone does not authorize optional stopping, changing N, dropping a
poorly performing model, or merging a replacement.
