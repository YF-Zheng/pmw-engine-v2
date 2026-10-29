# P1 Typed Process Modification Increment

Date: 2026-10-29, Asia/Shanghai. Starting checkpoint: `14cf16d`, clean
worktree at entry. Status: IN PROGRESS; full P1 remains open.

## Target And Existing Evidence

Expose bounded rate and remaining-duration modification of an already-running
trusted Process through the existing material/SkillBlueprint/Registry/Action
path shared by player/NPC. The prior public playtest found template-limited
skill diversity; this is another language-access prerequisite, not an Alpha UI
or new strategic-diversity acceptance claim. Current formal Effect parser
rejects process_modify with `GameplayContractError: $.effect.kind is invalid`;
real pre-edit evidence is `evidence/p1_process_modify_before.json`.

## Frozen Scope

- Effect kind `process_modify`, required commitment, current_area, active
  on_use only, no attribute/targeting bypass. Fields: process_template_id,
  optional process_rate and process_remaining_ticks; at least one required.
  Rate is finite positive non-bool; remaining ticks are positive integer
  non-bool. Runtime trusted template bounds and hard deadline are authoritative.
- Resolve exactly one fully local profile matching template and acting owner,
  using the accepted Process/Stock endpoint locality helper. Running state,
  input unit/domain/availability, writer exclusion and completed Tick boundary
  come from existing controller checks. Paused/stopped/expired are rejected.
- Conservative material capability/budget charge: five points per modification.
  At most one Process control operation (start OR modify) per Action, including
  mixed operations. Preserve the existing two-start rejection and old tests.
- Add a read-only prepare_modify which shares the existing controller's exact
  calculation/preflight with privileged modify. Do not duplicate time/deadline,
  progress or scheduler semantics in a separate simulator.
- Action compiler emits the existing PROCESS_MODIFY_EVENT with the prepared
  trusted before/after values; existing Process Laws own all writes and expiry
  rescheduling. Never invoke controller.modify during effect simulation.
- Confirm exact corresponding modification Law/cascade, actual component
  updates and expiry schedule, not just mana payment. Existing staged primary
  and timed submission own complete failure rollback and final quoted time.
- Public build semantics may expose template configuration only. Exclude both
  Process control kinds from actor-safe simulation until an authorized Process
  Observation/forecast gate exists; never copy hidden profiles or Stock data.

## Disjoint Ownership

Implementation worker: effects.py, actions.py, action_compiler.py, skills.py,
processes.py, build_analysis.py, simulation.py and new
tests/test_sandbox_process_modify.py only, all under gameplay_v04.

Independent QA worker: new tests/test_sandbox_process_modify_review.py,
docs/agent_bootstrap/P1_PROCESS_MODIFY_REVIEW.md and
evidence/p1_process_modify_review* only. Main owns architecture/source review,
status/spec/plan/QA/accounting documents and final frozen regression/checkpoint.
Actual main/child IDs and stages are recorded in project_run.json.

- Main turn: `01a185ea-111c-7ec1-a028-48c2a86e82d8`.
- Implementation: `01a185ed-22f2-7db0-b56b-c6b3f1e87508` (Planck).
- Independent QA: `01a185ed-76c5-79b0-8351-2fa4ff4f9a37` (Beauvoir).

No Engine/runtime/time-ledger/checkpoint/Observation/Alpha/old-test edits, global
configuration writes, remote pushes or game-generation provider calls. All
temporary paths and Git metadata must remain inside pmw-engine-v2.

## Acceptance

Normal parsed/registered/equipped start followed by modification for player/NPC;
quantitative subsequent Stock conversion, exact remaining-time/expiry behavior,
shortening and bounded extension without resetting hard deadline; mana/time,
owner/locality/ambiguity, numeric/state/writer/capability/budget denials; mixed
control rejection; real late event/tick rollback of state/scheduler/revisions/
stats; missing modification Law rejection; checkpoint continuation and changed
trusted static profile rejection; existing basic-action projection still works.
Keep every old assertion. Freeze both source/test scopes, then run the complete
Core/v06/Gameplay/Alpha/M0 regression before bounded acceptance.

