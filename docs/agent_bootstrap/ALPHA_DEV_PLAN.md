# Alpha Development Plan

基线：`feature/alpha-v02-seventh-night`, commit
`1433e957d5391b880b71e92da4b5cf2ebd9751cd`。总参考预算上限 ¥2,000。

## Stage Gates

| Stage | Budget CNY | Acceptance | Status |
| --- | ---: | --- | --- |
| P0 | 100 | evidence-backed audit, module boundaries, concrete tasks | accepted: 644 baseline tests |
| P1 | 400 | all ten formal Engine mechanism scenarios | not accepted |
| P2 | 350 | versioned IR, one compiler/runtime, 30 reference skills and adversarial/replay gates | not started |
| P3 | 200 | 200-500 real DS Flash candidates and behavior-based evaluation | not started |
| P4 | 400 | playable two-area generated-skill slice, three strategy types | not started |
| P5 | 400 | playtest-driven bounded iteration | not started |
| Reserve | 150 | regression, recovery and delivery | reserved |

## Ordered Work Queue

1. P0: run baseline core/v06/Gameplay/Alpha/M0 suites and formal v06 demos;
   record Windows environment failures separately from mechanics defects.
2. P1.1 (bounded increment accepted): explicit no-recovery Field mode in the EXISTING Gameplay dynamics
   language; verify curves, expiry stacking, save/load and zero implicit
   diffusion. No new Tick or Engine rewrite.
3. P1.2 (trusted sidecar accepted; game bridge open): trusted generic Stock/Process catalog and conservative conversion
   lowering into Gameplay's world-tick event. Scale input/output together;
   reject capacity overflow, forbidden sources and competing resource writers.
4. Accepted: fix the audited Alpha stale-time/flag-only-route defects through existing
   Gameplay clock and real PMW Relation Laws; preserve current game outcomes.
5. Accepted 2026-10-29: ecology baseline-curve dispatch uses live state with
   canonical formula IDs; 719 full tests and 3,141 subtests passed. The bounded
   P1.3 slice is now accepted: typed Stock/Process start through existing staged
   Action/material authority with player/NPC, mana/time, rollback and registry
   checkpoint replay; 742 tests/3,141 subtests pass. The subsequent bounded
   rate/remaining-duration Process modification bridge is also accepted:
   759 tests/3,152 subtests, exact Law/expiry confirmation and independent QA.
   Pause/resume/progress writes are not part of this Skill language slice.
   C1 repairs the verified native rate-only hard-deadline rejection and genuine
   optional-parameter schema gap: 776/3,180, 276 immutable hashes, real timed
   player/NPC proof. Next: C2 finite Stock-fed Field drive, then bridge remaining
   catalog operators into Action/Registry;
   reuse material capabilities and topology validator, add bounded event/query
   budgets and lifecycle ownership. Run all ten scenarios including player/NPC.
6. P2: versioned multi-trigger IR, typed conditions and bounded selectors;
   schema/capability/budget checks, 30 data-only reference skills, replay tests.
7. P3: external Flash generator with bounded repairs/timeouts, authorized
   context, normalized hashes and behavioral deduplication; no hidden answers.
8. P4: Alpha crafting preview/registration/save/play loop; preserve old playable
   slice while adding verified language. API failure leaves resources untouched.
9. P5: prioritize actual normal-entry playtest failures, not extra templates.

Blind P0 public-entry playtest used 19 actions and reached forest restoration,
not a completed game. Prioritize clear rule revelations and visible pending/
completed world-change feedback; slot labels may legitimately be one-based
display for zero-based API and require clarity, not automatic renumbering.

## Iteration Discipline

Each iteration records target, acceptance, risk, file ownership, tests, review,
checkpoint, ledger and next independent task. Same bug failing two fixes returns
to GPT root-cause analysis. Three ineffective iterations stop that direction.
Never delete tests, bypass validation or modify victory flags to pass gates.
No remote pushes or global Codex/Magpie configuration changes are required.

Checkpoint verification: latest frozen full regression **776 passed, 3,180
subtests passed in 407.04s**, all 276 Python hashes unchanged (previous
checkpoint: 759/3,152). P0 accepted;
only bounded P1 increments accepted, not the
full ten-scenario gate. No generation batch or P2 reference corpus was started.

Current playable startup (PowerShell, repository root):

```powershell
$env:PYTHONPATH = 'src'
python -m examples.pmw_alpha.server --port 8020
```

This starts the EXISTING Alpha, not the future P4 generated-skill slice.
