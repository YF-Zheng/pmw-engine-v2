# Alpha QA Report

2026-10-28 P0 baseline: **644 existing tests passed**, no baseline failures.

| Suite | Tests | Seconds | Evidence |
| --- | ---: | ---: | --- |
| Core | 254 | 32.75 | evidence/p0_core_qa_pytest.txt |
| v06 formal mechanism catalog/compiler | 170 | 32.13 | evidence/p0_next_tracks_v06_qa_pytest.txt |
| Gameplay | 172 | 96.91 | evidence/p0_gameplay_v04_qa_pytest.txt |
| Alpha + Storm Relay M0 | 48 | 129.59 | evidence/p0_alpha_storm_relay_qa_pytest.txt |

All tests ran in the local Python 3.12 runtime with `PYTHONPATH=src` and no
network installation. Five Engine-backed demos were separately regenerated to
evidence/p0_mechanisms; history outputs were not replaced. Detailed discovery,
commands and independent QA conclusions are in P0_BASELINE_QA.md.

New Sandbox v1 / P1 / P2 / generator / browser UX gates are NOT passed by these
baseline tests. Regression results for each new increment are appended after
implementation and independent review, rather than retroactively relabeling
baseline capabilities as complete.

## First P1 Integration Run

First combined run: **2 failed, 691 passed, 3,045 subtests**, 317.75s.
Failures were independently added assertions, NOT suppressed baseline tests:
formal no-recovery Law skipped the domain clamp, and ecology accepted a
nonzero-rate `none` baseline. Evidence is `evidence/p1_initial_regression.txt`.
Both are sent back for narrow repairs; acceptance requires a fresh clean run.
The first run overlapped final QA test-authoring; the final run is taken only
after implementation and independent test scopes have stopped changing.

An independent probe also found an older limitation: ecology base-curve
transitions change stored baseline data without regenerating the compiled base
variant. It predates this increment, is tracked for P1, and cannot be hidden by
claiming all dynamics semantics are restored.

## Final Frozen Regression

All implementation and independent QA workers were closed before this run;
the source/test scopes did not change during execution.

```powershell
$env:PYTHONPATH='src'
$env:PYTHONDONTWRITEBYTECODE='1'
python -m pytest -q -ra -p no:cacheprovider `
  tests `
  experiments/generative_mechanics/next_tracks_v06/tests `
  experiments/generative_mechanics/next_tracks_v06/gameplay_v04/tests `
  examples/pmw_alpha/tests examples/storm_relay/tests
```

**701 passed, 3,130 subtests passed in 342.67s (0:05:42)**. Exit code 0.
Evidence: `evidence/p1_frozen_final_regression.txt`.

The intervening `evidence/p1_combined_regression.txt` run recorded **6 failed,
695 passed, 3,130 subtests passed in 358.13s** against intermediate Process
source while its worker was still repairing `valid_duration` and capacity
branches. This is retained as failed-run history, not relabeled as a passing
result. The final frozen rerun above is the current cross-module result.

Bounded accepted changes: no-recovery curve/policy/domain clamp, trusted
Stock-conversion Process on the existing clock, Alpha authoritative completed
time and real topology, and fail-closed deduplicated reference-cost tooling.
Independent review: `P1_INDEPENDENT_REVIEW.md`; its QA-owned results remain
separate from this Main-owned full regression.

Full P1 remains open: all ten integrated scenarios, generic seven-Operator
Action/material/Registry access, global budgets/locality, and ecology base-curve
transition semantics. No P2/P3/P4/P5 acceptance or new generation-provider
calls follow from a green regression. Alpha save v0.3 deliberately rejects old
v0.2 saves; compatibility migration remains an explicit future decision.
