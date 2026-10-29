# P1 Ecology Live Baseline-Curve Increment

Date: 2026-10-29, Asia/Shanghai. Starting checkpoint: `e57b3c0`.
Status: ACCEPTED bounded ecology curve increment; full P1 NOT accepted.

## Bounded Objective

Make the existing formal Gameplay dynamics Laws use the current authoritative
Field baseline curve after an ecology transition. Do not add a clock, simulator,
per-tick Python evaluator, model-generated code, or direct WorldState writes.
Preserve source layering, rate/domain bounds, expiry-before-tick and staged
action transactions. P1/P2 gates remain open; no game skill-generation calls.

## Actual Before Evidence

`evidence/p1_ecology_curve_before.json` records three real `advance_world_tick`
calls. Ecology enters `beta` and stores `baseline.curve = none` at step 1, but
steps 2 and 3 still report `effective_curve = linear`. The frozen `FieldProfile`
chose the base formula at Law-build time. Target/rate expressions already read
live baseline state; the formula alone was stale. Rebuilding a session could
therefore change future behavior without changing the saved world.

## Acceptance And Risks

- All three base curves dispatch from live state, mutually exclusively, while
  active override priorities still choose exactly one formula.
- Preserve tick read-state ordering: ecology and dynamics are event Laws for
  the same WORLD_TICK_EVENT and read its pre-event state. Step N's baseline
  writes publish alongside its old-curve dynamics; step N+1 uses the new curve.
  Do not invent a separate post-dynamics ecology phase.
- Check quantitative values, not only diagnostics; verify two independent
  Areas, base target/rate changes, source contributions, override expiry and
  world save/rebuild deterministic continuation.
- Keep trusted input curve/rate validation and numerical stability limits.
  Arbitrary administrative mutation of hidden components is not a Skill API.
- Document the required expanded Law catalog; historical old-Law byte parity
  applies to the previous increment, not to this deliberate routing fix.
- Run focused owner/independent tests and frozen cross-module regression;
  retain red evidence and require independent acceptance before checkpoint.

## Ownership

| Role | Model route | Write scope |
| --- | --- | --- |
| Main architecture/accounting | tencent/gpt-6.1-sol | manifest, prior limitation expectation, status and evidence |
| Goodall implementation | tencent/deepseek-v4.1-flash | dynamics.py, runtime.py only if necessary, test_sandbox_ecology_curve.py |
| Descartes independent QA | tencent/deepseek-v4.1-flash | test_sandbox_ecology_curve_review.py, dedicated review/evidence |

Native child IDs and this resumed Main turn are selected explicitly in
`project_run.json`; actual rollout metadata, not identity prose, verifies routes.
Workers share the checkout but have explicit non-overlapping file ownership.
Main does not begin a cross-module acceptance run until both scopes freeze.

## Prior Limitation Assertion

The earlier independent test documented stale curve selection as a known
limitation. Main renames it to
`test_none_ecology_transition_selects_live_baseline_on_next_tick`, retains the
first-tick old-curve assertion and changes the next-tick expectation to `none`.
This intentionally stricter behavior assertion is expected to fail before the
fix; the original limitation remains in the checkpoint and before evidence.

## Main Architecture Review

The production fix is limited to base-variant selection in `dynamics.py`.
Every Field has live `baseline.curve` guards for linear, squared and none;
overrides and all numerical expressions retain existing behavior. No changes
to Engine, runtime.py, ecology.py, checkpoint schema or transaction code.

Main rejected profile-dependent naming in the draft because a registry or
checkpoint rebuild rediscovers the current baseline. Canonical names are now
`base` (linear), `base_distance_squared`, and `base_none`, independent of the
profile's initial curve. Independent QA checks complete applied causal traces,
not only numerical state equality. Main also removed the rationale for new
silent rate-skip guards: trusted initialization already validates input and
effective rate remains clamped as before. This patch does not promise recovery
from arbitrary administrator-written baseline corruption.

