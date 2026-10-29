# C1 Process Rate-Only Expiry Review

## Verdict

PASS against the frozen native, schema, and owner-test hashes below.

This review establishes the genuine original defect reproduction and positive
formal pure rate-only evidence. It does not accept native-only coverage or
explicit-duration behavior as proof of the pure rate-only path.

## Frozen Inputs

- Branch: `feature/alpha-v02-seventh-night`
- Parent: `0e4e45b`
- `gameplay_v04/processes.py` SHA256:
  `4f5f3b6941913b68ff3badac0d57e1c0c24cadb6516b1ea17a23d6488b78815b`
- `gameplay_v04/effects.py` SHA256:
  `79d383be2a80dceea385a7a067b079ae8f341baf71721ff003e8944249f0df3e`
- Owner native test SHA256:
  `3c0d7bf7f7f8e6c44bb1b52f37fbdf066ab7b53ab68b6208e2354e785ddec7de`
- Owner optional-schema test SHA256:
  `da5f3d7f90bb7be6829c8df24913fcbb3820931eefe62de56f91c71a5a79b2c9`
- Independent review test SHA256:
  `fcb243cdbfe6d55584f13f6b3cf945c9fbb2f80494dd38e61daeedbec115db23`

## Original Defect Evidence

`evidence/c1_rate_expiry_before.json` records the accepted `0e4e45b` native
`_prepare_modify` extraction against a trusted output-full setup and a normal
equipped paid start:

- Clock at `2.0`; stored `duration_ticks=3`, `remaining_ticks=3`,
  `elapsed_ticks=0`, `progress=0.0`, `hard_deadline=3.0`, expiry `3.0`.
- A rate-only modification was rejected with
  `GameplayContractError("Process duration cannot extend the hard deadline")`.
- World state was unchanged.

This reproduces the original native false rejection with duration equal to
`max_duration` and no explicit remaining-tick authorization.

The separate schema defect is also genuine. At `0e4e45b`, `effects.py` required
both `process_rate` and `process_remaining_ticks` through strict field equality,
despite the rate-or-remaining contract. `evidence/c1_optional_fields_before.json`
records rate-only and remaining-only rejection and both-key acceptance.

## Independent Review Coverage

The new review test has four bounded methods:

1. `test_pure_rate_only_cold_catalog_lifecycle_preserves_actual_expiry`
   - Parses a raw process modifier with no `process_remaining_ticks` key.
   - Asserts parsed `process_remaining_ticks is None`.
   - Uses a cold trusted catalog, normal `change_loadout`, and a real paid
     start at clock `2`, with stored `duration=remaining=3`,
     `hard_deadline=expiry=3`, and a fully stocked output.
   - Calls mana-paid `resolve_action` at clock `2`, before expiry, and verifies
     primary resolution retains
     `duration=remaining=3`, `progress=0`, elapsed and expiry fields and
     changes only the rate. A direct world tick then verifies exact expiry at
     clock `3`; this manual tick is not time-budget payment for the modifier.
2. `test_pure_rate_only_formal_player_and_npc_paid_actions_are_quantitative`
   - Independently exercises the same pure rate-only formal path for player
     and NPC equipped, mana-paid primary actions.
   - Checks one-mana deduction, ordinary clock budget before expiry, stored
     duration/remaining, and unchanged Stock when the productive conversion
     cannot complete before wall expiry.
   - The formal case uses a mana-paid `resolve_action` at clock `2` followed by
     `advance_world_tick` for the exact wall boundary. This avoids attributing
     an unrelated existing accounting behavior to the C1 expiry path.
3. `test_explicit_duration_and_invalid_schedule_rejections_are_distinct`
   - Keeps explicit-duration extension rejection separate from pure rate-only.
   - Verifies a valid explicit change uses now plus remaining and expires at
     the resulting deadline.
   - Covers missing, past, beyond-hard-deadline, and duplicate schedule
     handling with state comparisons where the rejection is controller-level;
     duplicate-ID validation is identified as world runtime validation rather
     than falsely attributed to `_prepare_modify`.
4. `test_cascade_late_tick_and_checkpoint_keep_rate_only_rollback_semantics`
   - Verifies actual event cascade failure rollback, late-tick failure
     rollback, and checkpoint continuation through exact expiry.

Production overlap is absent: the QA test imports and exercises the trusted
helpers and public action/runtime paths. Negative corrupted-fixture probes are
supporting checks only and do not establish loadout or manifest authorization.

## Executed Result

Command, with repository-only temporary and cache paths:

```powershell
$env:PYTHONPATH='src'
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTHONIOENCODING='utf-8'
$env:TEMP=(Resolve-Path 'docs/agent_bootstrap/evidence/test_tmp').Path
$env:TMP=$env:TEMP
$env:TMPDIR=$env:TEMP
python -m pytest -p no:cacheprovider `
  experiments/generative_mechanics/next_tracks_v06/gameplay_v04/tests/test_sandbox_process_rate_expiry_review.py `
  experiments/generative_mechanics/next_tracks_v06/gameplay_v04/tests/test_sandbox_process_rate_expiry.py `
  experiments/generative_mechanics/next_tracks_v06/gameplay_v04/tests/test_sandbox_process_optional_fields.py -q
```

Exact saved result:

```text
.................                            [100%]
17 passed, 28 subtests passed in 3.45s
```

Evidence is in `evidence/c1_rate_expiry_review_final.log`.

## Historical Evidence And Limits

Earlier `c1_rate_expiry_review_initial_red*` logs are preserved as fixture and
harness history. Earlier parser red logs are preserved as schema-defect
history; they are not expected behavior in the final tests.

The owner native test's `_saturated_profile` uses
`duration_ticks=3, max_duration_ticks=6`. Its native case therefore has
supporting backlog slack and is not the original defect reproduction. The
independent test above uses equality at the trusted maximum and has no
remaining-tick authorization, so it is the required positive pure rate-only
proof.

This report makes no production changes and does not alter owner tests,
manifests, Git state, global configuration, or external systems.

Main editorial clarification after review: pure-rate primary assertions above
do not by themselves establish modifier time-budget payment. Main separately
ran genuine `submit_timed_primary_action` for player and NPC: clock2 -> 3,
spent_ticks2 -> 3, remaining10 -> 9, one Mana paid, exact expiry at3 and unchanged
Stock. Evidence: `evidence/c1_rate_expiry_main_timed.json`. Independent test
source and all five frozen source/test hashes are unchanged by this clarification.
