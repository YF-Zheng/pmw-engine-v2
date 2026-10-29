# Continuous Execution Plan - 2026-10-29

User explicitly requested a long plan followed by consecutive implementation,
not ending the chat after one accepted increment. Repository-only writes,
feature/alpha-v02-seventh-night, no remote push or global configuration change.
Start reviewed checkpoint: 0e4e45b. Main turn:
01a1862b-a31c-7351-ac83-5a77abdf3769 (verified tencent/gpt-6.1-sol).

## Execution Rules

Run one attributable target through architecture -> bounded DeepSeek worker ->
independent review -> focused/cross-module frozen tests -> budget verification
-> local checkpoint, then immediately start the next independent target.
Do not accept unreviewed patches or placeholder/reference-only mechanisms.
P1 and P2 must both pass before any game skill-generation provider request.
Existing Engine, Gameplay clock, Observation, staging, playable Alpha and every
old test remain protected. New workers have explicit disjoint file ownership.
Every actual main turn and child thread enters the per-response cost selection.
Unknown/incomplete accounting stops spending. Cache is actual in evidence and
97% only for reference-cost estimates. Bootstrap remains separate.

Stop on explicit user stop, unrecoverable blocking condition, failed accounting
or stage/MAX budget gate, or the authorized deadline 2026-10-29 20:10 +08:00.
Finish safe regression/delivery near limits. Two failed fixes require Main root
cause review; three ineffective iterations stop that direction. Automatic
heartbeat remains paused; this is continuous work in the current active turn.

## Ordered Work

| Item | Scope and measurable gate | State |
| --- | --- | --- |
| C1 | Fix rate-only Process false rejection and genuine optional-schema defect; native/formal timed player/NPC, rollback/replay; 776 tests/3,180 subtests, 276 immutable hashes | accepted; local checkpoint next |
| C2 | Bounded typed Drive/Source on the existing Gameplay clock, with explicit trusted source/conservation, local authority, duration/ownership and staged Action tests | architecture next |
| C3 | Typed Relation modification using existing topology/lifecycle Laws; endpoint/type/scope/material rejection and actual downstream behavior | queued after C2 |
| C4 | Close remaining P1 Operator/condition/lifecycle/resource-budget gaps; measure event/query/active-instance boundaries; ten formal mechanism scenarios with player/NPC | queued; P1 not accepted |
| C5 | Only after P1: versioned multi-trigger IR/typed selectors/conditions, one compiler/runtime and 30 data-only reference skills with adversarial/replay gates | gated by P1 |
| C6 | Only after P2: real bounded Flash generation/evaluation, then Alpha generated-skill slice and public playtest-driven iteration | gated by P1 and P2 |

This is an ordered queue, not a promise that every stage fits the remaining
day. Gate failures may select a smaller independently valuable repair rather
than pretending a full stage passed. Update the table after every checkpoint;
continue without asking for ordinary engineering choices.

## C1 Frozen Policy

Saturated conversion does not increment productive elapsed or decrement stored
remaining ticks, while wall-clock expiry is unchanged. Rate-only modification
must retain the scheduled future expiry and stored duration/remaining/progress,
then validate that actual expiry against the immutable hard deadline. Explicit
remaining-tick changes still use now + requested remaining and bounded total
duration. No reset, extra production lifetime, new Tick phase or second clock.
Missing/past/duplicate expiry and over-hard-deadline requests reject atomically.
Implementation ownership: processes.py and a new rate-expiry owner test only.
Independent QA owns a distinct new review test/report/evidence only. Main owns
architecture, source review, governance/accounting and frozen full regression.

### C1 Independent Finding And Scope Extension

Independent pure-rate verification exposed a second genuine production defect:
effects.py strict field equality requires both numeric keys despite the
documented rate-or-remaining contract. Original 0e4e45b reproduction in
`evidence/c1_optional_fields_before.json`: rate-only and remaining-only reject,
both accept. Previous passing combined-parameter tests did not establish the
optional-parameter claim. Do not disguise this as a fixture-only error.

Native implementation Lagrange is frozen/closed; its owner tests are supporting
coverage, not sufficient defect reproduction (some profiles retain deadline
slack, and one formal case uses explicit remaining). Russell independently
owns formal pure-rate player/NPC evidence. Linnaeus now exclusively owns
effects.py and new test_sandbox_process_optional_fields.py: correct only required
versus allowed keys for process_modify, retaining unknown/null/type/budget gates
and every other Effect schema. Actual child ID is in project_run.json. No
production scope overlap, no native-only acceptance, no generator calls.
