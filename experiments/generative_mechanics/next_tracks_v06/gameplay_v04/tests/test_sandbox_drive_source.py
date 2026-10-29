from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
import json
import math
from types import MappingProxyType
import tempfile
import unittest
from unittest.mock import patch

from pmw import Relation

from experiments.generative_mechanics.next_tracks_v06.gameplay_v04 import time_ledger
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.action_compiler import (
    build_action_laws,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.actions import (
    ActionRegistry,
    ActionRequest,
    submit_timed_primary_action,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.basics import (
    basic_registry,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.blueprints import (
    instantiate_actor,
    instantiate_area,
    parse_actor_blueprint,
    parse_area_blueprint,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.checkpoint import (
    load_registry_checkpoint,
    save_registry_checkpoint,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.content_compiler import (
    Gate3Content,
    build_content_session,
    compile_content,
    initialize_content_world,
    make_content,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.contracts import (
    FieldDefinition,
    GameplayContractError,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.drives import (
    DRIVE_COMPONENT,
    DRIVE_STEP_EVENT,
    DriveController,
    DriveProfile,
    instantiate_drive,
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
    ConversionPort,
    ProcessController,
    ProcessLimits,
    ProcessProfile,
    ProcessTemplate,
    StockBinding,
    StockRef,
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
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.simulation import (
    SandboxSimulator,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.skills import (
    parse_skill_blueprint,
    registry_manifest,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.time_ledger import (
    initialize_time_budget,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.worlds import (
    build_gameplay_world,
)


PLAYER = "player_actor"
NPC = "npc_actor"
AREA = "field_area"
FIELD = "soil"
UNIT = "fuel"
PROFILE = "soil_drive"
SKILL = "start_soil_drive"


def _field(
    *,
    initial: float = 1.0,
    target: float = 1.0,
    rate: float = 0.0,
    curve: str = "none",
    maximum: float = 10.0,
) -> FieldDefinition:
    blueprint = parse_area_blueprint({
        "protocol": "pmw-gameplay-v0.4",
        "kind": "area_blueprint",
        "id": "drive_area_blueprint",
        "fields": [{
            "id": FIELD,
            "domain": {"min": 0.0, "max": maximum},
            "initial": initial,
            "target": target,
            "rate": rate,
            "curve": curve,
            "max_persistent_patches": 1,
            "max_temporary_modifiers": 2,
        }],
    })
    return blueprint.fields[0]


def _area(definition: FieldDefinition):
    blueprint = parse_area_blueprint({
        "protocol": "pmw-gameplay-v0.4",
        "kind": "area_blueprint",
        "id": "drive_area_blueprint",
        "fields": [{
            "id": definition.id,
            "domain": {"min": definition.minimum, "max": definition.maximum},
            "initial": definition.initial,
            "target": definition.target,
            "rate": definition.rate,
            "curve": definition.curve,
            "max_persistent_patches": definition.max_persistent_patches,
            "max_temporary_modifiers": definition.max_temporary_modifiers,
        }],
    })
    return instantiate_area(blueprint, AREA)


def _actor(actor_id: str, *, human: bool):
    blueprint = parse_actor_blueprint({
        "protocol": "pmw-gameplay-v0.4",
        "kind": "actor_blueprint",
        "id": "drive_actor_blueprint",
        "hp": {"max": 50.0, "initial": 50.0},
        "mana": {"max": 30.0, "initial": 20.0, "dynamics": None},
        "attributes": {
            "power": 4.0,
            "control": 4.0,
            "resilience": 4.0,
            "agility": 4.0,
        },
        "traits": [],
    })
    return instantiate_actor(
        blueprint, actor_id, controller="human" if human else "ai"
    )


def _located_actor(actor_id: str, *, human: bool) -> tuple:
    actor = _actor(actor_id, human=human)
    relation = Relation(
        f"located:{actor_id}:{AREA}", "located_in", actor_id, AREA
    )
    return actor, relation


def _profile(
    profile_id: str = PROFILE,
    *,
    owner: str = PLAYER,
    stock_id: str | None = None,
    coefficient: float = 2.0,
    max_rate: float = 4.0,
    max_duration: int = 8,
    field: FieldDefinition | None = None,
) -> DriveProfile:
    definition = field or _field()
    return DriveProfile(
        id=profile_id,
        drive_entity_id=f"drive_{profile_id}",
        owner=owner,
        area_id=AREA,
        field=definition,
        stock=StockRef(stock_id or f"{profile_id}_fuel"),
        stock_unit=UNIT,
        field_per_stock=coefficient,
        max_rate=max_rate,
        max_duration_ticks=max_duration,
    )


def _world(
    profiles: tuple[DriveProfile, ...],
    *,
    field: FieldDefinition | None = None,
    stock_amounts: dict[str, float] | None = None,
):
    definition = field or profiles[0].field
    player, player_relation = _located_actor(PLAYER, human=True)
    npc, npc_relation = _located_actor(NPC, human=False)
    area = _area(definition)
    world = build_gameplay_world(
        "drive_owner_world",
        areas=(area,),
        actors=(player, npc),
        placements=(),
    )
    world.entities.update({AREA: area, PLAYER: player, NPC: npc})
    world.relations[player_relation.id] = player_relation
    world.relations[npc_relation.id] = npc_relation
    for profile in profiles:
        amount = (stock_amounts or {}).get(profile.stock.entity_id, 10.0)
        world.entities[profile.drive_entity_id] = instantiate_drive(profile)
        world.entities[profile.stock.entity_id] = stock_entity(
            profile.stock.entity_id,
            amount=amount,
            capacity=max(10.0, amount),
            unit=profile.stock_unit,
        )
        for endpoint in (profile.drive_entity_id, profile.stock.entity_id):
            relation_id = f"located:{endpoint}:{AREA}"
            world.relations[relation_id] = Relation(
                relation_id, "located_in", endpoint, AREA
            )
    world.entities["pmw:v04:clock"] = clock_entity()
    return initialize_time_budget(world, 20)


def _material(duration: int = 4):
    return parse_material({
        "id": "drive_crystal",
        "tier": "rare",
        "region_rarity": "scarce",
        "traits": [{
            "id": "finite_field_drive",
            "effect_kinds": ["drive_source"],
            "selectors": ["current_area"],
            "budget_points": 5.0 + 0.1 * duration,
        }],
    })


def _skill(
    *,
    skill_id: str = SKILL,
    profile_id: str = PROFILE,
    rate: float = 2.0,
    duration: int = 4,
):
    material = _material(duration)
    return parse_skill_blueprint({
        "protocol": "pmw-gameplay-v0.4",
        "kind": "skill_blueprint",
        "id": skill_id,
        "version": 1,
        "trigger": "on_use",
        "condition": None,
        "duration": None,
        "cost": {"duration": 1, "mana": 4},
        "scope": {"selectors": ["current_area"], "relation_types": []},
        "effects": [{
            "id": "drive",
            "kind": "drive_source",
            "target": {"kind": "current_area"},
            "commitment": "required",
            "drive_profile_id": profile_id,
            "drive_rate": rate,
            "duration": duration,
        }],
        "budget": {"limit": 5.0 + 0.1 * duration},
        "max_firings_per_root": 1,
        "material_ids": ["drive_crystal"],
    }, basic_registry().statuses, material_authority((material,)))


def _native_runtime(
    profiles: tuple[DriveProfile, ...],
    *,
    field: FieldDefinition | None = None,
    stock_amounts: dict[str, float] | None = None,
):
    world = _world(profiles, field=field, stock_amounts=stock_amounts)
    controller = DriveController(profiles)
    return build_runtime(world, extra_laws=controller.laws), controller


def _formal_runtime(profile: DriveProfile, *, skill_id: str = SKILL, field=None):
    skill = _skill(skill_id=skill_id, profile_id=profile.id)
    base = ActionRegistry(
        basic_registry().actions.values(),
        basic_registry().statuses.values(),
        drive_controller=DriveController((profile,)),
    )
    content = make_content(
        base,
        skills=(skill,),
        material_ids=("drive_crystal",),
    )
    world = initialize_content_world(
        _world((profile,), field=field), content
    )
    compiled = compile_content(content)
    session = build_content_session(world, compiled)
    runtime = MechanismRegistryRuntime.from_compiled_content(session, compiled)
    change_loadout(
        runtime.session,
        runtime.manifest,
        actor_id=profile.owner,
        operation="equip_active",
        skill=skill_ref(skill),
        slot=0,
    )
    return runtime, compiled, skill


def _field_value(session) -> float:
    return float(
        session.state.entities[AREA]
        .components["pmw_gameplay_dynamics"]["fields"][FIELD]["value"]
    )


def _amount(session, entity_id: str) -> float:
    return float(session.state.entities[entity_id].components["stock"]["amount"])


def _drive(session, profile: DriveProfile) -> dict:
    return session.state.entities[profile.drive_entity_id].components[
        DRIVE_COMPONENT
    ]


def _snapshot(session):
    return (
        deepcopy(session.state.to_dict()),
        session.runtime.revision,
        session.runtime.object_revision,
        deepcopy(session.runtime.stats),
        session.runtime.state_closure_known,
        tuple(
            (event.id, event.type, event.time, deepcopy(event.payload))
            for event in session.state.scheduled_events
        ),
    )


def _process_profile(stock_id: str) -> ProcessProfile:
    template = ProcessTemplate(
        "fuel_boiler",
        (ConversionPort("fuel", 1.0, UNIT),),
        (ConversionPort("ash", 1.0, "ash"),),
        1.0,
        1,
        2.0,
        2,
    )
    return ProcessProfile(
        "boiler",
        template,
        "process_boiler",
        PLAYER,
        (StockBinding("fuel", StockRef(stock_id)),),
        (StockBinding("ash", StockRef("process_ash")),),
    )


class DriveSourceOwnerTests(unittest.TestCase):
    def test_profile_effect_schema_and_pure_prepare_start(self):
        profile = _profile()
        session, controller = _native_runtime((profile,))
        before = _snapshot(session)
        prepared = controller.prepare_start(
            session,
            profile.id,
            owner=PLAYER,
            rate=2.0,
            duration_ticks=4,
        )
        self.assertEqual(_snapshot(session), before)
        self.assertEqual(prepared["profile_hash"], profile.profile_hash)
        self.assertEqual(prepared["expires_at"], 4.0)
        with self.assertRaises(FrozenInstanceError):
            profile.max_rate = 5.0

        valid = {
            "id": "drive",
            "kind": "drive_source",
            "target": {"kind": "current_area"},
            "commitment": "required",
            "drive_profile_id": profile.id,
            "drive_rate": 2.0,
            "duration": 4,
        }
        self.assertEqual(
            parse_effect(valid, basic_registry().statuses).kind,
            "drive_source",
        )
        mutations = (
            ("source_unit", UNIT, "missing or unknown"),
            ("field_per_stock", 2.0, "missing or unknown"),
            ("target", {"kind": "self"}, "current_area"),
            ("drive_rate", True, "finite positive"),
            ("duration", 0, "positive integer"),
        )
        for key, value, pattern in mutations:
            raw = dict(valid)
            raw[key] = value
            with self.subTest(key=key), self.assertRaisesRegex(
                GameplayContractError, pattern
            ):
                parse_effect(raw, basic_registry().statuses)

        controller.start(
            session,
            profile.id,
            owner=PLAYER,
            rate=2.0,
            duration_ticks=4,
        )
        self.assertEqual(_drive(session, profile)["rate"], 2.0)
        self.assertEqual(_drive(session, profile)["last_step"], -1)

    def test_one_control_and_mixed_process_drive_rejection(self):
        raw = json.loads(_skill().canonical_document_json)
        raw["effects"] = [
            {
                "id": "start_one",
                "kind": "process_start",
                "target": {"kind": "current_area"},
                "commitment": "required",
                "process_template_id": "fuel_boiler",
            },
            {
                "id": "start_two",
                "kind": "process_start",
                "target": {"kind": "current_area"},
                "commitment": "required",
                "process_template_id": "fuel_boiler",
            },
        ]
        with self.assertRaisesRegex(
            GameplayContractError, "at most one process_start"
        ):
            parse_skill_blueprint(
                raw,
                basic_registry().statuses,
                material_authority((_material(),)),
            )

        mixed = json.loads(_skill().canonical_document_json)
        mixed["effects"].append({
            "id": "start_process",
            "kind": "process_start",
            "target": {"kind": "current_area"},
            "commitment": "required",
            "process_template_id": "fuel_boiler",
        })
        with self.assertRaisesRegex(
            GameplayContractError,
            "at most one Process/Drive control operation",
        ):
            parse_skill_blueprint(
                mixed,
                basic_registry().statuses,
                material_authority((_material(),)),
            )

    def test_formal_player_and_npc_timed_quantitative_ticks(self):
        for actor_id, skill_id, profile_id in (
            (PLAYER, "player_drive", "player_soil_drive"),
            (NPC, "npc_drive", "npc_soil_drive"),
        ):
            profile = _profile(
                profile_id,
                owner=actor_id,
                stock_id=f"{profile_id}_fuel",
            )
            runtime, _, skill = _formal_runtime(
                profile, skill_id=skill_id
            )
            self.assertEqual(skill.budget_used, 5.4)
            timed = submit_timed_primary_action(
                runtime.session,
                runtime.action_registry,
                ActionRequest(f"{skill_id}_cast", actor_id, skill_id),
            )
            self.assertEqual((timed.time.duration, timed.time.after_remaining), (1, 19))
            self.assertEqual(_field_value(runtime.session), 3.0)
            self.assertEqual(_amount(runtime.session, profile.stock.entity_id), 9.0)
            self.assertEqual(
                runtime.session.state.entities[actor_id]
                .components["pmw_gameplay_actor"]["mana"],
                16.0,
            )
            self.assertEqual(_drive(runtime.session, profile)["last_step"], 1)
            self.assertTrue(any(
                event.event.type == DRIVE_STEP_EVENT
                for event in timed.time.ticks[0].event_result.trace.events
            ))

    def test_duration_four_expires_before_tick_four_and_duration_one_is_exact(self):
        profile = _profile("duration_four")
        session, controller = _native_runtime((profile,))
        controller.start(
            session,
            profile.id,
            owner=PLAYER,
            rate=1.0,
            duration_ticks=4,
        )
        for step in (1, 2, 3):
            result = advance_world_tick(session)
            self.assertEqual(result.step, step)
            self.assertEqual(_field_value(session), 1.0 + step)
        self.assertEqual(_amount(session, profile.stock.entity_id), 8.5)
        advance_world_tick(session)
        self.assertEqual(_field_value(session), 4.0)
        self.assertEqual(_amount(session, profile.stock.entity_id), 8.5)
        self.assertIsNone(_drive(session, profile)["started_at"])

        short = _profile("duration_one")
        short_session, short_controller = _native_runtime((short,))
        short_controller.start(
            short_session,
            short.id,
            owner=PLAYER,
            rate=1.0,
            duration_ticks=1,
        )
        advance_world_tick(short_session)
        self.assertEqual(_field_value(short_session), 1.0)
        self.assertEqual(_amount(short_session, short.stock.entity_id), 10.0)
        self.assertEqual(_drive(short_session, short)["last_step"], -1)

    def test_full_field_linear_recovery_steps_after_root_dynamics(self):
        definition = _field(initial=9.9, target=9.5, rate=0.5, curve="linear")
        profile = _profile("recovery_drive", field=definition)
        runtime, _, _ = _formal_runtime(profile, field=definition)
        submit_timed_primary_action(
            runtime.session,
            runtime.action_registry,
            ActionRequest("fill_field", PLAYER, SKILL),
        )
        self.assertEqual(_field_value(runtime.session), 10.0)
        self.assertEqual(_amount(runtime.session, profile.stock.entity_id), 9.85)

        recovered = advance_world_tick(runtime.session)
        self.assertEqual(_field_value(runtime.session), 10.0)
        self.assertAlmostEqual(
            _amount(runtime.session, profile.stock.entity_id), 9.725
        )
        self.assertAlmostEqual(
            _drive(runtime.session, profile)["last_delta"], 0.25
        )
        steps = [
            event for event in recovered.event_result.trace.events
            if event.event.type == DRIVE_STEP_EVENT
        ]
        self.assertEqual(len(steps), 1)
        self.assertEqual(_drive(runtime.session, profile)["last_step"], 2)

    def test_unrepresentable_paired_changes_are_conservative_no_ops(self):
        huge_field = _field(initial=0.0, target=0.0, maximum=1.0)
        huge = _profile(
            "huge_stock_drive",
            coefficient=1e-6,
            field=huge_field,
        )
        huge_session, huge_controller = _native_runtime(
            (huge,),
            field=huge_field,
            stock_amounts={huge.stock.entity_id: 1e12},
        )
        huge_controller.start(
            huge_session,
            huge.id,
            owner=PLAYER,
            rate=1e-12,
            duration_ticks=4,
        )
        advance_world_tick(huge_session)
        self.assertEqual(_field_value(huge_session), 0.0)
        self.assertEqual(_amount(huge_session, huge.stock.entity_id), 1e12)
        self.assertEqual(_drive(huge_session, huge)["last_step"], 1)
        self.assertEqual(_drive(huge_session, huge)["last_delta"], 0.0)

        high_value = math.nextafter(1.0, 0.0)
        high_field = _field(initial=high_value, target=high_value, maximum=1.0)
        high = _profile(
            "high_field_drive",
            coefficient=1e-18,
            field=high_field,
        )
        high_session, high_controller = _native_runtime(
            (high,),
            field=high_field,
            stock_amounts={high.stock.entity_id: 1e6},
        )
        high_controller.start(
            high_session,
            high.id,
            owner=PLAYER,
            rate=1e-17,
            duration_ticks=4,
        )
        advance_world_tick(high_session)
        self.assertEqual(_field_value(high_session), high_value)
        self.assertEqual(_amount(high_session, high.stock.entity_id), 1e6)
        self.assertEqual(_drive(high_session, high)["last_step"], 1)
        self.assertEqual(_drive(high_session, high)["last_delta"], 0.0)

    def test_ordinary_coefficient_and_capacity_clamp_stay_proportional(self):
        profile = _profile("proportional_drive", coefficient=3.0)
        session, controller = _native_runtime(
            (profile,),
            stock_amounts={profile.stock.entity_id: 2.0},
        )
        controller.start(
            session,
            profile.id,
            owner=PLAYER,
            rate=1.5,
            duration_ticks=4,
        )
        advance_world_tick(session)
        self.assertEqual(_field_value(session), 2.5)
        self.assertEqual(_amount(session, profile.stock.entity_id), 1.5)
        self.assertEqual(_drive(session, profile)["last_delta"], 1.5)

        clamped_field = _field(initial=8.75, target=8.75, maximum=9.0)
        clamped = _profile("clamped_drive", field=clamped_field)
        clamped_session, clamped_controller = _native_runtime(
            (clamped,),
            field=clamped_field,
            stock_amounts={clamped.stock.entity_id: 0.1},
        )
        clamped_controller.start(
            clamped_session,
            clamped.id,
            owner=PLAYER,
            rate=2.0,
            duration_ticks=4,
        )
        advance_world_tick(clamped_session)
        self.assertAlmostEqual(_field_value(clamped_session), 8.95)
        self.assertAlmostEqual(
            _amount(clamped_session, clamped.stock.entity_id), 0.0
        )
        self.assertAlmostEqual(
            _drive(clamped_session, clamped)["last_delta"], 0.2, places=14
        )

    def test_shared_field_uses_stable_profile_id_order(self):
        definition = _field()
        profiles = (
            _profile("z_drive", coefficient=4.0, field=definition),
            _profile("a_drive", coefficient=2.0, field=definition),
            _profile("b_drive", coefficient=2.0, field=definition),
        )
        session, controller = _native_runtime(profiles, field=definition)
        for profile in reversed(profiles):
            controller.start(
                session,
                profile.id,
                owner=profile.owner,
                rate=2.0,
                duration_ticks=4,
            )
        advance_world_tick(session)
        self.assertEqual(_field_value(session), 7.0)
        self.assertEqual(
            {
                profile.id: _amount(session, profile.stock.entity_id)
                for profile in profiles
            },
            {"a_drive": 9.0, "b_drive": 9.0, "z_drive": 9.5},
        )

    def test_content_compile_rejects_process_input_and_output_stock_overlap(self):
        for drive_stock, process_stock, label in (
            ("shared_fuel", "shared_fuel", "input"),
            ("process_ash", None, "output"),
        ):
            if process_stock is None:
                process_stock = "process_fuel"
            drive = _profile("overlap_drive", stock_id=drive_stock)
            process = _process_profile(process_stock)
            registry = ActionRegistry(
                basic_registry().actions.values(),
                basic_registry().statuses.values(),
                process_controller=ProcessController((process,), ProcessLimits()),
                drive_controller=DriveController((drive,)),
            )
            content = Gate3Content(
                registry,
                (),
                registry_manifest(()),
                MappingProxyType({}),
                MappingProxyType({}),
                MappingProxyType({}),
                MappingProxyType({}),
                (),
            )
            with self.subTest(kind=label):
                with self.assertRaisesRegex(
                    GameplayContractError, "overlaps configured Process"
                ):
                    compile_content(content)

    def test_drive_child_cascade_and_formal_late_tick_rollback(self):
        profile = _profile("rollback_drive")
        runtime, _, _ = _formal_runtime(profile)
        laws = (
            *tuple(dict(item) for item in runtime.static_laws),
            *build_action_laws(runtime.action_registry),
        )
        runtime.session = build_runtime(
            deepcopy(runtime.session.state),
            runtime.session.profiles,
            (
                *laws,
                {
                    "id": "pmw.v04.owner.drive_step_explode",
                    "mode": "event",
                    "priority": 100,
                    "bindings": {
                        "drive": {
                            "kind": "entity",
                            "requires": [DRIVE_COMPONENT],
                        },
                    },
                    "when": {"all": [
                        {"event.type": {"eq": DRIVE_STEP_EVENT}},
                        {"ref": "$drive.id", "eq": profile.drive_entity_id},
                    ]},
                    "effects": [{
                        "op": "set",
                        "target": f"$drive.{DRIVE_COMPONENT}.last_delta",
                        "value": {"div": [1, 0]},
                    }],
                },
            ),
        )
        before = _snapshot(runtime.session)
        with self.assertRaises(ZeroDivisionError):
            submit_timed_primary_action(
                runtime.session,
                runtime.action_registry,
                ActionRequest("cascade_rollback", PLAYER, SKILL),
            )
        self.assertEqual(_snapshot(runtime.session), before)

        runtime, _, _ = _formal_runtime(_profile("late_tick_drive"))
        before = _snapshot(runtime.session)
        real_tick = time_ledger.advance_world_tick

        def fail_after_tick(working, **kwargs):
            result = real_tick(working, **kwargs)
            raise RuntimeError("owner late tick failure")

        with patch.object(
            time_ledger, "advance_world_tick", side_effect=fail_after_tick
        ):
            with self.assertRaisesRegex(RuntimeError, "late tick"):
                submit_timed_primary_action(
                    runtime.session,
                    runtime.action_registry,
                    ActionRequest("late_drive", PLAYER, SKILL),
                )
        self.assertEqual(_snapshot(runtime.session), before)

    def test_checkpoint_changed_profile_replay_and_actor_safe_projection(self):
        profile = _profile("checkpoint_drive")
        runtime, compiled, skill = _formal_runtime(profile)
        submit_timed_primary_action(
            runtime.session,
            runtime.action_registry,
            ActionRequest("checkpoint_cast", PLAYER, SKILL),
        )
        with tempfile.TemporaryDirectory() as directory:
            path = f"{directory}/drive_checkpoint.json"
            save_registry_checkpoint(path, runtime)
            restored = load_registry_checkpoint(path, compiled)
            self.assertIsNotNone(restored.base_registry.drive_controller)
            original_tick = advance_world_tick(runtime.session)
            restored_tick = advance_world_tick(restored.session)
            self.assertEqual(
                runtime.session.state.to_dict(),
                restored.session.state.to_dict(),
            )
            self.assertEqual(
                original_tick.event_result.trace.to_dict(),
                restored_tick.event_result.trace.to_dict(),
            )

            changed = replace(profile, field_per_stock=3.0)
            changed_content = make_content(
                ActionRegistry(
                    basic_registry().actions.values(),
                    basic_registry().statuses.values(),
                    drive_controller=DriveController((changed,)),
                ),
                skills=(skill,),
                material_ids=("drive_crystal",),
            )
            changed_compiled = compile_content(changed_content)
            with self.assertRaisesRegex(
                GameplayContractError, "static Law configuration"
            ):
                load_registry_checkpoint(path, changed_compiled)

        observation = ActorObservationBuilder().build(
            restored.session,
            restored.action_registry,
            PLAYER,
            ObservationDisclosure.create(),
        )
        rendered = json.dumps(observation.to_dict(), sort_keys=True)
        self.assertNotIn(profile.drive_entity_id, rendered)
        self.assertNotIn(profile.stock.entity_id, rendered)
        simulator = SandboxSimulator(restored.action_registry)
        projected, projected_registry, _ = simulator._build(observation)
        self.assertNotIn(profile.drive_entity_id, projected.state.entities)
        self.assertNotIn(profile.stock.entity_id, projected.state.entities)
        self.assertIsNone(projected_registry.drive_controller)
        self.assertNotIn(SKILL, projected_registry.actions)
        self.assertIn("basic_wait", projected_registry.actions)
        result = simulator.simulate(
            observation,
            ActionRequest("projected_wait", PLAYER, "basic_wait"),
        )
        self.assertTrue(result.legal, result.rejection)


if __name__ == "__main__":
    unittest.main()
