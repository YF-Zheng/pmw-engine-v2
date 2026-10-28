# PMW Generative Sandbox Project Status

日期：2026-10-28。契约：`DEVELOPMENT_CONTRACT.md`。
工作分支：`feature/alpha-v02-seventh-night`。
最后已验证旧版本：`1433e957d5391b880b71e92da4b5cf2ebd9751cd`。

## Gates

- P0 audit/boundary freeze: PASS. 644 baseline tests passed; five formal Engine
  mechanism demos replayed. Full matrix: SANDBOX_CAPABILITY_AUDIT.md.
- P1: bounded no-recovery, Process, cost-tool and Alpha-authority increments
  independently accepted; frozen full regression: 701 passed, 3,130 subtests
  passed in 342.67s. Full P1 NOT accepted. Existing mechanisms cannot yet
  all be authored as one generated Alpha skill. Ten scenarios are the full gate.
- P2-P5: not started/accepted. No 30-skill IR corpus or 200-500 generated batch.
- Existing Alpha playable baseline retained. No remote push/global config edit.

## Current Iteration

Goal: restore missing generic semantics without touching the frozen Core or
introducing a second clock, and fix real Alpha state-authority mismatches.

| Worker | Route | Owned scope | Acceptance |
| --- | --- | --- | --- |
| Main architecture/review | tencent/gpt-6.1-sol | combined docs, gate/review | source/test evidence, honest limits |
| Euler | tencent/deepseek-v4.1-flash | Alpha session/content/authority tests | topology and displayed time agree with real PMW state |
| Ramanujan | tencent/deepseek-v4.1-flash | Gameplay no-recovery contracts/laws/new tests | none/linear/squared parity, expiry/replay |
| Kierkegaard | tencent/deepseek-v4.1-flash | new Gameplay Process compiler/new tests | bounded stock conversion on existing clock; no arbitrary code |
| Turing | tencent/deepseek-v4.1-flash | cost CLI and isolated tests | actual counters preserved, dedupe/Unknown/fail-closed |
| Raman | tencent/deepseek-v4.1-flash | baseline QA evidence | 644 tests passed before P1 changes |
| Hume | tencent/deepseek-v4.1-flash | public-entry blind playtest evidence | no hidden state/source, <=20 public actions |

The previous bootstrap main was DeepSeek Pro. The current user turn's
`turn_context.model` is **tencent/gpt-6.1-sol**; model labels/self-description
are not routing proof. Cost tooling reads per-response session counter/model
records to verify these main/child routes. Bootstrap expenses stay separate.

## Known Issues And Risks

1. FIXED in this bounded increment: Alpha route availability reads actual
   adjacent Relations created through trusted Laws/staged commands. Flags
   alone no longer authorize travel; this is not a generic Skill IR bridge.
2. FIXED in this bounded increment: Alpha displays completed Gameplay steps,
   including per-tick log rows, not scheduler-root `WorldState.tick`.
3. Pre-inspection hints disclose exact mechanics. Existing tests deliberately
   demand actionable leads; needs a separate knowledge/UX policy iteration,
   not removing assertions in this patch.
4. Core Event cascades can partially commit before later failure. Full action
   safety must use existing Gameplay staging. Bare runtime remains privileged.
5. Current SkillBlueprint omits Process/Relation/drive and multi-trigger IR.
6. New generic Process increment needs a verified Action/Registry/Alpha stock
   bridge before generated skills can use it. Reference prices are estimates,
   not verified provider account bills.
7. Independent QA rejected the first no-recovery patch for formal domain-clamp
   and ecology zero-rate-policy gaps (first combined run 2 failed/691 passed).
   Narrow repairs are now independently accepted. Negative Process rate and
   forged shared-writer gaps are also guarded and covered by unchanged
   independent assertions. Final frozen full regression passed; intermediate
   failed-run evidence is retained in ALPHA_QA_REPORT.md.
8. Older ecology baseline-curve transitions are not reflected by cached Field
   profiles/Law base variants. Fix this before the full P1 dynamics gate.
9. Alpha topology save schema changes require an explicit compatibility decision;
   this increment rejects v0.2 saves rather than inventing links from flags.
10. Process controller preflight scans entity maps for active/writer checks;
    formal tick remains existing Law execution, but constant-work action
    validation is not established. Full P1 budgets/locality gates remain open.

## Recovery

Current reviewed checkpoint: the local commit with subject
`feat: checkpoint audited P1 sandbox increments` (resolve with `git log -1`).
It includes the accepted bounded increments and final regression evidence, not
full P1 acceptance. No remote push. Next independent task: repair the older
ecology baseline-curve/compiled-profile mismatch with a real formal-tick
regression, then continue the seven-Operator Action/material/Registry bridge.

Read status, audit, QA, spec, cost ledger and `project_run.json` first. The run
manifest holds the exact managed main/child/turn IDs and task-stage assignments;
append resumed turns/children before refreshing costs. Run focused tests for the
current increment, then cross-module regressions. Do not assume a started worker
or written feature has passed independent review. Do not discard dirty changes.
Accept a checkpoint only after review/tests; next work remains P1 integration,
not P3 generation until full P1/P2 gates pass.

## Autonomous Continuation

A real thread heartbeat named **PMW Sandbox 自主迭代** is ACTIVE in Codex
(automation ID `pmw-sandbox`). It resumes this existing chat hourly, skips
concurrent editing, reads checkpoints/ledger first and remains quiet unless
there is a verified milestone, failure or user action. It enforces the stage
gates and safety-adjusted ¥2,000 cap; unknown accounting stops further spend.
The requested one-day run ends at **2026-10-29 20:10 Asia/Shanghai**, or earlier
on user stop/budget exhaustion. Completion pauses the heartbeat and preserves
the final checkpoint. The app/execution host must remain available for runs;
this is not a detached service or a guarantee of uninterrupted execution.
