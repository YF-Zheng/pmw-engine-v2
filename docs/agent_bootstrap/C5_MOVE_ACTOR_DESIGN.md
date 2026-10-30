# C5.1 Bounded Formal Actor Relocation (`move_actor`)

Architecture by Main. Queued after the P1 ten-scenario conformance checkpoint.
The formal conformance run classified scenario 1 (off-Area persistent change)
and scenario 7 (relation change alters supply/path) as PARTIAL. The shared
root cause is that no formal paid Action can relocate an Actor: only the
protected Alpha `session.py::_travel` rewrites `located_in` privately, and no
formal consumer reads a Relation's `effective_enabled` for traversal. This
increment adds one closed Effect kind that moves the acting Actor to one
authorized adjacent Area through real Core lifecycle Laws, and makes that
traversal respect the C3 link overlay when (and only when) the adjacency
Relation carries the trusted `pmw_gameplay_link` component.

This is mechanics support only. Alpha is protected and keeps its private
travel; no Alpha/UI/playtest claim, no generic path solver, no topology
creation/deletion of `adjacent` edges, no push/pull of other Actors, no
teleport, no multi-step route, no provider generation.

## Request Shape

`ActionRequest` gains one trailing optional field `target_area_id: str | None
= None`. Positional meaning/defaults of the four existing fields are unchanged,
so hooks/combat/legal-action/Alpha/storm callers keep working.
`parse_action_request` accepts the optional `target_area_id` key with the same
`_ID` grammar; null/absent means None. The Action event payload adds a
`target_area_id` key ONLY when it is not None, so every existing Action
payload/trace stays byte-identical.

A request carrying `target_area_id` for an Action without a `move_actor`
Effect is rejected before any cost/time. An Action with `move_actor` requires
a `target_area_id`.

## Effect Schema

Closed kind `move_actor`. Raw fields are exactly the common
`id, kind, target, commitment` (no `condition`, `attribute_terms`,
`targeting`, amount, duration or other extras; unknown keys reject).
`target` must be `{"kind": "adjacent_area"}`; `commitment` must be
`required`. Add it to `EFFECT_KINDS` (append at the end, no reordering).
No new EffectSpec fields are needed. Material budget base cost `2.0` in
`skills.py`. Active `on_use` Skills only; passive/hook use rejects at parse
and at runtime (`execution_kind != "primary"` rejects like other world
writers). Materials must explicitly authorize the kind and the
`adjacent_area` selector through the existing capability path; do not edit
`materials.py` unless Main approves a concrete blocker.

Action-level restrictions enforced at Action parse (actions.py) AND at Skill
parse where Skill effects are validated:
- at most one `move_actor` Effect per Action;
- an Action with `move_actor` may additionally contain only actor-local or
  direct Field-write kinds: `heal, shield, add_resource, apply_status,
  grant_trait, modify_field, modify_attractor, modify_rate,
  dynamics_modifier`. It may NOT contain `damage` (hook cascade after the move),
  `process_start`, `process_modify`, `drive_source` or `relation_modifier`
  (their downstream Laws bind the actor location in later cascade events and
  would observe the moved actor). These are honest bounded restrictions.

All Effect selectors in the Action, including `current_area`, resolve against
the pre-action staged state; i.e. other Effects apply to the ORIGIN Area.

## Runtime Preparation (staged, before publication/cost/Tick)

In `_resolve_action`, for a `move_actor` Effect resolve `adjacent_area`
through the existing capability-checked selector, then filter to exactly
`request.target_area_id`; missing/not-adjacent rejects with
`GameplayContractError` and no mutation. Additionally:
- the actor has exactly one current `located_in` relation (reuse selector
  rule) and destination != origin, destination entity has
  `pmw_gameplay_area`;