## Not Claimed

Pause/resume/progress-write Operators, stopped Process restart, dynamic template
creation, reagent inventory debit, Process Observation/NPC planning, Alpha
stock/UI, drive/Relation bridges, full IR/global budgets, all ten P1 scenarios,
P2 or game-generation acceptance remain open. One increment does not close P1.

## Native Saturation Limitation

Main executed the accepted `14cf16d` _modify_process function extracted from
Git against a detached trusted fixture with initially full output Stock,
normal equipped start and a real saturated world tick. At wall time 1 the
running Process still stores remaining 3 / elapsed 0. A rate-only update to
1.5 rejects `Process duration cannot extend the hard deadline`, even though
it does not intend to change the existing expiry at 3. World state is retained.
Evidence: `evidence/p1_process_modify_saturation_baseline.json`.

This pre-existing controller limitation is not a new Action regression and
does not weaken hard-deadline tests. Factoring prepare_modify preserves native
semantics; this slice does not claim rate modification in every saturated
state. Conversion progress versus wall-clock remaining time needs its own
versioned policy/ordering review, rather than a silent broad repair here.

## Final Bounded Acceptance

ACCEPTED on 2026-10-29, starting checkpoint `14cf16d`. Both DeepSeek workers
are closed. Main's current context remains `tencent/gpt-6.1-sol`; actual child
contexts and per-response usage identify `tencent/deepseek-v4.1-flash`.
Attribution evidence: `evidence/p1_process_modify_route_attribution.json`.
No model identity prose, label-only proof or global configuration rewrite.

The original parser rejection above is now replaced by data-only rate and/or
remaining-duration Effects through existing material capability/budget,
Registry/equipment, owner/locality, shared player/NPC Action and timed staging.
Read-only preparation is shared with native modify; existing Process Laws and
scheduler own all mutations. Main rejected the initial suffix-only .modify Law
check. The frozen version confirms the exact profile modification Law,
component after-values and scheduled expiry; independent spoof QA checks it.

| Gate | Actual result | Evidence |
| --- | --- | --- |
| Owner new suite | 11 passed in 2.40s; QA rerun 11 passed in 2.30s | worker counters/report; independent review |
| Existing native controller | 11 passed in 0.40s | implementation review |
| Existing start Action | 18 passed in 2.95s | implementation review |
| Main focused cross-regression | 42 passed / 80 subtests in 7.45s | p1_process_modify_main_focused.txt |
| Independent frozen final | 6 passed / 11 subtests in 1.92s | p1_process_modify_review_final.txt |
| Complete frozen Core/v06/Gameplay/Alpha/M0 | 759 passed / 3,152 subtests in 332.41s | p1_process_modify_frozen_full_regression.txt |

Full run exit code 0. All 273 Python hashes match before/after; no Python paths
were added while running. Start/finish UTC, exact command and all hashes are in
`evidence/p1_process_modify_full_regression_meta.json`. The initial
`p1_process_modify_implementation_frozen.json` records pending QA at its earlier
freeze point, not current acceptance. The full metadata freezes all seven
implementation files and both new test files.
Raw pytest logs retain original Windows CRLF/traceback whitespace. Staged code,
test, report and JSON whitespace checks pass; raw log warnings and byte hashes
are recorded separately in `p1_process_modify_precommit_verification.json`.

Owner helpers partly use privileged native start, so owner green results are
supporting lower-level coverage only. Independent positive cases use a cold
trusted initial catalog, distinct parsed Skills, normal equipment, formal
start/modify Actions and real paid ticks. The trusted 2 ore -> 1 ingot conversion
produces player 5 ore / 2.5 ingot and NPC 4 ore / 3 ingot at the checked boundary.
Shorten/extend, fixed deadline, exact expiry, real downstream-event and late-tick
rollback, checkpoint continuation/static-profile rejection and private
Observation projection are checked. Basic wait still works in projection.
Checkpoint QA also introduces inert entities as a trusted fixture perturbation;
it does not prove dynamic Process template or Skill generation support.

