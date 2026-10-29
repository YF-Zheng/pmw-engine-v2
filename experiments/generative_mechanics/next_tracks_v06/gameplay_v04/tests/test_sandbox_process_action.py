from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
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
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.blueprints import (
    instantiate_actor,
    instantiate_area,
    parse_actor_blueprint,
    parse_area_blueprint,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.build_analysis import (
    BuildAnalyzer,
    RegistrySemanticsProvider,
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
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.hooks import (
    HookLineage,
    execute_hook,
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
    discover_profiles,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.simulation import (
    SandboxSimulator,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.skills import (
    parse_skill_blueprint,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.worlds import (
    build_gameplay_world,
)


TEMPLATE_ID = "refine_material"
MISSING_ID = "missing_work"
SKILL_ID = "start_refining"
PLAYER_ID = "player_actor"
NPC_ID = "npc_actor"
AREA_ID = "workshop_area"


def _actor(instance_id: str, *, controller: str, mana: float = 20.0):
    blueprint = parse_actor_blueprint({
        "protocol": "pmw-gameplay-v0.4",
        "kind": "actor_blueprint",
        "id": "actor_blueprint",
        "hp": {"max": 50, "initial": 50},
        "mana": {"max": 30, "initial": mana, "dynamics": None},
        "attributes": {"power": 4, "control": 4, "resilience": 4, "agility": 4},
        "traits": [],
    })
    return instantiate_actor(blueprint, instance_id, controller=controller)


def _area(instance_id: str = AREA_ID):
    blueprint = parse_area_blueprint({
        "protocol": "pmw-gameplay-v0.4",
        "kind": "area_blueprint",
        "id": "workshop_blueprint",
        "fields": [{
            "id": "heat",
            "domain": {"min": 0, "max": 10},
            "initial": 1,
            "target": 1,
            "rate": 0.1,
            "curve": "linear",
            "max_persistent_patches": 2,
            "max_temporary_modifiers": 2,
        }],
    })
    return instantiate_area(blueprint, instance_id)


def _template(template_id: str = TEMPLATE_ID):
    return ProcessTemplate(
        template_id,
        (ConversionPort("ore", 2.0, "ore"),),
        (ConversionPort("ingot", 1.0, "ingot"),),
        1.0,
        3,
        2.0,
        3,
    )


def _profile(
    profile_id: str,
    owner: str,
    *,
    template_id: str = TEMPLATE_ID,
    area_id: str = AREA_ID,
    stock_prefix: str | None = None,
    amount: float = 10.0,
):
    template = _template(template_id)
    prefix = stock_prefix or profile_id
    return ProcessProfile(
        profile_id,
        template,
        f"process_{profile_id}",
        owner,
        (StockBinding("ore", StockRef(f"{prefix}_ore")),),
        (StockBinding("ingot", StockRef(f"{prefix}_ingot")),),
    )


def _world(
    profiles: tuple[ProcessProfile, ...],
    *,
    player_mana: float = 20.0,
    npc_mana: float = 20.0,
    player_area: str = AREA_ID,
    npc_area: str = AREA_ID,
    placements: tuple[tuple[str, str], ...] | None = None,
):
    area_ids = {AREA_ID, player_area, npc_area}
    areas = {area_id: _area(area_id) for area_id in area_ids}
    entities = {
        PLAYER_ID: _actor(PLAYER_ID, controller="human", mana=player_mana),
        NPC_ID: _actor(NPC_ID, controller="ai", mana=npc_mana),
        **areas,
        **{profile.process_entity_id: instantiate_process(profile) for profile in profiles},
    }
    for profile in profiles:
        for port, ref in profile.input_ports:
            entities[ref.entity_id] = stock_entity(
                ref.entity_id, amount=10.0, capacity=20.0, unit=port.unit
            )
        for port, ref in profile.output_ports:
            entities[ref.entity_id] = stock_entity(
                ref.entity_id, amount=0.0, capacity=20.0, unit=port.unit
            )
    actor_placements = placements if placements is not None else (
        (PLAYER_ID, player_area),
        (NPC_ID, npc_area),
    )
    world = build_gameplay_world(
        "process_action_world",
        areas=areas.values(),
        actors=(entities[PLAYER_ID], entities[NPC_ID]),
        placements=actor_placements,
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
    return world


def _material(template_id: str = TEMPLATE_ID):
    return parse_material({
        "id": "process_crystal",
        "tier": "rare",
        "region_rarity": "scarce",
        "traits": [{
            "id": "process_shaping",
            "effect_kinds": ["process_start"],
            "selectors": ["current_area"],
            "budget_points": 5,
        }],
    })


def _blueprint(*, skill_id: str = SKILL_ID, template_id: str = TEMPLATE_ID):
    material = _material(template_id)
    return parse_skill_blueprint({
        "protocol": "pmw-gameplay-v0.4",
        "kind": "skill_blueprint",
        "id": skill_id,
        "version": 1,
        "trigger": "on_use",
        "condition": None,
        "duration": None,
        "cost": {"duration": 2, "mana": 4},
        "scope": {"selectors": ["current_area"], "relation_types": []},
        "effects": [{
            "id": "start",
            "kind": "process_start",
            "target": {"kind": "current_area"},
            "commitment": "required",
            "process_template_id": template_id,
        }],
        "budget": {"limit": 5},
        "max_firings_per_root": 1,
        "material_ids": ["process_crystal"],
    }, basic_registry().statuses, material_authority((material,)))


def _runtime(
    profiles: tuple[ProcessProfile, ...],
    *,
    skill=None,
    controller=None,
    time_budget: int | None = None,
    player_mana: float = 20.0,
    npc_mana: float = 20.0,
):
    skill = skill or _blueprint()
    controller = controller or ProcessController(profiles, ProcessLimits(max_instances=8, max_active=8))
    base = ActionRegistry(
        basic_registry().actions.values(), basic_registry().statuses.values(),
        process_controller=controller,
    )
    content = make_content(
        base,
        skills=(skill,),
        material_ids=("process_crystal",),
    )
    world = _world(profiles, player_mana=player_mana, npc_mana=npc_mana)
    world.entities["pmw:v04:clock"] = clock_entity()
    if time_budget is not None:
        from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.time_ledger import (
            initialize_time_budget,
        )
        world = initialize_time_budget(world, time_budget)
    world = initialize_content_world(world, content)
    compiled = compile_content(content)
    session = build_content_session(world, compiled)
    runtime = MechanismRegistryRuntime.from_compiled_content(session, compiled)
    for actor_id in (PLAYER_ID, NPC_ID):
        change_loadout(
            runtime.session,
            runtime.manifest,
            actor_id=actor_id,
            operation="equip_active",
            skill=skill_ref(skill),
            slot=0,
        )
    return runtime, compiled, skill


def _state(session):
    return session.state.to_dict()


def _revision(session):
    return (
        session.runtime.revision,
        session.runtime.object_revision,
        deepcopy(session.runtime.stats),
        session.runtime.state_closure_known,
    )


def _component(session, profile: ProcessProfile):
    return session.state.entities[profile.process_entity_id].components[PROCESS_COMPONENT]


def _amount(session, entity_id: str):
    return session.state.entities[entity_id].components["stock"]["amount"]


def _add_located(session, entity_id: str, area_id: str = AREA_ID):
    relation_id = f"extra:{entity_id}:{area_id}"
    session.state.relations[relation_id] = Relation(relation_id, "located_in", entity_id, area_id)
    session.runtime.revalidate()


class StandardProcessActionTests(unittest.TestCase):
    def test_same_blueprint_starts_player_and_npc_profiles_from_standard_flow(self):
        player = _profile("player_refining", PLAYER_ID)
        npc = _profile("npc_refining", NPC_ID)
        runtime, _, skill = _runtime((player, npc))
        self.assertEqual(skill.budget_used, 5.0)

        player_outcome = resolve_action(
            runtime.session, runtime.action_registry,
            ActionRequest("start_player_work", PLAYER_ID, SKILL_ID),
        )
        npc_outcome = resolve_action(
            runtime.session, runtime.action_registry,
            ActionRequest("start_npc_work", NPC_ID, SKILL_ID),
        )
        self.assertEqual(_component(runtime.session, player)["state"], "running")
        self.assertEqual(_component(runtime.session, npc)["state"], "running")
        self.assertEqual(
            runtime.session.state.entities[PLAYER_ID].components["pmw_gameplay_actor"]["mana"],
            16.0,
        )
        self.assertEqual(
            runtime.session.state.entities[NPC_ID].components["pmw_gameplay_actor"]["mana"],
            16.0,
        )
        self.assertEqual(player_outcome.effect_outcomes[0]["kind"], "process_start")
        self.assertEqual(npc_outcome.effect_outcomes[0]["kind"], "process_start")
        self.assertIn(
            PROCESS_START_EVENT,
            tuple(event.event.type for event in player_outcome.event_result.trace.events),
        )
        self.assertIn(
            PROCESS_START_EVENT,
            tuple(event.event.type for event in npc_outcome.event_result.trace.events),
        )

    def test_charged_tick_uses_existing_stock_stoichiometry_and_final_duration(self):
        player = _profile("timed_refining", PLAYER_ID)
        runtime, _, _ = _runtime((player,), time_budget=6)
        timed = submit_timed_primary_action(
            runtime.session,
            runtime.action_registry,
            ActionRequest("timed_start", PLAYER_ID, SKILL_ID),
        )
        self.assertEqual(timed.action.cost.duration, 2)
        self.assertEqual(timed.time.duration, 2)
        self.assertEqual(timed.time.after_remaining, 4)
        self.assertEqual(_amount(runtime.session, "timed_refining_ore"), 6.0)
        self.assertEqual(_amount(runtime.session, "timed_refining_ingot"), 2.0)
        self.assertEqual(_component(runtime.session, player)["elapsed_ticks"], 2)

    def test_preparation_is_read_only_and_checks_every_endpoint_area(self):
        player = _profile("read_only_refining", PLAYER_ID)
        runtime, _, _ = _runtime((player,))
        before_state = _state(runtime.session)
        before_revision = _revision(runtime.session)
        prepared = runtime.action_registry.process_controller.prepare_start(
            runtime.session, player.id, owner=PLAYER_ID
        )
        self.assertEqual(prepared, player)
        self.assertEqual(_state(runtime.session), before_state)
        self.assertEqual(_revision(runtime.session), before_revision)

        _add_located(runtime.session, player.process_entity_id, AREA_ID)
        before = _state(runtime.session)
        with self.assertRaisesRegex(GameplayContractError, "missing, ambiguous, or remote"):
            resolve_action(
                runtime.session, runtime.action_registry,
                ActionRequest("ambiguous_endpoint", PLAYER_ID, SKILL_ID),
            )
        self.assertEqual(_state(runtime.session), before)

    def test_remote_stock_or_process_endpoint_rejects_without_partial_action(self):
        player = _profile("remote_stock_refining", PLAYER_ID)
        runtime, _, _ = _runtime((player,))
        remote_area = _area("remote_area")
        runtime.session.state.entities[remote_area.id] = remote_area
        stock_id = player.inputs[0].stock.entity_id
        runtime.session.state.relations = {
            key: value for key, value in runtime.session.state.relations.items()
            if value.source != stock_id
        }
        runtime.session.state.relations["remote:ore"] = Relation(
            "remote:ore", "located_in", stock_id, "remote_area"
        )
        runtime.session.runtime.revalidate()
        before = _state(runtime.session)
        with self.assertRaisesRegex(GameplayContractError, "missing, ambiguous, or remote"):
            resolve_action(
                runtime.session, runtime.action_registry,
                ActionRequest("remote_stock", PLAYER_ID, SKILL_ID),
            )
        self.assertEqual(_state(runtime.session), before)

    def test_insufficient_mana_time_and_input_are_atomic(self):
        player = _profile("limited_refining", PLAYER_ID)
        runtime, _, _ = _runtime((player,), player_mana=3.0, time_budget=1)
        before = _state(runtime.session)
        with self.assertRaisesRegex(GameplayContractError, "insufficient mana"):
            resolve_action(
                runtime.session, runtime.action_registry,
                ActionRequest("no_mana", PLAYER_ID, SKILL_ID),
            )
        self.assertEqual(_state(runtime.session), before)

        player = _profile("time_refining", PLAYER_ID)
        runtime, _, _ = _runtime((player,), time_budget=1)
        before = _state(runtime.session)
        with self.assertRaisesRegex(GameplayContractError, "budget is exhausted"):
            submit_timed_primary_action(
                runtime.session, runtime.action_registry,
                ActionRequest("no_time", PLAYER_ID, SKILL_ID),
            )
        self.assertEqual(_state(runtime.session), before)

        player = _profile("empty_input_refining", PLAYER_ID)
        runtime, _, _ = _runtime((player,))
        runtime.session.state.entities[player.inputs[0].stock.entity_id].components["stock"]["amount"] = 0.0
        before = _state(runtime.session)
        with self.assertRaisesRegex(GameplayContractError, "input .* empty"):
            resolve_action(
                runtime.session, runtime.action_registry,
                ActionRequest("no_input", PLAYER_ID, SKILL_ID),
            )
        self.assertEqual(_state(runtime.session), before)

    def test_context_owner_template_and_missing_law_are_rejected(self):
        player = _profile("context_refining", PLAYER_ID)
        npc = _profile("other_owner_refining", NPC_ID)
        runtime, _, _ = _runtime((player, npc))
        no_controller = ActionRegistry(
            runtime.action_registry.actions.values(),
            runtime.action_registry.statuses.values(),
            runtime.action_registry.hooks.values(),
        )
        before = _state(runtime.session)
        with self.assertRaisesRegex(GameplayContractError, "trusted ProcessController"):
            resolve_action(
                runtime.session, no_controller,
                ActionRequest("no_context", PLAYER_ID, SKILL_ID),
            )
        self.assertEqual(_state(runtime.session), before)
        with self.assertRaisesRegex(GameplayContractError, "trusted ProcessController"):
            ActionRegistry((), process_controller=object())

        missing_controller = ProcessController(
            (player,),
            external_stock_writers={player.inputs[0].stock.entity_id: "alpha_writer"},
        )
        missing_registry = ActionRegistry(
            runtime.action_registry.actions.values(),
            runtime.action_registry.statuses.values(),
            runtime.action_registry.hooks.values(),
            process_controller=missing_controller,
        )
        before = _state(runtime.session)
        with self.assertRaisesRegex(GameplayContractError, "configured world writer"):
            resolve_action(
                runtime.session, missing_registry,
                ActionRequest("writer_conflict", PLAYER_ID, SKILL_ID),
            )
        self.assertEqual(_state(runtime.session), before)

        before = _state(runtime.session)
        with self.assertRaisesRegex(GameplayContractError, "no Process profile"):
            resolve_action(
                runtime.session,
                ActionRegistry(
                    runtime.action_registry.actions.values(),
                    runtime.action_registry.statuses.values(),
                    runtime.action_registry.hooks.values(),
                    process_controller=ProcessController((npc,)),
                ),
                ActionRequest("wrong_npc_skill", PLAYER_ID, SKILL_ID),
            )
        self.assertEqual(_state(runtime.session), before)

        missing_skill = _blueprint(template_id=MISSING_ID)
        missing_runtime, _, _ = _runtime((player,), skill=missing_skill)
        before = _state(missing_runtime.session)
        with self.assertRaisesRegex(GameplayContractError, "no Process profile"):
            resolve_action(
                missing_runtime.session,
                missing_runtime.action_registry,
                ActionRequest("unknown_template", PLAYER_ID, SKILL_ID),
            )
        self.assertEqual(_state(missing_runtime.session), before)

    def test_request_and_skill_data_cannot_inject_process_authority(self):
        player = _profile("injection_refining", PLAYER_ID)
        runtime, _, _ = _runtime((player,))
        document = json.loads(json.dumps(basic_registry_document()))
        document["actions"].append({
            "id": "forged_process",
            "version": 1,
            "action_type": "skill",
            "cost": {"duration": 1, "mana": 0},
            "scope": {"selectors": ["current_area"], "relation_types": []},
            "effects": [{
                "id": "start",
                "kind": "process_start",
                "target": {"kind": "current_area"},
                "commitment": "required",
                "process_template_id": TEMPLATE_ID,
                "process_entity_id": player.process_entity_id,
            }],
        })
        with self.assertRaises(GameplayContractError):
            ActionRegistry.parse(document)

        effect = deepcopy(runtime.action_registry.actions[SKILL_ID].effects[0])
        self.assertEqual(effect.process_template_id, TEMPLATE_ID)
        with self.assertRaisesRegex(GameplayContractError, "current_area"):
            from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.effects import (
                parse_effect,
            )
            parse_effect({
                "id": "bad",
                "kind": "process_start",
                "target": {"kind": "self"},
                "commitment": "required",
                "process_template_id": TEMPLATE_ID,
            }, runtime.action_registry.statuses)

        with self.assertRaisesRegex(GameplayContractError, "active on_use"):
            parse_skill_blueprint({
                "protocol": "pmw-gameplay-v0.4",
                "kind": "passive_blueprint",
                "id": "passive_start",
                "version": 1,
                "trigger": "action_started",
                "condition": None,
                "duration": None,
                "cost": {"duration": 1, "mana": 0},
                "scope": {"selectors": ["current_area"], "relation_types": []},
                "effects": [{
                    "id": "start",
                    "kind": "process_start",
                    "target": {"kind": "current_area"},
                    "commitment": "required",
                    "process_template_id": TEMPLATE_ID,
                }],
                "budget": {"limit": 5},
                "max_firings_per_root": 1,
                "material_ids": ["process_crystal"],
            }, runtime.action_registry.statuses, material_authority((_material(),)))

    def test_only_one_process_start_per_action(self):
        document = basic_registry_document()
        document["actions"].append({
            "id": "two_starts",
            "version": 1,
            "action_type": "skill",
            "cost": {"duration": 1, "mana": 0},
            "scope": {"selectors": ["current_area"], "relation_types": []},
            "effects": [
                {
                    "id": "one",
                    "kind": "process_start",
                    "target": {"kind": "current_area"},
                    "commitment": "required",
                    "process_template_id": TEMPLATE_ID,
                },
                {
                    "id": "two",
                    "kind": "process_start",
                    "target": {"kind": "current_area"},
                    "commitment": "required",
                    "process_template_id": TEMPLATE_ID,
                },
            ],
        })
        with self.assertRaisesRegex(GameplayContractError, "at most one"):
            ActionRegistry.parse(document)


class TrustedLifecycleTests(unittest.TestCase):
    def test_hook_or_passive_process_start_is_rejected(self):
        player = _profile("hook_refining", PLAYER_ID)
        runtime, _, _ = _runtime((player,))
        from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.actions import (
            _resolve_action,
        )
        before = _state(runtime.session)
        with self.assertRaisesRegex(GameplayContractError, "active primary execution"):
            _resolve_action(
                runtime.session,
                runtime.action_registry,
                ActionRequest("forged_hook", PLAYER_ID, SKILL_ID),
                execution_kind="hook",
                hook_context={"hook_id": "forged", "cooldown_until": 0},
            )
        self.assertEqual(_state(runtime.session), before)

    def test_equipment_disable_and_hash_checks_remain_authoritative(self):
        player = _profile("equipment_refining", PLAYER_ID)
        runtime, compiled, skill = _runtime((player,))
        change_loadout(
            runtime.session,
            runtime.manifest,
            actor_id=PLAYER_ID,
            operation="unload_active",
            slot=0,
        )
        change_loadout(
            runtime.session,
            runtime.manifest,
            actor_id=NPC_ID,
            operation="unload_active",
            slot=0,
        )
        before = _state(runtime.session)
        with self.assertRaisesRegex(GameplayContractError, "equipped"):
            resolve_action(
                runtime.session,
                runtime.action_registry,
                ActionRequest("not_equipped", PLAYER_ID, SKILL_ID),
            )
        self.assertEqual(_state(runtime.session), before)

        tampered_document = json.loads(skill.canonical_document_json)
        tampered_document["version"] = 2
        tampered_document["effects"][0]["process_template_id"] = "other_template"
        tampered = parse_skill_blueprint(
            tampered_document,
            runtime.base_registry.statuses,
            skill.material_authority,
        )
        with self.assertRaisesRegex(GameplayContractError, "canonical hash"):
            runtime.install_blueprint(replace(tampered, canonical_hash=skill.canonical_hash))

    def test_disabling_keeps_retired_lifecycle_laws_with_controller_context(self):
        player = _profile("disabled_refining", PLAYER_ID)
        runtime, _, _ = _runtime((player,))
        change_loadout(
            runtime.session,
            runtime.manifest,
            actor_id=PLAYER_ID,
            operation="unload_active",
            slot=0,
        )
        change_loadout(
            runtime.session,
            runtime.manifest,
            actor_id=NPC_ID,
            operation="unload_active",
            slot=0,
        )
        result = runtime.disable(SKILL_ID)
        self.assertEqual(result.after.entries[-1].enabled, False)
        self.assertNotIn(SKILL_ID, runtime.action_registry.actions)
        self.assertIsNotNone(runtime.base_registry.process_controller)

        missing_law_runtime, compiled, _ = _runtime((player,))
        content = compiled.content
        filtered = tuple(
            law for law in compiled.laws
            if not law["id"].startswith("pmw.v04.sandbox.process.")
        )
        broken = type(compiled)(content, filtered)
        with self.assertRaisesRegex(GameplayContractError, "cascade did not activate"):
            session = build_content_session(
                deepcopy(missing_law_runtime.session.state),
                broken,
            )
            resolve_action(
                session,
                missing_law_runtime.action_registry,
                ActionRequest("missing_law", PLAYER_ID, SKILL_ID),
            )

    def test_operation_exception_rolls_back_complete_process_action(self):
        player = _profile("rollback_refining", PLAYER_ID)
        runtime, _, _ = _runtime((player,))
        before = _state(runtime.session)
        revisions = _revision(runtime.session)
        from experiments.generative_mechanics.next_tracks_v06.gameplay_v04 import processes

        original_preflight = processes._preflight
        controller = runtime.action_registry.process_controller

        def fail_after_preflight(*args, **kwargs):
            original_preflight(*args, **kwargs)
            raise RuntimeError("injected late process preflight failure")

        with patch.object(processes, "_preflight", side_effect=fail_after_preflight):
            with self.assertRaisesRegex(RuntimeError, "injected late"):
                resolve_action(
                    runtime.session,
                    runtime.action_registry,
                    ActionRequest("late_failure", PLAYER_ID, SKILL_ID),
                )
        self.assertEqual(_state(runtime.session), before)
        self.assertEqual(_revision(runtime.session), revisions)

    def test_actual_tick_failure_rolls_back_action_time_and_stock(self):
        player = _profile("tick_failure_refining", PLAYER_ID)
        runtime, _, _ = _runtime((player,), time_budget=4)
        before = _state(runtime.session)
        from experiments.generative_mechanics.next_tracks_v06.gameplay_v04 import time_ledger

        real_tick = time_ledger.advance_world_tick
        calls = 0

        def fail_second_tick(working, **kwargs):
            nonlocal calls
            calls += 1
            result = real_tick(working, **kwargs)
            if calls == 2:
                raise RuntimeError("injected late tick failure")
            return result

        with patch.object(time_ledger, "advance_world_tick", side_effect=fail_second_tick):
            with self.assertRaisesRegex(RuntimeError, "late tick"):
                submit_timed_primary_action(
                    runtime.session,
                    runtime.action_registry,
                    ActionRequest("tick_failure", PLAYER_ID, SKILL_ID),
                )
        self.assertEqual(_state(runtime.session), before)


class ContentAndProjectionTests(unittest.TestCase):
    def test_registry_checkpoint_rebuild_and_static_tamper_rejection(self):
        player = _profile("checkpoint_refining", PLAYER_ID)
        runtime, compiled, _ = _runtime((player,))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "registry.json"
            save_registry_checkpoint(path, runtime)
            restored = load_registry_checkpoint(path, compiled)
            self.assertEqual(restored.session.state.to_dict(), runtime.session.state.to_dict())
            self.assertIsNotNone(restored.base_registry.process_controller)
            outcome = resolve_action(
                restored.session,
                restored.action_registry,
                ActionRequest("restored_start", PLAYER_ID, SKILL_ID),
            )
            self.assertTrue(outcome.event_result.changed)

            document = json.loads(path.read_text(encoding="utf-8"))
            document["runtime_config"]["static_laws"] = []
            path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(GameplayContractError, "payload hash mismatch"):
                load_registry_checkpoint(path, compiled)

    def test_blueprint_template_identity_is_world_independent(self):
        skill = _blueprint()
        player = _profile("world_one_refining", PLAYER_ID)
        one, _, _ = _runtime((player,), skill=skill)
        other_player = _profile("world_two_refining", PLAYER_ID)
        two, _, _ = _runtime((other_player,), skill=skill)
        self.assertEqual(
            one.action_registry.actions[SKILL_ID].canonical_hash,
            two.action_registry.actions[SKILL_ID].canonical_hash,
        )
        one_outcome = resolve_action(
            one.session, one.action_registry,
            ActionRequest("world_one_use", PLAYER_ID, SKILL_ID),
        )
        two_outcome = resolve_action(
            two.session, two.action_registry,
            ActionRequest("world_two_use", PLAYER_ID, SKILL_ID),
        )
        self.assertTrue(one_outcome.event_result.changed)
        self.assertTrue(two_outcome.event_result.changed)
        self.assertNotEqual(
            one_outcome.effect_outcomes[0]["values"]["process_profile_id"],
            two_outcome.effect_outcomes[0]["values"]["process_profile_id"],
        )

    def test_semantics_graph_represents_process_template_without_hidden_identity(self):
        player = _profile("analysis_refining", PLAYER_ID)
        runtime, _, _ = _runtime((player,))
        analysis = RegistrySemanticsProvider(runtime.action_registry).semantics(SKILL_ID)
        process_write = next(row for row in analysis.writes if row.operation == "process_start")
        self.assertEqual(process_write.path, f"process:{TEMPLATE_ID}:state")
        self.assertNotIn(player.id, process_write.path)
        self.assertNotIn(player.process_entity_id, process_write.path)
        graph = BuildAnalyzer(RegistrySemanticsProvider(runtime.action_registry)).analyze((SKILL_ID, "basic_attack"))
        self.assertIn(SKILL_ID, graph.action_ids)

    def test_sandbox_projection_drops_process_action_without_hidden_context(self):
        player = _profile("projection_refining", PLAYER_ID)
        runtime, _, _ = _runtime((player,))
        observation = ActorObservationBuilder().build(
            runtime.session,
            runtime.action_registry,
            PLAYER_ID,
            ObservationDisclosure.create(),
        )
        simulator = SandboxSimulator(runtime.action_registry)
        projected, projected_registry, _ = simulator._build(observation)
        self.assertNotIn(SKILL_ID, projected_registry.actions)
        self.assertIsNone(projected_registry.process_controller)
        self.assertIn("basic_wait", projected_registry.actions)
        result = simulator.simulate(
            observation,
            ActionRequest("projected_process", PLAYER_ID, SKILL_ID),
        )
        self.assertFalse(result.legal)
        self.assertIn("unknown registered action", result.rejection)

    def test_existing_default_registry_and_time_paths_remain_unchanged(self):
        basic = basic_registry()
        self.assertIsNone(basic.process_controller)
        compiled = compile_content(
            make_content(basic, material_ids=())
        )
        self.assertFalse(any(
            law["id"].startswith("pmw.v04.sandbox.process.")
            for law in compiled.laws
        ))


if __name__ == "__main__":
    unittest.main()
