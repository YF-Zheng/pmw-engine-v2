from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.actions import (
    ActionRegistry,
    ActionRequest,
    parse_action_definition,
    resolve_action,
    submit_timed_primary_action,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.action_compiler import (
    build_action_laws,
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
    DynamicsSource,
    GameplayContractError,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.effects import (
    EFFECT_KINDS,
    EffectSpec,
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
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.registry import (
    MechanismRegistryRuntime,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.runtime import (
    advance_world_tick,
    build_runtime,
    clock_entity,
    discover_profiles,
    source_state,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.skills import (
    _effect_cost,
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
PLAYER = "dynamics_player"
NPC = "dynamics_npc"
AREA = "dynamics_area"
OTHER_AREA = "dynamics_other_area"
MATERIAL_ID = "dynamics_crystal"
SKILL_ID = "dynamics_freeze"
ACTOR_COMPONENT = "pmw_gameplay_actor"
DYNAMICS_COMPONENT = "pmw_gameplay_dynamics"

def _material(*, kinds=("dynamics_modifier",)):
    return parse_material({
        "id": MATERIAL_ID,
        "tier": "rare",
        "region_rarity": "scarce",
        "traits": [{
            "id": "dynamics_control",
            "effect_kinds": list(kinds),
            "selectors": ["current_area"],
            "budget_points": 8.0,
        }],
    })


def _field(
    field_id="humidity",
    *,
    initial=0.2,
    target=0.8,
    rate=0.2,
    curve="linear",
    temporary_slots=2,
    persistent_slots=2,
):
    return {
        "id": field_id,
        "domain": {"min": 0.0, "max": 1.0},
        "initial": initial,
        "target": target,
        "rate": rate,
        "curve": curve,
        "max_persistent_patches": persistent_slots,
        "max_temporary_modifiers": temporary_slots,
    }


def _area(area_id=AREA, *, fields=None):
    blueprint = parse_area_blueprint({
        "protocol": "pmw-gameplay-v0.4",
        "kind": "area_blueprint",
        "id": "dynamics_area_blueprint",
        "fields": fields or [_field()],
    })
    return instantiate_area(blueprint, area_id)


def _actor(actor_id, *, controller, mana=20.0):
    blueprint = parse_actor_blueprint({
        "protocol": "pmw-gameplay-v0.4",
        "kind": "actor_blueprint",
        "id": "dynamics_actor_blueprint",
        "hp": {"max": 50, "initial": 50},
        "mana": {"max": 30, "initial": mana, "dynamics": None},
        "attributes": {
            "power": 4, "control": 4, "resilience": 4, "agility": 4,
        },
        "traits": [],
    })
    return instantiate_actor(blueprint, actor_id, controller=controller)


def _effect_document(**overrides):
    raw = {
        "id": "freeze_recovery",
        "kind": "dynamics_modifier",
        "target": {"kind": "current_area"},
        "commitment": "required",
        "field_id": "humidity",
        "rate_add": 0.1,
        "rate_multiplier": 2.0,
        "curve": "none",
        "curve_priority": 3,
        "duration": 3,
    }
    raw.update(overrides)
    return raw


def _skill_document(
    *,
    effect=None,
    extra_effect=None,
    skill_id=SKILL_ID,
    kind="skill_blueprint",
    budget=8.0,
):
    effect = effect or _effect_document()
    effects = [effect]
    if extra_effect is not None:
        effects.append(extra_effect)
    return {
        "protocol": "pmw-gameplay-v0.4",
        "kind": kind,
        "id": skill_id,
        "version": 1,
        "trigger": "on_use" if kind == "skill_blueprint" else "damage_resolved",
        "condition": None,
        "duration": None,
        "cost": {"duration": 1, "mana": 4},
        "scope": {"selectors": ["current_area"], "relation_types": []},
        "effects": effects,
        "budget": {"limit": budget},
        "max_firings_per_root": 1,
        "material_ids": [MATERIAL_ID],
    }


def _skill(**kwargs):
    kinds = tuple(
        dict.fromkeys(
            [item["kind"] for item in _skill_document(**kwargs)["effects"]]
        )
    )
    return parse_skill_blueprint(
        _skill_document(**kwargs),
        basic_registry().statuses,
        material_authority((_material(kinds=kinds),)),
    )


def _world(
    fields=None,
    *,
    player_area=AREA,
    npc_area=AREA,
    other_fields=None,
    budget=20,
):
    areas = {
        AREA: _area(AREA, fields=fields),
        OTHER_AREA: _area(OTHER_AREA, fields=other_fields or fields or [_field()]),
    }
    actors = (
        _actor(PLAYER, controller="human"),
        _actor(NPC, controller="ai"),
    )
    world = build_gameplay_world(
        "dynamics_action_world",
        areas=areas.values(),
        actors=actors,
        placements=((PLAYER, player_area), (NPC, npc_area)),
    )
    world.entities["pmw:v04:clock"] = clock_entity()
    return initialize_time_budget(world, budget)


def _runtime(*, skills=None, fields=None, npc_area=AREA, budget=20, other_fields=None):
    skills = skills or (_skill(),)
    base = ActionRegistry(
        basic_registry().actions.values(),
        basic_registry().statuses.values(),
    )
    content = make_content(
        base,
        skills=tuple(skills),
        material_ids=(MATERIAL_ID,),
    )
    world = initialize_content_world(
        _world(fields, npc_area=npc_area, budget=budget, other_fields=other_fields),
        content,
    )
    compiled = compile_content(content)
    session = build_content_session(world, compiled)
    runtime = MechanismRegistryRuntime.from_compiled_content(session, compiled)
    for actor_id in (PLAYER, NPC):
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


def _field_state(runtime, area_id=AREA, field_id="humidity"):
    return runtime.session.state.entities[area_id].components[
        DYNAMICS_COMPONENT
    ]["fields"][field_id]


def _actor_state(runtime, actor_id):
    return runtime.session.state.entities[actor_id].components[ACTOR_COMPONENT]


def _budget(runtime):
    return runtime.session.state.entities["pmw:v04:clock"].components[
        TIME_BUDGET_COMPONENT
    ]


def _snapshot(runtime):
    return (
        deepcopy(runtime.session.state.to_dict()),
        deepcopy(runtime.session.runtime.stats),
        runtime.session.runtime.revision,
        runtime.session.runtime.object_revision,
        runtime.session.runtime.state_closure_known,
        deepcopy(runtime.session.state.scheduled_events),
        deepcopy(runtime.manifest),
        id(runtime.session.runtime),
    )


def _digest(value):
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()).hexdigest()


def _eval_ids(outcome, suffix):
    return [
        law_id for law_id in outcome.event_result.triggered_law_ids
        if law_id.endswith(suffix)
    ]


class DynamicsModifierSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        TEST_TMP.mkdir(parents=True, exist_ok=True)

    def test_closed_effect_shape_and_trailing_typed_fields(self):
        statuses = basic_registry().statuses
        effect = parse_effect(_effect_document(), statuses)
        self.assertIsInstance(effect, EffectSpec)
        self.assertIn("dynamics_modifier", EFFECT_KINDS)
        self.assertEqual(effect.rate_add, 0.1)
        self.assertEqual(effect.rate_multiplier, 2.0)
        self.assertEqual(effect.curve, "none")
        self.assertEqual(effect.curve_priority, 3)
        self.assertEqual(effect.duration, 3)
        self.assertIsNone(effect.amount)

        old = {
            "id": "strike",
            "kind": "damage",
            "target": {"kind": "target_actor"},
            "commitment": "required",
            "amount": 3,
        }
        old_effect = parse_effect(old, statuses)
        self.assertIsNone(old_effect.rate_add)
        self.assertIsNone(old_effect.curve)
        with self.assertRaisesRegex(
            GameplayContractError, "missing or unknown fields"
        ):
            parse_effect(old | {"curve": "linear"}, statuses)

    def test_every_required_raw_key_and_no_legacy_optional_terms(self):
        statuses = basic_registry().statuses
        for key in _effect_document():
            raw = _effect_document()
            raw.pop(key)
            with self.subTest(key=key):
                with self.assertRaises(GameplayContractError):
                    parse_effect(raw, statuses)
        for extra in (
            {"amount": 1},
            {"attribute_terms": []},
            {"targeting": {"sensing": "none", "evadable": False}},
            {"condition": None},
            {"extra": True},
        ):
            with self.subTest(extra=extra):
                with self.assertRaisesRegex(
                    GameplayContractError, "missing or unknown fields"
                ):
                    parse_effect(_effect_document() | extra, statuses)

    def test_invalid_values_reject_strictly(self):
        statuses = basic_registry().statuses
        cases = (
            ({"rate_add": None}, "finite number"),
            ({"rate_add": True}, "finite number"),
            ({"rate_add": "0.1"}, "finite number"),
            ({"rate_add": math.nan}, "finite number"),
            ({"rate_add": math.inf}, "finite number"),
            ({"rate_add": -1.0001}, r"\[-1, 1\]"),
            ({"rate_add": 1.0001}, r"\[-1, 1\]"),
            ({"rate_multiplier": None}, "finite number"),
            ({"rate_multiplier": False}, "finite number"),
            ({"rate_multiplier": math.nan}, "finite number"),
            ({"rate_multiplier": -0.01}, r"\[0, 8\]"),
            ({"rate_multiplier": 8.01}, r"\[0, 8\]"),
            ({"curve": None}, "curve must be one of"),
            ({"curve": "exponential"}, "curve must be one of"),
            ({"curve_priority": True}, "integer in \\[0, 31\\]"),
            ({"curve_priority": 3.0}, "integer in \\[0, 31\\]"),
            ({"curve_priority": "3"}, "integer in \\[0, 31\\]"),
            ({"curve_priority": -1}, "integer in \\[0, 31\\]"),
            ({"curve_priority": 32}, "integer in \\[0, 31\\]"),
            ({"duration": True}, "integer in \\[1, 64\\]"),
            ({"duration": None}, "integer in \\[1, 64\\]"),
            ({"duration": 1.0}, "integer in \\[1, 64\\]"),
            ({"duration": 0}, "integer in \\[1, 64\\]"),
            ({"duration": 65}, "integer in \\[1, 64\\]"),
            ({"field_id": None}, "field_id is invalid"),
            ({"field_id": "Humidity"}, "field_id is invalid"),
            ({"field_id": "humidity.temperature"}, "field_id is invalid"),
            ({"target": {"kind": "self"}}, "target must be current_area"),
            ({"commitment": "conditional"}, "commitment must be required"),
        )
        for change, error in cases:
            with self.subTest(change=change):
                with self.assertRaisesRegex(GameplayContractError, error):
                    parse_effect(_effect_document(**change), statuses)

    def test_active_on_use_authority_and_three_plus_duration_budget(self):
        skill = _skill()
        self.assertEqual(skill.budget_used, 3.3)
        self.assertAlmostEqual(_effect_cost(skill.effects[0]), 3.3)
        self.assertEqual(skill.action.cost.mana, 4)

        passive = _skill_document(kind="passive_blueprint")
        with self.assertRaisesRegex(
            GameplayContractError, "only on active on_use skills"
        ):
            parse_skill_blueprint(
                passive,
                basic_registry().statuses,
                material_authority((_material(),)),
            )
        with self.assertRaisesRegex(
            GameplayContractError, "budget"
        ):
            parse_skill_blueprint(
                _skill_document(budget=3.2),
                basic_registry().statuses,
                material_authority((_material(),)),
            )

    def test_parse_action_and_skill_do_not_reinterpret_old_hashes(self):
        statuses = basic_registry().statuses
        for row in basic_registry_document()["actions"]:
            parsed = parse_action_definition(deepcopy(row), statuses)
            self.assertEqual(
                parsed.canonical_hash,
                basic_registry().actions[row["id"]].canonical_hash,
            )


class DynamicsModifierRuntimeTests(unittest.TestCase):
    def test_none_curve_freezes_exact_duration_then_restores_current_baseline(self):
        runtime, _ = _runtime()
        accepted = submit_timed_primary_action(
            runtime.session,
            runtime.action_registry,
            ActionRequest("freeze_run", PLAYER, SKILL_ID),
        )
        self.assertEqual(accepted.action.cost.duration, 1)
        self.assertEqual(_budget(runtime)["spent_ticks"], 1)
        self.assertEqual(_budget(runtime)["remaining_ticks"], 19)
        self.assertEqual(_actor_state(runtime, PLAYER)["mana"], 16.0)
        self.assertAlmostEqual(_field_state(runtime)["value"], 0.2, delta=1e-12)
        slot = _field_state(runtime)["temporary_modifiers"]["slot_0"]
        self.assertTrue(slot["active"])
        self.assertEqual(slot["curve"], "none")
        self.assertEqual(slot["curve_priority"], 3)
        self.assertEqual(
            [(event.id, event.time) for event in runtime.session.state.scheduled_events],
            [("pmw:v04:action-expiry:freeze_run:freeze_recovery", 3.0)],
        )
        self.assertTrue(_eval_ids(
            accepted.action, ".slot_0.apply"
        ))

        _field_state(runtime)["baseline"].update({
            "target": 0.6, "rate": 0.4, "curve": "linear",
        })
        first = advance_world_tick(runtime.session)
        self.assertAlmostEqual(_field_state(runtime)["value"], 0.2, delta=1e-12)
        self.assertEqual(_field_state(runtime)["diagnostics"]["effective_curve"], "none")
        self.assertEqual(_field_state(runtime)["diagnostics"]["effective_rate"], 0.0)
        self.assertTrue(any(
            law_id.endswith(".slot_2_none.all")
            for law_id in first.event_result.triggered_law_ids
        ))

        second = advance_world_tick(runtime.session)
        self.assertAlmostEqual(_field_state(runtime)["value"], 0.36, delta=1e-12)
        self.assertEqual(_field_state(runtime)["diagnostics"]["effective_curve"], "linear")
        self.assertAlmostEqual(_field_state(runtime)["diagnostics"]["effective_rate"], 0.4, delta=1e-12)
        self.assertFalse(_field_state(runtime)["temporary_modifiers"]["slot_0"]["active"])
        self.assertEqual(runtime.session.state.scheduled_events, [])
        self.assertTrue(_eval_ids(second, ".base.all"))

        third = advance_world_tick(runtime.session)
        state = _field_state(runtime)
        self.assertAlmostEqual(state["value"], 0.456, delta=1e-12)
        self.assertEqual(state["diagnostics"]["effective_curve"], "linear")
        self.assertAlmostEqual(state["diagnostics"]["effective_rate"], 0.4, delta=1e-12)
        self.assertFalse(state["temporary_modifiers"]["slot_0"]["active"])
        self.assertEqual(runtime.session.state.scheduled_events, [])
        self.assertTrue(_eval_ids(third, ".base.all"))

        fourth = advance_world_tick(runtime.session)
        self.assertAlmostEqual(_field_state(runtime)["value"], 0.5136, delta=1e-12)
        self.assertTrue(_eval_ids(fourth, ".base.all"))

    def test_same_parsed_skill_player_npc_two_areas_pay_once(self):
        runtime, _ = _runtime(npc_area=OTHER_AREA)
        skill = runtime.blueprints[(SKILL_ID, 1)]
        self.assertEqual(
            skill.canonical_hash,
            _digest(json.loads(skill.canonical_document_json)),
        )
        for actor_id, request_id in ((PLAYER, "player_cast"), (NPC, "npc_cast")):
            submitted = submit_timed_primary_action(
                runtime.session,
                runtime.action_registry,
                ActionRequest(request_id, actor_id, SKILL_ID),
            )
            self.assertEqual(submitted.action.definition.canonical_hash,
                             skill.action.canonical_hash)
            self.assertEqual(_actor_state(runtime, actor_id)["mana"], 16.0)
        self.assertEqual(_budget(runtime)["spent_ticks"], 2)
        self.assertEqual(_budget(runtime)["remaining_ticks"], 18)
        self.assertTrue(_field_state(runtime, AREA)["temporary_modifiers"]["slot_0"]["active"])
        self.assertTrue(_field_state(runtime, OTHER_AREA)["temporary_modifiers"]["slot_0"]["active"])
        self.assertEqual(len(runtime.session.state.scheduled_events), 2)

        advance_world_tick(runtime.session)
        self.assertAlmostEqual(_field_state(runtime, AREA)["value"], 0.32, delta=1e-12)
        self.assertAlmostEqual(_field_state(runtime, OTHER_AREA)["value"], 0.32, delta=1e-12)
        advance_world_tick(runtime.session)
        advance_world_tick(runtime.session)
        self.assertAlmostEqual(_field_state(runtime, AREA)["value"], 0.4928, delta=1e-12)
        self.assertAlmostEqual(_field_state(runtime, OTHER_AREA)["value"], 0.4928, delta=1e-12)

    def test_add_multiply_and_hand_calculated_curve_evolution(self):
        runtime, _ = _runtime()
        alternate = {
            **_effect_document(),
            "id": "boost_recovery",
            "rate_add": 0.3,
            "rate_multiplier": 1.5,
            "curve": "linear",
        }
        boost = parse_skill_blueprint(
            _skill_document(
                effect=alternate,
                skill_id="dynamics_boost",
                budget=8.0,
            ),
            basic_registry().statuses,
            material_authority((_material(),)),
        )
        runtime, _ = _runtime(skills=(boost,))
        outcome = submit_timed_primary_action(
            runtime.session, runtime.action_registry,
            ActionRequest("boosted", PLAYER, "dynamics_boost"),
        )
        slot = _field_state(runtime)["temporary_modifiers"]["slot_0"]
        self.assertEqual(
            (slot["rate_add"], slot["rate_multiplier"], slot["curve"]),
            (0.3, 1.5, "linear"),
        )
        self.assertEqual(_actor_state(runtime, PLAYER)["mana"], 16.0)
        self.assertEqual(_budget(runtime)["spent_ticks"], 1)
        # The timed action applies this Effect during its Tick-1 schedule pass:
        # (base 0.2 + 0.3) * 1.5 = 0.75, then
        # 0.2 + 0.75 * (0.8 - 0.2) = 0.65.
        self.assertAlmostEqual(
            _field_state(runtime)["value"], 0.65, delta=1e-12
        )
        advance_world_tick(runtime.session)
        self.assertAlmostEqual(_field_state(runtime)["value"], 0.7625, delta=1e-12)
        self.assertAlmostEqual(
            _field_state(runtime)["diagnostics"]["effective_rate"], 0.75,
            delta=1e-12,
        )
        self.assertTrue(_eval_ids(outcome.action, ".slot_0.apply"))

    def test_priority_conflict_with_persistent_source_is_atomic(self):
        runtime, _ = _runtime()
        field = _field_state(runtime)
        source = DynamicsSource(
            "persistent_curve", "world_law", curve="distance_squared",
            curve_priority=3,
        )
        field["persistent_patches"]["slot_0"].update(source_state(source))
        runtime.session.runtime.revalidate()
        before = _snapshot(runtime)
        with self.assertRaisesRegex(
            GameplayContractError, "curve override priority conflict"
        ):
            submit_timed_primary_action(
                runtime.session,
                runtime.action_registry,
                ActionRequest("priority_conflict", PLAYER, SKILL_ID),
            )
        self.assertEqual(_snapshot(runtime), before)

    def test_priority_conflict_with_temporary_source_is_atomic(self):
        runtime, _ = _runtime()
        source = DynamicsSource(
            "temporary_curve", "world_law", curve="distance_squared",
            curve_priority=3, duration_ticks=2,
        )
        _field_state(runtime)["temporary_modifiers"]["slot_0"].update(
            source_state(source, "existing_handle")
        )
        runtime.session.runtime.revalidate()
        before = _snapshot(runtime)
        with self.assertRaisesRegex(
            GameplayContractError, "curve override priority conflict"
        ):
            submit_timed_primary_action(
                runtime.session,
                runtime.action_registry,
                ActionRequest("temporary_conflict", PLAYER, SKILL_ID),
            )
        self.assertEqual(_snapshot(runtime), before)

    def test_full_capacity_and_two_new_writes_do_not_reuse_one_slot(self):
        runtime, _ = _runtime(fields=[_field(temporary_slots=1)])
        first = _effect_document()
        second = {
            **_effect_document(),
            "id": "second_source",
            "rate_add": 0.0,
            "curve_priority": 4,
        }
        with self.assertRaisesRegex(
            GameplayContractError, "conflicting writes"
        ):
            parse_skill_blueprint(
                _skill_document(effect=first, extra_effect=second),
                basic_registry().statuses,
                material_authority((_material(),)),
            )
        source = DynamicsSource(
            "occupied_source", "world_law", rate_add=0.1,
        )
        _field_state(runtime)["temporary_modifiers"]["slot_0"].update(
            source_state(source, "occupied_handle")
        )
        runtime.session.runtime.revalidate()
        before = _snapshot(runtime)
        with self.assertRaisesRegex(
            GameplayContractError, "temporary dynamics modifier capacity exhausted"
        ):
            submit_timed_primary_action(
                runtime.session,
                runtime.action_registry,
                ActionRequest("full_capacity", PLAYER, SKILL_ID),
            )
        self.assertEqual(_snapshot(runtime), before)

    def test_two_old_source_writers_reject_when_one_slot_is_free(self):
        rate = {
            "id": "rate_source",
            "kind": "modify_rate",
            "target": {"kind": "current_area"},
            "commitment": "required",
            "field_id": "humidity",
            "amount": 0.1,
            "duration": 3,
        }
        attractor = {
            "id": "attractor_source",
            "kind": "modify_attractor",
            "target": {"kind": "current_area"},
            "commitment": "required",
            "field_id": "humidity",
            "amount": 0.5,
            "duration": 3,
        }
        skill = _skill(
            effect=rate,
            extra_effect=attractor,
            skill_id="two_old_sources",
        )
        runtime, _ = _runtime(
            skills=(skill,), fields=[_field(temporary_slots=1)]
        )
        before = _snapshot(runtime)
        with self.assertRaisesRegex(
            GameplayContractError, "temporary dynamics modifier capacity exhausted"
        ):
            submit_timed_primary_action(
                runtime.session,
                runtime.action_registry,
                ActionRequest("old_sources_one_slot", PLAYER, skill.id),
            )
        self.assertEqual(_snapshot(runtime), before)

    def test_two_old_source_writers_use_distinct_free_slots(self):
        rate = {
            "id": "rate_source",
            "kind": "modify_rate",
            "target": {"kind": "current_area"},
            "commitment": "required",
            "field_id": "humidity",
            "amount": 0.1,
            "duration": 3,
        }
        attractor = {
            "id": "attractor_source",
            "kind": "modify_attractor",
            "target": {"kind": "current_area"},
            "commitment": "required",
            "field_id": "humidity",
            "amount": 0.5,
            "duration": 3,
        }
        skill = _skill(
            effect=rate,
            extra_effect=attractor,
            skill_id="two_old_sources",
        )
        runtime, _ = _runtime(
            skills=(skill,), fields=[_field(temporary_slots=2)]
        )
        submitted = submit_timed_primary_action(
            runtime.session,
            runtime.action_registry,
            ActionRequest("old_sources_two_slots", PLAYER, skill.id),
        )
        slots = [
            row["values"]["slot"]
            for row in submitted.action.effect_outcomes
            if row["kind"] in {"modify_rate", "modify_attractor"}
        ]
        self.assertEqual(slots, ["slot_0", "slot_1"])
        self.assertTrue(
            _field_state(runtime)["temporary_modifiers"]["slot_0"]["active"]
        )
        self.assertTrue(
            _field_state(runtime)["temporary_modifiers"]["slot_1"]["active"]
        )
        self.assertEqual(
            submitted.action.event_result.trace.events[0].event.payload["reservations"],
            [],
        )

    def test_same_action_source_footprint_rejects(self):
        first = _effect_document()
        second = {
            **first,
            "id": "second_source",
        }
        with self.assertRaisesRegex(
            GameplayContractError, "conflicting writes"
        ):
            parse_skill_blueprint(
                _skill_document(effect=first, extra_effect=second),
                basic_registry().statuses,
                material_authority((_material(),)),
            )

    def test_unknown_field_rejects_atomically(self):
        skill = parse_skill_blueprint(
            _skill_document(
                effect=_effect_document(field_id="missing_field"),
                skill_id="dynamics_missing",
            ),
            basic_registry().statuses,
            material_authority((_material(),)),
        )
        runtime, _ = _runtime(skills=(skill,))
        before = _snapshot(runtime)
        with self.assertRaisesRegex(GameplayContractError, "unknown Field"):
            submit_timed_primary_action(
                runtime.session,
                runtime.action_registry,
                ActionRequest("missing_field", PLAYER, skill.id),
            )
        self.assertEqual(_snapshot(runtime), before)

    def test_engine_cascade_and_late_tick_failure_roll_back(self):
        runtime, _ = _runtime()
        laws = (
            *runtime.static_laws,
            *build_action_laws(runtime.action_registry),
            {
                "id": "pmw.v04.owner.dynamics_cascade_failure",
                "mode": "event",
                "priority": 100,
                "bindings": {
                    "area": {
                        "kind": "entity",
                        "requires": [DYNAMICS_COMPONENT],
                    },
                },
                "when": {"all": [
                    {"event.type": {"eq": "pmw.v04.action.resolve"}},
                    {"ref": "$area.id", "eq": AREA},
                ]},
                "effects": [{
                    "op": "set",
                    "target": f"$area.{DYNAMICS_COMPONENT}.fields.humidity.value",
                    "value": {"div": [1, 0]},
                }],
            },
        )
        runtime.session = build_runtime(
            deepcopy(runtime.session.state),
            discover_profiles(runtime.session.state),
            laws,
        )
        before = _snapshot(runtime)
        with self.assertRaises(ZeroDivisionError):
            resolve_action(
                runtime.session,
                runtime.action_registry,
                ActionRequest("cascade_failure", PLAYER, SKILL_ID),
            )
        self.assertEqual(_snapshot(runtime), before)

        runtime, _ = _runtime()
        before = _snapshot(runtime)
        from experiments.generative_mechanics.next_tracks_v06.gameplay_v04 import (
            time_ledger,
        )
        real_tick = time_ledger.advance_world_tick

        def fail_after_tick(working, **kwargs):
            result = real_tick(working, **kwargs)
            raise RuntimeError("injected late dynamics tick")

        with patch.object(
            time_ledger, "advance_world_tick", side_effect=fail_after_tick
        ):
            with self.assertRaisesRegex(RuntimeError, "late dynamics tick"):
                submit_timed_primary_action(
                    runtime.session,
                    runtime.action_registry,
                    ActionRequest("late_tick_failure", PLAYER, SKILL_ID),
                )
        self.assertEqual(_snapshot(runtime), before)

    def test_checkpoint_rebuild_preserves_new_action_and_skill_hashes(self):
        runtime, compiled = _runtime()
        skill = runtime.blueprints[(SKILL_ID, 1)]
        action_hash = runtime.action_registry.actions[SKILL_ID].canonical_hash
        with tempfile.TemporaryDirectory(dir=TEST_TMP) as directory:
            path = Path(directory) / "dynamics_checkpoint.json"
            save_registry_checkpoint(path, runtime)
            restored = load_registry_checkpoint(path, compiled)
        self.assertEqual(
            restored.blueprints[(SKILL_ID, 1)].canonical_hash,
            skill.canonical_hash,
        )
        self.assertEqual(
            restored.action_registry.actions[SKILL_ID].canonical_hash,
            action_hash,
        )
        submitted = submit_timed_primary_action(
            restored.session,
            restored.action_registry,
            ActionRequest("restored_cast", PLAYER, SKILL_ID),
        )
        self.assertEqual(
            submitted.action.definition.canonical_hash, action_hash
        )

    def test_submit_timed_pays_one_cost_and_ticks_only_action_duration(self):
        runtime, _ = _runtime(fields=[_field()])
        before_mana = _actor_state(runtime, PLAYER)["mana"]
        submitted = submit_timed_primary_action(
            runtime.session,
            runtime.action_registry,
            ActionRequest("cost_once", PLAYER, SKILL_ID),
        )
        self.assertEqual(submitted.action.cost.mana, 4)
        self.assertEqual(submitted.action.cost.duration, 1)
        self.assertEqual(_actor_state(runtime, PLAYER)["mana"], before_mana - 4)
        self.assertEqual(_budget(runtime)["spent_ticks"], 1)
        self.assertEqual(_budget(runtime)["remaining_ticks"], 19)
        self.assertEqual(len(runtime.session.state.scheduled_events), 1)

    def test_effective_source_state_is_the_staged_dynamics_source(self):
        runtime, _ = _runtime()
        outcome = submit_timed_primary_action(
            runtime.session,
            runtime.action_registry,
            ActionRequest("source_shape", PLAYER, SKILL_ID),
        )
        slot = _field_state(runtime)["temporary_modifiers"]["slot_0"]
        self.assertEqual(slot["target"], 0.0)
        self.assertEqual(slot["target_weight"], 0.0)
        self.assertRegex(slot["source_id"], r"^dm_[a-f0-9]{32}$")
        self.assertEqual(slot["owner"], PLAYER)
        prepared = outcome.action.effect_outcomes[0]["values"]["source"]
        self.assertEqual(prepared["source_id"], slot["source_id"])
        self.assertEqual(prepared["curve_priority"], slot["curve_priority"])
        self.assertEqual(prepared["expiry_handle"], slot["expiry_handle"])


if __name__ == "__main__":
    unittest.main()
