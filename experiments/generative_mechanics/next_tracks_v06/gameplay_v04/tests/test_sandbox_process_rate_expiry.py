from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import unittest

from pmw import Event, Relation, WorldState
from pmw.validation.errors import WorldValidationError

from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.actions import (
    ActionRegistry,
    ActionRequest,
    resolve_action,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.basics import (
    basic_registry,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.checkpoint import (
    load_registry_checkpoint,
    save_registry_checkpoint,
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
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.loadout import (
    change_loadout,
    skill_ref,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.materials import (
    material_authority,
    parse_material,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.processes import (
    PROCESS_COMPONENT,
    ProcessController,
    ProcessLimits,
    build_process_laws,
    instantiate_process,
    stock_entity,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.registry import (
    MechanismRegistryRuntime,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.runtime import (
    advance_world_tick,
    build_runtime,
    clock_entity,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.skills import (
    parse_skill_blueprint,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.tests.test_sandbox_process_action import (
    AREA_ID,
    PLAYER_ID,
    TEMPLATE_ID,
    _actor,
    _area,
    _blueprint,
    _component,
    _profile,
    _revision,
    _state,
    _template,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.worlds import (
    build_gameplay_world,
)


RATE_SKILL_ID = "rate_only_refining"
MODIFY_SKILL_ID = "modify_to_deadline"
LIFECYCLE_FIELDS = (
    "duration_ticks",
    "remaining_ticks",
    "elapsed_ticks",
    "progress",
    "started_at",
    "hard_deadline",
    "expiry_handle",
    "last_step",
    "last_failure",
)


def _saturated_profile(profile_id: str = "saturated_rate"):
    template = replace(_template(), duration_ticks=3, max_duration_ticks=6)
    return replace(_profile(profile_id, PLAYER_ID), template=template)


def _world(profile, *, output_amount: float, output_capacity: float = 20.0):
    entities = {
        PLAYER_ID: _actor(PLAYER_ID, controller="human", mana=20.0),
        AREA_ID: _area(),
        profile.process_entity_id: instantiate_process(profile),
        "pmw:v04:clock": clock_entity(),
    }
    for port, ref in profile.input_ports:
        entities[ref.entity_id] = stock_entity(
            ref.entity_id, amount=10.0, capacity=20.0, unit=port.unit
        )
    for port, ref in profile.output_ports:
        entities[ref.entity_id] = stock_entity(
            ref.entity_id,
            amount=output_amount,
            capacity=output_capacity,
            unit=port.unit,
        )
    world = build_gameplay_world(
        "process_rate_expiry_world",
        areas=(entities[AREA_ID],),
        actors=(entities[PLAYER_ID],),
        placements=((PLAYER_ID, AREA_ID),),
    )
    for entity_id, entity in entities.items():
        world.entities.setdefault(entity_id, entity)
    for entity_id in (
        profile.process_entity_id,
        *(item.stock.entity_id for item in (*profile.inputs, *profile.outputs)),
    ):
        relation_id = f"located:{entity_id}:{AREA_ID}"
        world.relations[relation_id] = Relation(
            relation_id, "located_in", entity_id, AREA_ID
        )
    return world


def _rate_material():
    return parse_material({
        "id": "process_crystal",
        "tier": "rare",
        "region_rarity": "scarce",
        "traits": [{
            "id": "process_shaping",
            "effect_kinds": ["process_start", "process_modify"],
            "selectors": ["current_area"],
            "budget_points": 5,
        }],
    })


def _modify_skill():
    return parse_skill_blueprint({
        "protocol": "pmw-gameplay-v0.4",
        "kind": "skill_blueprint",
        "id": MODIFY_SKILL_ID,
        "version": 1,
        "trigger": "on_use",
        "condition": None,
        "duration": None,
        "cost": {"duration": 1, "mana": 1},
        "scope": {"selectors": ["current_area"], "relation_types": []},
        "effects": [{
            "id": "modify",
            "kind": "process_modify",
            "target": {"kind": "current_area"},
            "commitment": "required",
            "process_template_id": TEMPLATE_ID,
            "process_rate": 1.5,
            "process_remaining_ticks": 2,
        }],
        "budget": {"limit": 5},
        "max_firings_per_root": 1,
        "material_ids": ["process_crystal"],
    }, basic_registry().statuses,
       material_authority((_rate_material(),)))


def _formal_runtime(profile, *, output_amount: float):
    start = _blueprint()
    modify = _modify_skill()
    controller = ProcessController(
        (profile,), ProcessLimits(max_instances=8, max_active=8)
    )
    base = ActionRegistry(
        basic_registry().actions.values(),
        basic_registry().statuses.values(),
        process_controller=controller,
    )
    content = make_content(
        base,
        skills=(start, modify),
        material_ids=("process_crystal",),
    )
    world = initialize_content_world(
        _world(profile, output_amount=output_amount), content
    )
    compiled = compile_content(content)
    session = build_content_session(world, compiled)
    runtime = MechanismRegistryRuntime.from_compiled_content(session, compiled)
    for skill, slot in ((start, 0), (modify, 1)):
        change_loadout(
            runtime.session,
            runtime.manifest,
            actor_id=PLAYER_ID,
            operation="equip_active",
            skill=skill_ref(skill),
            slot=slot,
        )
    return runtime, compiled


def _native_runtime(profile, *, output_amount: float):
    world = _world(profile, output_amount=output_amount)
    return build_runtime(
        WorldState("process_rate_expiry_native", entities=world.entities),
        extra_laws=build_process_laws((profile,)),
    )


def _snapshot(session):
    return (
        _state(session),
        _revision(session),
        tuple(
            (event.id, event.type, event.time, deepcopy(event.payload))
            for event in session.state.scheduled_events
        ),
        id(session.runtime),
    )


def _start(runtime, profile):
    return resolve_action(
        runtime.session,
        runtime.action_registry,
        ActionRequest("rate_start", PLAYER_ID, "start_refining"),
    )


def _modify(runtime):
    return resolve_action(
        runtime.session,
        runtime.action_registry,
        ActionRequest("rate_modify", PLAYER_ID, MODIFY_SKILL_ID),
    )


class ProcessRateOnlyExpiryTests(unittest.TestCase):
    def test_native_rate_only_after_saturated_tick_retains_exact_lifecycle(self):
        profile = _saturated_profile()
        session = _native_runtime(profile, output_amount=20.0)
        controller = ProcessController((profile,))
        controller.start(session, profile.id, owner=PLAYER_ID)
        advance_world_tick(session)

        before = deepcopy(_component(session, profile))
        self.assertEqual(before["elapsed_ticks"], 0)
        self.assertEqual(before["remaining_ticks"], 3)
        self.assertEqual(before["progress"], 0.0)
        self.assertEqual(before["last_step"], 1)
        expiry = [(event.id, event.time) for event in session.state.scheduled_events]
        self.assertEqual(expiry, [(before["expiry_handle"], 3.0)])
        world_before = _snapshot(session)
        prepared = controller.prepare_modify(
            session, profile.id, owner=PLAYER_ID, rate=1.5
        )
        self.assertEqual(_snapshot(session), world_before)
        self.assertEqual(prepared["after_rate"], 1.5)
        self.assertEqual(prepared["after_duration"], before["duration_ticks"])
        self.assertEqual(prepared["after_remaining"], before["remaining_ticks"])
        self.assertEqual(prepared["after_progress"], before["progress"])
        self.assertEqual(prepared["deadline"], 3.0)

        controller.modify(session, profile.id, owner=PLAYER_ID, rate=1.5)
        after = _component(session, profile)
        self.assertEqual(after["rate"], 1.5)
        for field in LIFECYCLE_FIELDS:
            self.assertEqual(after[field], before[field], field)
        self.assertEqual(
            [(event.id, event.time) for event in session.state.scheduled_events],
            expiry,
        )

        session.state.entities[profile.outputs[0].stock.entity_id].components[
            "stock"
        ]["amount"] = 0.0
        advance_world_tick(session)
        self.assertEqual(_component(session, profile)["elapsed_ticks"], 1)
        self.assertEqual(_component(session, profile)["remaining_ticks"], 2)
        self.assertAlmostEqual(_component(session, profile)["progress"], 1 / 3)

    def test_formal_rate_update_after_saturated_tick_keeps_expiry_and_hard_deadline(self):
        profile = _saturated_profile("formal_saturated_rate")
        runtime, _ = _formal_runtime(profile, output_amount=20.0)
        _start(runtime, profile)
        advance_world_tick(runtime.session)
        before = deepcopy(_component(runtime.session, profile))
        output = runtime.session.state.entities[
            profile.outputs[0].stock.entity_id
        ].components["stock"]["amount"]
        input_amount = runtime.session.state.entities[
            profile.inputs[0].stock.entity_id
        ].components["stock"]["amount"]
        self.assertEqual((input_amount, output), (10.0, 20.0))
        self.assertEqual(before["last_step"], 1)

        snapshot = _snapshot(runtime.session)
        outcome = _modify(runtime)
        self.assertEqual(outcome.effect_outcomes[0]["kind"], "process_modify")
        after = _component(runtime.session, profile)
        self.assertEqual(after["rate"], 1.5)
        self.assertEqual(after["remaining_ticks"], 2)
        self.assertEqual(after["duration_ticks"], 2)
        self.assertEqual(after["elapsed_ticks"], before["elapsed_ticks"])
        self.assertEqual(after["progress"], before["progress"])
        self.assertEqual(after["started_at"], before["started_at"])
        self.assertEqual(after["hard_deadline"], before["hard_deadline"])
        self.assertEqual(after["last_step"], before["last_step"])
        self.assertEqual(after["last_failure"], before["last_failure"])
        self.assertEqual(
            [(event.id, event.time) for event in runtime.session.state.scheduled_events],
            [(before["expiry_handle"], 3.0)],
        )
        self.assertNotEqual(_snapshot(runtime.session), snapshot)

    def test_normal_productive_rate_only_retains_progress_and_future_expiry(self):
        profile = _saturated_profile("productive_rate")
        runtime, _ = _formal_runtime(profile, output_amount=0.0)
        _start(runtime, profile)
        advance_world_tick(runtime.session)
        before = deepcopy(_component(runtime.session, profile))
        self.assertEqual(
            (before["elapsed_ticks"], before["remaining_ticks"], before["progress"]),
            (1, 2, 1 / 3),
        )
        prepared = runtime.action_registry.process_controller.prepare_modify(
            runtime.session, profile.id, owner=PLAYER_ID, rate=1.5
        )
        self.assertEqual(prepared["after_duration"], 3)
        self.assertEqual(prepared["after_remaining"], 2)
        self.assertEqual(prepared["after_progress"], 1 / 3)
        self.assertEqual(prepared["deadline"], 3.0)
        _modify(runtime)
        after = _component(runtime.session, profile)
        self.assertEqual(after["rate"], 1.5)
        for field in LIFECYCLE_FIELDS:
            self.assertEqual(after[field], before[field], field)

    def test_explicit_remaining_keeps_now_plus_remaining_and_extension_rule(self):
        profile = _saturated_profile("explicit_remaining")
        runtime, _ = _formal_runtime(profile, output_amount=20.0)
        _start(runtime, profile)
        advance_world_tick(runtime.session)
        before = deepcopy(_component(runtime.session, profile))
        prepared = runtime.action_registry.process_controller.prepare_modify(
            runtime.session,
            profile.id,
            owner=PLAYER_ID,
            remaining_ticks=2,
        )
        self.assertEqual(prepared["deadline"], 3.0)
        self.assertEqual(prepared["after_duration"], 2)
        self.assertEqual(prepared["after_remaining"], 2)
        self.assertEqual(prepared["after_progress"], 0.0)
        runtime.action_registry.process_controller.modify(
            runtime.session, profile.id, owner=PLAYER_ID, remaining_ticks=2
        )
        after = _component(runtime.session, profile)
        self.assertEqual(after["remaining_ticks"], 2)
        self.assertEqual(after["duration_ticks"], 2)
        self.assertEqual(after["elapsed_ticks"], before["elapsed_ticks"])
        self.assertEqual(after["progress"], 0.0)
        self.assertEqual(
            [(event.id, event.time) for event in runtime.session.state.scheduled_events],
            [(before["expiry_handle"], 3.0)],
        )

        with self.assertRaisesRegex(GameplayContractError, "hard deadline"):
            runtime.action_registry.process_controller.prepare_modify(
                runtime.session,
                profile.id,
                owner=PLAYER_ID,
                remaining_ticks=6,
            )

    def test_rate_only_current_schedule_beyond_hard_deadline_rejects_atomically(self):
        profile = _saturated_profile("rate_beyond_schedule")
        session = _native_runtime(profile, output_amount=0.0)
        controller = ProcessController((profile,))
        controller.start(session, profile.id, owner=PLAYER_ID)
        session.state.scheduled_events[0].time = 7.0
        session.runtime.revalidate()
        before = _snapshot(session)
        with self.assertRaisesRegex(GameplayContractError, "schedule exceeds"):
            controller.prepare_modify(session, profile.id, owner=PLAYER_ID, rate=1.5)
        self.assertEqual(_snapshot(session), before)

    def test_invalid_or_over_deadline_schedule_denies_atomically(self):
        cases = (
            ("missing", "missing", 3.0, "missing"),
            ("past", "keep", 1.0, "not in the future"),
            ("duplicate", "duplicate", 3.0, "duplicate id"),
            ("beyond", "keep", 7.0, "schedule exceeds"),
        )
        for name, handle_mode, event_time, error in cases:
            with self.subTest(name=name):
                profile = _saturated_profile(f"saturated_{name}")
                session = _native_runtime(profile, output_amount=20.0)
                controller = ProcessController((profile,))
                controller.start(session, profile.id, owner=PLAYER_ID)
                advance_world_tick(session)
                if handle_mode == "missing":
                    session.state.scheduled_events = []
                elif handle_mode == "duplicate":
                    original = session.state.scheduled_events[0]
                    session.state.scheduled_events.append(
                        Event(
                            original.id,
                            original.type,
                            original.time,
                            original.source,
                            original.target,
                            deepcopy(original.payload),
                        )
                    )
                else:
                    session.state.scheduled_events[0].time = event_time
                before = _snapshot(session)
                expected = (
                    WorldValidationError
                    if name == "duplicate"
                    else GameplayContractError
                )
                with self.assertRaisesRegex(expected, error):
                    controller.modify(session, profile.id, owner=PLAYER_ID, rate=1.5)
                self.assertEqual(_snapshot(session), before)

    def test_checkpoint_rate_only_continues_with_retained_expiry(self):
        import tempfile
        from pathlib import Path

        profile = _saturated_profile("checkpoint_saturated_rate")
        runtime, compiled = _formal_runtime(profile, output_amount=20.0)
        _start(runtime, profile)
        advance_world_tick(runtime.session)
        _modify(runtime)
        expected = deepcopy(_component(runtime.session, profile))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rate_expiry_checkpoint.json"
            save_registry_checkpoint(path, runtime)
            restored = load_registry_checkpoint(path, compiled)
            self.assertEqual(
                restored.session.state.to_dict(), runtime.session.state.to_dict()
            )
            advance_world_tick(runtime.session)
            advance_world_tick(restored.session)
            self.assertEqual(
                runtime.session.state.to_dict(), restored.session.state.to_dict()
            )
            self.assertEqual(
                _component(restored.session, profile)["hard_deadline"],
                expected["hard_deadline"],
            )
            self.assertEqual(
                [(event.id, event.time) for event in restored.session.state.scheduled_events],
                [(expected["expiry_handle"], 3.0)],
            )

    def test_expiry_event_still_uses_retained_schedule(self):
        profile = _saturated_profile("expiry_rate")
        runtime, _ = _formal_runtime(profile, output_amount=20.0)
        _start(runtime, profile)
        advance_world_tick(runtime.session)
        _modify(runtime)
        expected_handle = _component(runtime.session, profile)["expiry_handle"]
        self.assertEqual(
            [(event.id, event.time) for event in runtime.session.state.scheduled_events],
            [(expected_handle, 3.0)],
        )
        advance_world_tick(runtime.session)
        advance_world_tick(runtime.session)
        after = _component(runtime.session, profile)
        self.assertEqual(after["state"], "stopped")
        self.assertEqual(after["remaining_ticks"], 0)
        self.assertIsNone(after["expiry_handle"])


if __name__ == "__main__":
    unittest.main()
