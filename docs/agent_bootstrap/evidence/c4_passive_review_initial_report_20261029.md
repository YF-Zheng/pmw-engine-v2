# C4.2 Independent QA: Bounded Damage-Passive Auto-Dispatch

Review date: 2026-10-29

## Finding

**P1 - automatic Hook request IDs do not use the frozen `auto_hook_` prefix.**
The stable implementation derives `"ah" + sha256(...)[:61]` in
`experiments/generative_mechanics/next_tracks_v06/gameplay_v04/hooks.py:639`.
The accepted fixture produces
`ahafa086d21776790f0d0e6191c01c16d3c2e777e0b16a02f2b8bd9cb6c32e3`,
while the frozen design requires a deterministic bounded `auto_hook_` identity.
The independent red test is
`test_auto_hook_request_id_contract`; the owner test does not assert this
prefix. This is a product acceptance finding, not a QA fixture error.

No other independent acceptance failure was observed. The remaining tested
behavior passed against the stable source hashes below. This report does not
accept C4.2 until the owner corrects the request-ID contract and the full
focused/frozen regression is rerun.

## Verified Behavior

- Real parsed material, passive Skill, registry binding, and loadout on both
  player and NPC; paid player/NPC attacks consume exactly one Tick and do not
  charge hook Mana/time.
- Real damage notification is authenticated from the accepted `emit_event`
  proposal, exact compiled damage Law, parent Action event, and actual
  positive HP/shield commit deltas. HP-only and fully-absorbed writes do not
  require fabricated no-op scalar deltas.
- Root and Hook Engine calls retain separate raw traces. QA builds a test-only
  traversal view of `auto_hooks` child outcomes; it never requires a merged
  primary trace or rewrites `event_result`.
- Same parsed Skill hash on both owners works, Skill hash differs from Action
  hash, and shared root owner+hook dedup terminates the counter chain.
- Ascending-slot sibling hooks re-read current staged state; the second
  sibling condition observes the first sibling shield write.
- A normal active self-damage Skill has a parent Action target of `None` while
  its prepared effect and notification target are the acting Actor.
- Shield absorption is quantitatively attributed. Zero accepted damage emits
  no notification and dispatches no hook. A typed/privileged spoof
  notification is rejected and the staged transaction rolls back.
- Unequipped, stowed, disabled, forged, wrong-kind, wrong-owner, remote, dead,
  false-condition, cooldown, and bare manual-only hook cases do not auto-fire.
  The cooldown case is labeled privileged support because passive Skill JSON
  does not gain a cooldown field in this slice.
- Lowered trusted depth/firing/notification limits and real Hook exceptions
  roll back World, revisions, stats, schedule, closure, and time budget.
  A late paid-Tick failure preserves the entire staged transaction.
- Save/load continuation, registry checkpoint rebuild, static notification Laws,
  and projections without private dispatch authority were exercised. New
  managed roots reset root-local dedup and budget.

## Provenance

Repository: `C:\Users\orinzheng\Documents\Codex\2026-10-28\magpie-codex-deepseek-17-21-codex\pmw-engine-v2`

Branch: `feature/alpha-v02-seventh-night`

Baseline: `718be652754c065b88d6d6cbf013c754f90c05c0`

Stable source hashes were independently read twice with identical results:

```text
hooks.py           CEC4FCFB97C2FF8D3BE9CFCC4BAFEC084794132C062C251C575026C2F25A3067
actions.py         9E2D3589990D7DBF915AF00A9A0434241F831903FA92D49EBC542CB8E1F89530
action_compiler.py D6C9C9D417F535B7DDDD5777F6DC4388E84A826984C18C1CE29B927177699C0A
content_compiler.py AAD8458AB51F2699E50CFA39206B0A13188A761D8E0811FC098310FB8FA20ACF
registry.py        1EC2172BBAA89118FCACD2AD01CDC89ED3989132A9175D54866F3C54A2AC4FDD
checkpoint.py      451411970CC030D19D14343374F68D849ACD15CABDF07BB938A3DF8BCB70EBCC
owner test         B3DA88D8950D66E1B84002907F4F919B4FB9F125B9677B478ABFDEF1C84ADD38
```

Independent QA test hash:

```text
test_sandbox_passive_dispatch_review.py F23BF6790FEC74DD82FDD7C8550143BAED17521DE498E1341D815718F3AC5EBC
```

Evidence hashes:

```text
c4_passive_review_final_20261029.log              6C4B10D892C0487F6CA807521962CC69539E627D39AFD9B6B5C4C5E0A2A88F53
c4_passive_review_owner_20261029.log              42118430996648CB7488404FF6764A334532A3FFBDEE86759FB1AECF199BE4A9
c4_passive_review_cross_20261029.log              43873E29C7549C67494F3A18F2741730C707FA9479AF1E27F6EC2E4CD6F93662
c4_passive_review_red_preimplementation_20261029.log EEAFC352BF0BBFFEF2A66A4227197B86A6717FEE58A447969DA0D3A1FE82AC2F
```

## Commands And Results

All Python runs used `PYTHONPATH=<PMW>/src`,
`PYTHONDONTWRITEBYTECODE=1`, PMW-local `TEMP/TMP/TMPDIR`, no
`PYTHONPYCACHEPREFIX`, and `-p no:cacheprovider`.

```text
python -B -m pytest -q -p no:cacheprovider experiments/generative_mechanics/next_tracks_v06/gameplay_v04/tests/test_sandbox_passive_dispatch_review.py
1 failed, 20 passed, 13 subtests passed in 5.85s
FAILED test_auto_hook_request_id_contract: expected auto_hook_ prefix, got ah...

python -B -m pytest -q -p no:cacheprovider experiments/generative_mechanics/next_tracks_v06/tests/test_sandbox_passive_dispatch.py
13 passed, 8 subtests passed in 3.47s

python -B -m pytest -q -p no:cacheprovider test_gate2_effects_hooks.py test_gate2_actions.py test_gate3_loadout_integration.py test_gate4_registry_checkpoint.py test_gate52_time_transaction.py
45 passed, 2 subtests passed in 7.66s
```

The preimplementation red record remains preserved: the equipped passive did
not respond and the raw gap probe ended at HP 30 with zero shield.

## Boundaries And Non-Claims

Independent QA changed only the new review test, this report, and
`evidence/c4_passive_review*`. No production, old-test, Engine, clock,
Observation, Alpha, or PMW-external file was modified. No commit or push was
made. The unrelated C4.3 active top-level false-condition gap remains standalone
and is not used as a collected wrong-behavior oracle.

This review does not establish arbitrary World/Tick notification dispatch,
other legacy trigger names, multi-trigger IR, forecasting/private projection,
global CPU/query budgets, full P1/P2, Alpha UI, or any game-generation/provider
call. Main retains full freeze, budget, and checkpoint acceptance.

