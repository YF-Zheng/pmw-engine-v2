from __future__ import annotations

from copy import deepcopy
import unittest

from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.actions import (
    ActionRegistry,
    ActionRequest,
    submit_timed_primary_action,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.basics import (
    basic_registry,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.content_compiler import (
    build_content_session,
    compile_content,
    initialize_content_world,
    make_content,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.contracts import (
    GameplayContractError,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.derived import (
    DERIVED_COMPONENT,
    parse_derived_spec,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.loadout import (
    change_loadout,
    skill_ref,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.registry import (
    MechanismRegistryRuntime,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.runtime import (
    advance_world_tick,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.tests.test_p1_scenarios import (
    AREA,
    MATERIAL_ID as P1_MATERIAL_ID,
    NPC,
    PLAYER,
    _actor_state,
    _budget,
    _field,
    _field_state,
    _skill,
    _skill_raw,
    _world,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.tests.test_sandbox_move_actor import (
    AREA_A,
    AREA_B,
    MATERIAL_ID as MOVE_MATERIAL_ID,
    NPC as MOVE_NPC,
    PLAYER as MOVE_PLAYER,
    _actor_state as _move_actor_state,
    _budget as _move_budget,
    _control_world,
    _field_state as _move_field_state,
    _locations,
    _move_effect,
    _move_world,
    _profile,
    _skill as _parse_move_skill,
    _skill_document as _move_skill_document,
    _snapshot,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.relations import (
    RELATION_COMPONENT,
    RelationController,
)


REVIEW_ATTRACTOR = "review_orbit_stiffness"
REVIEW_MOVE = "review_cross_adjacent"
REVIEW_LINK = "review_link_authority"
REVIEW_OPENER = "review_humidity_step"
REVIEW_LOWER = "review_humidity_drop"
REVIEW_GATE = "review_area_threshold_gate"


def _runtime(
    world,
    skills,
    *,
    relation_controller=None,
    derived_by_area=None,
):
    base = ActionRegistry(
        basic_registry().actions.values(),
        basic_registry().statuses.values(),
        relation_controller=relation_controller,
    )
    content = make_content(
        base,
        skills=skills,
        material_ids=(P1_MATERIAL_ID, MOVE_MATERIAL_ID),
        relation_controller=relation_controller,
        derived_by_area=derived_by_area,
    )
    initialized = initialize_content_world(world, content)
    compiled = compile_content(content)
    session = build_content_session(initialized, compiled)
    runtime = MechanismRegistryRuntime.from_compiled_content(session, compiled)
    actor_ids = (
        MOVE_PLAYER
        if any(actor_id in world.entities for actor_id in (MOVE_PLAYER, MOVE_NPC))
        else PLAYER
    )
    npc_id = MOVE_NPC if actor_ids == MOVE_PLAYER else NPC
    for actor_id in (actor_ids, npc_id):
        for slot, skill in enumerate(skills):
            change_loadout(
                runtime.session,
                runtime.manifest,
                actor_id=actor_id,
                operation="equip_active",
                skill=skill_ref(skill),
                slot=slot,
            )
    return runtime


def _attractor_skill():
    return _skill(_skill_raw(
        REVIEW_ATTRACTOR,
        [{
            "id": "stiffen_humidity",
            "kind": "modify_attractor",
            "target": {"kind": "current_area"},
            "commitment": "required",
            "field_id": "humidity",
            "amount": 0.4,
            "duration": 10,
        }],
        duration=1,
        mana=5.0,
        budget=8.0,
    ))


def _move_skill():
    return _parse_move_skill(
        _move_skill_document(REVIEW_MOVE, [_move_effect()])
    )


def _link_skill():
    return _skill(_skill_raw(
        REVIEW_LINK,
        [{
            "id": "close_review_link",
            "kind": "relation_modifier",
            "target": {"kind": "current_area"},
            "commitment": "required",
            "relation_profile_id": "move_link_control",
            "relation_enabled": False,
            "duration": 3,
        }],
        duration=1,
        mana=1.0,
        budget=8.0,
        relations=("adjacent",),
    ))


def _opener_skill():
    return _skill(_skill_raw(
        REVIEW_OPENER,
        [{
            "id": "raise_humidity",
            "kind": "modify_field",
            "target": {"kind": "current_area"},
            "commitment": "required",
            "field_id": "humidity",
            "amount": 0.3,
        }],
        duration=1,
        mana=3.0,
        budget=4.0,
    ))


def _lower_skill():
    return _skill(_skill_raw(
        REVIEW_LOWER,
        [{
            "id": "lower_humidity",
            "kind": "modify_field",
            "target": {"kind": "current_area"},
            "commitment": "required",
            "field_id": "humidity",
            "amount": -0.1,
        }],
        duration=1,
        mana=2.0,
        budget=4.0,
    ))


def _gate_skill():
    return _skill(_skill_raw(
        REVIEW_GATE,
        [{
            "id": "derived_gate_shield",
            "kind": "shield",
            "target": {"kind": "self"},
            "commitment": "required",
            "amount": 1.0,
        }],
        condition={"derived": {
            "subject": "current_area",
            "key": "humid",
            "comparator": "gte",
            "value": 0.5,
        }},
        duration=1,
        mana=4.0,
        budget=5.0,
    ))


def _location(runtime, actor_id):
    return [relation.target for relation in _locations(runtime, actor_id)]


def _derived_values(runtime, area_id=AREA):
    return runtime.session.state.entities[area_id].components[
        DERIVED_COMPONENT
    ]["values"]


def _state_change_rows(event_result, entity_id, component, prefix=""):
    address_prefix = f"entity:{entity_id}/{component}/"
    rows = []
    for event in event_result.trace.events:
        for commit in event.commits:
            for delta in commit.state_deltas:
                address = str(delta.address)
                if address.startswith(address_prefix):
                    suffix = address[len(address_prefix):]
                    if suffix.startswith(prefix):
                        rows.append((
                            suffix[len(prefix):],
                            delta.old_value,
                            delta.new_value,
                        ))
    return rows


def _registry_identity(runtime):
    return (
        tuple(
            (
                entry.skill_id,
                entry.version,
                entry.canonical_hash,
                entry.kind,
                entry.enabled,
            )
            for entry in runtime.manifest.entries
        ),
        tuple(sorted(
            (key, blueprint.canonical_hash)
            for key, blueprint in runtime.blueprints.items()
        )),
        tuple(sorted(
            (key, action.canonical_hash)
            for key, action in runtime.action_registry.actions.items()
        )),
    )


class CompletionConformanceReviewTests(unittest.TestCase):
    def test_review_scenario01_attractor_counterfactual_while_off_area(self):
        attractor = _attractor_skill()
        move = _move_skill()

        for actor_id in (MOVE_PLAYER, MOVE_NPC):
            with self.subTest(actor_id=actor_id):
                active = _runtime(
                    _move_world(links=(("review_bare_link", None),)),
                    (attractor, move),
                )
                first = submit_timed_primary_action(
                    active.session,
                    active.action_registry,
                    ActionRequest(f"review_bias_{actor_id}", actor_id, attractor.id),
                )
                self.assertEqual(first.time.duration, 1)
                self.assertAlmostEqual(
                    _move_field_state(active, AREA_A)["diagnostics"][
                        "effective_target"
                    ],
                    0.6,
                    delta=1e-12,
                )
                self.assertAlmostEqual(
                    _move_field_state(active, AREA_A)["value"],
                    0.28,
                    delta=1e-12,
                )

                left = submit_timed_primary_action(
                    active.session,
                    active.action_registry,
                    ActionRequest(
                        f"review_leave_{actor_id}",
                        actor_id,
                        move.id,
                        None,
                        AREA_B,
                    ),
                )
                self.assertEqual(left.time.duration, 1)
                self.assertEqual(_location(active, actor_id), [AREA_B])
                self.assertAlmostEqual(
                    _move_field_state(active, AREA_A)["value"],
                    0.344,
                    delta=1e-12,
                )
                self.assertEqual(_move_actor_state(active, actor_id)["mana"], 11.0)
                self.assertEqual(_move_budget(active)["spent_ticks"], 2)
                for expected in (0.3952, 0.43616, 0.468928):
                    advance_world_tick(active.session)
                    self.assertAlmostEqual(
                        _move_field_state(active, AREA_A)["value"],
                        expected,
                        delta=1e-12,
                    )
                    self.assertEqual(_location(active, actor_id), [AREA_B])
                self.assertAlmostEqual(
                    _move_field_state(active, AREA_A)["value"],
                    0.468928,
                    delta=1e-12,
                )

                control = _runtime(
                    _move_world(links=(("review_bare_link", None),)),
                    (move,),
                )
                # A paid no-field action consumes the same first Tick, so the
                # only causal difference is the absent attractor Skill.
                submit_timed_primary_action(
                    control.session,
                    control.action_registry,
                    ActionRequest(
                        f"review_control_wait_{actor_id}",
                        actor_id,
                        "basic_wait",
                    ),
                )
                submit_timed_primary_action(
                    control.session,
                    control.action_registry,
                    ActionRequest(
                        f"review_control_leave_{actor_id}",
                        actor_id,
                        move.id,
                        None,
                        AREA_B,
                    ),
                )
                self.assertAlmostEqual(
                    _move_field_state(control, AREA_A)["diagnostics"][
                        "effective_target"
                    ],
                    0.8,
                    delta=1e-12,
                )
                self.assertEqual(_location(control, actor_id), [AREA_B])
                self.assertAlmostEqual(
                    _move_field_state(control, AREA_A)["value"],
                    0.416,
                    delta=1e-12,
                )
                for expected in (0.4928, 0.55424, 0.603392):
                    advance_world_tick(control.session)
                    self.assertAlmostEqual(
                        _move_field_state(control, AREA_A)["value"],
                        expected,
                        delta=1e-12,
                    )
                self.assertAlmostEqual(
                    _move_field_state(control, AREA_A)["value"],
                    0.603392,
                    delta=1e-12,
                )
                self.assertAlmostEqual(
                    _move_field_state(control, AREA_A)["value"]
                    - _move_field_state(active, AREA_A)["value"],
                    0.134464,
                    delta=1e-12,
                )

    def test_review_scenario07_overlay_is_only_cause_and_rejection_is_atomic(self):
        control = _link_skill()
        move = _move_skill()

        for actor_id in (MOVE_PLAYER, MOVE_NPC):
            with self.subTest(actor_id=actor_id):
                profile = _profile(actor_id)
                controller = RelationController((profile,))
                runtime = _runtime(
                    _control_world(profile=profile, base_enabled=True),
                    (control, move),
                    relation_controller=controller,
                )
                initial_link = runtime.session.state.relations[
                    profile.relation_id
                ].components[RELATION_COMPONENT]
                self.assertIs(initial_link["effective_enabled"], True)

                # No-overlay control: the same parsed move succeeds unchanged.
                baseline = _runtime(
                    _control_world(profile=profile, base_enabled=True),
                    (move,),
                    relation_controller=RelationController((profile,)),
                )
                moved_control = submit_timed_primary_action(
                    baseline.session,
                    baseline.action_registry,
                    ActionRequest(
                        f"review_no_overlay_{actor_id}",
                        actor_id,
                        move.id,
                        None,
                        AREA_B,
                    ),
                )
                self.assertEqual(moved_control.time.duration, 1)
                self.assertEqual(_location(baseline, actor_id), [AREA_B])
                self.assertEqual(_move_actor_state(baseline, actor_id)["mana"], 16.0)

                disabled = submit_timed_primary_action(
                    runtime.session,
                    runtime.action_registry,
                    ActionRequest(
                        f"review_disable_{actor_id}",
                        actor_id,
                        control.id,
                    ),
                )
                self.assertEqual(disabled.time.duration, 1)
                link = runtime.session.state.relations[
                    profile.relation_id
                ].components[RELATION_COMPONENT]
                self.assertIs(link["effective_enabled"], False)
                self.assertEqual(link["expires_at"], 3.0)
                self.assertEqual(_move_actor_state(runtime, actor_id)["mana"], 19.0)
                self.assertEqual(_move_budget(runtime)["spent_ticks"], 1)

                before = _snapshot(runtime)
                registry_before = _registry_identity(runtime)
                with self.assertRaisesRegex(
                    GameplayContractError, "path is disabled"
                ):
                    submit_timed_primary_action(
                        runtime.session,
                        runtime.action_registry,
                        ActionRequest(
                            f"review_blocked_{actor_id}",
                            actor_id,
                            move.id,
                            None,
                            AREA_B,
                        ),
                    )
                self.assertEqual(_snapshot(runtime), before)
                self.assertEqual(_registry_identity(runtime), registry_before)
                self.assertEqual(_move_actor_state(runtime, actor_id)["mana"], 19.0)
                self.assertEqual(_move_budget(runtime)["spent_ticks"], 1)
                self.assertEqual(_location(runtime, actor_id), [AREA_A])

                for _ in range(2):
                    advance_world_tick(runtime.session)
                link = runtime.session.state.relations[
                    profile.relation_id
                ].components[RELATION_COMPONENT]
                self.assertIs(link["effective_enabled"], True)
                allowed = submit_timed_primary_action(
                    runtime.session,
                    runtime.action_registry,
                    ActionRequest(
                        f"review_after_expiry_{actor_id}",
                        actor_id,
                        move.id,
                        None,
                        AREA_B,
                    ),
                )
                self.assertEqual(allowed.time.duration, 1)
                self.assertEqual(_location(runtime, actor_id), [AREA_B])
                self.assertEqual(_move_actor_state(runtime, actor_id)["mana"], 15.0)
                self.assertEqual(_move_budget(runtime)["spent_ticks"], 2)

    def test_review_scenario09_boundary_crossings_are_exact_for_both_controllers(self):
        weighted = parse_derived_spec({
            "id": "comfort",
            "kind": "weighted_sum",
            "terms": [["humidity", 2.0]],
            "bias": 0.0,
            "minimum": 0.0,
            "maximum": 2.0,
        })
        threshold = parse_derived_spec({
            "id": "humid",
            "kind": "threshold",
            "field_id": "humidity",
            "comparator": "gte",
            "value": 0.5,
        })
        derived_by_area = {AREA: (weighted, threshold)}
        opener = _opener_skill()
        gate = _gate_skill()

        for actor_id in (PLAYER, NPC):
            with self.subTest(actor_id=actor_id):
                runtime = _runtime(
                    _world([
                        _field(
                            "humidity",
                            initial=0.2,
                            target=0.8,
                            rate=0.2,
                        )
                    ]),
                    (opener, gate),
                    derived_by_area=derived_by_area,
                )
                self.assertAlmostEqual(
                    _derived_values(runtime)["comfort"], 0.4, delta=1e-12
                )
                self.assertEqual(_derived_values(runtime)["humid"], 0.0)

                gate_request = ActionRequest(
                    f"review_gate_early_{actor_id}", actor_id, gate.id
                )
                before = (
                    deepcopy(runtime.session.state.to_dict()),
                    _actor_state(runtime, actor_id)["mana"],
                    _budget(runtime)["spent_ticks"],
                )
                with self.assertRaisesRegex(
                    GameplayContractError,
                    "^action condition is not satisfied$",
                ):
                    submit_timed_primary_action(
                        runtime.session,
                        runtime.action_registry,
                        gate_request,
                    )
                self.assertEqual(
                    (
                        runtime.session.state.to_dict(),
                        _actor_state(runtime, actor_id)["mana"],
                        _budget(runtime)["spent_ticks"],
                    ),
                    before,
                )

                # 0.2 + 0.3 = 0.5 exactly, so gte flips at the boundary.
                opened = submit_timed_primary_action(
                    runtime.session,
                    runtime.action_registry,
                    ActionRequest(
                        f"review_open_{actor_id}", actor_id, opener.id
                    ),
                )
                self.assertEqual(opened.time.duration, 1)
                field_rows = _state_change_rows(
                    opened.action.event_result,
                    AREA,
                    "pmw_gameplay_dynamics",
                    "fields/humidity/value",
                )
                self.assertEqual(len(field_rows), 1)
                self.assertAlmostEqual(field_rows[0][1], 0.2, delta=1e-12)
                self.assertAlmostEqual(field_rows[0][2], 0.5, delta=1e-12)
                derived_rows = _state_change_rows(
                    opened.action.event_result,
                    AREA,
                    DERIVED_COMPONENT,
                    "values/",
                )
                comfort_rows = [
                    row for row in derived_rows if row[0] == "comfort"
                ]
                humid_rows = [
                    row for row in derived_rows if row[0] == "humid"
                ]
                self.assertEqual(len(comfort_rows), 1)
                self.assertEqual(len(humid_rows), 1)
                self.assertAlmostEqual(comfort_rows[0][1], 0.4, delta=1e-12)
                self.assertAlmostEqual(comfort_rows[0][2], 1.0, delta=1e-12)
                self.assertEqual(humid_rows[0][1:], (0.0, 1.0))
                self.assertAlmostEqual(
                    _derived_values(runtime)["comfort"], 1.12, delta=1e-12
                )
                self.assertEqual(_derived_values(runtime)["humid"], 1.0)

                # The paid Tick moves 0.5 -> 0.56, and Derived follows exactly.
                self.assertAlmostEqual(
                    _field_state(runtime, AREA)["value"], 0.56, delta=1e-12
                )
                self.assertAlmostEqual(
                    _derived_values(runtime)["comfort"], 1.12, delta=1e-12
                )
                self.assertEqual(_derived_values(runtime)["humid"], 1.0)
                self.assertEqual(_actor_state(runtime, actor_id)["mana"], 27.0)
                self.assertEqual(_budget(runtime)["spent_ticks"], 1)

                advance_world_tick(runtime.session)
                self.assertAlmostEqual(
                    _field_state(runtime, AREA)["value"], 0.608, delta=1e-12
                )
                self.assertAlmostEqual(
                    _derived_values(runtime)["comfort"], 1.216, delta=1e-12
                )
                self.assertEqual(_derived_values(runtime)["humid"], 1.0)

                advance_world_tick(runtime.session)
                self.assertAlmostEqual(
                    _field_state(runtime, AREA)["value"], 0.6464, delta=1e-12
                )
                self.assertAlmostEqual(
                    _derived_values(runtime)["comfort"], 1.2928, delta=1e-12
                )
                self.assertEqual(_derived_values(runtime)["humid"], 1.0)

                accepted = submit_timed_primary_action(
                    runtime.session,
                    runtime.action_registry,
                    gate_request,
                )
                self.assertEqual(accepted.time.duration, 1)
                self.assertEqual(_actor_state(runtime, actor_id)["mana"], 23.0)
                self.assertEqual(_actor_state(runtime, actor_id)["shield"], 1.0)
                self.assertEqual(_budget(runtime)["spent_ticks"], 2)

    def test_review_scenario09_gate_exact_boundary_and_epsilon_below(self):
        weighted = parse_derived_spec({
            "id": "comfort",
            "kind": "weighted_sum",
            "terms": [["humidity", 2.0]],
            "bias": 0.0,
            "minimum": 0.0,
            "maximum": 2.0,
        })
        threshold = parse_derived_spec({
            "id": "humid",
            "kind": "threshold",
            "field_id": "humidity",
            "comparator": "gte",
            "value": 0.5,
        })
        derived_by_area = {AREA: (weighted, threshold)}
        gate = _gate_skill()

        for actor_id in (PLAYER, NPC):
            with self.subTest(actor_id=actor_id, boundary="exact"):
                runtime = _runtime(
                    _world([
                        _field(
                            "humidity",
                            initial=0.5,
                            target=0.8,
                            rate=0.0,
                            curve="none",
                        )
                    ]),
                    (gate,),
                    derived_by_area=derived_by_area,
                )
                self.assertAlmostEqual(
                    _derived_values(runtime)["comfort"], 1.0, delta=1e-12
                )
                self.assertEqual(_derived_values(runtime)["humid"], 1.0)
                accepted = submit_timed_primary_action(
                    runtime.session,
                    runtime.action_registry,
                    ActionRequest(
                        f"review_exact_gate_{actor_id}", actor_id, gate.id
                    ),
                )
                self.assertEqual(accepted.time.duration, 1)
                self.assertEqual(_actor_state(runtime, actor_id)["shield"], 1.0)
                self.assertEqual(_budget(runtime)["spent_ticks"], 1)

            with self.subTest(actor_id=actor_id, boundary="epsilon_below"):
                runtime = _runtime(
                    _world([
                        _field(
                            "humidity",
                            initial=0.499999999999,
                            target=0.8,
                            rate=0.0,
                            curve="none",
                        )
                    ]),
                    (gate,),
                    derived_by_area=derived_by_area,
                )
                self.assertEqual(_derived_values(runtime)["humid"], 0.0)
                before = (
                    deepcopy(runtime.session.state.to_dict()),
                    _actor_state(runtime, actor_id)["mana"],
                    _budget(runtime)["spent_ticks"],
                )
                with self.assertRaisesRegex(
                    GameplayContractError,
                    "^action condition is not satisfied$",
                ):
                    submit_timed_primary_action(
                        runtime.session,
                        runtime.action_registry,
                        ActionRequest(
                            f"review_below_gate_{actor_id}",
                            actor_id,
                            gate.id,
                        ),
                    )
                self.assertEqual(
                    (
                        runtime.session.state.to_dict(),
                        _actor_state(runtime, actor_id)["mana"],
                        _budget(runtime)["spent_ticks"],
                    ),
                    before,
                )

    def test_review_scenario09_threshold_closes_after_downward_crossing(self):
        weighted = parse_derived_spec({
            "id": "comfort",
            "kind": "weighted_sum",
            "terms": [["humidity", 2.0]],
            "bias": 0.0,
            "minimum": 0.0,
            "maximum": 2.0,
        })
        threshold = parse_derived_spec({
            "id": "humid",
            "kind": "threshold",
            "field_id": "humidity",
            "comparator": "gte",
            "value": 0.5,
        })
        derived_by_area = {AREA: (weighted, threshold)}
        lower = _lower_skill()
        gate = _gate_skill()

        for actor_id in (PLAYER, NPC):
            with self.subTest(actor_id=actor_id):
                runtime = _runtime(
                    _world([
                        _field(
                            "humidity",
                            initial=0.6,
                            target=0.8,
                            rate=0.0,
                            curve="none",
                        )
                    ]),
                    (lower, gate),
                    derived_by_area=derived_by_area,
                )
                self.assertAlmostEqual(
                    _derived_values(runtime)["comfort"], 1.2, delta=1e-12
                )
                self.assertEqual(_derived_values(runtime)["humid"], 1.0)

                accepted = submit_timed_primary_action(
                    runtime.session,
                    runtime.action_registry,
                    ActionRequest(
                        f"review_gate_high_{actor_id}", actor_id, gate.id
                    ),
                )
                self.assertEqual(accepted.time.duration, 1)
                self.assertEqual(_actor_state(runtime, actor_id)["shield"], 1.0)

                at_boundary = submit_timed_primary_action(
                    runtime.session,
                    runtime.action_registry,
                    ActionRequest(
                        f"review_lower_to_boundary_{actor_id}",
                        actor_id,
                        lower.id,
                    ),
                )
                field_rows = _state_change_rows(
                    at_boundary.action.event_result,
                    AREA,
                    "pmw_gameplay_dynamics",
                    "fields/humidity/value",
                )
                self.assertEqual(len(field_rows), 1)
                self.assertAlmostEqual(field_rows[0][1], 0.6, delta=1e-12)
                self.assertAlmostEqual(field_rows[0][2], 0.5, delta=1e-12)
                self.assertAlmostEqual(
                    _field_state(runtime, AREA)["value"], 0.5, delta=1e-12
                )
                self.assertAlmostEqual(
                    _derived_values(runtime)["comfort"], 1.0, delta=1e-12
                )
                self.assertEqual(_derived_values(runtime)["humid"], 1.0)

                below = submit_timed_primary_action(
                    runtime.session,
                    runtime.action_registry,
                    ActionRequest(
                        f"review_lower_below_{actor_id}", actor_id, lower.id
                    ),
                )
                derived_rows = _state_change_rows(
                    below.action.event_result,
                    AREA,
                    DERIVED_COMPONENT,
                    "values/",
                )
                humid_rows = [
                    row for row in derived_rows if row[0] == "humid"
                ]
                self.assertEqual(humid_rows, [("humid", 1.0, 0.0)])
                self.assertAlmostEqual(
                    _field_state(runtime, AREA)["value"], 0.4, delta=1e-12
                )
                self.assertEqual(_derived_values(runtime)["humid"], 0.0)

                current_mana = _actor_state(runtime, actor_id)["mana"]
                current_ticks = _budget(runtime)["spent_ticks"]
                before = (
                    deepcopy(runtime.session.state.to_dict()),
                    current_mana,
                    current_ticks,
                )
                with self.assertRaisesRegex(
                    GameplayContractError,
                    "^action condition is not satisfied$",
                ):
                    submit_timed_primary_action(
                        runtime.session,
                        runtime.action_registry,
                        ActionRequest(
                            f"review_gate_after_drop_{actor_id}",
                            actor_id,
                            gate.id,
                        ),
                    )
                self.assertEqual(
                    (
                        runtime.session.state.to_dict(),
                        _actor_state(runtime, actor_id)["mana"],
                        _budget(runtime)["spent_ticks"],
                    ),
                    before,
                )


if __name__ == "__main__":
    unittest.main()
