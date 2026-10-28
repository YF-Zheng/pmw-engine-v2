# P1 Alpha Authority Increment

Date: 2026-10-28  
Branch: `feature/alpha-v02-seventh-night`  
Baseline: `1433e957d5391b880b71e92da4b5cf2ebd9751cd`

## Scope

This increment fixes two bounded Alpha integration authorities:

1. Public time and event timestamps now read the Gameplay clock's completed step, not the PMW scheduler's `WorldState.tick`.
2. Travel topology now comes only from typed `adjacent` Relations. Lift and root-bridge unlocks create those Relations through trusted PMW Event/Law effects inside the existing public `perform` transaction.

Clue disclosure was deliberately left unchanged because existing tests assert pre-inspection hints and that requires a separate UX/knowledge policy.

## Implementation

### Public Time Authority

- `examples/pmw_alpha/session.py` adds `_time()`, sourced from `pmw:v04:clock.pmw_gameplay_clock.last_completed_step`.
- `public_state()["time"]`, ecological events, and normal feedback events use `_time()`.
- Each multi-tick world-progress event uses that tick's own `TickResult.step`, so a two-tick action records `[1, 2]`, not `[2, 2]`.
- Scheduler roots may increment `WorldState.tick` without changing displayed Gameplay time.
- The production clock remains `pmw:v04:clock`; no v0.6 normalized clock was introduced.

### Relation-Backed Routes

- `examples/pmw_alpha/content.py` compiles two trusted, static Alpha route Laws with the normal Gameplay content:
  - `pmw.alpha.route.mine_lift`
  - `pmw.alpha.route.forest_root_bridge`
- Each Law validates the route Event, origin/destination, and the existing unlock condition:
  - Lift: mine charge `>= .60`
  - Root bridge: forest biomass `>= .62`
- The Law emits `create_relation` for a canonical typed `adjacent` Relation and sets the existing compatibility flag. It does not write the relation map directly.
- `session._neighbors()` reads all and only `adjacent` Relations.
- `_power_lift()` and `_progress_routes()` request the trusted route Event; public `perform` still stages and publishes the complete operation atomically.
- Relation components record `route_id` and `unlocked_by`, making the edge inspectable and distinct from the three starting edges.

The route Laws are part of `compile_alpha_content()`, so normal Gameplay static-Law hashing, registry rebuilds, and checkpoint verification cover them.

### Save Compatibility

- The Alpha save schema advances from `pmw-alpha-save-v0.2` to `pmw-alpha-save-v0.3`.
- Old v0.2 saves are rejected explicitly because they cannot safely represent the new Relation-backed topology.
- Restore validates that every compatibility route flag agrees with a canonical Relation of type `adjacent`, the expected sorted endpoints, and the expected `route_id`/`unlocked_by` metadata. Wrong type, endpoints, or metadata is rejected rather than silently recreating or deleting topology.
- New saves round-trip real unlocked edges and their route metadata through the Gameplay checkpoint.

## Regressions Added

`examples/pmw_alpha/tests/test_sandbox_authority.py` covers:

- Public time moves with inspect/travel and is not inflated by a scheduled future root.
- Multi-tick world-progress timestamps preserve each completed step even with scheduled roots present.
- Lift and bridge unlocks create real edges visible to `_neighbors()` and the reusable `adjacent_area` selector.
- A compatibility flag alone never authorizes travel, and an absent Relation remains non-traversable.
- Failed public route unlock preserves both WorldState and the registry component.
- Save/load preserves real unlocked edges, selector visibility, and compatibility flags.
- A canonical route ID with wrong Relation type, endpoints, or route metadata is rejected on restore.

## Verification

```text
python -m unittest discover -s examples/pmw_alpha/tests -p 'test_*.py'
Ran 26 tests ... OK

python -m unittest discover -s experiments/generative_mechanics/next_tracks_v06/gameplay_v04/tests -p 'test_gate1_blueprints.py'
Ran 7 tests ... OK

python -m unittest discover -s experiments/generative_mechanics/next_tracks_v06/gameplay_v04/tests -p 'test_gate4_registry_checkpoint.py'
Ran 7 tests ... OK

python -m unittest discover -s experiments/generative_mechanics/next_tracks_v06/gameplay_v04/tests -p 'test_gate52_time_transaction.py'
Ran 8 tests ... OK
```

No provider calls, commits, game-balance changes, or magical victory updates were made.

## Limitations

- This increment intentionally does not migrate v0.2 saves. Rejection is explicit and preferable to manufacturing topology from legacy flags.
- Route unlocks retain the existing production conditions and outcomes; no new routes or encounter semantics were introduced.
- Private Alpha handlers remain non-transactional by themselves. Public `perform` remains the supported authoritative boundary, consistent with the prior architecture decision.
