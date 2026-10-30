from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import unittest

from pmw import Entity, Relation

from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.actions import (
    ACTOR_COMPONENT,
    ACTION_EVENT,
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
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.combat import (
    run_combat_round,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.content_compiler import (
    build_content_session,
    compile_content,
    initialize_content_world,
    make_content,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.dynamics import (
    DYNAMICS_COMPONENT,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.ecology import (
    ECOLOGY_COMPONENT,
    ECOLOGY_CHANGED_EVENT,
    parse_ecology_spec,
    sample_ecology,
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
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.relations import (
    RELATION_COMPONENT,
    RelationController,
    RelationProfile,
    instantiate_relation,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.runtime import (
    advance_world_tick,
    clock_entity,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.skills import (
    parse_skill_blueprint,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.time_ledger import (
    TIME_BUDGET_COMPONENT,
    initialize_time_budget,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.worlds import (
    build_gameplay_world,
)


PROJECT_ROOT = Path(__file__).resolve().parents[5]
TEST_TMP = PROJECT_ROOT / "docs" / "agent_bootstrap" / "evidence" / "test_tmp"

PLAYER = "p1_player"
NPC = "p1_npc"
AREA = "p1_area"
OTHER_AREA = "p1_other_area"
MATERIAL_ID = "p1_material"
CLOCK_ID = "pmw:v04:clock"


def _proof(name: str, **values):
    return {"proof": name, **values}


def _material(*kinds: str, budget: float = 40.0):
    return parse_material({
        "id": MATERIAL_ID,
        "tier": "rare",
        "region_rarity": "scarce",
        "traits": [{
            "id": "p1_authority",
            "effect_kinds": list(kinds),
            "selectors": ["self", "target_actor", "current_area"],
            "budget_points": budget,
        }],
    })


def _skill_raw(
    skill_id: str,
    effects: list[dict],
    *,
    kind: str = "skill_blueprint",
    trigger: str = "on_use",
    condition=None,
    duration: int = 1,
    mana: float = 4.0,
    budget: float = 40.0,
    max_firings: int = 1,
    relations: tuple[str, ...] = (),
):
    return {
        "protocol": "pmw-gameplay-v0.4",
        "kind": kind,
        "id": skill_id,
        "version": 1,
        "trigger": trigger,
        "condition": condition,
        "duration": None,
        "cost": {"duration": 1 if kind == "passive_blueprint" else duration, "mana": 0 if kind == "passive_blueprint" else mana},
        "scope": {
            "selectors": list(dict.fromkeys(
                [item["target"]["kind"] for item in effects]
            )),
            "relation_types": list(relations),
        },
        "effects": effects,
        "budget": {"limit": budget},
        "max_firings_per_root": max_firings,
        "material_ids": [MATERIAL_ID],
    }


def _skill(raw: dict):
    kinds = tuple(dict.fromkeys(item["kind"] for item in raw["effects"]))
    return parse_skill_blueprint(
        raw,
        basic_registry().statuses,
        material_authority((_material(*kinds, budget=raw["budget"]["limit"]),)),
    )


def _field(
    field_id: str,
    *,
    initial: float = 0.2,
    target: float = 0.8,
    rate: float = 0.2,
    curve: str = "linear",
    slots: int = 3,
):
    return {
        "id": field_id,
        "domain": {"min": 0.0, "max": 1.0},
        "initial": initial,
        "target": target,
        "rate": rate,
        "curve": curve,
        "max_persistent_patches": slots,
        "max_temporary_modifiers": slots,
    }


def _area(area_id: str, fields: list[dict]):
    blueprint = parse_area_blueprint({
        "protocol": "pmw-gameplay-v0.4",
        "kind": "area_blueprint",
        "id": f"{area_id}_blueprint",
        "fields": fields,
    })
    return instantiate_area(blueprint, area_id)


def _actor(actor_id: str, controller: str, *, mana: float = 30.0):
    blueprint = parse_actor_blueprint({
        "protocol": "pmw-gameplay-v0.4",
        "kind": "actor_blueprint",
        "id": f"{actor_id}_blueprint",
        "hp": {"max": 50.0, "initial": 50.0},
        "mana": {"max": 100.0, "initial": mana, "dynamics": None},
        "attributes": {
            "power": 4.0,
            "control": 4.0,
            "resilience": 4.0,
            "agility": 4.0,
        },
        "traits": [],
    })
    return instantiate_actor(blueprint, actor_id, controller=controller)


def _world(
    fields: list[dict],
    *,
    other_fields: list[dict] | None = None,
    extra_entities: dict[str, Entity] | None = None,
    extra_relations: tuple[Relation, ...] = (),
    npc_area: str = AREA,
    time_budget: int = 40,
):
    areas = {
        AREA: _area(AREA, fields),
        OTHER_AREA: _area(OTHER_AREA, other_fields or deepcopy(fields)),
    }
    actors = {
        PLAYER: _actor(PLAYER, "human"),
        NPC: _actor(NPC, "ai"),
    }
    world = build_gameplay_world(
        "p1_scenario_world",
        areas=areas.values(),
        actors=actors.values(),
        placements=((PLAYER, AREA), (NPC, npc_area)),
    )
    for entity in (*areas.values(), *actors.values(), *(extra_entities or {}).values()):
        world.entities[entity.id] = entity
    for relation in extra_relations:
        world.relations[relation.id] = relation
    world.entities[CLOCK_ID] = clock_entity()
    return initialize_time_budget(world, time_budget)


def _formal_runtime(
    world,
    skills: tuple,
    *,
    process_controller=None,
    relation_controller=None,
    ecology_by_area=None,
):
    base = ActionRegistry(
        basic_registry().actions.values(),
        basic_registry().statuses.values(),
        process_controller=process_controller,
        relation_controller=relation_controller,
    )
    content = make_content(
        base,
        skills=skills,
        material_ids=(MATERIAL_ID,),
        ecology_by_area=ecology_by_area,
    )
    initialized = initialize_content_world(world, content)
    compiled = compile_content(content)
    session = build_content_session(initialized, compiled)
    runtime = MechanismRegistryRuntime.from_compiled_content(session, compiled)
    for actor_id in (PLAYER, NPC):
        for slot, skill in enumerate(skills):
            change_loadout(
                runtime.session,
                runtime.manifest,
                actor_id=actor_id,
                operation=(
                    "equip_active"
                    if skill.kind == "skill_blueprint"
                    else "equip_passive"
                ),
                skill=skill_ref(skill),
                slot=slot,
            )
    return runtime, compiled


def _field_state(runtime, area_id=AREA, field_id="humidity"):
    return runtime.session.state.entities[area_id].components[
        DYNAMICS_COMPONENT
    ]["fields"][field_id]


def _actor_state(runtime, actor_id):
    return runtime.session.state.entities[actor_id].components[ACTOR_COMPONENT]


def _budget(runtime):
    return runtime.session.state.entities[CLOCK_ID].components[
        TIME_BUDGET_COMPONENT
    ]


def _law_ids(outcome):
    return list(outcome.event_result.triggered_law_ids)


def _locate(area_id: str, *entity_ids: str):
    return tuple(
        Relation(f"located:{entity_id}:{area_id}", "located_in", entity_id, area_id)
        for entity_id in entity_ids
    )


def _relation_world(profile: RelationProfile):
    source = Entity("p1_power_source", "p1_relation_endpoint", components={"p1_supply_source": {}})
    target = Entity("p1_power_sink", "p1_relation_endpoint", components={"p1_supply_sink": {}})
    relations = (
        *_locate(AREA, source.id, target.id),
        instantiate_relation(profile, base_enabled=True),
    )
    return _world(
        [_field("heat", initial=1.0, target=1.0, rate=0.0, curve="none")],
        extra_entities={source.id: source, target.id: target},
        extra_relations=relations,
        time_budget=20,
    )


def _relation_profile(owner: str, profile_id: str, relation_id: str) -> RelationProfile:
    return RelationProfile(
        profile_id,
        relation_id,
        "supplies_power",
        "p1_power_source",
        "p1_power_sink",
        owner,
        AREA,
        ("p1_supply_source",),
        ("p1_supply_sink",),
        8,
    )


def _relation_skill(profile_id: str):
    return _skill(_skill_raw(
        "p1_relation_control",
        [{
            "id": "disable_supply",
            "kind": "relation_modifier",
            "target": {"kind": "current_area"},
            "commitment": "required",
            "relation_profile_id": profile_id,
            "relation_enabled": False,
            "duration": 3,
        }],
        mana=1.0,
        budget=6.0,
        relations=("supplies_power",),
    ))


def _process_profile(owner: str, profile_id: str):
    template = ProcessTemplate(
        "p1_refine",
        (ConversionPort("ore", 1.0, "ore"),),
        (ConversionPort("ingot", 1.0, "ingot"),),
        1.0,
        4,
        4.0,
        8,
    )
    return ProcessProfile(
        profile_id,
        template,
        f"p1_process_{profile_id}",
        owner,
        (StockBinding("ore", StockRef(f"p1_ore_{profile_id}")),),
        (StockBinding("ingot", StockRef(f"p1_ingot_{profile_id}")),),
    )


def _process_world(profiles: tuple[ProcessProfile, ...]):
    entities = {}
    relations: list[Relation] = []
    for profile in profiles:
        entities[profile.process_entity_id] = instantiate_process(profile)
        ore = f"p1_ore_{profile.id}"
        ingot = f"p1_ingot_{profile.id}"
        entities[ore] = stock_entity(ore, amount=8.0, capacity=30.0, unit="ore")
        entities[ingot] = stock_entity(ingot, amount=0.0, capacity=30.0, unit="ingot")
        relations.extend(_locate(
            AREA,
            profile.process_entity_id,
            ore,
            ingot,
        ))
    return _world(
        [_field("heat", initial=1.0, target=1.0, rate=0.0, curve="none")],
        extra_entities=entities,
        extra_relations=tuple(relations),
        time_budget=30,
    )


def _process_start_skill():
    return _skill(_skill_raw(
        "p1_start_refine",
        [{
            "id": "start_refine",
            "kind": "process_start",
            "target": {"kind": "current_area"},
            "commitment": "required",
            "process_template_id": "p1_refine",
        }],
        duration=1,
        mana=4.0,
        budget=8.0,
    ))


def _process_modify_skill(*, rate=None, remaining=None):
    effect = {
        "id": "modify_refine",
        "kind": "process_modify",
        "target": {"kind": "current_area"},
        "commitment": "required",
        "process_template_id": "p1_refine",
    }
    if rate is not None:
        effect["process_rate"] = rate
    if remaining is not None:
        effect["process_remaining_ticks"] = remaining
    return _skill(_skill_raw(
        "p1_modify_refine",
        [effect],
        duration=1,
        mana=4.0,
        budget=8.0,
    ))


class P1ScenarioConformanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        TEST_TMP.mkdir(parents=True, exist_ok=True)

    def test_scenario01_persistent_area_change_partial_without_formal_relocation(self):
        skill = _skill(_skill_raw(
            "p1_area_pulse",
            [{
                "id": "persistent_humidity",
                "kind": "dynamics_modifier",
                "target": {"kind": "current_area"},
                "commitment": "required",
                "field_id": "humidity",
                "rate_add": 0.2,
                "rate_multiplier": 1.0,
                "curve": "linear",
                "curve_priority": 2,
                "duration": 6,
            }],
            duration=1,
            mana=5.0,
            budget=8.0,
        ))
        final_values = {}
        for actor_id in (PLAYER, NPC):
            runtime, _ = _formal_runtime(_world([_field("humidity")]), (skill,))
            result = submit_timed_primary_action(
                runtime.session,
                runtime.action_registry,
                ActionRequest(f"p1_scenario01_{actor_id}", actor_id, skill.id),
            )
            self.assertEqual((result.action.cost.duration, result.time.duration), (1, 1))
            self.assertEqual(_budget(runtime)["spent_ticks"], 1)
            self.assertEqual(_budget(runtime)["remaining_ticks"], 39)
            self.assertEqual(_actor_state(runtime, actor_id)["mana"], 25.0)
            self.assertEqual(
                _field_state(runtime)["temporary_modifiers"]["slot_0"]["owner"],
                actor_id,
            )
            expected = 0.44
            self.assertAlmostEqual(_field_state(runtime)["value"], expected, delta=1e-12)
            for _ in range(3):
                advance_world_tick(runtime.session)
                current = _field_state(runtime)["value"]
                expected = expected + 0.4 * (0.8 - expected)
                self.assertAlmostEqual(current, expected, delta=1e-12)
            active = _field_state(runtime)["temporary_modifiers"]["slot_0"]
            self.assertTrue(active["active"])
            self.assertEqual(active["owner"], actor_id)
            self.assertIsNotNone(active["expiry_handle"])
            applied = [
                law for law in _law_ids(result.action)
                if law.endswith(".slot_0.apply")
            ]
            self.assertEqual(len(applied), 1)
            final_values[actor_id] = expected
        self.assertAlmostEqual(final_values[PLAYER], final_values[NPC], delta=1e-12)
        # PARTIAL boundary: leaving the Area requires a formal relocation Effect,
        # which is absent.  This test therefore verifies persistence/evolution
        # while the paid owner remains in the affected Area.

    def test_scenario02_target_and_rate_are_separate_sources(self):
        skill = _skill(_skill_raw(
            "p1_target_and_rate",
            [
                {
                    "id": "move_target",
                    "kind": "modify_attractor",
                    "target": {"kind": "current_area"},
                    "commitment": "required",
                    "field_id": "humidity",
                    "amount": 0.4,
                    "duration": 4,
                },
                {
                    "id": "raise_rate",
                    "kind": "modify_rate",
                    "target": {"kind": "current_area"},
                    "commitment": "required",
                    "field_id": "humidity",
                    "amount": 0.1,
                    "duration": 4,
                },
            ],
            duration=1,
            mana=6.0,
            budget=20.0,
        ))
        for actor_id in (PLAYER, NPC):
            runtime, _ = _formal_runtime(_world([_field("humidity")]), (skill,))
            outcome = submit_timed_primary_action(
                runtime.session,
                runtime.action_registry,
                ActionRequest(f"p1_scenario02_{actor_id}", actor_id, skill.id),
            )
            source_slots = {
                row["effect_id"]: row["values"]["source"]
                for row in outcome.action.effect_outcomes
                if row["kind"] in {"modify_attractor", "modify_rate"}
            }
            self.assertNotEqual(
                _field_state(runtime)["temporary_modifiers"]["slot_0"]["source_id"],
                _field_state(runtime)["temporary_modifiers"]["slot_1"]["source_id"],
            )
            field = _field_state(runtime)
            self.assertAlmostEqual(
                field["diagnostics"]["effective_target"], 0.6, delta=1e-12
            )
            self.assertAlmostEqual(
                field["diagnostics"]["effective_rate"], 0.3, delta=1e-12
            )
            self.assertEqual(field["diagnostics"]["effective_curve"], "linear")
            self.assertAlmostEqual(field["value"], 0.32, delta=1e-12)
            self.assertAlmostEqual(
                source_slots["move_target"]["target"], 0.4, delta=1e-12
            )
            self.assertEqual(
                source_slots["raise_rate"]["target_weight"], 0.0
            )
            self.assertEqual(_budget(runtime)["spent_ticks"], 1)
            advance_world_tick(runtime.session)
            self.assertAlmostEqual(
                _field_state(runtime)["value"], 0.404, delta=1e-12
            )
            self.assertEqual(_budget(runtime)["spent_ticks"], 1)

    def test_scenario03_multiple_dynamics_modifiers_expire_independently(self):
        def raw(field_id: str, priority: int):
            return {
                "id": f"p1_{field_id}_modifier",
                "kind": "dynamics_modifier",
                "target": {"kind": "current_area"},
                "commitment": "required",
                "field_id": field_id,
                "rate_add": 0.2,
                "rate_multiplier": 1.0,
                "curve": "linear",
                "curve_priority": priority,
                "duration": 2 if field_id == "humidity" else 4,
            }

        skill = _skill(_skill_raw(
            "p1_two_fields",
            [raw("humidity", 2), raw("temperature", 3)],
            duration=1,
            mana=7.0,
            budget=20.0,
        ))
        runtime, _ = _formal_runtime(
            _world([
                _field("humidity"),
                _field("temperature", initial=0.2, target=0.8, rate=0.1),
            ]),
            (skill,),
        )
        for actor_id in (PLAYER, NPC):
            if actor_id == NPC:
                runtime, _ = _formal_runtime(
                    _world([
                        _field("humidity"),
                        _field(
                            "temperature",
                            initial=0.2,
                            target=0.8,
                            rate=0.1,
                        ),
                    ]),
                    (skill,),
                )
            result = submit_timed_primary_action(
                runtime.session,
                runtime.action_registry,
                ActionRequest(f"p1_scenario03_{actor_id}", actor_id, skill.id),
            )
            self.assertEqual(result.time.duration, 1)
            self.assertEqual(_actor_state(runtime, actor_id)["mana"], 23.0)
            humidity = _field_state(runtime, field_id="humidity")
            temperature = _field_state(runtime, field_id="temperature")
            self.assertAlmostEqual(
                humidity["diagnostics"]["effective_rate"], 0.4, delta=1e-12
            )
            self.assertAlmostEqual(
                temperature["diagnostics"]["effective_rate"], 0.3, delta=1e-12
            )
            advance_world_tick(runtime.session)
            humidity = _field_state(runtime, field_id="humidity")
            temperature = _field_state(runtime, field_id="temperature")
            self.assertFalse(
                humidity["temporary_modifiers"]["slot_0"]["active"]
            )
            self.assertTrue(
                temperature["temporary_modifiers"]["slot_0"]["active"]
            )
            self.assertAlmostEqual(
                humidity["diagnostics"]["effective_rate"], 0.2, delta=1e-12
            )
            self.assertAlmostEqual(
                temperature["diagnostics"]["effective_rate"], 0.3, delta=1e-12
            )
            for _ in range(2):
                advance_world_tick(runtime.session)
            temperature = _field_state(runtime, field_id="temperature")
            self.assertFalse(
                temperature["temporary_modifiers"]["slot_0"]["active"]
            )
            self.assertAlmostEqual(
                temperature["diagnostics"]["effective_rate"], 0.1, delta=1e-12
            )
            self.assertEqual(runtime.session.state.scheduled_events, [])
            self.assertEqual(_budget(runtime)["spent_ticks"], 1)

    def test_scenario04_process_converts_input_stock_to_output_stock(self):
        skill = _process_start_skill()
        for actor_id in (PLAYER, NPC):
            profile = _process_profile(actor_id, f"{actor_id}_refine")
            controller = ProcessController(
                (profile,), ProcessLimits(max_instances=4, max_active=4)
            )
            runtime, _ = _formal_runtime(
                _process_world((profile,)),
                (skill,),
                process_controller=controller,
            )
            result = submit_timed_primary_action(
                runtime.session,
                runtime.action_registry,
                ActionRequest(f"p1_scenario04_{actor_id}", actor_id, skill.id),
            )
            self.assertEqual(result.time.duration, 1)
            process = runtime.session.state.entities[
                profile.process_entity_id
            ].components["pmw_sandbox_process"]
            self.assertEqual(process["state"], "running")
            self.assertEqual(process["owner"], actor_id)
            self.assertEqual(
                runtime.session.state.entities[
                    f"p1_ore_{profile.id}"
                ].components["stock"]["amount"],
                7.0,
            )
            self.assertEqual(
                runtime.session.state.entities[
                    f"p1_ingot_{profile.id}"
                ].components["stock"]["amount"],
                1.0,
            )
            self.assertEqual(_actor_state(runtime, actor_id)["mana"], 26.0)
            self.assertEqual(_budget(runtime)["spent_ticks"], 1)
            self.assertEqual(_budget(runtime)["remaining_ticks"], 29)
            advance_world_tick(runtime.session)
            self.assertEqual(
                runtime.session.state.entities[
                    f"p1_ore_{profile.id}"
                ].components["stock"]["amount"],
                6.0,
            )
            self.assertEqual(
                runtime.session.state.entities[
                    f"p1_ingot_{profile.id}"
                ].components["stock"]["amount"],
                2.0,
            )
            self.assertEqual(_budget(runtime)["spent_ticks"], 1)

    def test_scenario05_process_rate_and_remaining_duration_modification(self):
        player = _process_profile(PLAYER, "player_refine")
        npc = _process_profile(NPC, "npc_refine")
        controller = ProcessController(
            (player, npc), ProcessLimits(max_instances=4, max_active=4)
        )
        start = _process_start_skill()
        modify = _process_modify_skill(rate=2.0, remaining=3)
        runtime, _ = _formal_runtime(
            _process_world((player, npc)),
            (start, modify),
            process_controller=controller,
        )
        for actor_id, profile in ((PLAYER, player), (NPC, npc)):
            submit_timed_primary_action(
                runtime.session,
                runtime.action_registry,
                ActionRequest(f"p1_scenario05_start_{actor_id}", actor_id, start.id),
            )
            before_mana = _actor_state(runtime, actor_id)["mana"]
            result = submit_timed_primary_action(
                runtime.session,
                runtime.action_registry,
                ActionRequest(f"p1_scenario05_modify_{actor_id}", actor_id, modify.id),
            )
            process = runtime.session.state.entities[
                profile.process_entity_id
            ].components["pmw_sandbox_process"]
            self.assertEqual(process["rate"], 2.0)
            self.assertEqual(process["remaining_ticks"], 2)
            self.assertEqual(process["duration_ticks"], 4)
            self.assertEqual(process["elapsed_ticks"], 2)
            self.assertEqual(result.time.duration, 1)
            self.assertEqual(_actor_state(runtime, actor_id)["mana"], before_mana - 4.0)
            self.assertEqual(
                runtime.session.state.entities[
                    f"p1_ore_{profile.id}"
                ].components["stock"]["amount"],
                5.0,
            )
            self.assertEqual(
                runtime.session.state.entities[
                    f"p1_ingot_{profile.id}"
                ].components["stock"]["amount"],
                3.0,
            )
        self.assertEqual(_budget(runtime)["spent_ticks"], 4)
        self.assertEqual(_budget(runtime)["remaining_ticks"], 26)

    def test_scenario06_damage_passive_fires_once_and_recursion_stops(self):
        passive = _skill(_skill_raw(
            "p1_counter",
            [{
                "id": "counter_damage",
                "kind": "damage",
                "target": {"kind": "target_actor"},
                "commitment": "required",
                "amount": 4,
            }],
            kind="passive_blueprint",
            trigger="damage_resolved",
            budget=8.0,
            max_firings=1,
        ))
        runtime, _ = _formal_runtime(_world([_field("heat", rate=0.0, curve="none")]), (passive,))
        result = run_combat_round(
            runtime.session,
            runtime.action_registry,
            round_index=1,
            actor_order=(NPC, PLAYER),
            requests={
                NPC: ActionRequest("p1_scenario06_attack", NPC, "basic_attack", PLAYER)
            },
        )
        primary = result.outcomes[0]
        self.assertEqual(_actor_state(runtime, PLAYER)["hp"], 36.0)
        self.assertEqual(_actor_state(runtime, NPC)["hp"], 46.0)
        fired = [row for row in primary.auto_hooks if row.status == "fired"]
        self.assertEqual(len(fired), 2)
        self.assertEqual(
            {row.owner for row in fired},
            {PLAYER, NPC},
        )
        hook_roots = []
        for record in fired:
            roots = [
                row.event for row in record.outcome.event_result.trace.events
                if row.event.type == ACTION_EVENT
            ]
            self.assertEqual(len(roots), 1)
            hook_roots.append(roots[0])
            self.assertEqual(roots[0].payload["execution_kind"], "hook")
        self.assertEqual(len({root.id for root in hook_roots}), 2)
        skipped = [row for row in primary.auto_hooks if row.status == "skipped"]
        self.assertEqual(
            [(row.owner, row.depth, row.reason) for row in skipped],
            [(
                PLAYER,
                3,
                "duplicate owner+hook source in this root",
            )],
        )
        self.assertEqual(
            _actor_state(runtime, PLAYER)["hp"],
            36.0,
        )
        self.assertEqual(
            _actor_state(runtime, NPC)["hp"],
            46.0,
        )
        self.assertEqual(_budget(runtime)["spent_ticks"], 1)
        self.assertEqual(result.time_spend_result.duration, 1)
        self.assertEqual(
            sum(row.status == "fired" for row in primary.auto_hooks),
            2,
        )

    def test_scenario07_relation_overlay_partial_without_supply_path_consumer(self):
        profile_id = "p1_supply"
        skill = _relation_skill(profile_id)
        for actor_id in (PLAYER, NPC):
            profile = _relation_profile(actor_id, profile_id, "p1_power_link")
            controller = RelationController((profile,))
            runtime, _ = _formal_runtime(
                _relation_world(profile),
                (skill,),
                relation_controller=controller,
            )
            component = runtime.session.state.relations[
                profile.relation_id
            ].components[RELATION_COMPONENT]
            self.assertIs(component["effective_enabled"], True)
            result = submit_timed_primary_action(
                runtime.session,
                runtime.action_registry,
                ActionRequest(f"p1_scenario07_{actor_id}", actor_id, skill.id),
            )
            self.assertEqual(result.time.duration, 1)
            self.assertEqual(_actor_state(runtime, actor_id)["mana"], 29.0)
            component = runtime.session.state.relations[
                profile.relation_id
            ].components[RELATION_COMPONENT]
            self.assertIs(component["base_enabled"], True)
            self.assertIs(component["enabled"], False)
            self.assertIs(component["effective_enabled"], False)
            self.assertTrue(component["active"])
            self.assertEqual(component["expires_at"], 3.0)
            self.assertEqual(result.time.after_remaining, 19)
            for _ in range(3):
                advance_world_tick(runtime.session)
            component = runtime.session.state.relations[
                profile.relation_id
            ].components[RELATION_COMPONENT]
            self.assertFalse(component["active"])
            self.assertIs(component["effective_enabled"], True)
            self.assertEqual(_budget(runtime)["spent_ticks"], 1)
            self.assertEqual(_budget(runtime)["remaining_ticks"], 19)
        # PARTIAL boundary: the parsed Action updates a typed Relation's
        # availability overlay and expiry. No formal generated supply/path
        # consumer currently reads that overlay to alter movement or Stocks.

    def test_scenario08_ecology_discrete_transition_triggered_by_field_law(self):
        spec = parse_ecology_spec({
            "protocol": "pmw-gameplay-v0.4",
            "id": "p1_ecology",
            "label": "P1 threshold ecology",
            "initial_regime": "dry",
            "sample_count": 2,
            "regimes": [
                {
                    "id": "dry",
                    "label": "Dry",
                    "clue": "dry baseline",
                    "baselines": [{
                        "field_id": "humidity",
                        "target": 0.1,
                        "rate": 0.2,
                        "curve": "linear",
                    }],
                },
                {
                    "id": "wet",
                    "label": "Wet",
                    "clue": "wet baseline",
                    "baselines": [{
                        "field_id": "humidity",
                        "target": 0.9,
                        "rate": 0.2,
                        "curve": "linear",
                    }],
                },
            ],
            "transitions": [{
                "id": "rain",
                "from": "dry",
                "to": "wet",
                "condition": {
                    "field_id": "humidity",
                    "comparator": "gte",
                    "threshold": 0.55,
                },
                "window_ticks": 1,
                "clue": "rain threshold reached",
            }],
        })
        plan = sample_ecology(spec, 17)
        skill = _skill(_skill_raw(
            "p1_rain_call",
            [{
                "id": "soak",
                "kind": "modify_field",
                "target": {"kind": "current_area"},
                "commitment": "required",
                "field_id": "humidity",
                "amount": 0.5,
            }],
            duration=1,
            mana=3.0,
            budget=5.0,
        ))
        for actor_id in (PLAYER, NPC):
            runtime, _ = _formal_runtime(
                _world([_field("humidity", initial=0.2, target=0.1, rate=0.2)]),
                (skill,),
                ecology_by_area={AREA: plan, OTHER_AREA: plan},
            )
            self.assertEqual(
                runtime.session.state.entities[AREA].components[
                    ECOLOGY_COMPONENT
                ]["current"],
                "dry",
            )
            result = submit_timed_primary_action(
                runtime.session,
                runtime.action_registry,
                ActionRequest(f"p1_scenario08_{actor_id}", actor_id, skill.id),
            )
            self.assertEqual(result.time.duration, 1)
            self.assertEqual(len(result.time.ticks), 1)
            tick_trace = result.time.ticks[0].event_result.trace
            changed = [
                row.event for row in tick_trace.events
                if row.event.type == ECOLOGY_CHANGED_EVENT
            ]
            self.assertEqual(len(changed), 1)
            self.assertEqual(
                (
                    changed[0].payload["from"],
                    changed[0].payload["to"],
                    changed[0].payload["transition_id"],
                ),
                ("dry", "wet", "rain"),
            )
            state = runtime.session.state.entities[AREA]
            self.assertEqual(
                state.components[ECOLOGY_COMPONENT]["current"], "wet"
            )
            self.assertEqual(
                state.components["pmw_gameplay_area"]["ecology_state"], "wet"
            )
            self.assertAlmostEqual(
                _field_state(runtime)["baseline"]["target"], 0.9, delta=1e-12
            )
            self.assertAlmostEqual(_field_state(runtime)["value"], 0.58, delta=1e-12)
            self.assertEqual(_actor_state(runtime, actor_id)["mana"], 27.0)
            self.assertEqual(_budget(runtime)["spent_ticks"], 1)
            advance_world_tick(runtime.session)
            self.assertAlmostEqual(_field_state(runtime)["value"], 0.644, delta=1e-12)
            self.assertEqual(_budget(runtime)["spent_ticks"], 1)

    def test_scenario09_field_diagnostics_are_partial_derived_bridge(self):
        skill = _skill(_skill_raw(
            "p1_rate_half",
            [{
                "id": "rate_half",
                "kind": "dynamics_modifier",
                "target": {"kind": "current_area"},
                "commitment": "required",
                "field_id": "humidity",
                "rate_add": -0.1,
                "rate_multiplier": 1.0,
                "curve": "linear",
                "curve_priority": 4,
                "duration": 2,
            }],
            duration=1,
            mana=4.0,
            budget=8.0,
        ))
        for actor_id in (PLAYER, NPC):
            runtime, _ = _formal_runtime(_world([_field("humidity")]), (skill,))
            before = _field_state(runtime)["diagnostics"]
            self.assertAlmostEqual(before["effective_rate"], 0.2, delta=1e-12)
            result = submit_timed_primary_action(
                runtime.session,
                runtime.action_registry,
                ActionRequest(f"p1_scenario09_{actor_id}", actor_id, skill.id),
            )
            self.assertEqual(result.time.duration, 1)
            self.assertAlmostEqual(
                _field_state(runtime)["diagnostics"]["effective_rate"],
                0.1,
                delta=1e-12,
            )
            self.assertAlmostEqual(_field_state(runtime)["value"], 0.26, delta=1e-12)
            advance_world_tick(runtime.session)
            self.assertAlmostEqual(
                _field_state(runtime)["diagnostics"]["effective_rate"],
                0.2,
                delta=1e-12,
            )
            self.assertFalse(
                _field_state(runtime)["temporary_modifiers"]["slot_0"]["active"]
            )
            self.assertEqual(_budget(runtime)["spent_ticks"], 1)
        # PARTIAL boundary: the live Field diagnostic is derived from the
        # dependency change, but there is no candidate-facing read-only
        # unified Derived catalog/value bridge.

    def test_scenario10_same_parsed_skill_executes_for_player_and_npc(self):
        skill = _skill(_skill_raw(
            "p1_self_shield",
            [{
                "id": "self_shield",
                "kind": "shield",
                "target": {"kind": "self"},
                "commitment": "required",
                "amount": 7,
            }],
            duration=1,
            mana=3.0,
            budget=4.0,
        ))
        runtime, _ = _formal_runtime(
            _world(
                [_field("heat", rate=0.0, curve="none")],
                npc_area=OTHER_AREA,
            ),
            (skill,),
        )
        blueprint = runtime.blueprints[(skill.id, 1)]
        self.assertEqual(blueprint.canonical_hash, skill.canonical_hash)
        self.assertEqual(blueprint.action.canonical_hash, skill.action.canonical_hash)
        for actor_id in (PLAYER, NPC):
            result = submit_timed_primary_action(
                runtime.session,
                runtime.action_registry,
                ActionRequest(f"p1_scenario10_{actor_id}", actor_id, skill.id),
            )
            self.assertEqual(result.action.definition.canonical_hash, skill.action.canonical_hash)
            self.assertEqual(result.action.cost.mana, 3.0)
            self.assertEqual(result.action.cost.duration, 1)
            self.assertEqual(_actor_state(runtime, actor_id)["mana"], 27.0)
            self.assertEqual(_actor_state(runtime, actor_id)["shield"], 7.0)
        self.assertEqual(_budget(runtime)["spent_ticks"], 2)
        self.assertEqual(_budget(runtime)["remaining_ticks"], 38)
        advance_world_tick(runtime.session)
        self.assertEqual(_budget(runtime)["spent_ticks"], 2)
if __name__ == "__main__":
    unittest.main()