Earlier red QA drafts retain fixture/version, ambiguous-start, mixed-shape,
property and incorrect conservation-oracle failures. Main root-caused them;
final QA does not weaken production guards or alter old tests. Independent
source is frozen; Main corrected only its report's fixture count to five parsed
modifiers (plus start), matching the actual test. No source/test edits follow
the complete frozen regression.

## Reproduce

From the repository root, with all temporary paths inside PMW:

```powershell
$env:PYTHONPATH='src'
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTHONIOENCODING='utf-8'
$env:TEMP=Join-Path (Get-Location) 'docs/agent_bootstrap/evidence/test_tmp'
$env:TMP=$env:TEMP
$env:TMPDIR=$env:TEMP
python -m pytest -q -ra -p no:cacheprovider `
  tests `
  experiments/generative_mechanics/next_tracks_v06/tests `
  experiments/generative_mechanics/next_tracks_v06/gameplay_v04/tests `
  examples/pmw_alpha/tests examples/storm_relay/tests
.\tools\refresh_cost_ledger.ps1 -CheckBudget
```

## Accounting And Checkpoint

Exact current-increment main turns and two actual child IDs, separate GPT/Flash
actual input/cache/output/reasoning counters and per-response reference prices:
`evidence/p1_process_modify_cost_snapshot.json`. The subset is already charged
once in cumulative `evidence/agent_cost_ledger.json`; never add it again.
Historical QA fixture repairs and this manual continuation are charged.
Observed cutoff: `2026-10-29T05:29:13.804Z` (13:29:13 Asia/Shanghai).

| Family | Responses | Actual input | Actual cache | Actual output | Reasoning (included) | Reference USD |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| GPT | 65 | 10,002,870 | 9,597,170 | 64,014 | 33,575 | 2.21059064 |
| DeepSeek Flash | 280 | 42,560,721 | 41,320,576 | 232,543 | 76,516 | 0.90980146 |
| Unknown | 0 | 0 | 0 | 0 | 0 | N/A (no records) |

Current increment subset: USD 3.12039210 / CNY 20.80178190. Project cumulative:
USD 14.88522230 / CNY 99.23084594, safety-reserved CNY 125.03586732 out of
2,000; all stage budget gates pass. This subset is NOT added to that cumulative
total again. Separate Bootstrap USD 0.35971320 / CNY 2.39799208 stays excluded.
Prices/FX stay pinned to the verified 2026-10-28 official-reference sources in
COST_LEDGER.md; this is not a fresh quote or actual intranet invoice. The 97%
cache assumption affects only estimated price, never actual cache counts.
Observed cutoff excludes not-yet-finalized closing responses; refresh them on
the next continuation before spending. Unknown/incomplete accounting fails
closed; Bootstrap remains separate. COST_LEDGER.md holds the latest snapshot.

Reviewed local checkpoint subject:
`feat: bridge bounded process modification through staged actions`.
Resolve its ID with git log; no push or external/global configuration changes.
Automatic execution remains paused, and the authorized run cutoff remains
2026-10-29 20:10 Asia/Shanghai. No additional development target is started
during this acceptance/closure step.

## Next Independent Target

Narrow rate-only hard-deadline false-rejection repair after saturated ticks.
Freeze productive-progress versus wall-clock semantics first. Retain actual
expiry and hard deadline when duration is unchanged; add native and formal
Skill/paid-tick regressions with full rollback. Do not reset progress, extend
lifetime, change Tick ordering or create a second clock as an incidental fix.
Then continue remaining Operator/global-budget/ten-scenario gates. Full P1/P2,
Alpha generated-skill UI and game-generation provider calls remain blocked by
their acceptance gates, not claimed complete from this increment.