- traversal authorization: among ALL `adjacent` relations joining origin and
  destination (either direction), at least one is traversable. A relation is
  traversable if it has no `pmw_gameplay_link` component, or its component
  `effective_enabled is True`. A disabled C3 overlay on the only joining link
  therefore blocks movement; enabling it (or base enabled) permits it.
  Malformed link components reject (do not treat as bare);
- new relation id `located:{actor_id}:{destination}` must not already exist
  as a Relation or Entity id;
- the effect outcome `values` contain exactly `origin_area_id`,
  `destination_area_id`, `old_relation_id`, `new_relation_id`, and
  `via_relation_ids` (sorted traversable joining ids). JSON-serializable.

## Lowering (action_compiler.py)

Two event Laws per `move_actor` Effect, both guarded by the common
action/hash/`status == applied` conditions, `$event.payload.execution_kind ==
primary`, actor id == `$event.source`:
1. delete: bindings `actor` entity requiring `pmw_gameplay_actor`, `loc`
   relation of type `located_in` with source `$actor`; when also
   `$loc.id == values.old_relation_id` and `$loc.target ==
   values.origin_area_id`; effect `{"op":"delete_relation","target":"$loc"}`.
2. create: binding `actor`; effect `create_relation` with value
   `{"id": values.new_relation_id, "type": "located_in", "source":
   "$event.source", "target": values.destination_area_id}`.
Use the existing binding grammar (see `relations.py` relation bindings) and
Core `create_relation`/`delete_relation` ops validated by `validate_laws`.
Do not mutate relations from Python; only accepted Engine lifecycle deltas
prove the move. After `run_event`, verify that exactly one `located_in` for
the actor exists and targets the destination; otherwise raise so the staged
session is discarded (no partial publication).

## Proposed Write Ownership

Owner (DeepSeek Flash): `gameplay_v04/effects.py`, `skills.py`,
`actions.py`, `action_compiler.py` and NEW
`gameplay_v04/tests/test_sandbox_move_actor.py`. No edits to `selectors.py`,
`materials.py`, `hooks.py`, `legal_actions.py`, `relations.py`, Engine
`src/`, Alpha, Core files, old tests, Observation, global config.
Independent QA: NEW `gameplay_v04/tests/test_sandbox_move_actor_review.py`,
`docs/agent_bootstrap/C5_MOVE_ACTOR_REVIEW.md`, `evidence/c5_move_review*`.
Main: design, baseline, probes, frozen regression, accounting, checkpoint.

## Required Real Acceptance Evidence

- Same parsed/equipped Skill for player and NPC through real registry,
  `change_loadout(equip_active)` and `submit_timed_primary_action`: actor
  moves A->B, Mana/time paid once, exactly one `located_in` afterwards, Engine
  trace shows accepted delete+create lifecycle changes, paid World Tick then
  runs with the actor in B (e.g. Area-scoped Law/selector sees B).
- Scenario-1 style: apply a dynamics/field effect in A, move away in a later
  paid Action, A keeps evolving over Ticks without the actor present.
- C3 overlay: with the only A-B adjacency link disabled by a real paid
  `relation_modifier`, move rejects atomically; after expiry (or with base
  enabled) the same request succeeds. A bare adjacency relation is
  traversable; a second enabled parallel link keeps the path open.
- Rejections with zero publication/cost/time/revision/schedule change:
  missing/unknown/non-adjacent/same-Area target, target_area_id on non-move
  Action, missing target on move Action, unauthorized selector capability,
  hook/passive use, forbidden effect combinations, duplicate move, extra raw
  keys, wrong target/commitment, relation id collision, zero/two
  `located_in`.
- Checkpoint save/load/rebuild preserves Action/Skill hashes and the moved
  location; old Action payload bytes unchanged for requests without
  `target_area_id`.
- All accepted old tests, Core 23 and Alpha 13 files byte-identical; full
  frozen cross-module suite; independent review before checkpoint.

Do not claim Alpha travel integration, NPC legal-action enumeration of move
targets (`legal_actions.py` does not enumerate areas in this slice), a path
solver, complete Relation language or complete P1.
