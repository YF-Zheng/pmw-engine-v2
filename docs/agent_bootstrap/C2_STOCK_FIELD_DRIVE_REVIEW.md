# C2 Finite Stock-To-Field Drive Independent Review

Date: 2026-10-29, Asia/Shanghai. Commit:
`a4ad912c85f8c15f169c0826eea6c045e0ca2f7e`. Branch:
`feature/alpha-v02-seventh-night`.

Status: **INDEPENDENT QA PASS; FOCUSED SCOPE ONLY**. The six QA-owned methods
pass against the implementation hashes supplied by Main. No C2 product defect
was found in this focused review. This is not the full frozen regression, not
Main's final source acceptance, and not promotion of the bounded C2 increment
to full P1.

## Scope And Ownership

QA read the complete `docs/agent_bootstrap/C2_STOCK_FIELD_DRIVE_DESIGN.md`,
including **Shared Interface For Disjoint Workers** and **Main Review
Clarifications**. Exported DriveProfile fields/classes were treated as fixed.

QA wrote only:

- `experiments/generative_mechanics/next_tracks_v06/gameplay_v04/tests/test_sandbox_drive_source_review.py`
- this report
- `docs/agent_bootstrap/evidence/c2_drive_review*.log` / report-local temp data

No production, owner test, old test, manifest, Git metadata, global
configuration, external service, worker, or game-generation call was changed or
used. QA did not run full regression after source freeze.

## Frozen Provenance

Main supplied these implementation hashes; QA independently recomputed and
matched them before the final focused run:

```text
48E639D21B752E6FB0E02F32FDB91D18774BEA720B200CE0D82AC399C0B52727  drives.py
FC259A3059592A0503FE9766F6A6C1F6A21E618D1C9AD031F9554CB51E544324  tests/test_sandbox_drive_source.py
B2FB1B95710D0DDD2B0576054D76EB0939E0C5A1E437F33857893A466A3EF354  content_compiler.py
5AC63142229118590A31C140EEF610368D6C16F9E9FA5674E850DB8867B18304  effects.py
```

Main reported owner evidence `11 passed / 7 subtests`, focused regression
`52 / 84`, and direct compile-overlap checks `1 / 2`. Those are Main/owner
results, not rerun as full regression here.

## Six Independent Methods

### 1. Formal Player/NPC Timed Source And Dynamics

`test_formal_player_npc_timed_source_and_dynamics`

- Parses a material-authorized `drive_source` Skill from an existing
  `parse_material` + `material_authority` path. The duration-4 Skill uses
  `budget_used == 5.4`, matching base `5.0` plus existing duration cost
  `0.4`; the fixture allowance is `6.0`.
- Equips the same parsed Skill through normal `change_loadout`.
- Player and NPC separately use shared `submit_timed_primary_action`, with real
  time duration `1`. It asserts spent/remaining counters `(2, 18)`, mana,
  actual Fuel debit, Field gain at trusted coefficient `2`, distinct expiry
  handles, and real emitted `DRIVE_STEP_EVENT` children.
- For duration `3`, compares `none` versus `linear` recovery: both debit Fuel
  `3.0`; Field finishes at `7.0` with `none` and `6.42` with linear recovery.
  This is a quantitative separation from one-shot impulse behavior, not a
  claim that the Drive invented an attractor mechanism.

### 2. Capacity, Partial Fuel, Expiry, Numeric No-Op, And Ownership

`test_capacity_fuel_owned_expiry_and_owner_departure`

- Capacity clamp: Field gain `0.5`, paired Fuel debit `0.25`.
- Low Fuel uses the design formula `min(rate, stock * coefficient, headroom)`.
  It does not stop merely because a whole rate step is unaffordable: with
  `rate=0.2`, stock `0.1`, coefficient `2`, and headroom `0.25`, accepted gain
  is `0.2` and Stock becomes `0.0`.
- Normal proportional control: gain `1.0`, debit `0.5`.
- Huge Stock (`1e12`) / tiny rate (`1e-12`): unrepresentable Field gain is a
  conservative no-op; Field remains `0.0`, Stock remains `1e12`,
  `last_step` advances, and `last_delta == 0`.
- High Field (`nextafter(1.0, 0.0)`) / tiny rate (`1e-17`): unrepresentable
  gain is a conservative no-op; Field and Stock remain unchanged while
  `last_step` advances and `last_delta == 0`.
- Empty Stock activation is atomically denied.
- Activation duration `4` converts only at Ticks `1,2,3`; expiry happens before
  Tick `4`. A latched old expiry event does not terminate a later reactivation,
  which owns a distinct expiry handle. Reactivation is covered directly here,
  not merely inferred.
- After owner/source fixture relocation, the active source continues in its
  own Area and performs one accepted conversion (Field `3.0`, Fuel `9.0`).
  This relocation is **support-fixture evidence**, clearly distinct from the
  formal Skill/equipment path and not genuine normal movement.
- The same method includes the pre-existing full-Field activation refusal and
  a separate after-dynamics recovery probe: an active source begins with full
  Field, linear dynamics first lowers it, and the child converts in that same
  tick (Field `10.0`, Fuel `9.905`, delta `0.19`). A subsequent tick continues
  conversion. Root pre-state filtering therefore does not suppress same-tick
  child validation.

