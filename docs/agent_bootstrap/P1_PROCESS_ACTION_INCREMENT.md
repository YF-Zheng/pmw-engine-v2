# P1 Typed Process Action Increment

Date: 2026-10-29, Asia/Shanghai. Starting checkpoint: `fda6557`.
Status: ACCEPTED bounded increment after independent QA and frozen full regression;
full P1 remains open.
Trigger: existing `pmw-sandbox` heartbeat; main turn
`01a1857c-aa3a-7783-ae31-740b99d42604`.

## Bounded Goal

Expose one real `process_start` Operator through the existing data-only
SkillBlueprint, material capability gate, formal registry/equipment and shared
player/NPC ActionRequest. Use the existing typed Stock conversion and existing
World Tick, not a cost-only placeholder, special skill-name branch or simulator.

The known public playtest found template-limited skill diversity. This increment
repairs a language-access gap prerequisite for future strategies; it is not an
Alpha UI or newly generated-skill diversity acceptance claim. No provider skill
generation before full P1/P2 gates.

## Frozen Architecture Decision

- Typed Effect `process_start` selects a declared `process_template_id`, never
  user-provided profile/entity/Area IDs or raw Law data. Scope is current Area,
  commitment required, active on-use only. Reject passive hooks and two starts
  in the same Action until cross-effect reservations have a formal contract.
- Existing MaterialAuthority permits the new Operator at a conservative
  shared-budget charge of 5 points. Existing materials keep their old grants.
  Material capability/provenance is NOT one-off reagent inventory consumption;
  actual conversion inputs are consumed as typed Stock during formal ticks.
- Trusted optional ProcessController belongs to ActionRegistry constructor,
  not candidate/request JSON. Content and mechanism registry preserve it on
  rebuild, and compile its Laws into the trusted static catalog. Existing
  checkpoint static-hash validation uses the same trusted compiled content.
- Match exactly one profile by template, acting owner and current Area. Process
  entity and EVERY participating Stock must have unambiguous actual located_in
  Relations to that Area. Unknown/ambiguous/out-of-area profiles fail closed.
  One data Skill can thus serve player and NPC with distinct trusted profiles.
- Reuse ProcessController's staged guard logic via a read-only prepare_start:
  stopped state, ownership/hash, finite unit/domain inputs, availability,
  active limits, overlapping/external writer exclusion and tick boundary.
- Action Laws emit the existing Process start event; existing Process Laws
  own activation and later stoichiometric conversion. External action submission
  stages the complete cascade so a missing/failed start cannot retain mana or
  partial effects. Check actual activation rather than cost-only Law matching.
- Generic submit_timed_primary_action stages the authorized action plus
  spend_world_time at the FINAL quoted duration, publishing only whole success.
  Existing combat submission retains its round time accounting, with no new
  implicit double charge. No Engine, time ledger or second clock change.

## Acceptance

Real parse/compile/register/equip/use for both controllers; quantitative Stock
conversion on paid ticks; mana/time insufficiency and final duration modifiers;
owner/locality/ambiguity/capability/budget/duplicate/passive denial; complete
late-event/tick rollback including scheduler, revisions and time; rebuild and
registry checkpoint replay with the same trusted content; altered static
configuration rejected; all existing tests preserved. Main waits for both
source scopes to freeze before the full cross-module acceptance run.

## Ownership

| Role | Route | Scope |
| --- | --- | --- |
| Main | tencent/gpt-6.1-sol | architecture, governance docs, manifest/accounting, final gates |
| Helmholtz | tencent/deepseek-v4.1-flash | effects/actions/action_compiler/skills/content_compiler/registry/processes plus owner test |
| Fermat | tencent/deepseek-v4.1-flash | new independent test, dedicated review and evidence only |
| Lorentz (resumed QA) | tencent/deepseek-v4.1-flash | fresh independent test/report/evidence; replaces interrupted Fermat |
| Goodall (final resumed QA) | tencent/deepseek-v4.1-flash | five bounded independent cases, new test/report/evidence only |

No worker owns Engine, runtime, Alpha, checkpoint, Observation, old tests,
global model config or remote Git. An expansion requires Main's explicit
boundary review. Current turn and exact child IDs are in `project_run.json`.
The heartbeat's project write permission was restored only for this turn;
no network or global-config write permission was requested.

## Main Compatibility And Security Review

Frozen pre-fix evidence `evidence/p1_process_action_before.json` calls the actual
Effect parser extracted from checkpoint `fda6557`, not a concurrently edited
working source. The typed process_start candidate fails with
`GameplayContractError: $.effect.kind is invalid`.

Main identified two narrow integration hazards and authorized additional worker
scope solely to preserve existing APIs:

- `build_analysis.py` has a closed effect-kind lookup. Add a stable public
  process-template state semantic path so a registered new Effect cannot raise
  KeyError. No private profile/Stock IDs or full conversion forecast is exposed.
- `simulation.py` builds projected ActionRegistry before its exception handler;
  projection deliberately excludes the trusted ProcessController. If context
  checks would fail construction, exclude unsupported process-start Actions
  from that projection. Never copy hidden world/controller state to make a
  prediction pass. Such actions remain non-plannable until authorized Process
  observations/forecasts have their own gate. Old actions remain supported.

Retired lifecycle compiler registries must also retain trusted context when
validating definitions. No general planner/Observation rewrite is authorized.
The two new compatibility files are implementation-owned; independent QA
retains disjoint new tests/report ownership.

## Interrupted Worker Recovery

