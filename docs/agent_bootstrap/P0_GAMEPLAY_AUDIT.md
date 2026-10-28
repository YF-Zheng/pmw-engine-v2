# P0 Gameplay + Alpha Integration Audit

Date: 2026-10-28  
Baseline: `1433e957d5391b880b71e92da4b5cf2ebd9751cd`  
Branch: `feature/alpha-v02-seventh-night`  
Scope: `examples/pmw_alpha`, `experiments/generative_mechanics/next_tracks_v06/gameplay_v04`, and the separate v0.6 IR under `experiments/generative_mechanics/next_tracks_v06`  
Constraints: source read-only; this document is the only write; no providers; no engine or baseline-QA duplication.

## Executive Finding

Alpha is a real Gameplay v0.4 integration, not a template-only mock. It reuses v0.4 Area/Actor construction, dynamic Fields, the action registry, loadouts, shields/statuses, the staged time ledger, and the registry checkpoint. Focused suites passed: Alpha 15/15, selected v0.4 machinery 47/47, and v0.6 170/170.

The main integration gap is architectural rather than a wholesale absence of machinery: Alpha targets the **v0.4 Gameplay contract**, while the supplied six-object/seven-operator contract exists in the **separate v0.6 research IR**. Alpha therefore does not expose v0.6 Stock/Process/Relation/Discrete/Derived objects, its seven operators, or its compiler-derived activation/trigger model. Alpha’s world clock is the production `pmw:v04:clock`; it is not replaced by the normalized `gm:v06:clock`.

There are also concrete Alpha presentation/authority defects: undiscovered clue prose is sent before inspection, and unlocked routes are player flags plus a hard-coded edge set rather than PMW `adjacent` Relations. The public `perform("craft", ...)` boundary is atomic under a real budget failure, but private handlers used by existing tests are not independently atomic.

## Severity-Ranked Findings

### P1. Hidden clue prose is disclosed before inspection

