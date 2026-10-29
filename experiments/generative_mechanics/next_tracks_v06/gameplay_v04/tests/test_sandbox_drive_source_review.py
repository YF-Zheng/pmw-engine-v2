from __future__ import annotations

from copy import deepcopy
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pmw import Event, Relation

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
    CompiledGate3Content,
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
    DRIVE_EXPIRE_EVENT,
    DRIVE_STEP_EVENT,
    DriveController,
    DriveLimits,
    DriveProfile,
    instantiate_drive,
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
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.simulation import (
    SandboxSimulator,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.skills import (
    parse_skill_blueprint,
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
REMOTE = "remote_area"
FIELD = "soil"
UNIT = "fuel"
SKILL = "start_charge_soil"
PROFILE = "soil_drive"


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
        "id": "field_blueprint",
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


def _area(area_id: str, definition: FieldDefinition):
    blueprint = parse_area_blueprint({
        "protocol": "pmw-gameplay-v0.4",
        "kind": "area_blueprint",
        "id": f"{area_id}_blueprint",
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
    return instantiate_area(blueprint, area_id)


def _actor(actor_id: str, *, human: bool):
    blueprint = parse_actor_blueprint({
        "protocol": "pmw-gameplay-v0.4",
        "kind": "actor_blueprint",
        "id": f"{actor_id}_blueprint",
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
        blueprint,
        actor_id,
        controller="human" if human else "ai",
    )


def _profile(
    profile_id: str = PROFILE,
    *,
    owner: str = PLAYER,
    area_id: str = AREA,
    stock_id: str = "fuel_stock",
    coefficient: float = 2.0,
    max_rate: float = 4.0,
    max_duration: int = 8,
    field: FieldDefinition | None = None,
) -> DriveProfile:
    return DriveProfile(
        id=profile_id,
        drive_entity_id=f"drive_{profile_id}",
        owner=owner,
        area_id=area_id,
        field=field or _field(),
        stock=StockRef(stock_id),
        stock_unit=UNIT,
        field_per_stock=coefficient,
        max_rate=max_rate,
        max_duration_ticks=max_duration,
    )


def _profile_changed(profile: DriveProfile, **changes) -> DriveProfile:
    values = {
        "id": profile.id,
        "drive_entity_id": profile.drive_entity_id,
        "owner": profile.owner,
        "area_id": profile.area_id,
        "field": profile.field,
        "stock": profile.stock,
        "stock_unit": profile.stock_unit,
        "field_per_stock": profile.field_per_stock,
        "max_rate": profile.max_rate,
        "max_duration_ticks": profile.max_duration_ticks,
    }
    values.update(changes)
    return DriveProfile(**values)


def _material(budget: float = 6.0):
    effect_kinds = ["drive_source"]
    if budget >= 10.0:
        effect_kinds.append("process_start")
    return parse_material({
        "id": "drive_crystal",
        "tier": "rare",
        "region_rarity": "scarce",
        "traits": [{
            "id": "finite_field_drive",
            "effect_kinds": effect_kinds,
            "selectors": ["current_area"],
            "budget_points": budget,
        }],
    })


def _skill(
    *,
    skill_id: str = SKILL,
    profile_id: str = PROFILE,
    rate: float = 2.0,
    mana: float = 4.0,
    duration: int = 4,
    action_duration: int = 1,
    budget: float = 6.0,
):
    return parse_skill_blueprint({
        "protocol": "pmw-gameplay-v0.4",
        "kind": "skill_blueprint",
        "id": skill_id,
        "version": 1,
        "trigger": "on_use",
        "condition": None,
        "duration": None,
        "cost": {"duration": action_duration, "mana": mana},
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
        "budget": {"limit": budget},
        "max_firings_per_root": 1,
        "material_ids": ["drive_crystal"],
    }, basic_registry().statuses, material_authority((_material(budget),)))


def _process_profile() -> ProcessProfile:
    template = ProcessTemplate(
        "boiler_process",
        (ConversionPort("fuel", 1.0, UNIT),),
        (ConversionPort("ash", 1.0, "ash"),),
        1.0,
        1,
        1.0,
        2,
    )
    return ProcessProfile(
        "boiler",
        template,
        "process_boiler",
        PLAYER,
        (StockBinding("fuel", StockRef("fuel_stock")),),
        (StockBinding("ash", StockRef("process_ash")),),
    )


def _world(
    profiles: tuple[DriveProfile, ...],
    *,
    field: FieldDefinition | None = None,
    stock_amounts: dict[str, float] | None = None,
    process_profile: ProcessProfile | None = None,
    player_area: str = AREA,
    npc_area: str = AREA,
):
    definition = field or (profiles[0].field if profiles else _field())
    areas = {
        AREA: _area(AREA, definition),
        REMOTE: _area(REMOTE, _field(initial=2.0, target=2.0)),
    }
    actors = {
        PLAYER: _actor(PLAYER, human=True),
        NPC: _actor(NPC, human=False),
    }
    world = build_gameplay_world(
        "drive_review_world",
        areas=areas.values(),
        actors=actors.values(),
        placements=((PLAYER, player_area), (NPC, npc_area)),
    )
    world.entities.update(areas)
    world.entities.update(actors)
    for profile in profiles:
        world.entities[profile.drive_entity_id] = instantiate_drive(profile)
        stock_id = profile.stock.entity_id
        world.entities[stock_id] = stock_entity(
            stock_id,
            amount=(stock_amounts or {}).get(stock_id, 10.0),
            capacity=max(10.0, (stock_amounts or {}).get(stock_id, 10.0)),
            unit=profile.stock_unit,
        )
        for endpoint in (profile.drive_entity_id, stock_id):
            relation_id = f"located:{endpoint}:{profile.area_id}"
            world.relations[relation_id] = Relation(
                relation_id, "located_in", endpoint, profile.area_id
            )
    if process_profile is not None:
        world.entities[process_profile.process_entity_id] = instantiate_process(process_profile)
        for port, ref in (*process_profile.input_ports, *process_profile.output_ports):
            world.entities[ref.entity_id] = stock_entity(
                ref.entity_id, amount=10.0, capacity=20.0, unit=port.unit
            )
            relation_id = f"located:{ref.entity_id}:{AREA}"
            world.relations[relation_id] = Relation(
                relation_id, "located_in", ref.entity_id, AREA
            )
        relation_id = f"located:{process_profile.process_entity_id}:{AREA}"
        world.relations[relation_id] = Relation(
            relation_id, "located_in", process_profile.process_entity_id, AREA
        )
    world.entities["pmw:v04:clock"] = clock_entity()
    return initialize_time_budget(world, 20)


def _runtime(
    drives: tuple[DriveProfile, ...],
    *,
    skills: tuple[object, ...] | None = None,
    limits: DriveLimits | None = None,
    processes: tuple[ProcessProfile, ...] = (),
    material_id: str = "drive_crystal",
    **world_options,
):
    skill_items = tuple(
        skills
        if skills is not None
        else tuple(
            _skill(
                skill_id=SKILL if index == 0 else f"{SKILL}_{profile.id}",
                profile_id=profile.id,
            )
            for index, profile in enumerate(drives)
        )
    )
    base = ActionRegistry(
        basic_registry().actions.values(),
        basic_registry().statuses.values(),
        drive_controller=DriveController(drives, limits or DriveLimits()),
        process_controller=(
            ProcessController(processes, ProcessLimits())
            if processes else None
        ),
    )
    content = make_content(
        base,
        skills=skill_items,
        material_ids=(material_id,),
    )
    world = _world(
        drives,
        process_profile=processes[0] if processes else None,
        **world_options,
    )
    world = initialize_content_world(world, content)
    compiled = compile_content(content)
    session = build_content_session(world, compiled)
    runtime = MechanismRegistryRuntime.from_compiled_content(session, compiled)
    for index, actor_id in enumerate((PLAYER, NPC)):
        equipped = skill_items[min(index, len(skill_items) - 1)]
        change_loadout(
            runtime.session,
            runtime.manifest,
            actor_id=actor_id,
            operation="equip_active",
            skill=skill_ref(equipped),
            slot=0,
        )
    return runtime, compiled, skill_items


def _native_runtime(
    drives: tuple[DriveProfile, ...],
    *,
    field: FieldDefinition | None = None,
    stock_amounts: dict[str, float] | None = None,
):
    """Run only the native Drive Laws; this is support evidence, not the bridge."""
    world = _world(drives, field=field, stock_amounts=stock_amounts)
    controller = DriveController(drives)
    session = build_runtime(world, extra_laws=controller.laws)
    return session, controller


def _start_native(
    session,
    controller: DriveController,
    profile: DriveProfile,
    *,
    rate: float = 2.0,
    duration: int = 4,
):
    return controller.start(
        session,
        profile.id,
        owner=profile.owner,
        rate=rate,
        duration_ticks=duration,
    )


def _field_value(session, area_id: str = AREA) -> float:
    return float(
        session.state.entities[area_id]
        .components["pmw_gameplay_dynamics"]["fields"][FIELD]["value"]
    )


def _amount(session, entity_id: str) -> float:
    return float(session.state.entities[entity_id].components["stock"]["amount"])


def _drive(session, profile: DriveProfile) -> dict:
    return session.state.entities[profile.drive_entity_id].components[DRIVE_COMPONENT]


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


class DriveSourceIndependentReviewTests(unittest.TestCase):
    def test_formal_player_npc_timed_source_and_dynamics(self):
        player = _profile()
        npc = _profile("npc_drive", owner=NPC, area_id=AREA, stock_id="npc_fuel")
        runtime, _, skills = _runtime((player, npc))
        skill = skills[0]
        self.assertEqual(skill.budget_used, 5.4)

        first = submit_timed_primary_action(
            runtime.session,
            runtime.action_registry,
            ActionRequest("player_cast", PLAYER, SKILL),
        )
        second = submit_timed_primary_action(
            runtime.session,
            runtime.action_registry,
            ActionRequest("npc_cast", NPC, skills[1].id),
        )
        self.assertEqual((first.time.duration, first.time.after_remaining), (1, 19))
        self.assertEqual((second.time.duration, second.time.after_remaining), (1, 18))
        self.assertEqual(
            runtime.session.state.entities[PLAYER]
            .components["pmw_gameplay_actor"]["mana"],
            16.0,
        )
        self.assertEqual(
            runtime.session.state.entities[NPC]
            .components["pmw_gameplay_actor"]["mana"],
            16.0,
        )
        self.assertEqual(_amount(runtime.session, "fuel_stock"), 8.0)
        self.assertEqual(_amount(runtime.session, "npc_fuel"), 9.0)
        self.assertEqual(_field_value(runtime.session), 7.0)
        self.assertEqual(_drive(runtime.session, player)["last_step"], 2)
        self.assertEqual(_drive(runtime.session, npc)["last_step"], 2)
        budget = runtime.session.state.entities["pmw:v04:clock"].components[
            "pmw_gameplay_time_budget"
        ]
        self.assertEqual((budget["spent_ticks"], budget["remaining_ticks"]), (2, 18))
        self.assertNotEqual(
            _drive(runtime.session, player)["expiry_handle"],
            _drive(runtime.session, npc)["expiry_handle"],
        )
        self.assertEqual(
            sum(
                event.event.type == DRIVE_STEP_EVENT
                for tick in (*first.time.ticks, *second.time.ticks)
                for event in tick.event_result.trace.events
            ),
            3,
        )

        none = _profile("none_drive", stock_id="none_fuel")
        none_skill = _skill(
            skill_id="none_skill", profile_id=none.id, action_duration=3
        )
        none_runtime, _, _ = _runtime((none,), skills=(none_skill,))
        none_outcome = submit_timed_primary_action(
            none_runtime.session,
            none_runtime.action_registry,
            ActionRequest("none_cast", PLAYER, none_skill.id),
        )
        self.assertEqual(
            (none_outcome.time.duration, none_outcome.time.before_remaining,
             none_outcome.time.after_remaining),
            (3, 20, 17),
        )
        self.assertEqual(_field_value(none_runtime.session), 7.0)
        self.assertEqual(_amount(none_runtime.session, "none_fuel"), 7.0)

        linear_field = _field(rate=0.1, curve="linear")
        linear = _profile("linear_drive", stock_id="linear_fuel", field=linear_field)
        linear_skill = _skill(
            skill_id="linear_skill", profile_id=linear.id, action_duration=3
        )
        linear_runtime, _, _ = _runtime(
            (linear,), skills=(linear_skill,), field=linear_field
        )
        linear_outcome = submit_timed_primary_action(
            linear_runtime.session,
            linear_runtime.action_registry,
            ActionRequest("linear_cast", PLAYER, linear_skill.id),
        )
        self.assertEqual(
            (linear_outcome.time.duration, linear_outcome.time.before_remaining,
             linear_outcome.time.after_remaining),
            (3, 20, 17),
        )
        self.assertAlmostEqual(_field_value(linear_runtime.session), 6.42, places=12)
        self.assertEqual(_amount(linear_runtime.session, "linear_fuel"), 7.0)

    def test_capacity_fuel_owned_expiry_and_owner_departure(self):
        capacity_field = _field(initial=8.5, target=8.5, maximum=9.0)
        capacity = _profile(field=capacity_field)
        capacity_session, capacity_controller = _native_runtime(
            (capacity,), field=capacity_field
        )
        _start_native(capacity_session, capacity_controller, capacity)
        advance_world_tick(capacity_session)
        self.assertEqual(_field_value(capacity_session), 9.0)
        self.assertEqual(_amount(capacity_session, "fuel_stock"), 9.75)
        self.assertEqual(_drive(capacity_session, capacity)["last_delta"], 0.5)

        recovered_field = _field(initial=9.9, target=9.0, rate=0.1, curve="linear")
        recovered = _profile(
            "recovered_drive", stock_id="recovered_fuel", field=recovered_field
        )
        recovered_session, recovered_controller = _native_runtime(
            (recovered,), field=recovered_field
        )
        _start_native(recovered_session, recovered_controller, recovered, rate=0.2)
        advance_world_tick(recovered_session)
        self.assertAlmostEqual(_field_value(recovered_session), 10.0, places=12)
        self.assertAlmostEqual(_amount(recovered_session, "recovered_fuel"), 9.905, places=12)
        self.assertAlmostEqual(
            _drive(recovered_session, recovered)["last_delta"], 0.19, places=12
        )
        advance_world_tick(recovered_session)
        self.assertEqual(_field_value(recovered_session), 10.0)
        self.assertAlmostEqual(_amount(recovered_session, "recovered_fuel"), 9.855, places=12)
        self.assertEqual(_drive(recovered_session, recovered)["last_step"], 2)
        self.assertAlmostEqual(
            _drive(recovered_session, recovered)["last_delta"], 0.1, places=12
        )

        fresh = _profile("fresh_drive", stock_id="fresh_fuel")
        fresh_session, fresh_controller = _native_runtime((fresh,))
        _start_native(fresh_session, fresh_controller, fresh)
        advance_world_tick(fresh_session)
        self.assertEqual(_drive(fresh_session, fresh)["last_step"], 1)

        limited_field = _field(initial=8.75, target=8.75, maximum=9.0)
        limited = _profile("limited_drive", stock_id="limited_fuel", field=limited_field)
        limited_session, limited_controller = _native_runtime(
            (limited,),
            field=limited_field,
            stock_amounts={"limited_fuel": 0.1},
        )
        _start_native(limited_session, limited_controller, limited)
        advance_world_tick(limited_session)
        self.assertAlmostEqual(_field_value(limited_session), 8.95)
        self.assertAlmostEqual(_amount(limited_session, "limited_fuel"), 0.0, places=12)
        self.assertAlmostEqual(
            _drive(limited_session, limited)["last_delta"], 0.2, places=12
        )

        normal = _profile("normal_drive", stock_id="normal_fuel", coefficient=2.0)
        normal_session, normal_controller = _native_runtime((normal,))
        _start_native(normal_session, normal_controller, normal, rate=1.0)
        advance_world_tick(normal_session)
        self.assertEqual(_field_value(normal_session), 2.0)
        self.assertEqual(_amount(normal_session, "normal_fuel"), 9.5)
        self.assertEqual(_drive(normal_session, normal)["last_delta"], 1.0)

        huge_field = _field(initial=0.0, target=0.0, maximum=1.0)
        huge = _profile(
            "huge_stock_drive",
            stock_id="huge_fuel",
            coefficient=1e-6,
            field=huge_field,
        )
        huge_session, huge_controller = _native_runtime(
            (huge,),
            field=huge_field,
            stock_amounts={"huge_fuel": 1e12},
        )
        _start_native(huge_session, huge_controller, huge, rate=1e-12)
        advance_world_tick(huge_session)
        self.assertEqual(_field_value(huge_session), 0.0)
        self.assertEqual(_amount(huge_session, "huge_fuel"), 1e12)
        self.assertEqual(_drive(huge_session, huge)["last_step"], 1)
        self.assertEqual(_drive(huge_session, huge)["last_delta"], 0.0)

        high_value = math.nextafter(1.0, 0.0)
        high_field = _field(initial=high_value, target=high_value, maximum=1.0)
        high = _profile(
            "high_field_drive",
            stock_id="high_fuel",
            coefficient=1e-18,
            field=high_field,
        )
        high_session, high_controller = _native_runtime(
            (high,),
            field=high_field,
            stock_amounts={"high_fuel": 1e6},
        )
        _start_native(high_session, high_controller, high, rate=1e-17)
        advance_world_tick(high_session)
        self.assertEqual(_field_value(high_session), high_value)
        self.assertEqual(_amount(high_session, "high_fuel"), 1e6)
        self.assertEqual(_drive(high_session, high)["last_step"], 1)
        self.assertEqual(_drive(high_session, high)["last_delta"], 0.0)

        empty = _profile("empty_drive", stock_id="empty_fuel")
        empty_session, empty_controller = _native_runtime(
            (empty,), stock_amounts={"empty_fuel": 0.0}
        )
        before = _snapshot(empty_session)
        with self.assertRaisesRegex(GameplayContractError, "empty|insufficient"):
            _start_native(empty_session, empty_controller, empty)
        self.assertEqual(_snapshot(empty_session), before)

        expiry = _profile("expiry_drive")
        expiry_session, expiry_controller = _native_runtime((expiry,))
        _start_native(expiry_session, expiry_controller, expiry)
        old_expiry_handle = _drive(expiry_session, expiry)["expiry_handle"]
        old_expiry_event = next(
            event
            for event in expiry_session.state.scheduled_events
            if event.id == old_expiry_handle
        )
        for _ in range(4):
            advance_world_tick(expiry_session)
        self.assertIsNone(_drive(expiry_session, expiry)["started_at"])
        self.assertEqual(_field_value(expiry_session), 7.0)
        self.assertEqual(_amount(expiry_session, "fuel_stock"), 7.0)
        self.assertFalse(any(
            event.type == DRIVE_EXPIRE_EVENT and event.time == 4.0
            for event in expiry_session.state.scheduled_events
        ))
        _start_native(expiry_session, expiry_controller, expiry, duration=6)
        new_expiry_handle = _drive(expiry_session, expiry)["expiry_handle"]
        self.assertNotEqual(old_expiry_handle, new_expiry_handle)
        expiry_session.runtime.run_event(old_expiry_event)
        self.assertIsNotNone(_drive(expiry_session, expiry)["started_at"])
        self.assertEqual(_drive(expiry_session, expiry)["expiry_handle"], new_expiry_handle)

        continued = _profile("continued_drive")
        continued_session, continued_controller = _native_runtime((continued,))
        _start_native(continued_session, continued_controller, continued)
        continued_session.state.relations = {
            key: value for key, value in continued_session.state.relations.items()
            if not (
                value.type == "located_in"
                and value.source == PLAYER
            )
        }
        continued_session.state.relations["moved:player"] = Relation(
            "moved:player", "located_in", PLAYER, REMOTE
        )
        continued_session.runtime.revalidate()
        advance_world_tick(continued_session)
        self.assertEqual(_field_value(continued_session), 3.0)
        self.assertEqual(_amount(continued_session, "fuel_stock"), 9.0)

    def test_sorted_overlap_and_none_vs_impulse(self):
        definitions = [
            _field(),
            _field(),
            _field(),
        ]
        profiles = (
            _profile("z_drive", stock_id="z_fuel", coefficient=4.0, field=definitions[0]),
            _profile("a_drive", stock_id="a_fuel", field=definitions[1]),
            _profile("b_drive", stock_id="b_fuel", field=definitions[2]),
        )
        session, controller = _native_runtime(profiles)
        for profile in profiles:
            _start_native(session, controller, profile)
        advance_world_tick(session)
        self.assertEqual(_field_value(session), 7.0)
        self.assertEqual(session.state.entities[AREA]
                         .components["pmw_gameplay_dynamics"]["fields"][FIELD]
                         ["diagnostics"]["effective_curve"], "none")
        self.assertEqual(
            [_amount(session, f"{name}_fuel") for name in ("a", "b", "z")],
            [9.0, 9.0, 9.5],
        )
        reordered, reordered_controller = _native_runtime(tuple(reversed(profiles)))
        for profile in reversed(profiles):
            _start_native(reordered, reordered_controller, profile)
        advance_world_tick(reordered)
        self.assertEqual(_field_value(reordered), 7.0)
        self.assertEqual(
            [_amount(reordered, f"{name}_fuel") for name in ("a", "b", "z")],
            [9.0, 9.0, 9.5],
        )
        self.assertEqual(session.state.to_dict(), reordered.state.to_dict())

        impulse = _profile("impulse_drive")
        impulse_session, impulse_controller = _native_runtime((impulse,))
        before = _field_value(impulse_session)
        _start_native(impulse_session, impulse_controller, impulse)
        advance_world_tick(impulse_session)
        self.assertEqual(_field_value(impulse_session), 3.0)
        self.assertNotEqual(before, _field_value(impulse_session))

        one_shot_field = _field()
        impulse_law = {
            "id": "pmw.v04.review.one_shot_impulse",
            "mode": "event",
            "priority": 100,
            "bindings": {
                "subject": {"kind": "entity", "requires": ["pmw_gameplay_dynamics"]},
            },
            "when": {"all": [
                {"event.type": {"eq": "pmw.v04.review.one_shot_impulse"}},
                {"ref": "$subject.id", "eq": AREA},
            ]},
            "effects": [{
                "op": "delta",
                "target": f"$subject.pmw_gameplay_dynamics.fields.{FIELD}.value",
                "value": 2.0,
            }],
        }
        transient_world = _world((), field=one_shot_field)
        transient = build_runtime(transient_world, extra_laws=(impulse_law,))
        transient.runtime.run_event(Event(
            "one_shot_impulse",
            "pmw.v04.review.one_shot_impulse",
            time=transient.state.sim_time,
            target=AREA,
        ))
        self.assertEqual(_field_value(transient), 3.0)
        advance_world_tick(transient)
        self.assertEqual(_field_value(transient), 3.0)
        self.assertEqual(_field_value(impulse_session), 3.0)

    def test_denials_unknown_coefficient_and_mixed_control(self):
        profile = _profile()
        self.assertFalse(hasattr(profile, "source_coefficient"))
        self.assertFalse(hasattr(profile, "stock_unit_definition"))
        controller = DriveController((profile,))
        base = ActionRegistry(
            basic_registry().actions.values(),
            basic_registry().statuses.values(),
            drive_controller=controller,
        )
        with self.assertRaisesRegex(GameplayContractError, "duplicate action id"):
            make_content(
                base,
                skills=(_skill(), _skill()),
                material_ids=("drive_crystal",),
            )

        limit_profiles = (
            _profile("limit_a", stock_id="limit_a_fuel"),
            _profile("limit_b", stock_id="limit_b_fuel"),
        )
        limit_base = ActionRegistry(
            basic_registry().actions.values(),
            basic_registry().statuses.values(),
            drive_controller=DriveController(
                limit_profiles, DriveLimits(max_instances=2, max_active=1)
            ),
        )
        limit_skills = tuple(
            _skill(skill_id=f"limit_{index}_skill", profile_id=profile.id)
            for index, profile in enumerate(limit_profiles)
        )
        limit_content = make_content(
            limit_base, skills=limit_skills, material_ids=("drive_crystal",)
        )
        limit_compiled = compile_content(limit_content)
        limit_world = _world(limit_profiles)
        limit_world = initialize_content_world(limit_world, limit_content)
        limit_session = build_content_session(limit_world, limit_compiled)
        limit_runtime = MechanismRegistryRuntime.from_compiled_content(
            limit_session, limit_compiled
        )
        for index, limit_skill in enumerate(limit_skills):
            change_loadout(
                limit_runtime.session,
                limit_runtime.manifest,
                actor_id=PLAYER,
                operation="equip_active",
                skill=skill_ref(limit_skill),
                slot=index,
            )
        limit_outcome = submit_timed_primary_action(
            limit_runtime.session,
            limit_runtime.action_registry,
            ActionRequest("limit_first", PLAYER, limit_skills[0].id),
        )
        self.assertEqual(
            (limit_outcome.time.duration, limit_outcome.time.after_remaining), (1, 19)
        )
        before = _snapshot(limit_runtime.session)
        with self.assertRaisesRegex(GameplayContractError, "active|limit"):
            limit_runtime.action_registry.drive_controller.prepare_start(
                limit_runtime.session,
                limit_profiles[1].id,
                owner=PLAYER,
                rate=2.0,
                duration_ticks=4,
            )
        self.assertEqual(_snapshot(limit_runtime.session), before)
        third = _profile("limit_c", stock_id="limit_c_fuel")
        with self.assertRaisesRegex(GameplayContractError, "max_instances"):
            DriveController(
                (*limit_profiles, third), DriveLimits(max_instances=2, max_active=1)
            )

        process = _process_profile()
        process_base = ActionRegistry(
            basic_registry().actions.values(),
            basic_registry().statuses.values(),
            drive_controller=controller,
            process_controller=ProcessController((process,)),
        )
        with self.assertRaisesRegex(
            GameplayContractError, "overlap|configured Process"
        ):
            make_content(
                process_base,
                skills=(_skill(),),
                material_ids=("drive_crystal",),
            )
        raw = json.loads(_skill().canonical_document_json)
        raw["effects"].append({
            "id": "boiler",
            "kind": "process_start",
            "target": {"kind": "current_area"},
            "commitment": "required",
            "process_template_id": "boiler_process",
        })
        raw["budget"]["limit"] = 10.0
        with self.assertRaisesRegex(GameplayContractError, "one|single|Process"):
            parse_skill_blueprint(
                raw,
                basic_registry().statuses,
                material_authority((_material(10.0),)),
            )
        with self.assertRaisesRegex(GameplayContractError, "budget|shared budget"):
            _skill(budget=5.3)

        for field, value, pattern in (
            ("source_unit", UNIT, "unknown|source"),
            ("field_per_stock", 2.0, "unknown|coefficient"),
            ("source", "candidate_stock", "unknown|source"),
            ("target", {"kind": "self"}, "current_area"),
            ("drive_rate", True, "numeric|finite|positive"),
            ("drive_rate", math.nan, "numeric|finite|positive"),
            ("drive_rate", math.inf, "numeric|finite|positive"),
            ("duration", 0, "duration|positive"),
        ):
            mutated = json.loads(_skill().canonical_document_json)
            mutated["effects"][0][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(
                GameplayContractError, pattern
            ):
                parse_skill_blueprint(
                    mutated,
                    basic_registry().statuses,
                    material_authority((_material(),)),
                )

        wrong_owner = _profile_changed(profile, owner=NPC, stock=StockRef("npc_stock"))
        owner_runtime, _, _ = _runtime((wrong_owner,))
        before = _snapshot(owner_runtime.session)
        with self.assertRaisesRegex(GameplayContractError, "owner|profile"):
            submit_timed_primary_action(
                owner_runtime.session,
                owner_runtime.action_registry,
                ActionRequest("owner_denied", PLAYER, SKILL),
            )
        self.assertEqual(_snapshot(owner_runtime.session), before)

        known_skill = _skill()
        unknown_base = ActionRegistry(
            basic_registry().actions.values(),
            basic_registry().statuses.values(),
            drive_controller=controller,
        )
        unknown_content = make_content(
            unknown_base,
            skills=(known_skill,),
            material_ids=("drive_crystal",),
        )
        unknown_world = initialize_content_world(_world((profile,)), unknown_content)
        unknown_session = build_content_session(
            unknown_world, compile_content(unknown_content)
        )
        with self.assertRaisesRegex(GameplayContractError, "unknown Drive profile"):
            controller.prepare_start(
                unknown_session,
                "not_a_profile",
                owner=PLAYER,
                rate=2.0,
                duration_ticks=4,
            )
        with self.assertRaisesRegex(
            GameplayContractError, "may not share an input Stock"
        ):
            DriveController((
                profile,
                _profile_changed(profile, id="same_stock_drive",
                                 drive_entity_id="drive_same_stock_drive"),
            ))

        unit_runtime, _, _ = _runtime((profile,))
        unit_runtime.session.state.entities["fuel_stock"].components["stock"]["unit"] = "other"
        before = _snapshot(unit_runtime.session)
        with self.assertRaisesRegex(GameplayContractError, "unit"):
            submit_timed_primary_action(
                unit_runtime.session,
                unit_runtime.action_registry,
                ActionRequest("unit_denied", PLAYER, SKILL),
            )
        self.assertEqual(_snapshot(unit_runtime.session), before)

        scope_runtime, _, _ = _runtime((_profile(area_id=REMOTE),))
        before = _snapshot(scope_runtime.session)
        with self.assertRaisesRegex(GameplayContractError, "scope|local|Area"):
            submit_timed_primary_action(
                scope_runtime.session,
                scope_runtime.action_registry,
                ActionRequest("scope_denied", PLAYER, SKILL),
            )
        self.assertEqual(_snapshot(scope_runtime.session), before)

    def test_real_cascade_and_late_tick_rollback(self):
        profile = _profile("cascade_drive")
        runtime, _, _ = _runtime((profile,))
        exploding = build_runtime(
            deepcopy(runtime.session.state),
            runtime.session.profiles,
            (
                *runtime.static_laws,
                *build_action_laws(runtime.action_registry),
                {
                "id": "pmw.v04.review.drive_step_explode",
                "mode": "event",
                "priority": 100,
                "bindings": {
                    "drive": {"kind": "entity", "requires": [DRIVE_COMPONENT]},
                },
                "when": {"all": [{
                    "event.type": {"eq": DRIVE_STEP_EVENT},
                }, {
                    "ref": "$drive.id",
                    "eq": profile.drive_entity_id,
                }]},
                "effects": [{
                    "op": "set",
                    "target": f"$drive.{DRIVE_COMPONENT}.last_delta",
                    "value": {"div": [1, 0]},
                }],
                },
            ),
        )
        before = _snapshot(exploding)
        with self.assertRaises(ZeroDivisionError):
            submit_timed_primary_action(
                exploding,
                runtime.action_registry,
                ActionRequest("cascade_cast", PLAYER, SKILL),
            )
        self.assertEqual(_snapshot(exploding), before)

        real_tick = time_ledger.advance_world_tick
        calls = 0

        def fail_tick(working, **kwargs):
            nonlocal calls
            calls += 1
            result = real_tick(working, **kwargs)
            if calls == 1:
                raise RuntimeError("review late tick failure")
            return result

        before = _snapshot(runtime.session)
        with patch.object(time_ledger, "advance_world_tick", side_effect=fail_tick):
            with self.assertRaisesRegex(RuntimeError, "late tick"):
                submit_timed_primary_action(
                    runtime.session,
                    runtime.action_registry,
                    ActionRequest("late_denied", PLAYER, SKILL),
                )
        self.assertEqual(calls, 1)
        self.assertEqual(_snapshot(runtime.session), before)

    def test_checkpoint_changed_profile_projection_and_wait(self):
        profile = _profile("checkpoint_drive")
        runtime, compiled, _ = _runtime((profile,))
        submit_timed_primary_action(
            runtime.session,
            runtime.action_registry,
            ActionRequest("checkpoint_cast", PLAYER, SKILL),
        )
        temp_root = Path("docs/agent_bootstrap/evidence/c2_drive_review_tmp")
        temp_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temp_root) as directory:
            path = Path(directory) / "checkpoint.json"
            save_registry_checkpoint(path, runtime)
            restored = load_registry_checkpoint(path, compiled)
            changed = _profile_changed(profile, field_per_stock=3.0)
            changed_controller = DriveController((changed,))
            changed_compiled = CompiledGate3Content(
                make_content(
                    ActionRegistry(
                        (row for row in runtime.action_registry.actions.values()
                         if row.id != SKILL),
                        runtime.action_registry.statuses.values(),
                        drive_controller=changed_controller,
                    ),
                    skills=(runtime.blueprints[(SKILL, 1)],),
                    material_ids=("drive_crystal",),
                ),
                (
                    *(
                        law for law in compiled.laws
                        if not law["id"].startswith("pmw.v04.sandbox.drive.")
                    ),
                    *changed_controller.laws,
                ),
            )
            with self.assertRaisesRegex(
                GameplayContractError, "static Law|profile"
            ):
                load_registry_checkpoint(path, changed_compiled)

        advance_world_tick(restored.session)
        self.assertEqual(_field_value(restored.session), 5.0)
        self.assertEqual(_amount(restored.session, "fuel_stock"), 8.0)

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
        self.assertIsNone(projected_registry.drive_controller)
        self.assertIn("basic_wait", projected_registry.actions)
        result = simulator.simulate(
            observation,
            ActionRequest("projected_wait", PLAYER, "basic_wait"),
        )
        self.assertTrue(result.legal, result.rejection)
        self.assertTrue(result.next_observation.to_dict()["area"]["fields"])


if __name__ == "__main__":
    unittest.main()