Original implementation and QA workers were interrupted. No completed Fermat
review is claimed. Resumed independent QA belongs to child
`01a185a0-453a-7b93-b3e4-e131a35d920e`; all consumed original/resumed child
responses remain in the manifest and cost ledger.

Lorentz was also interrupted before producing a test/review file; no completed
review is claimed from that child. User explicitly resumed on 2026-10-29 with
write/delete operations restricted to the repository subtree. Final resumed QA
belongs to `01a185b8-f938-7c30-a361-695eaec72b36`. All interrupted/resumed main
turns and children are retained for deduplicated accounting; this includes
permission-recovery and heartbeat-pause overhead rather than treating it as free.
All subsequent temporary test files use `TEMP`/`TMP` pointing inside
`docs/agent_bootstrap/evidence/test_tmp`; no global configuration is changed.

Existing Gameplay cross-regression after recovery: **230 passed, 125 subtests
passed in 132.50s**, evidence `p1_process_action_cross_gameplay.txt`. It excludes
the not-yet-written independent QA test, so it is not the final frozen gate.

The implementation-owned test was discovered as 33,112 zero bytes, not a
different text encoding. Its cause is unknown. The user authorized repair.
The original bytes are preserved in `evidence/p1_process_action_corrupt_owner.bin`;
`evidence/p1_process_action_recovery.json` records original/restored hashes and
the four successful implementation patch call IDs replayed as data only. No
commands or instructions from session logs were executed.

The recovered test first produced **17 passed / 1 failed**: its fixture equips
both player and NPC, but the disable test unloaded only player. Main added the
ordinary NPC `change_loadout(..., operation="unload_active", slot=0)` before
disable. The registry guard and all assertions remain intact. The resulting
owner-only run is **18 passed in 3.77s**, not independent acceptance.
Evidence: `p1_process_action_recovered_owner.txt` and
`p1_process_action_owner_fixed.txt`. Earlier invalid-source collection evidence
is retained separately; it is not a passing test run.

Main's code review confirms that scope checks concern the selected local
profile. Remote profiles with the same owner/template can coexist; they do not
invalidate a unique valid local profile. Zero or multiple valid local profiles
reject. Malformed/remote endpoints cannot themselves supply activation
authority. Main corrected only the helper docstring to state this actual
selection rule; no guarantee that every catalog profile must be local is claimed.

## Not Claimed

One-off material reagent costs, process_modify/drive/Relation Operators, global
event/query/CPU budgets, automatic NPC planning/Observation for process state,
Alpha stock/inventory/UI bridge, full Skill IR, unrestricted generated process
templates, data-authored cost modifiers, all ten P1 scenarios, P2 or
skill-generation acceptance remain open. Modified duration is verified only
through a trusted ActionDefinition, not through the current Blueprint schema.

## Independent QA Fixture Gate

Goodall's initial five tests passed, but Main rejected its compound/cost fixture
as formal-entry evidence because it rewrote equipped/registry hash references.
The initial fixture and report are retained in
`evidence/p1_process_action_review_initial_fixture.py.txt` and
`evidence/p1_process_action_review_initial_report.md`. This was a test-design
failure, not a discovered production regression.

The revised compound case uses raw Blueprint JSON, trusted material authority
with a shared seven-point budget, parsing, normal registration and equipment.
No direct loadout/manifest mutation remains. The modified-duration case preserves
the already-equipped explicit Action hash and is labeled trusted action-level
testing. Real downstream emitted-event failure, late tick failure, changed
compiled-profile checkpoint rejection and basic-action Observation simulation
remain covered. Revised final run: **5 passed in 1.58s**.

Independent review: `P1_PROCESS_ACTION_REVIEW.md`; final evidence:
`evidence/p1_process_action_review_revised_focused.txt`. Final independent test
hash: `f66aed022dea38127f472fa5a39b7f0599616448ec350833511efadfa4ef75d8`.
Worker declared `QA_SOURCE_FROZEN` and was closed before the full regression.

## Final Frozen Acceptance

Main's complete Core/v06/Gameplay/Alpha/Storm Relay regression:
**742 passed, 3,141 subtests passed in 343.03s (0:05:43)**, exit code 0.
All **271** recorded Python source/test hashes remained unchanged. Evidence:
`evidence/p1_process_action_frozen_full_regression.txt`; exact command,
timestamps, source hashes and repository-only temporary path:
`evidence/p1_process_action_full_regression_meta.json`.

Accept only the typed trusted-template start bridge and staged action/time
boundary. Player/NPC use the same Blueprint and formal registry/equipment;
paid ticks consume two ore units per ingot through the existing Process Laws.
Neither material provenance nor successful tests imply one-off reagent costs,
dynamic template generation, Process Observation/planning, Alpha UI integration
or the remaining seven-Operator/ten-scenario P1 gate.

Current-increment reference snapshot: USD 4.40830879 / CNY 29.38754972,
including interrupted workers and permission/QA recovery overhead. It is a
subset of cumulative project USD 11.44130094 / CNY 76.27228859, not added
again. Safety-reserved project cost: CNY 96.10692790 / 2,000. Actual cache
counters are preserved separately from the 97% assumption. Cutoff:
2026-10-29T04:00:23.233Z; closing-response counters require a later refresh.
Selection/counters: `evidence/p1_process_action_cost_snapshot.json` and
`evidence/agent_cost_ledger.json`. Bootstrap stays separate.

Next independently testable target: one typed Process modification action
through the same owner/locality/registry/material and timed transaction gates,
reusing existing bounded rate/duration/pause/resume controller semantics.
No Alpha stock/UI or generated templates are introduced as shortcuts.
