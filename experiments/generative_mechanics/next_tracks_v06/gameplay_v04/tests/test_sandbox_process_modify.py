from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pmw import Relation

from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.actions import (
    ActionRegistry,
    ActionRequest,
    resolve_action,
    submit_timed_primary_action,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.basics import (
    basic_registry,
    basic_registry_document,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.build_analysis import (
    RegistrySemanticsProvider,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.checkpoint import (
    load_registry_checkpoint,
    save_registry_checkpoint,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.content_compiler import (
    make_content,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.contracts import (
    GameplayContractError,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.effects import (
    parse_effect,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.loadout import (
    change_loadout,
    skill_ref,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.materials import (
    material_authority,
    parse_material,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.observation import (
    ActorObservationBuilder,
    ObservationDisclosure,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.processes import (
    PROCESS_COMPONENT,
    PROCESS_MODIFY_EVENT,
    PROCESS_START_EVENT,
    ConversionPort,
    ProcessController,
    ProcessLimits,
    ProcessProfile,
    ProcessTemplate,
    StockBinding,
    StockRef,
    instantiate_process,
    stock_entity,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.registry import (
    MechanismRegistryRuntime,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.runtime import (
    advance_world_tick,
    clock_entity,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.simulation import (
    SandboxSimulator,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.skills import (
    parse_skill_blueprint,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.tests.test_sandbox_process_action import (
    AREA_ID,
    NPC_ID,
    PLAYER_ID,
    TEMPLATE_ID,
    _actor,
    _amount,
    _area,
    _blueprint,
    _component,
    _revision,
    _runtime,
    _state,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.worlds import (
    build_gameplay_world,
)


MODIFY_ID = "modify_refining"
START_ID = "start_refining"
MATERIAL_ID = "process_crystal"


def _template(*, template_id: str = TEMPLATE_ID):
    return ProcessTemplate(
        template_id,
        (ConversionPort("ore", 2.0, "ore"),),
        (ConversionPort("ingot", 1.0, "ingot"),),
        1.0,
        3,
        2.0,
        6,
    )


def _profile(
    profile_id: str,
    owner: str,
    *,
    template_id: str = TEMPLATE_ID,
    amount: float = 10.0,
):
    template = _template(template_id=template_id)
    return ProcessProfile(
        profile_id,
        template,
        f"process_{profile_id}",
        owner,
        (StockBinding("ore", StockRef(f"{profile_id}_ore")),),
        (StockBinding("ingot", StockRef(f"{profile_id}_ingot")),),
    )


def _world(profiles: tuple[ProcessProfile, ...], *, time_budget: int | None = None):
    entities = {
        PLAYER_ID: _actor(PLAYER_ID, controller="human", mana=24.0),
        NPC_ID: _actor(NPC_ID, controller="ai", mana=24.0),
        AREA_ID: _area(),
        **{profile.process_entity_id: instantiate_process(profile) for profile in profiles},
    }
    for profile in profiles:
        for port, ref in profile.input_ports:
            entities[ref.entity_id] = stock_entity(
                ref.entity_id, amount=10.0, capacity=30.0, unit=port.unit
            )
        for port, ref in profile.output_ports:
            entities[ref.entity_id] = stock_entity(
                ref.entity_id, amount=0.0, capacity=30.0, unit=port.unit
            )
    world = build_gameplay_world(
        "process_modify_world",
        areas=(entities[AREA_ID],),
        actors=(entities[PLAYER_ID], entities[NPC_ID]),
        placements=((PLAYER_ID, AREA_ID), (NPC_ID, AREA_ID)),
    )
    for entity_id, entity in entities.items():
        world.entities.setdefault(entity_id, entity)
    for profile in profiles:
        for endpoint in (
            profile.process_entity_id,
            *(item.stock.entity_id for item in (*profile.inputs, *profile.outputs)),
        ):
            relation_id = f"located:{endpoint}:{AREA_ID}"
            world.relations[relation_id] = Relation(
                relation_id, "located_in", endpoint, AREA_ID
            )
    world.entities["pmw:v04:clock"] = clock_entity()
    if time_budget is not None:
        from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.time_ledger import (
            initialize_time_budget,
        )
        world = initialize_time_budget(world, time_budget)
    return world


def _material(*, kinds: tuple[str, ...] = ("process_start", "process_modify")):
    return parse_material({
        "id": MATERIAL_ID,
        "tier": "rare",
        "region_rarity": "scarce",
        "traits": [{
            "id": "process_shaping",
            "effect_kinds": list(kinds),
            "selectors": ["current_area"],
            "budget_points": 10.0 if len(kinds) > 1 else 5.0,
        }],
    })


def _raw_blueprint(
    skill_id: str = MODIFY_ID,
    *,
    rate=1.5,
    remaining=2,
    kind: str = "process_modify",
    extra_effect=None,
):
    effect = {
        "id": "modify" if kind == "process_modify" else "start",
        "kind": kind,
        "target": {"kind": "current_area"},
        "commitment": "required",
        "process_template_id": TEMPLATE_ID,
    }
    if kind == "process_modify":
        if rate is not _ABSENT:
            effect["process_rate"] = rate
        if remaining is not _ABSENT:
            effect["process_remaining_ticks"] = remaining
    effects = [effect]
    if extra_effect is not None:
        effects.append(extra_effect)
    kinds = [item["kind"] for item in effects]
    return {
        "protocol": "pmw-gameplay-v0.4",
        "kind": "skill_blueprint",
        "id": skill_id,
        "version": 1,
        "trigger": "on_use",
        "condition": None,
        "duration": None,
        "cost": {"duration": 2, "mana": 4},
        "scope": {"selectors": ["current_area"], "relation_types": []},
        "effects": effects,
        "budget": {"limit": 5.0},
        "max_firings_per_root": 1,
        "material_ids": [MATERIAL_ID],
    }


_ABSENT = object()


def _skill(*, rate=1.5, remaining=2, kinds=("process_modify",)):
    document = _raw_blueprint(rate=rate, remaining=remaining)
    authority = material_authority((_material(kinds=kinds),))
    return parse_skill_blueprint(document, basic_registry().statuses, authority)


def _runtime_with_modify(
    profiles: tuple[ProcessProfile, ...],
    *,
    rate=1.5,
    remaining=2,
    time_budget: int | None = 12,
):
    start = _blueprint()
    base = ActionRegistry(
        basic_registry().actions.values(),
        basic_registry().statuses.values(),
        process_controller=ProcessController(
            profiles, ProcessLimits(max_instances=8, max_active=8)
        ),
    )
    content = make_content(
        base,
        skills=(start,),
        material_ids=(MATERIAL_ID,),
    )
    from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.content_compiler import (
        build_content_session,
        compile_content,
        initialize_content_world,
    )

    world = initialize_content_world(_world(profiles, time_budget=time_budget), content)
    compiled = compile_content(content)
    session = build_content_session(world, compiled)
    runtime = MechanismRegistryRuntime.from_compiled_content(session, compiled)
    for actor_id in (PLAYER_ID, NPC_ID):
        change_loadout(
            runtime.session,
            runtime.manifest,
            actor_id=actor_id,
            operation="equip_active",
            skill=skill_ref(start),
            slot=0,
        )
    modify = _skill(rate=rate, remaining=remaining)
    runtime.install_blueprint(modify)
    for actor_id in (PLAYER_ID, NPC_ID):
        change_loadout(
            runtime.session,
            runtime.manifest,
            actor_id=actor_id,
            operation="unload_active",
            slot=0,
        )
        change_loadout(
            runtime.session,
            runtime.manifest,
            actor_id=actor_id,
            operation="equip_active",
            skill=skill_ref(modify),
            slot=0,
        )
    return runtime, compiled, modify


def _start_direct(runtime, profile, owner):
    runtime.action_registry.process_controller.start(
        runtime.session, profile.id, owner=owner
    )


def _snapshot(session):
    return (
        _state(session),
        _revision(session),
        deepcopy(session.runtime.stats),
        tuple((event.id, event.time) for event in session.state.scheduled_events),
        id(session.runtime),
    )


class ProcessModifyParsingTests(unittest.TestCase):
    def test_material_parser_and_effect_shape_are_strict(self):
        statuses = basic_registry().statuses
        valid = {
            "id": "modify",
            "kind": "process_modify",
            "target": {"kind": "current_area"},
            "commitment": "required",
            "process_template_id": TEMPLATE_ID,
            "process_rate": 1.5,
            "process_remaining_ticks": 2,
        }
        effect = parse_effect(valid, statuses)
        self.assertEqual(effect.process_rate, 1.5)
        self.assertEqual(effect.process_remaining_ticks, 2)
        self.assertIn("process_modify", _material().traits[0].effect_kinds)

        for mutation, error in (
            ({"process_rate": None}, "missing or unknown fields"),
            ({"process_remaining_ticks": None}, "missing or unknown fields"),
            ({"process_rate": True}, "finite positive"),
            ({"process_rate": 0}, "finite positive"),
            ({"process_rate": float("inf")}, "finite positive"),
            ({"process_remaining_ticks": True}, "positive integer"),
            ({"process_remaining_ticks": 0}, "positive integer"),
            ({"process_remaining_ticks": 1.0}, "positive integer"),
        ):
            raw = deepcopy(valid)
            raw.update(mutation)
            if mutation.get("process_rate", 0) is None:
                raw.pop("process_remaining_ticks", None)
            if mutation.get("process_remaining_ticks", 0) is None:
                raw.pop("process_rate", None)
            with self.assertRaisesRegex(GameplayContractError, error):
                parse_effect(raw, statuses)

        no_value = deepcopy(valid)
        no_value.pop("process_rate")
        no_value.pop("process_remaining_ticks")
        with self.assertRaisesRegex(GameplayContractError, "missing or unknown fields"):
            parse_effect(no_value, statuses)

    def test_material_capability_budget_and_passive_scope_are_denied(self):
        raw = _raw_blueprint()
        with self.assertRaisesRegex(GameplayContractError, "material effect authorization"):
            parse_skill_blueprint(
                raw,
                basic_registry().statuses,
                material_authority((_material(kinds=("process_start",)),)),
            )
        over_budget = deepcopy(raw)
        over_budget["budget"]["limit"] = 5.5
        with self.assertRaisesRegex(GameplayContractError, "budget.limit exceeds"):
            parse_skill_blueprint(
                over_budget,
                basic_registry().statuses,
                material_authority((_material(kinds=("process_modify",)),)),
            )
        passive = deepcopy(raw)
        passive["kind"] = "passive_blueprint"
        passive["trigger"] = "action_started"
        passive["cost"] = {"duration": 1, "mana": 0}
        passive["budget"]["limit"] = 5.0
        with self.assertRaisesRegex(GameplayContractError, "active on_use"):
            parse_skill_blueprint(
                passive,
                basic_registry().statuses,
                material_authority((_material(kinds=("process_modify",)),)),
            )

    def test_mixed_control_rejection_preserves_two_start_error(self):
        document = basic_registry_document()
        document["actions"].append({
            "id": "mixed_controls",
            "version": 1,
            "action_type": "skill",
            "cost": {"duration": 1, "mana": 0},
            "scope": {"selectors": ["current_area"], "relation_types": []},
            "effects": [
                {
                    "id": "start",
                    "kind": "process_start",
                    "target": {"kind": "current_area"},
                    "commitment": "required",
                    "process_template_id": TEMPLATE_ID,
                },
                {
                    "id": "modify",
                    "kind": "process_modify",
                    "target": {"kind": "current_area"},
                    "commitment": "required",
                    "process_template_id": TEMPLATE_ID,
                    "process_rate": 1.5,
                    "process_remaining_ticks": 2,
                },
            ],
        })
        with self.assertRaisesRegex(GameplayContractError, "at most one Process control"):
            ActionRegistry.parse(document)

        two_start = deepcopy(document)
        two_start["actions"][-1]["effects"][1] = {
            "id": "modify",
            "kind": "process_start",
            "target": {"kind": "current_area"},
            "commitment": "required",
            "process_template_id": TEMPLATE_ID,
        }
        with self.assertRaisesRegex(GameplayContractError, "at most one process_start"):
            ActionRegistry.parse(two_start)


class ProcessModifyExecutionTests(unittest.TestCase):
    def test_player_and_npc_modify_through_formal_install_and_equipment(self):
        player = _profile("player_modify", PLAYER_ID)
        npc = _profile("npc_modify", NPC_ID)
        runtime, _, skill = _runtime_with_modify((player, npc))
        self.assertEqual(skill.budget_used, 5.0)
        self.assertEqual(
            [item.skill_id for item in runtime.manifest.entries if item.enabled],
            ["modify_refining", "start_refining"],
        )
        _start_direct(runtime, player, PLAYER_ID)
        _start_direct(runtime, npc, NPC_ID)
        for actor_id, profile in ((PLAYER_ID, player), (NPC_ID, npc)):
            outcome = resolve_action(
                runtime.session,
                runtime.action_registry,
                ActionRequest(f"modify_{actor_id}", actor_id, MODIFY_ID),
            )
            component = _component(runtime.session, profile)
            self.assertEqual(outcome.effect_outcomes[0]["kind"], "process_modify")
            self.assertEqual(component["rate"], 1.5)
            self.assertEqual(component["remaining_ticks"], 2)
            self.assertEqual(component["duration_ticks"], 2)
            self.assertIn(
                PROCESS_MODIFY_EVENT,
                tuple(item.event.type for item in outcome.event_result.trace.events),
            )

    def test_quantitative_paid_ticks_and_deadline_shortening(self):
        profile = _profile("paid_modify", PLAYER_ID)
        runtime, _, _ = _runtime_with_modify((profile,))
        _start_direct(runtime, profile, PLAYER_ID)
        old_deadline = _component(runtime.session, profile)["hard_deadline"]
        timed = submit_timed_primary_action(
            runtime.session,
            runtime.action_registry,
            ActionRequest("timed_modify", PLAYER_ID, MODIFY_ID),
        )
        self.assertEqual(timed.action.cost.duration, 2)
        self.assertEqual(timed.time.duration, 2)
        component = _component(runtime.session, profile)
        self.assertEqual(component["hard_deadline"], old_deadline)
        self.assertEqual(component["remaining_ticks"], 0)
        self.assertEqual(component["elapsed_ticks"], 1)
        self.assertEqual(_amount(runtime.session, f"{profile.id}_ore"), 7.0)
        self.assertEqual(_amount(runtime.session, f"{profile.id}_ingot"), 1.5)
        self.assertEqual(runtime.session.state.scheduled_events, [])

    def test_extension_is_bounded_by_hard_deadline_and_prepare_is_read_only(self):
        profile = _profile("extend_modify", PLAYER_ID)
        runtime, _, _ = _runtime_with_modify((profile,))
        _start_direct(runtime, profile, PLAYER_ID)
        advance_world_tick(runtime.session)
        hard_deadline = _component(runtime.session, profile)["hard_deadline"]
        before = _snapshot(runtime.session)
        prepared = runtime.action_registry.process_controller.prepare_modify(
            runtime.session,
            profile.id,
            owner=PLAYER_ID,
            rate=1.75,
            remaining_ticks=3,
        )
        self.assertEqual(prepared["after_rate"], 1.75)
        self.assertEqual(prepared["after_remaining"], 3)
        self.assertEqual(_snapshot(runtime.session), before)
        self.assertLessEqual(3 + runtime.session.state.sim_time, hard_deadline)

        with self.assertRaisesRegex(GameplayContractError, "hard deadline"):
            runtime.action_registry.process_controller.prepare_modify(
                runtime.session,
                profile.id,
                owner=PLAYER_ID,
                remaining_ticks=6,
            )
        self.assertEqual(_snapshot(runtime.session), before)

    def test_missing_modify_law_and_owner_locality_reject_atomically(self):
        player = _profile("missing_law_modify", PLAYER_ID)
        runtime, compiled, _ = _runtime_with_modify((player,))
        _start_direct(runtime, player, PLAYER_ID)
        exact_law_id = f"pmw.v04.sandbox.process.{player.id}.modify"
        decoy = {
            "id": "pmw.v04.sandbox.process.unrelated.modify",
            "mode": "event",
            "priority": 100,
            "when": {"all": [
                {"event.type": {"eq": PROCESS_MODIFY_EVENT}},
                {"ref": "$event.payload.profile_id", "eq": "unrelated"},
            ]},
            "effects": [],
        }
        filtered = tuple(
            law for law in compiled.laws
            if law["id"] != exact_law_id
        ) + (decoy,)
        filtered = tuple(sorted(filtered, key=lambda law: law["id"]))
        from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.runtime import (
            discover_profiles,
        )
        from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.runtime import (
            build_runtime,
        )
        session = build_runtime(
            deepcopy(runtime.session.state), discover_profiles(runtime.session.state), filtered
        )
        before = session.state.to_dict()
        with self.assertRaisesRegex(GameplayContractError, "action did not match"):
            resolve_action(
                session,
                runtime.action_registry,
                ActionRequest("missing_modify_law", PLAYER_ID, MODIFY_ID),
            )
        self.assertEqual(session.state.to_dict(), before)

        remote = _profile("remote_modify", PLAYER_ID)
        runtime, _, _ = _runtime_with_modify((remote,))
        _start_direct(runtime, remote, PLAYER_ID)
        area = _area("remote_area")
        runtime.session.state.entities[area.id] = area
        runtime.session.state.relations["remote:process"] = Relation(
            "remote:process", "located_in", remote.process_entity_id, area.id
        )
        runtime.session.runtime.revalidate()
        before = _snapshot(runtime.session)
        with self.assertRaisesRegex(GameplayContractError, "missing, ambiguous, or remote"):
            resolve_action(
                runtime.session,
                runtime.action_registry,
                ActionRequest("remote_modify", PLAYER_ID, MODIFY_ID),
            )
        self.assertEqual(_snapshot(runtime.session), before)

    def test_state_writer_and_input_denials_are_atomic(self):
        profile = _profile("state_modify", PLAYER_ID)
        runtime, _, _ = _runtime_with_modify((profile,))
        before = _snapshot(runtime.session)
        with self.assertRaisesRegex(GameplayContractError, "state must be one of running"):
            resolve_action(
                runtime.session,
                runtime.action_registry,
                ActionRequest("stopped_modify", PLAYER_ID, MODIFY_ID),
            )
        self.assertEqual(_snapshot(runtime.session), before)

        _start_direct(runtime, profile, PLAYER_ID)
        runtime.session.state.entities[
            profile.inputs[0].stock.entity_id
        ].components["stock"]["amount"] = 0.0
        before = _snapshot(runtime.session)
        with self.assertRaisesRegex(GameplayContractError, "input .* empty"):
            resolve_action(
                runtime.session,
                runtime.action_registry,
                ActionRequest("empty_modify", PLAYER_ID, MODIFY_ID),
            )
        self.assertEqual(_snapshot(runtime.session), before)

    def test_late_cascade_and_tick_failures_roll_back_complete_modify(self):
        profile = _profile("rollback_modify", PLAYER_ID)
        runtime, _, _ = _runtime_with_modify((profile,))
        _start_direct(runtime, profile, PLAYER_ID)
        before = _snapshot(runtime.session)
        from experiments.generative_mechanics.next_tracks_v06.gameplay_v04 import (
            processes,
        )

        original = processes._prepare_modify

        def fail_after_prepare(*args, **kwargs):
            original(*args, **kwargs)
            raise RuntimeError("injected late modification failure")

        with patch.object(processes, "_prepare_modify", side_effect=fail_after_prepare):
            with self.assertRaisesRegex(RuntimeError, "late modification"):
                resolve_action(
                    runtime.session,
                    runtime.action_registry,
                    ActionRequest("late_modify", PLAYER_ID, MODIFY_ID),
                )
        self.assertEqual(_snapshot(runtime.session), before)

        from experiments.generative_mechanics.next_tracks_v06.gameplay_v04 import (
            time_ledger,
        )
        real_tick = time_ledger.advance_world_tick
        calls = 0

        def fail_second_tick(working, **kwargs):
            nonlocal calls
            calls += 1
            result = real_tick(working, **kwargs)
            if calls == 2:
                raise RuntimeError("injected late modify tick failure")
            return result

        before = _snapshot(runtime.session)
        with patch.object(time_ledger, "advance_world_tick", side_effect=fail_second_tick):
            with self.assertRaisesRegex(RuntimeError, "late modify tick"):
                submit_timed_primary_action(
                    runtime.session,
                    runtime.action_registry,
                    ActionRequest("late_tick_modify", PLAYER_ID, MODIFY_ID),
                )
        self.assertEqual(_snapshot(runtime.session), before)


class ProcessModifyCompatibilityTests(unittest.TestCase):
    def test_checkpoint_rebuild_and_changed_profile_rejection(self):
        profile = _profile("checkpoint_modify", PLAYER_ID)
        runtime, compiled, _ = _runtime_with_modify((profile,))
        _start_direct(runtime, profile, PLAYER_ID)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "modify_checkpoint.json"
            save_registry_checkpoint(path, runtime)
            restored = load_registry_checkpoint(path, compiled)
            outcome = resolve_action(
                restored.session,
                restored.action_registry,
                ActionRequest("restored_modify", PLAYER_ID, MODIFY_ID),
            )
            self.assertTrue(outcome.event_result.changed)
            self.assertEqual(_component(restored.session, profile)["rate"], 1.5)

            changed_profile = ProcessProfile(
                profile.id,
                profile.template,
                profile.process_entity_id,
                profile.owner,
                (StockBinding("ore", StockRef("changed_ore")),),
                (StockBinding("ingot", StockRef("changed_ingot")),),
            )
            changed_content = make_content(
                ActionRegistry(
                    basic_registry().actions.values(),
                    basic_registry().statuses.values(),
                    process_controller=ProcessController((changed_profile,)),
                ),
                skills=(_blueprint(),),
                material_ids=(MATERIAL_ID,),
            )
            from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.content_compiler import (
                compile_content,
            )
            with self.assertRaisesRegex(GameplayContractError, "static Law configuration"):
                load_registry_checkpoint(path, compile_content(changed_content))

    def test_semantics_and_projection_exclude_control_authority(self):
        profile = _profile("projection_modify", PLAYER_ID)
        runtime, _, _ = _runtime_with_modify((profile,))
        semantics = RegistrySemanticsProvider(runtime.action_registry).semantics(MODIFY_ID)
        write = next(row for row in semantics.writes if row.operation == "process_modify")
        self.assertEqual(write.path, f"process:{TEMPLATE_ID}:configuration")
        self.assertNotIn(profile.id, write.path)
        observation = ActorObservationBuilder().build(
            runtime.session,
            runtime.action_registry,
            PLAYER_ID,
            ObservationDisclosure.create(),
        )
        simulator = SandboxSimulator(runtime.action_registry)
        _, projected, _ = simulator._build(observation)
        self.assertNotIn(MODIFY_ID, projected.actions)
        self.assertNotIn(START_ID, projected.actions)
        self.assertIn("basic_wait", projected.actions)
        result = simulator.simulate(
            observation,
            ActionRequest("projected_modify", PLAYER_ID, MODIFY_ID),
        )
        self.assertFalse(result.legal)
        self.assertIn("unknown registered action", result.rejection)


if __name__ == "__main__":
    unittest.main()
