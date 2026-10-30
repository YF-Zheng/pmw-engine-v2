from __future__ import annotations

from copy import deepcopy
from pathlib import Path
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
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.relations import (
    RELATION_COMPONENT,
    RelationController,
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
    PLAYER as MOVE_PLAYER,
    NPC as MOVE_NPC,
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


ATTRACTOR_SKILL = "p1c_orbit_bias"
MOVE_SKILL = "p1c_leave_return"
LINK_CONTROL_SKILL = "p1c_link_control"
DERIVED_OPENER_SKILL = "p1c_derived_opener"
DERIVED_GATE_SKILL = "p1c_derived_gate"
SKILL_IDS = (
    ATTRACTOR_SKILL,
    MOVE_SKILL,
    LINK_CONTROL_SKILL,
    DERIVED_OPENER_SKILL,
    DERIVED_GATE_SKILL,
)


def _formal_runtime(
    world,
    skills: tuple,
    *,
    equip_actors: tuple[str, str],
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
    for actor_id in equip_actors:
        for slot, skill in enumerate(skills):
            change_loadout(
                runtime.session,
                runtime.manifest,
                actor_id=actor_id,
                operation="equip_active",
                skill=skill_ref(skill),
                slot=slot,
            )
    return runtime, compiled


def _assert_shared_blueprints(testcase, runtime, skills):
    for skill in skills:
        testcase.assertEqual(
            runtime.blueprints[(skill.id, skill.version)].canonical_hash,
            skill.canonical_hash,
        )
        testcase.assertEqual(
            runtime.action_registry.actions[skill.id].canonical_hash,
            skill.action.canonical_hash,
        )


def _parsed_move_skill():
    return _parse_move_skill(
        _move_skill_document(MOVE_SKILL, [_move_effect()])
    )


def _parsed_attractor_skill():
    return _skill(_skill_raw(
        ATTRACTOR_SKILL,
        [{
            "id": "bias_humidity",
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


def _parsed_link_control():
    return _skill(_skill_raw(
        LINK_CONTROL_SKILL,
        [{
            "id": "disable_link",
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


def _parsed_derived_opener():
    return _skill(_skill_raw(
        DERIVED_OPENER_SKILL,
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


def _parsed_derived_gate():
    return _skill(_skill_raw(
        DERIVED_GATE_SKILL,
        [{
            "id": "gated_shield",
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


def _derived_values(runtime, area_id=AREA):
    return runtime.session.state.entities[area_id].components[
        DERIVED_COMPONENT
    ]["values"]


def _derived_change_rows(outcome, area_id=AREA):
    prefix = f"entity:{area_id}/{DERIVED_COMPONENT}/values/"
    rows = []
    for event in outcome.event_result.trace.events:
        for commit in event.commits:
            for delta in commit.state_deltas:
                address = str(delta.address)
                if address.startswith(prefix):
                    rows.append((
                        address[len(prefix):],
                        delta.old_value,
                        delta.new_value,
                    ))
    return rows


def _derived_law_ids(outcome):
    return {
        match.law_id
        for event in outcome.event_result.trace.events
        for match in event.state_law_matches
        if match.law_id.startswith(f"pmw.v04.derived.{AREA}.")
    }


def _location_rows(runtime, actor_id):
    return [
        (relation.id, relation.target)
        for relation in _locations(runtime, actor_id)
    ]


class P1CompletionConformanceTests(unittest.TestCase):
    def test_scenario01_same_skills_leave_evolve_and_return(self):
        attractor = _parsed_attractor_skill()
        move = _parsed_move_skill()
        skills = (attractor, move)

        for actor_id in (MOVE_PLAYER, MOVE_NPC):
            with self.subTest(actor_id=actor_id):
                runtime, _ = _formal_runtime(
                    _move_world(links=(("p1c_bare_ab", None),)),
                    skills,
                    equip_actors=(MOVE_PLAYER, MOVE_NPC),
                )
                _assert_shared_blueprints(self, runtime, skills)
                self.assertAlmostEqual(
                    _move_field_state(runtime, AREA_A)["value"],
                    0.2,
                    delta=1e-12,
                )
                self.assertEqual(
                    _location_rows(runtime, actor_id),
                    [(f"located:{actor_id}:{AREA_A}", AREA_A)],
                )

                first = submit_timed_primary_action(
                    runtime.session,
                    runtime.action_registry,
                    ActionRequest(
                        f"p1c_attractor_{actor_id}", actor_id, attractor.id
                    ),
                )
                self.assertEqual(first.action.cost.mana, 5.0)
                self.assertEqual(
                    first.action.definition.canonical_hash,
                    attractor.action.canonical_hash,
                )
                self.assertEqual(first.time.duration, 1)
                # Target = (0.8 * 1 + 0.4 * 1) / (1 + 1) = 0.6.
                # The paid Tick gives 0.2 + 0.2 * (0.6 - 0.2) = 0.28.
                self.assertAlmostEqual(
                    _move_field_state(runtime, AREA_A)["value"],
                    0.28,
                    delta=1e-12,
                )
                self.assertEqual(_move_actor_state(runtime, actor_id)["mana"], 15.0)
                # The paid attractor Tick has completed.
                self.assertEqual(_move_budget(runtime)["spent_ticks"], 1)

                # Mana: 20 initial - 5 attractor = 15.
                leave_request = ActionRequest(
                    f"p1c_leave_{actor_id}", actor_id, move.id, None, AREA_B
                )
                left = submit_timed_primary_action(
                    runtime.session,
                    runtime.action_registry,
                    leave_request,
                )
                self.assertEqual(left.action.cost.mana, 4.0)
                self.assertEqual(
                    left.action.definition.canonical_hash,
                    move.action.canonical_hash,
                )
                self.assertEqual(left.time.duration, 1)
                # The move commits before its paid Tick. The actor is already in
                # B for this Tick: 0.28 + 0.2 * (0.6 - 0.28) = 0.344.
                self.assertAlmostEqual(
                    _move_field_state(runtime, AREA_A)["value"],
                    0.344,
                    delta=1e-12,
                )
                self.assertEqual(
                    _location_rows(runtime, actor_id),
                    [(f"located:{actor_id}:{AREA_B}", AREA_B)],
                )
                # Mana: 15 - 4 move = 11. Spent Ticks: 1 + 1 = 2.
                self.assertEqual(_move_budget(runtime)["spent_ticks"], 2)

                # Tick 3: 0.344 + 0.2 * (0.6 - 0.344) = 0.3952.
                # Tick 4: 0.3952 + 0.2 * (0.6 - 0.3952) = 0.43616.
                # Tick 5: 0.43616 + 0.2 * (0.6 - 0.43616) = 0.468928.
                expected_values = (0.3952, 0.43616, 0.468928)
                for expected in expected_values:
                    advance_world_tick(runtime.session)
                    self.assertAlmostEqual(
                        _move_field_state(runtime, AREA_A)["value"],
                        expected,
                        delta=1e-12,
                    )
                    self.assertEqual(
                        _location_rows(runtime, actor_id),
                        [(f"located:{actor_id}:{AREA_B}", AREA_B)],
                    )
                # Free Ticks do not spend finite world time.
                self.assertEqual(_move_budget(runtime)["spent_ticks"], 2)
                self.assertEqual(_move_budget(runtime)["remaining_ticks"], 18)

                before_return = _move_field_state(runtime, AREA_A)["value"]
                returned = submit_timed_primary_action(
                    runtime.session,
                    runtime.action_registry,
                    ActionRequest(
                        f"p1c_return_{actor_id}", actor_id, move.id, None, AREA_A
                    ),
                )
                self.assertEqual(returned.time.duration, 1)
                # The return move commits before its paid Tick:
                # 0.468928 + 0.2 * (0.6 - 0.468928) = 0.4951424.
                self.assertAlmostEqual(
                    _move_field_state(runtime, AREA_A)["value"],
                    0.4951424,
                    delta=1e-12,
                )
                self.assertGreater(
                    _move_field_state(runtime, AREA_A)["value"],
                    before_return,
                )
                self.assertEqual(
                    _location_rows(runtime, actor_id),
                    [(f"located:{actor_id}:{AREA_A}", AREA_A)],
                )
                # Mana: 11 - 4 return = 7. Spent Ticks: 2 + 1 = 3.
                self.assertEqual(_move_actor_state(runtime, actor_id)["mana"], 7.0)
                self.assertEqual(_move_budget(runtime)["spent_ticks"], 3)

    def test_scenario07_relation_overlay_blocks_then_expiry_allows_move(self):
        control = _parsed_link_control()
        move = _parsed_move_skill()
        skills = (control, move)

        for actor_id in (MOVE_PLAYER, MOVE_NPC):
            with self.subTest(actor_id=actor_id):
                profile = _profile(actor_id)
                controller = RelationController((profile,))
                runtime, _ = _formal_runtime(
                    _control_world(profile=profile, base_enabled=True),
                    skills,
                    equip_actors=(MOVE_PLAYER, MOVE_NPC),
                    relation_controller=controller,
                )
                _assert_shared_blueprints(self, runtime, skills)
                link = runtime.session.state.relations[
                    profile.relation_id
                ].components[RELATION_COMPONENT]
                self.assertIs(link["effective_enabled"], True)

                disabled = submit_timed_primary_action(
                    runtime.session,
                    runtime.action_registry,
                    ActionRequest(
                        f"p1c_disable_{actor_id}", actor_id, control.id
                    ),
                )
                self.assertEqual(disabled.time.duration, 1)
                self.assertEqual(
                    disabled.action.definition.canonical_hash,
                    control.action.canonical_hash,
                )
                link = runtime.session.state.relations[
                    profile.relation_id
                ].components[RELATION_COMPONENT]
                self.assertIs(link["effective_enabled"], False)
                self.assertEqual(link["expires_at"], 3.0)
                self.assertEqual(
                    _move_actor_state(runtime, actor_id)["mana"], 19.0
                )
                # Mana: 20 initial - 1 disable = 19.
                self.assertEqual(_move_budget(runtime)["spent_ticks"], 1)

                blocked = ActionRequest(
                    f"p1c_blocked_move_{actor_id}",
                    actor_id,
                    move.id,
                    None,
                    AREA_B,
                )
                before = _snapshot(runtime)
                with self.assertRaisesRegex(
                    GameplayContractError, "path is disabled"
                ):
                    submit_timed_primary_action(
                        runtime.session,
                        runtime.action_registry,
                        blocked,
                    )
                self.assertEqual(_snapshot(runtime), before)
                self.assertEqual(
                    _move_actor_state(runtime, actor_id)["mana"], 19.0
                )
                self.assertEqual(_move_budget(runtime)["spent_ticks"], 1)
                self.assertEqual(
                    _location_rows(runtime, actor_id),
                    [(f"located:{actor_id}:{AREA_A}", AREA_A)],
                )

                # The disable happened at time 0 with expiry 3. Its paid Tick
                # reached time 1, so two free Ticks reach time 3 and expire it.
                for _ in range(2):
                    advance_world_tick(runtime.session)
                link = runtime.session.state.relations[
                    profile.relation_id
                ].components[RELATION_COMPONENT]
                self.assertIs(link["effective_enabled"], True)
                # The paid disable Tick has completed; the two free Ticks do
                # not consume the finite exploration budget.
                self.assertEqual(_move_budget(runtime)["spent_ticks"], 1)

                moved = submit_timed_primary_action(
                    runtime.session,
                    runtime.action_registry,
                    blocked,
                )
                self.assertEqual(moved.time.duration, 1)
                self.assertEqual(
                    moved.action.definition.canonical_hash,
                    move.action.canonical_hash,
                )
                self.assertEqual(
                    _location_rows(runtime, actor_id),
                    [(f"located:{actor_id}:{AREA_B}", AREA_B)],
                )
                self.assertEqual(
                    _move_actor_state(runtime, actor_id)["mana"], 15.0
                )
                # Mana: 19 - 4 move = 15. Spent Ticks: 1 + 1 = 2.
                self.assertEqual(_move_budget(runtime)["spent_ticks"], 2)
                self.assertEqual(_move_budget(runtime)["remaining_ticks"], 18)

    def test_scenario09_derived_values_and_gate_follow_real_field_changes(self):
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
        opener = _parsed_derived_opener()
        gate = _parsed_derived_gate()
        skills = (opener, gate)

        for actor_id in (PLAYER, NPC):
            with self.subTest(actor_id=actor_id):
                runtime, _ = _formal_runtime(
                    _world([_field("humidity", initial=0.2, target=0.8, rate=0.2)]),
                    skills,
                    equip_actors=(PLAYER, NPC),
                    derived_by_area=derived_by_area,
                )
                _assert_shared_blueprints(self, runtime, skills)
                # Initial: comfort = 0 + 2 * 0.2 = 0.4;
                # humid = 0.0 because 0.2 >= 0.5 is false.
                self.assertAlmostEqual(
                    _derived_values(runtime)["comfort"], 0.4, delta=1e-12
                )
                self.assertEqual(_derived_values(runtime)["humid"], 0.0)

                gate_request = ActionRequest(
                    f"p1c_gate_{actor_id}", actor_id, gate.id
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

                opened = submit_timed_primary_action(
                    runtime.session,
                    runtime.action_registry,
                    ActionRequest(
                        f"p1c_open_{actor_id}", actor_id, opener.id
                    ),
                )
                self.assertEqual(opened.action.cost.mana, 3.0)
                self.assertEqual(
                    opened.action.definition.canonical_hash,
                    opener.action.canonical_hash,
                )
                self.assertEqual(opened.time.duration, 1)
                # The paid field write is 0.2 + 0.3 = 0.5 before the paid Tick.
                # In that same Action event: comfort = 2 * 0.5 = 1.0;
                # humid flips 0.0 -> 1.0 because 0.5 >= 0.5.
                rows = _derived_change_rows(opened.action)
                comfort_rows = [row for row in rows if row[0] == "comfort"]
                humid_rows = [row for row in rows if row[0] == "humid"]
                self.assertEqual(len(comfort_rows), 1)
                self.assertEqual(len(humid_rows), 1)
                self.assertAlmostEqual(comfort_rows[0][1], 0.4, delta=1e-12)
                self.assertAlmostEqual(comfort_rows[0][2], 1.0, delta=1e-12)
                self.assertEqual(humid_rows[0][1:], (0.0, 1.0))
                self.assertEqual(
                    _derived_law_ids(opened.action),
                    {
                        f"pmw.v04.derived.{AREA}.comfort.weighted_sum",
                        f"pmw.v04.derived.{AREA}.humid.threshold.true",
                    },
                )
                # Paid Tick: 0.5 + 0.2 * (0.8 - 0.5) = 0.56;
                # comfort = 2 * 0.56 = 1.12; humid remains 1.0.
                self.assertAlmostEqual(
                    _field_state(runtime, AREA)["value"], 0.56, delta=1e-12
                )
                self.assertAlmostEqual(
                    _derived_values(runtime)["comfort"], 1.12, delta=1e-12
                )
                self.assertEqual(_derived_values(runtime)["humid"], 1.0)
                self.assertEqual(_actor_state(runtime, actor_id)["mana"], 27.0)
                self.assertEqual(_budget(runtime)["spent_ticks"], 1)

                # Free Tick 1: 0.56 + 0.2 * (0.8 - 0.56) = 0.608;
                # comfort = 2 * 0.608 = 1.216.
                advance_world_tick(runtime.session)
                self.assertAlmostEqual(
                    _field_state(runtime, AREA)["value"], 0.608, delta=1e-12
                )
                self.assertAlmostEqual(
                    _derived_values(runtime)["comfort"], 1.216, delta=1e-12
                )
                self.assertEqual(_derived_values(runtime)["humid"], 1.0)

                # Free Tick 2: 0.608 + 0.2 * (0.8 - 0.608) = 0.6464;
                # comfort = 2 * 0.6464 = 1.2928.
                advance_world_tick(runtime.session)
                self.assertAlmostEqual(
                    _field_state(runtime, AREA)["value"], 0.6464, delta=1e-12
                )
                self.assertAlmostEqual(
                    _derived_values(runtime)["comfort"], 1.2928, delta=1e-12
                )
                self.assertEqual(_derived_values(runtime)["humid"], 1.0)
                self.assertEqual(_budget(runtime)["spent_ticks"], 1)

                accepted = submit_timed_primary_action(
                    runtime.session,
                    runtime.action_registry,
                    gate_request,
                )
                self.assertEqual(
                    accepted.action.definition.canonical_hash,
                    gate.action.canonical_hash,
                )
                self.assertEqual(accepted.action.cost.mana, 4.0)
                self.assertEqual(accepted.time.duration, 1)
                self.assertEqual(_actor_state(runtime, actor_id)["mana"], 23.0)
                self.assertEqual(_actor_state(runtime, actor_id)["shield"], 1.0)
                self.assertEqual(_budget(runtime)["spent_ticks"], 2)

    def test_production_has_no_skill_or_test_name_special_cases(self):
        production = Path(__file__).resolve().parents[1]
        tokens = (*SKILL_IDS, "test_p1_scenarios_completion")
        hits = []
        for path in sorted(production.glob("*.py")):
            text = path.read_text(encoding="utf-8")
            for token in tokens:
                if token in text:
                    hits.append((path.name, token))
        self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main()
