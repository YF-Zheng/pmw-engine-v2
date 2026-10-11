# PMW Gameplay v0.4 Gate 5.1 Compatibility Report

Status: **PASS**

Baseline: `326d29b4e6887ff257115dbb07e06d984deec1af`  
Protected-tree baseline: `a98ff51561760f87689093c815508fa93120807d`

## Protected scope

The sorted `git ls-tree -r` manifest for `src/pmw` plus
`experiments/generative_mechanics` excluding `next_tracks_v06` is unchanged:

```text
entries: 381
SHA-256: a20fd763cad342ac357a08d94ee96ca42075f215efcbff93c4017b65a8ddd669
```

The baseline and final manifests compare byte-for-byte. The working-tree diff
over those protected paths is empty. PMW Core, old Generative Mechanics,
preregistration, pilot, and formal experiment assets were not modified.

## Public behavior changes

- `run_combat_round()` uses finite formal time by default. Old no-ledger fixtures
  must opt into `time_policy="unbudgeted_fixture"`; that mode cannot bypass a
  real ledger.
- `CombatRoundResult.time_spend_result` exposes the one-Tick combat charge.
- `resolve_harvest()` now includes the complete time/Tick transaction.
  `HarvestOutcome.time_result` replaces a caller-side second time charge.
- Public `resolve_action()` now authorizes equipment. Trusted Hook execution is
  internal and validates the installed Hook/effect bundle.
- Actor WorldState gains bounded shield provenance while preserving the public
  aggregate `actor.shield` value.

All in-repository callers were migrated. The explicit changes close authority
or atomicity bypasses; no compatibility shim silently weakens production rules.

## Save and migration behavior

New checkpoints preserve time budget, receipt relations, status ownership, and
all shield layers. Continuation after Registry checkpoint is state- and
trace-equivalent in the covered scenarios.

At the shared Gameplay attach boundary, a pre-Gate-5.1 Actor missing the shield
component receives an unowned legacy layer equal to its old scalar shield.
Status slots missing `shield_layer_slot` receive `None`. The migration is
idempotent and prevents old active Guard state from erasing unknown shield
provenance. It does not guess unrecoverable historical ownership.

## Regression evidence

```text
PMW Core                 254/254   26.181s
Old Generative Mechanics 345/345   68.362s
v0.6                     170/170   25.745s
Gameplay v0.4            145/145   76.394s
Total                    914/914
```

There were zero failures, errors, skips, or expected failures. Log hashes are
recorded in `GATE51_REPAIR_REPORT.md`. Independent QA passed 10/10 adversarial
tests and is documented in `GATE51_INDEPENDENT_QA_REPORT.md`.

The Gate 5 Demo is byte-identical across two fresh processes with SHA-256
`db9b7877b19c4d664bbf0df4baa8bf7d9182b36d0b36c355705d0b5b868b575b`.
`git diff --check` passes.

No TODO2 collection, benchmark freeze, or TODO3 game production was started.