### 3. Shared Field Ordering And One-Shot Distinction

`test_sorted_overlap_and_none_vs_impulse`

- Three profiles share one Field with distinct Stocks and coefficients.
- Starting and inputting them in normal and reversed container order yields
  byte-identical `state.to_dict()` outcomes and sorted Stock debits.
- The shared Field ends at `7.0`; order-independent per-profile debits are
  `[9.0, 9.0, 9.5]`.
- A Drive source adds its configured amount on its paid tick. A separate
  test-local Engine event Law adds one genuine one-shot Field impulse, and the
  following `none`-curve tick leaves that impulse unchanged. This confirms the
  Drive is not being confused with a generic recovery/impulse effect; it does
  not claim a new production impulse kind.

### 4. Denials, Limits, Unknown Injection, And Static Exclusions

`test_denials_unknown_coefficient_and_mixed_control`

- Rejects injected `source_unit`, `field_per_stock`, and candidate `source`
  fields; confirms the frozen profile exposes no alternate coefficient/unit
  fields.
- Rejects target bypass, non-bool numeric rate variants (including NaN and
  Infinity), zero duration, duplicate Skill identity, and an explicit
  insufficient material budget.
- Rejects a Skill combining `drive_source` with `process_start` through the
  existing single-control-operation parser.
- Real Action denials for wrong owner, wrong Stock unit, and nonlocal scope all
  leave the full session snapshot unchanged.
- `DriveLimits(max_instances=2, max_active=1)`: formal first start succeeds;
  second `prepare_start` rejects without state change; a third active profile
  constructor rejects `max_instances`.
- Unknown `profile_id` rejects at the trusted controller boundary; duplicate
  input Stock profiles reject constructor validation.
- Static Drive/Process input-or-output Stock overlap rejects at content
  compilation, including inactive profiles. This is the design's conservative
  static exclusion, not a generic concurrent-writer resolver.
- The existing FieldDefinition/Process unit-catalog gap remains explicit.
  These tests do not claim universal dimensional typing of Field units.

### 5. Real Child Cascade And Rollback

`test_real_cascade_and_late_tick_rollback`

- Uses a deep-copied isolated session, the real action registry, installed
  dynamic action Laws, and an actual equipped Skill request through
  `submit_timed_primary_action`.
- A test-local downstream event Law intentionally raises `ZeroDivisionError`
  on the emitted `DRIVE_STEP_EVENT` after the real paid child path begins.
- The complete isolated snapshot (state serialization, revisions, stats,
  closure status, and scheduled events) is identical after the failure.
- A second bounded probe patches the real existing tick function to fail on
  its first paid tick and likewise asserts complete rollback and one real call.
- The earlier setup failures were QA fixture/API setup issues. They are
  preserved as red evidence and are not classified as product defects.

### 6. Checkpoint, Changed Profile, Projection, And Wait

`test_checkpoint_changed_profile_projection_and_wait`

- Saves and loads an active Drive, then performs the next trusted coefficient
  conversion at the restored Field and Stock values.
- Loading against a changed trusted profile coefficient rejects through the
  compiled static Law/profile hash path.
- Actor observation omits Drive/private Stock; `SandboxSimulator` projection
  omits the Drive entity/controller/actions, while `basic_wait` remains legal
  and preserves visible Area Fields.

## Focused Execution

Environment and repo-local temp discipline:

```powershell
$env:PYTHONPATH='src'
$env:PYTHONIOENCODING='utf-8'
$env:PYTHONDONTWRITEBYTECODE='1'
$env:TEMP=(Resolve-Path 'docs/agent_bootstrap/evidence').Path
$env:TMP=$env:TEMP
python -m unittest `
  experiments.generative_mechanics.next_tracks_v06.gameplay_v04.tests.test_sandbox_drive_source_review `
  -v
```

Final evidence:
`docs/agent_bootstrap/evidence/c2_drive_review_frozen_focused_final.log`

```text
Ran 6 tests in 2.459s
OK
```

Preserved historical QA evidence includes initial missing-module red,
native-interface partial/core runs, the first focused runs, and the first two
frozen focused runs. Their failures were stale interface/API or QA fixture
assumptions; they were not final product defects. The final green evidence
supersedes only the execution result, not the preserved provenance.

## Residual Risks And Non-Claims

- No full frozen regression, commit, spawn, game generation, provider access,
  or production edit was performed by independent QA.
- No universal dimensional typing, arbitrary sink/open-source behavior, Stock
  transfer, generic writer resolution, Alpha UI, or full P1 promotion is
  claimed.
- The owner-leaves conversion uses a support-fixture relocation; it is not
  formal movement/equipment evidence.
- Main and the owner test remain responsible for the final acceptance matrix
  beyond these six bounded methods, including any broader regression and
  source-review obligations not reproduced here.

## QA-Owned Artifact Hash

Final independent review test:

```text
561ECE5CB6F7A53A2D9AAFAFD7058E72CDE43250229B361705ACF1CD939D5B8A  experiments/generative_mechanics/next_tracks_v06/gameplay_v04/tests/test_sandbox_drive_source_review.py
```

The report itself is frozen by its whole-file SHA256 reported to Main after
this final edit.