`evidence/p1_ecology_main_probe.json` records source hash and real before/after
behavior. With one Field, two persistent slots and two temporary slots plus
the existing clock, the Law catalog grows from 28 (old linear/none) or 29 (old
squared) to 31 for every initial curve. One Field formula matches each tested
tick. This is bounded catalog expansion, not a new scheduler or proof of a
global constant-work budget. Historical byte-for-byte catalog parity and old
squared/none base trace names do not survive this deliberate correctness fix.

Independent frozen QA: 9 tests and 5 subtests passed at source hash
`d057121d008fa5a1d4057fbf838fe4018a8d0386a72c7348664bb0ebe7d67dcb`.
QA identified a contradictory two-Area assertion in the owner draft. Owner
corrected it to independent quantitative assertions, published changes through
test Event/Laws instead of direct live-state writes, and froze both scopes.
Main's final regression runs only after both workers were closed.
`P1_ECOLOGY_CURVE_REVIEW.md` retains the finding at its original review cutoff;
Main's final results will record resolution without rewriting review history.

Owner final focused result: 9 tests, 6 subtests passed. Combined owner-focused
regression: 36 tests, 92 subtests passed (worker-reported). Independent suite
rerun: 9 tests, 5 subtests passed. Main's frozen full run stores all 269 Python
source/test file hashes in `evidence/p1_ecology_full_regression_meta.json` and
checks for changes before accepting the cross-module result.

## Review Cutoff Clarifications

The independent report remains frozen at its original cutoff. Its owner-test
blocker is resolved by the owner final 9-test run; full acceptance still depends
on Main's frozen regression. The intermediate expiry failure came from QA's
own draft, not production authorization logic. The final separate quantitative
expiry cases cover both baseline-curve transition and target/rate change.

The final production source has no new live baseline-rate skip guard. Unknown
administrator-authored curves can have no matching variant; lawful input is
validated at trusted construction and effective rates remain clamped. Do not
infer arbitrary corrupted-state validation from the independent report's
authoring-era boundary comments.

## Next Bounded Task

Continue P1, not P2/P3 generation: bridge trusted typed Stock/Process operations
through existing staged Action and material authority, without exposing raw
Laws, hardcoded skill-name branches or arbitrary target IDs. Start with one
data-defined stock-conversion action usable by player and NPC; verify mana,
material and time costs plus whole-action rollback and registry checkpoint
replay. The current Process sidecar is not yet this game-facing bridge. Expand
to the remaining operators and all ten contract scenarios only after that
bounded integration passes independent review.

## Final Main Acceptance

After both workers were closed, Main ran the complete frozen regression:

```powershell
$env:PYTHONPATH='src'
$env:PYTHONDONTWRITEBYTECODE='1'
python -m pytest -q -ra -p no:cacheprovider `
  tests `
  experiments/generative_mechanics/next_tracks_v06/tests `
  experiments/generative_mechanics/next_tracks_v06/gameplay_v04/tests `
  examples/pmw_alpha/tests examples/storm_relay/tests
```

**719 passed, 3,141 subtests passed in 373.46s (0:06:13)**. Exit code 0.
Start 2026-10-29 10:18:25, finish 10:24:40 Asia/Shanghai. All 269 recorded
Python source/test hashes were unchanged during the run. Evidence:
`evidence/p1_ecology_frozen_full_regression.txt` and
`evidence/p1_ecology_full_regression_meta.json`.

Acceptance combines source review, independent frozen QA, the genuine red
counterexample, actual unique-rule before/after probe, and frozen full green
regression. The owner-test contradiction and QA draft expiry correction are
resolved; their review history remains. No Engine, runtime, clock, global
configuration, gameplay transaction or save schema change. No remote push.
Local checkpoint subject: `fix: select live ecology dynamics curves`.

This closes only the baseline-curve mismatch. Seven-Operator game access,
typed Stock/Process Action/material/Registry bridge, full execution budgets,
and all ten integrated P1 scenarios remain open. No P2/P3 generation gate was
passed or bypassed. Costs are selected per turn/child and recorded separately
from bootstrap in `COST_LEDGER.md`.
