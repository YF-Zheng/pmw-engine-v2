# C2 Finite Stock-To-Field Source Increment

Status: ACCEPTED FOR BOUNDED C2. Reviewed starting checkpoint a4ad912.
Branch feature/alpha-v02-seventh-night. Continuous run stays in this chat;
the paused heartbeat and global configuration are unchanged.

## Architecture And Protected Boundaries

Trusted immutable DriveProfile binds one preallocated local Drive, finite
typed Stock, existing Area Field, owner, coefficient and positive rate/duration
limits. Candidate Effect data controls only profile ID/rate/duration, through
existing Skill material authorization, registry/equipment and staged paid Action.
Core Event Laws own source conversion; no second clock or authoritative Python
per-tick updater is introduced. Sources run in sorted profile ID order and
expiry T precedes root Tick T. Shared Drive inputs and overlap with configured
Process input/output Stock reject conservatively at content construction.

This scope is only a positive finite source: not sinks/open-system generation,
Stock transfer, universal Field units, full Drive language, Alpha UI, P1 or P2.
Player/NPC quantitative timed evidence, rollback, replay, projection and old
tests are mandatory before acceptance, not inferred from the architecture.

## Main Critical Findings During Implementation

1. Root matches the pre-dynamics state. Filtering child emission by pre-state
   headroom skips replenishment when a previously full Field recovers downward
   before the child. Move conversion viability into the after-root child and
   independently test full-before/recovery/source/debit ordering.
2. Represented floating changes must be paired. Huge Stock/tiny rate can yield
   apparent Field gain with unchanged fuel, while high Field/tiny rate can
   consume fuel with unchanged Field. Conservatively no-op unrepresentable
   pairs; test these cases independently and ordinary coefficient scaling.
3. A make_content(materials=...) extension and skill-material-set equality
   were not required C2 functionality. Main requested removal rather than
   widening production API to satisfy a new review fixture.
4. Review fixture assumptions (duration4 budget5.1 instead of>=5.4, whole-rate
   rather than partial fuel scaling, nonexistent keyword/positional APIs)
   must be corrected and distinguished from genuine production findings.

Intermediate import/fixture failures are preserved in c2_drive_review*.log.
They are not accepted behavioral evidence or a fabricated gate pass.

## Provenance And Pending Gate

Main session 01a181f1-8fad-7161-a01f-04678ebd7df0, continuous turn
01a1862b-a31c-7351-ac83-5a77abdf3769: actual rollout model tencent/gpt-6.1-sol.
Implementation Maxwell: 01a18662-9a71-74e0-aef5-69c6cbab991d.
Independent QA Schrodinger: 01a18663-0625-7c61-b1da-3dd878a44cca.
Both actual turn_context models are tencent/deepseek-v4.1-flash. Actual IDs
are registered P1 for per-response accounting, not attributed from identity
prose. Main observed 87 tracked test files unchanged from a4ad912 before
freeze; final all-source before/after hashes still pending.

Acceptance remains pending source freeze, owner focused tests, independent
timed/scaling/order/numeric/rollback/replay review, Main source review, complete
frozen Core/v06/Gameplay/Alpha/M0 regression, verified cost snapshot and explicit
local checkpoint. No old test, Engine, clock, Observation or Alpha source
change is authorized. Once accepted, proceed directly to C3 without ending
the continuous run after this increment.

## Frozen Focused Results And Integrity Notes

Both workers are now frozen/closed. Owner suite11/7 subtests, Main cross-Process
focus53/30 subtests, independent six methods in2.459s all pass. Main's first
focused command chose two nonexistent test paths: exit4/no tests ran, retained
in c2_drive_main_focus.txt. Corrected real paths pass in
c2_drive_main_focus_retry.txt; do not relabel the path error as a product failure.
Main source review/hashes: c2_drive_main_source_review.json. Independent final
test SHA256561ece5cb6f7a53a2d9aafafd7058e72cde43250229b361705acf1cd939d5b8a.

Main clarifies the independent report's wording without modifying its frozen
test/report: the formal player/NPC fixtures equip separate equivalent parsed
Skills bound to their distinct owned profiles, not a single same-ID Skill that
can select both owners. They use the same parser/registry/timed Action path.
Its after-root probe activates below capacity, fills the Field, and verifies
that the NEXT full-before Tick still recovers and sources after root dynamics.
The report's NaN/Infinity coverage wording is broader than its rate mutation
list; Main's c2_drive_main_denials.json separately confirms nonfinite/zero/
negative parsing and pure-native unknown-profile/duration/owner denials (eight
rejecting probes). These are complementary, not additional formal timed proof.

Full regression started with279 Python files frozen; no production/test edits
or new coding worker may run during it. Result remains pending until metadata
reports exit0 and every before/after hash agrees.

## C2 Accounting Cutoff

Actual per-response snapshot: evidence/c2_cost_snapshot.json, observed cutoff
2026-10-29T07:22:10.040Z (15:22 local). C2 ordinal/child subset USD2.72178455 /
CNY18.14450452 is ALREADY included in project cumulative USD20.92559077 /
CNY139.49835831; never add the subset again. Safety-reserved CNY175.77496247 /
2000, P1 reserve138.12502981 /400. Complete observed accounting; Unknown0,
malformed0. Actual cache counters remain untouched, 97% only reference-price
assumption; official price/FX sources remain pinned to verified2026-10-28.
Bootstrap is separate. Source-ordinal boundary allocates shared closing and
next-item architecture preparation to this capture, not exact semantic task
inference. Closing usage is charged once in the next capture; no future-zero
claim or intranet invoice verification is made.

## Final Frozen Acceptance

C2 bounded finite Stock-to-Field source is ACCEPTED: frozen full regression793 passed/3,195 subtests in388.43s, exit0, all279 Python hashes unchanged. Owner11/7, independent6 methods, Main focused53/30 and complementary8 denials pass. Reports: C2_STOCK_FIELD_DRIVE_INCREMENT.md / C2_STOCK_FIELD_DRIVE_REVIEW.md; complete metadata/log: evidence/c2_drive_frozen_full_regression_meta.json / c2_drive_frozen_full_regression.txt. Existing clock, Engine, staged Action, Observation, Alpha and all87 tracked test files at a4ad912 remain protected. Positive finite source only; no sinks/open source/universal Field units, Alpha UI, complete P1/P2 or generation claim. Local checkpoint subject: feat: add bounded stock-fed field sources. Next independent task C3_RELATION_MODIFIER_DESIGN.md, then C4_CONDITION_BUDGET_DESIGN.md and remaining P1 gates.

The pending language in earlier sections records the actual sequence; this final section supersedes the pending execution state only. All workers were closed before full regression. No generation, global configuration, push or Alpha UI change occurred.