Alpha claims that only discovered values are public ([ALPHA_PLAN.md:42](C:\Users\orinzheng\Documents\Codex\2026-10-28\magpie-codex-deepseek-17-21-codex\pmw-engine-v2\examples\pmw_alpha\ALPHA_PLAN.md#L42)), but `public_state` emits `INTERACTION_HINTS` whenever the point is merely not inspected:

- [session.py:217](C:\Users\orinzheng\Documents\Codex\2026-10-28\magpie-codex-deepseek-17-21-codex\pmw-engine-v2\examples\pmw_alpha\session.py#L217) chooses the hint unless `point in inspected`.
- [session.py:34](C:\Users\orinzheng\Documents\Codex\2026-10-28\magpie-codex-deepseek-17-21-codex\pmw-engine-v2\examples\pmw_alpha\session.py#L34) contains actionable thresholds and paths, including the lift charge requirement and forest route.
- [session.py:194](C:\Users\orinzheng\Documents\Codex\2026-10-28\magpie-codex-deepseek-17-21-codex\pmw-engine-v2\examples\pmw_alpha\session.py#L194) also exposes those hints in pre-inspection controls.
- [ALPHA_ACCEPTANCE.md:5](C:\Users\orinzheng\Documents\Codex\2026-10-28\magpie-codex-deepseek-17-21-codex\pmw-engine-v2\examples\pmw_alpha\ALPHA_ACCEPTANCE.md#L5) requires hidden information to remain withheld until inspection/discovery.

Reproduction: after travel to `thunder_mine` and before inspecting `damaged_conduit`, the public state already contains actionable clue prose for that point. Existing `test_visible_world_objects_explain_their_actionable_leads` asserts the pre-inspection disclosure path at [test_session.py:94](C:\Users\orinzheng\Documents\Codex\2026-10-28\magpie-codex-deepseek-17-21-codex\pmw-engine-v2\examples\pmw_alpha\tests\test_session.py#L94), so the test encodes the accepted behavior.

Minimal regression: start a new game, travel to `thunder_mine`, and assert that the public `damaged_conduit` description does not contain `0.60` until `perform("inspect", target="damaged_conduit")`.

### P1. Route unlocks are not authoritative PMW topology

The world starts with three `adjacent` Relations ([content.py:63](C:\Users\orinzheng\Documents\Codex\2026-10-28\magpie-codex-deepseek-17-21-codex\pmw-engine-v2\examples\pmw_alpha\content.py#L63)), but Alpha’s travel availability is reconstructed from a hard-coded edge tuple plus two player flags:

- [session.py:184](C:\Users\orinzheng\Documents\Codex\2026-10-28\magpie-codex-deepseek-17-21-codex\pmw-engine-v2\examples\pmw_alpha\session.py#L184) rebuilds edges from `STARTING_MAP_EDGES`, then adds Observatory edges from `lift_powered`/`root_bridge_formed`.
- [session.py:111](C:\Users\orinzheng\Documents\Codex\2026-10-28\magpie-codex-deepseek-17-21-codex\pmw-engine-v2\examples\pmw_alpha\session.py#L111) authorizes travel from that synthesized set.
- [session.py:146](C:\Users\orinzheng\Documents\Codex\2026-10-28\magpie-codex-deepseek-17-21-codex\pmw-engine-v2\examples\pmw_alpha\session.py#L146) changes only the player flag for the lift; [session.py:103](C:\Users\orinzheng\Documents\Codex\2026-10-28\magpie-codex-deepseek-17-21-codex\pmw-engine-v2\examples\pmw_alpha\session.py#L103) does the same for the root bridge.
- The reusable selector machinery correctly reads PMW `adjacent` Relations at [selectors.py:51](C:\Users\orinzheng\Documents\Codex\2026-10-28\magpie-codex-deepseek-17-21-codex\pmw-engine-v2\experiments\generative_mechanics\next_tracks_v06\gameplay_v04\selectors.py#L51), but Alpha travel never calls it.

Reproduction: before and after setting `lift_powered=True`, `any(relation.type == "adjacent" and "ash_observatory" ...)` remains `False`, while `_neighbors("thunder_mine")` includes `ash_observatory`. This means a genuine `adjacent_area` action cannot use Alpha’s unlocked route, and a corrupted/removed Relation would not affect Alpha travel.

Save/load currently preserves the flags and therefore preserves Alpha’s route behavior, but it does **not** round-trip the promised real map link because no link exists. This bears directly on [ALPHA_ACCEPTANCE.md:15](C:\Users\orinzheng\Documents\Codex\2026-10-28\magpie-codex-deepseek-17-21-codex\pmw-engine-v2\examples\pmw_alpha\ALPHA_ACCEPTANCE.md#L15).

Minimal regression: unlock the lift and assert an `adjacent` Relation between `thunder_mine` and `ash_observatory` exists; then assert travel and `adjacent_area` selector resolution agree.

### P1. Alpha clock state is inconsistent with its displayed time

Production Alpha uses `pmw:v04:clock` ([content.py:162](C:\Users\orinzheng\Documents\Codex\2026-10-28\magpie-codex-deepseek-17-21-codex\pmw-engine-v2\examples\pmw_alpha\content.py#L162), [content.py:35](C:\Users\orinzheng\Documents\Codex\2026-10-28\magpie-codex-deepseek-17-21-codex\pmw-engine-v2\examples\pmw_alpha\content.py#L35)). Its world tick advances `pmw_gameplay_clock.next_step`/`last_completed_step` ([dynamics.py:109](C:\Users\orinzheng\Documents\Codex\2026-10-28\magpie-codex-deepseek-17-21-codex\pmw-engine-v2\experiments\generative_mechanics\next_tracks_v06\gameplay_v04\dynamics.py#L109)), but not `WorldState.tick`.

Alpha reports `"time": self.state.tick` at [session.py:217](C:\Users\orinzheng\Documents\Codex\2026-10-28\magpie-codex-deepseek-17-21-codex\pmw-engine-v2\examples\pmw_alpha\session.py#L217). Reproduction: after start, inspect, and travel, `state.tick` remains `0`, while the gameplay clock advances from step `1` to `3` and `sim_time` advances from `0.0` to `3.0`. A cast also decrements remaining time and advances the gameplay clock while leaving displayed `time` unchanged.

This is a real projection inconsistency, not a request to adopt `gm:v06:clock`. Measured values: start `(tick=0, sim_time=0.0, next_step=1)`; after one-tick inspection `(tick=0, sim_time=1.0, next_step=2)`; after two-tick travel `(tick=0, sim_time=3.0, next_step=4)`. The correct production source is the existing `pmw:v04:clock.pmw_gameplay_clock` state (or its `sim_time`/completed step), not the normalized v0.6 clock.

Minimal regression: spend one tick and assert the public numeric time changes in lockstep with the gameplay clock’s completed step.

### P2. The public command boundary is atomic; private handlers are not

`perform` preflights a public control, deep-clones the session, executes on the clone, and publishes only on success ([session.py:76](C:\Users\orinzheng\Documents\Codex\2026-10-28\magpie-codex-deepseek-17-21-codex\pmw-engine-v2\examples\pmw_alpha\session.py#L76), [session.py:71](C:\Users\orinzheng\Documents\Codex\2026-10-28\magpie-codex-deepseek-17-21-codex\pmw-engine-v2\examples\pmw_alpha\session.py#L71)). The time ledger itself stages a full runtime and preflights the complete duration ([time_ledger.py:75](C:\Users\orinzheng\Documents\Codex\2026-10-28\magpie-codex-deepseek-17-21-codex\pmw-engine-v2\experiments\generative_mechanics\next_tracks_v06\gameplay_v04\time_ledger.py#L75), [transactions.py:10](C:\Users\orinzheng\Documents\Codex\2026-10-28\magpie-codex-deepseek-17-21-codex\pmw-engine-v2\experiments\generative_mechanics\next_tracks_v06\gameplay_v04\transactions.py#L10)).

Verified behavior:

- `perform("craft", ...)` with a one-tick budget and a two-tick cost raises `world time budget is exhausted`; WorldState, materials, crafted list, and registry remain unchanged.
- Calling `_craft` directly with the same precondition mutates materials, registers/commits the blueprint, appends the skill, and then raises on `_spend(2)`. The transaction promise is therefore enforceable only at `perform`, not at the handler.

This matters because production tests exercise private handlers directly at [test_session.py:41](C:\Users\orinzheng\Documents\Codex\2026-10-28\magpie-codex-deepseek-17-21-codex\pmw-engine-v2\examples\pmw_alpha\tests\test_session.py#L41), [test_session.py:57](C:\Users\orinzheng\Documents\Codex\2026-10-28\magpie-codex-deepseek-17-21-codex\pmw-engine-v2\examples\pmw_alpha\tests\test_session.py#L57), and [test_session.py:62](C:\Users\orinzheng\Documents\Codex\2026-10-28\magpie-codex-deepseek-17-21-codex\pmw-engine-v2\examples\pmw_alpha\tests\test_session.py#L62). Those tests can pass while bypassing the end-to-end atomicity contract.

Minimal regression: route every mutating test through `perform`; inject exhaustion at the final charged step and assert the whole command is unchanged. This is Alpha integration evidence, not a finding about bare `Engine.run_event` cascade semantics.

The separately reproduced bare-Engine sequence is therefore classified as documented **core event-cascade behavior**: a root write can survive while a child event raises `ZeroDivisionError`. It is not a new Gameplay transaction regression. Gameplay's staged transaction boundary is a stronger contract, and Alpha's public `perform` correctly uses that boundary; only direct private-handler use bypasses it.

### P2. Supported Field dynamics are already implemented; only an explicit `None` curve is rejected

This is not an Alpha integration gap. The production Gameplay v0.4 contract exposes Field `target` and `rate` ([contracts.py:27](C:\Users\orinzheng\Documents\Codex\2026-10-28\magpie-codex-deepseek-17-21-codex\pmw-engine-v2\experiments\generative_mechanics\next_tracks_v06\gameplay_v04\contracts.py#L27)) and exactly the `linear` and `distance_squared` curves ([contracts.py:10](C:\Users\orinzheng\Documents\Codex\2026-10-28\magpie-codex-deepseek-17-21-codex\pmw-engine-v2\experiments\generative_mechanics\next_tracks_v06\gameplay_v04\contracts.py#L10)). Blueprint parsing accepts both and rejects anything else ([blueprints.py:68](C:\Users\orinzheng\Documents\Codex\2026-10-28\magpie-codex-deepseek-17-21-codex\pmw-engine-v2\experiments\generative_mechanics\next_tracks_v06\gameplay_v04\blueprints.py#L68)); evaluation applies target/rate and dispatches both curves ([dynamics.py:82](C:\Users\orinzheng\Documents\Codex\2026-10-28\magpie-codex-deepseek-17-21-codex\pmw-engine-v2\experiments\generative_mechanics\next_tracks_v06\gameplay_v04\dynamics.py#L82), [dynamics.py:95](C:\Users\orinzheng\Documents\Codex\2026-10-28\magpie-codex-deepseek-17-21-codex\pmw-engine-v2\experiments\generative_mechanics\next_tracks_v06\gameplay_v04\dynamics.py#L95)).

The only negative case found is an explicit Field `curve=None`, which fails the closed `CURVES` membership check at [blueprints.py:69](C:\Users\orinzheng\Documents\Codex\2026-10-28\magpie-codex-deepseek-17-21-codex\pmw-engine-v2\experiments\generative_mechanics\next_tracks_v06\gameplay_v04\blueprints.py#L69). That is correct fail-closed validation for the current schema, not a missing implementation of the supported curves or their target/rate dynamics.

### P2. Alpha does not expose the v0.6 object/operator IR

The v0.6 contract defines exactly the requested six object kinds and seven operator kinds at [contracts.py:9](C:\Users\orinzheng\Documents\Codex\2026-10-28\magpie-codex-deepseek-17-21-codex\pmw-engine-v2\experiments\generative_mechanics\next_tracks_v06\contracts.py#L9). Its `MechanismSpec` carries operators and scope/capability data at [spec.py:180](C:\Users\orinzheng\Documents\Codex\2026-10-28\magpie-codex-deepseek-17-21-codex\pmw-engine-v2\experiments\generative_mechanics\next_tracks_v06\spec.py#L180).

Alpha instead builds v0.4 content via [content.py:13](C:\Users\orinzheng\Documents\Codex\2026-10-28\magpie-codex-deepseek-17-21-codex\pmw-engine-v2\examples\pmw_alpha\content.py#L13) and uses v0.4 `SkillBlueprint` effect kinds. The generated Alpha skills contain only `modify_field`, `modify_attractor`, or `shield` ([session.py:268](C:\Users\orinzheng\Documents\Codex\2026-10-28\magpie-codex-deepseek-17-21-codex\pmw-engine-v2\examples\pmw_alpha\session.py#L268), [session.py:274](C:\Users\orinzheng\Documents\Codex\2026-10-28\magpie-codex-deepseek-17-21-codex\pmw-engine-v2\examples\pmw_alpha\session.py#L274)). The v0.4 effect schema is separate at [effects.py:16](C:\Users\orinzheng\Documents\Codex\2026-10-28\magpie-codex-deepseek-17-21-codex\pmw-engine-v2\experiments\generative_mechanics\next_tracks_v06\gameplay_v04\effects.py#L16).

Consequently Alpha has no working path for Stock flow, Process start/modify, Relation modification, Discrete transitions, or Derived read-only values, and no `impulse`/`drive`/`dynamics_modifier`/`process_*`/`relation_modifier` exposure. This is primarily a **contract-target gap**, not evidence that v0.6 itself is broken: v0.6’s operator suite passes.

### P2. Alpha exposes a reduced trigger/selector surface

Alpha uses v0.4’s closed trigger set: skill `on_use`; passive hooks limited to six events at [skills.py:77](C:\Users\orinzheng\Documents\Codex\2026-10-28\magpie-codex-deepseek-17-21-codex\pmw-engine-v2\experiments\generative_mechanics\next_tracks_v06\gameplay_v04\skills.py#L77), with hook triggers listed at [hooks.py:12](C:\Users\orinzheng\Documents\Codex\2026-10-28\magpie-codex-deepseek-17-21-codex\pmw-engine-v2\experiments\generative_mechanics\next_tracks_v06\gameplay_v04\hooks.py#L12). It supports five selectors at [selectors.py:41](C:\Users\orinzheng\Documents\Codex\2026-10-28\magpie-codex-deepseek-17-21-codex\pmw-engine-v2\experiments\generative_mechanics\next_tracks_v06\gameplay_v04\selectors.py#L41).

Alpha’s own generated skills use only `on_use`/`damage_resolved` and `current_area`/`self`, and their conditions are `None` ([session.py:287](C:\Users\orinzheng\Documents\Codex\2026-10-28\magpie-codex-deepseek-17-21-codex\pmw-engine-v2\examples\pmw_alpha\session.py#L287)). This is not “template-only semantics” in the sense of absent execution, because the blueprints compile and cast through the registry. It does mean the Alpha content does not exercise the broader selector/condition/IR surface available elsewhere.

### P3. Observation authorization exists, but Alpha does not use the actor builder for its public projection

v0.4’s `ActorObservationBuilder` limits visible actors to the current area and limits known actions to built-ins plus explicitly revealed/equipped actions ([observation.py:96](C:\Users\orinzheng\Documents\Codex\2026-10-28\magpie-codex-deepseek-17-21-codex\pmw-engine-v2\experiments\generative_mechanics\next_tracks_v06\gameplay_v04\observation.py#L96), [observation.py:117](C:\Users\orinzheng\Documents\Codex\2026-10-28\magpie-codex-deepseek-17-21-codex\pmw-engine-v2\experiments\generative_mechanics\next_tracks_v06\gameplay_v04\observation.py#L117)). A direct check on Alpha’s session showed only `seventh_walker` and the three built-in actions, with no inventory or private AI fields.

Alpha’s `public_state` is a separate hand-built projection ([session.py:213](C:\Users\orinzheng\Documents\Codex\2026-10-28\magpie-codex-deepseek-17-21-codex\pmw-engine-v2\examples\pmw_alpha\session.py#L213)) and does not call that builder. The missing authorization checks are therefore concentrated in the hand-built field/hint/map projection, not evidence that the v0.4 builder leaks private state.

### P3. Save/load is working and hash-checked

Alpha embeds the v0.4 registry checkpoint and verifies its envelope before restore ([savegame.py:92](C:\Users\orinzheng\Documents\Codex\2026-10-28\magpie-codex-deepseek-17-21-codex\pmw-engine-v2\examples\pmw_alpha\savegame.py#L92), [savegame.py:127](C:\Users\orinzheng\Documents\Codex\2026-10-28\magpie-codex-deepseek-17-21-codex\pmw-engine-v2\examples\pmw_alpha\savegame.py#L127)). The checkpoint contains world state, blueprints, and trusted runtime configuration, and rejects hash/static-law mismatches ([checkpoint.py:25](C:\Users\orinzheng\Documents\Codex\2026-10-28\magpie-codex-deepseek-17-21-codex\pmw-engine-v2\experiments\generative_mechanics\next_tracks_v06\gameplay_v04\checkpoint.py#L25), [checkpoint.py:68](C:\Users\orinzheng\Documents\Codex\2026-10-28\magpie-codex-deepseek-17-21-codex\pmw-engine-v2\experiments\generative_mechanics\next_tracks_v06\gameplay_v04\checkpoint.py#L68)).

Verified round trip after crafting, equipping, casting, and unlocking the lift: `WorldState` documents matched exactly, registry entries matched, and Alpha’s flag-derived route behavior survived. The caveat is that the route link was never represented as a real Relation, so save/load cannot be said to round-trip a link that Alpha never creates.

## Contract Matrix: What Alpha Actually Exposes

| Contract surface | Status | Evidence |
|---|---|---|
| Six object kinds | Defined in v0.6, not exposed by Alpha | `contracts.py:11` |
| Seven operators | Defined/tested in v0.6, not generated by Alpha | `contracts.py:12`; Alpha effects at `session.py:268` |
| Field dynamics | Working v0.4 prototype; linear and distance-squared | `dynamics.py:101`; focused tests passed |
| Action transaction | Public boundary atomic; private handlers are not | `session.py:76`; direct `_craft` reproduction |
| Blueprint/registry | Working v0.4 registry with canonical hash and checkpoint | `registry.py:144`; `checkpoint.py:25` |
| Observation authorization | Working v0.4 actor builder; Alpha bypasses it | `observation.py:96`; `session.py:213` |
| World tick | Production `pmw:v04:clock`; advances gameplay step/sim time | `content.py:162`; `dynamics.py:109` |
| Process/Relation operators | No Alpha exposure | v0.6-only `OPERATOR_KINDS` |
| Full IR triggers/selectors | Reduced v0.4 surface | `skills.py:77`; `selectors.py:41` |
| Savegame | Working v0.4 hash-checked registry checkpoint | `savegame.py:92`; `checkpoint.py:68` |

## Prototype vs Production

- **Prototype:** the v0.6 operator research track is explicitly an implementation candidate, not a frozen benchmark ([README.md:8](C:\Users\orinzheng\Documents\Codex\2026-10-28\magpie-codex-deepseek-17-21-codex\pmw-engine-v2\experiments\generative_mechanics\next_tracks_v06\README.md#L8)).
- **Production Alpha path:** `examples/pmw_alpha` on v0.4 world/action/registry/time/checkpoint machinery. The production clock is `pmw:v04:clock`.
- **Prototype Alpha behavior:** booleans for lift/root-bridge lifecycle and player-facing hint prose. These are the concrete sources of the route and disclosure findings above.
- **Working production machinery reused by Alpha:** v0.4 selectors, staged time spending, canonical blueprints, registry changes, and checkpoint verification.

## Verification Performed

```text
python -m unittest examples.pmw_alpha.tests.test_session examples.pmw_alpha.tests.test_skills examples.pmw_alpha.tests.test_savegame
Ran 15 tests ... OK

python -m unittest <selected v0.4 dynamics/actions/observation/QA/time tests>
Ran 47 tests ... OK

python -m unittest discover -s experiments/generative_mechanics/next_tracks_v06/tests -p 'test_*.py'
Ran 170 tests ... OK
```

No provider calls were made. No source files were changed.

