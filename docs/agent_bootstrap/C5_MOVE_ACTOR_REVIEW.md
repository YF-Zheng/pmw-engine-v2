# C5.1 Move Actor Independent Review

Status: **ACCEPT** for the bounded C5.1 increment. Full P1/P2, Alpha travel
integration, NPC legal-area enumeration, multi-step routing, push/pull, and
generic topology mutation remain outside this claim.

## Frozen Identity

- Repository: `pmw-engine-v2`
- Branch: `feature/alpha-v02-seventh-night`
- Baseline HEAD: `55299dac0f709c42195ce8d27be2cea93a9cf191`
- Review scope: uncommitted owner changes in `effects.py`, `skills.py`,
  `actions.py`, `action_compiler.py`, the owner test, and the frozen design.
- QA files: new independent test and this report. No production file or owner
  test was edited. No commit, push, stash, reset, checkout, or deletion occurred.

## Final Evidence

| Suite | Result | Log |
| --- | --- | --- |
| Independent review | `12 passed, 17 subtests passed` | `evidence/c5_move_review_independent_16.txt` |
| Owner C5.1 test | `11 passed, 30 subtests passed` | `evidence/c5_move_review_owner_final.txt` |
| P1 scenarios | `10 passed` | `evidence/c5_move_review_p1_final.txt` |

All used `PYTHONPATH=src`, bytecode suppression, UTF-8 IO, the mandated
temporary/cache paths under `docs/agent_bootstrap/evidence/test_tmp`, and
pytest `-p no:cacheprovider`. `git diff --check` is clean.

## Independent Coverage

The new suite uses parsed `SkillBlueprint`s with material authority, then
`make_content`, `compile_content`, `MechanismRegistryRuntime`,
`change_loadout(equip_active)`, `submit_timed_primary_action`, and the real
paid World Tick. It covers:

1. The same parsed Skill moves PLAYER and NPC. Each pays Mana `4.0` and exactly
   one Tick; each ends with exactly one `located_in`; the action trace contains
   accepted `delete_relation` and `create_relation` proposals with the compiled
   move Law IDs and destination values.
2. A support Area-scoped event Law installed before the paid Action observes
   `actor -> located_in -> destination` in the same paid World Tick.
3. A `current_area` field co-effect in the same move Action changes the origin,
   while the destination advances only through its normal paid Tick Dynamics.
4. A real paid `relation_modifier` disable followed by movement: a bare parallel
   A-B relation keeps the path open. A separate trusted Area-to-Area
   `instantiate_relation(base_enabled=False)` blocks atomically and
   `base_enabled=True` permits movement.
5. Atomic byte-identical rejection includes non-adjacent, same Area, unknown
   Area, area target on a non-move Action, missing target, zero/two
   `located_in`, Relation/Entity ID collision, malformed link component,
   passive/hook use, forbidden co-effects at Action and Skill parse, duplicate
   move, extra fields, wrong selector, and conditional commitment.
6. Requests without `target_area_id` retain the exact HEAD payload digest
   `5fc39b697eea0cd855ce7c6ea25b3a94cad674cc9b3b022fec72d81ef6a0eafb`
   and canonical `basic_wait` hash
   `76402836ee7b674883344f555ca8d8e0d85d5f9fb3806c4330749e562679c3ee`.
7. Move A->B then back to A, a second actor moving in the next paid action,
   checkpoint save/load/rebuild after movement, hash preservation, and a
   subsequent post-restore move.
8. Scenario-1 style origin Dynamics continue evolving after the actor leaves,
   including after destination Tick advancement.

## Product Findings

No confirmed PRODUCT defect was found in the bounded C5.1 change.

The only residual behavior worth recording is diagnostic classification:

- C3-style `RelationProfile`s can represent trusted local marker endpoints
  rather than the A-B edge itself. Such a profile is not an `adjacent` Area
  relation, so disabling it does not alter Area adjacency. The owner's C3 test
  correctly constructs its overlay relation differently.
- A real A-B relation carrying `pmw_gameplay_link.effective_enabled == False`
  is rejected atomically as `move_actor target is not an adjacent Area`, rather
  than a dedicated `disabled` error. The design requires no specific text.
  Owned Area-to-Area disabled and enabled fixtures both preserve the required
  behavioral distinctions: reject versus accept with no partial publication.

No failing product probe is being converted into a pass. The observation above
is a bounded diagnostic distinction, not a claim that disabled C3 traversal is
bypassed.

## Fixture Corrections

The following were corrected in the QA fixture, not production:

1. Exact compiled move Law IDs include version/hash tokens; assertions now
   match the documented ID shape rather than an invented constant ID.
2. Hook rejection must exercise private `_resolve_action(..., execution_kind=
   "hook", hook_context=...)`; the public timed path intentionally never enters
   hook execution.
3. Time accounting checks use the registered budget reasons and exclude a bare
   post-action `advance_world_tick` from the paid-action tick count.
4. Dynamics in the same paid Tick advance after the origin co-effect. The origin
   expectation includes both the co-effect and the paid Tick rate; destination
   advancement is its normal baseline once.
5. A RelationProfile used for a paid local overlay requires endpoint markers
   located inside the profile Area. Marker endpoints are not themselves the A-B
   joining edge, so the C3 test uses the owner-compatible local marker profile
   while the disabled Area-edge behavior is exercised separately through
   trusted `instantiate_relation`.
6. The destination observer is installed before the paid Action. Rebuilding an
   observer after the Action cannot retroactively observe that completed Tick.
7. Selector scopes need the correct `ScopeCapability` constructor shape and
   the correct event type `pmw.v04.world.tick`.

## Residual Limits

- No full suite was run, per review instructions.
- The independent tests do not claim Alpha travel migration, generic path
  solving, legal-area enumeration, relation creation/deletion beyond the two
  compiled lifecycle Laws, or complete C3/selector integration.
- Owner and P1 suites were run once each as requested; the final independent
  suite is the current green artifact after fixture corrections.
