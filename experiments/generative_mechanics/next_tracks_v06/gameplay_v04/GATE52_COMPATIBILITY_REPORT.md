# PMW Gameplay v0.4 Gate 5.2 Compatibility Report

Status: **PASS - READY_FOR_FINAL_OWNER_SIGNOFF**

Baseline: `645d82dd926c51094fac8089af1e090c0a5ca32c`  
Implementation commit: `75ebe9eaaff3e7cd2349bfd33fde58fbb2c0713d`

## Protected scope

The sorted `git ls-tree -r` manifest for `src/pmw` plus
`experiments/generative_mechanics`, excluding `next_tracks_v06`, is unchanged
from the Gate 5.1 baseline:

```text
entries: 381
SHA-256: a20fd763cad342ac357a08d94ee96ca42075f215efcbff93c4017b65a8ddd669
```

The baseline and final manifests compare byte-for-byte. The working-tree diff
over protected paths is empty. PMW Core, old Generative Mechanics, formal
protocols, preregistration, pilot outputs, and experiment assets were not
modified.

## Gameplay behavior changes

- Same-spec Status instances from different action/caster sources can coexist
  under `refresh` and `add_stacks`; explicit `reject` and `replace` policies
  remain cross-source constraints.
- Temporary shield layers have validated Status instance, caster owner, and
  action-to-effect source lineage. Invalid historical temporary layers migrate
  away without deleting unrelated persistent capacity.
- `spend_world_time()` is a whole-request staged transaction. Combat and
  harvest reuse the same staging helper and keep one authoritative charge.
- Harvest cost conditions now see the same active Status/granted-trait view as
  Action resolution, so the committed duration is the legally modified final
  duration.

These changes close ownership and atomicity defects. They do not alter PMW Core
Scheduler semantics, add Operators, expand content, or change the registered
public Gameplay entry points documented in `TODO1_FINAL_HANDOFF.md`.

## Save and migration behavior

New checkpoints preserve source-local Status identity, temporary shield
ownership, time ledger, Scheduler queue, and runtime continuation. On attach,
pre-5.2 invalid temporary ownership is removed idempotently; valid persistent
layers and conservative legacy scalar migration remain intact. A malformed
live ownership graph fails closed before Action commit.

## Regression evidence

```text
PMW Core                 254/254   26.207s
Old Generative Mechanics 345/345   68.326s
v0.6                     170/170   25.732s
Gameplay v0.4            172/172   78.165s
Total                    941/941
```

There were zero failures, errors, skips, or expected failures. Complete log
hashes are recorded in `GATE52_FINAL_REPAIR_REPORT.md`. Independent QA passed
5/5 adversarial tests, all Gate 5.2 tests passed 27/27, and no remaining P1/P2
was found.

Two independent Gate 5 Demo processes were byte-identical with SHA-256
`89c9e21b676c2079967634339954ebf698a04397bf8b385198032a212a7b74b9`.
`git diff --check` passes.

No TODO2 model collection, benchmark freeze, or TODO3 game production was
started. Owner acceptance is intentionally not asserted.
