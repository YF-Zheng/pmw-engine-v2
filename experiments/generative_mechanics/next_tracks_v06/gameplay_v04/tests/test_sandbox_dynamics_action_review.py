"""Independent C4.4 dynamics_modifier Action review; not an owner oracle."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, is_dataclass
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pmw import Relation

from experiments.generative_mechanics.next_tracks_v06.gameplay_v04 import (
    time_ledger,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.action_compiler import (
    build_action_laws,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.actions import (
    ActionRegistry,
    ActionRequest,
    parse_action_definition,
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
    build_content_session,
    compile_content,
    initialize_content_world,
    make_content,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.contracts import (
    DynamicsSource,
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
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.registry import (
    MechanismRegistryRuntime,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.runtime import (
    advance_world_tick,
    apply_source,
    clock_entity,
    remove_source,
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
REVIEW_TMP = PROJECT_ROOT / "docs" / "agent_bootstrap" / "evidence" / "test_tmp"
PLAYER = "c44_player"
NPC = "c44_npc"
AREA_A = "c44_area_a"
AREA_B = "c44_area_b"
MATERIAL_ID = "c44_review_material"
SKILL_ID = "c44_shared_heat"
FIELD_ID = "heat"
ACTOR_COMPONENT = "pmw_gameplay_actor"
DYNAMICS_COMPONENT = "pmw_gameplay_dynamics"


# Generated independently from git archive HEAD 7c975cb before reading the
# owner's new test. These are semantic Action and raw Skill canonical hashes.
HEAD_ACTION_HASHES = {
    "damage": "b74b92b474ab1cd79786809a77b6a3c068abc8e04486a3975c45404f3784f938",
    "heal": "82046c648852308dbd92bd5e85174a27973c10262c6a257662c8c70649f9f609",
    "shield": "4a5d0358eacc73c471341b40b4b7559d899c27895e3df6fe63462e6fafc2366b",
    "add_resource": "69134f2b06df999296ea96cf4c29ffd55684e99405cf16d7ee65ec47f0bc80eb",
    "apply_status": "8aa0882108720fe66662c3d6ff3721b916a34d7f5d2251717a7f2854b42c5cef",
    "modify_field": "ed12a8dd1927c95308b034ad1f66daaf16b0b39743c21514ca9bead150d771ec",
    "modify_attractor": "f8c284b649e3843b52fb07577dec8c7e59a81e10cff7c653df6c763cc60fd425",
    "modify_rate": "e29680898dbf9956d9a7954330bd3803dd24bae02c609ab0056a18ef0b53655d",
    "grant_trait": "1c3a8f6eb195402185d99eb406dadcecbb3a2b3de531c42c43d24168e5655781",
    "process_start": "fecd324b209f4f786d47173e904e98c57601fc5f5a0606ceebb39a8a6222a756",
    "process_modify": "4d271a84189bac2d33467045af07ec01e2b1b7e90ab7975cfe80ac7162a7d8e9",
    "drive_source": "c1ea3986b77d6d2f177944a5ff305d2b1643b1fee432801ea9728f2fb24122ce",
    "relation_modifier": "6d8cd81b2f363ed7c917d823b64dfb0966653a83f8f7d8e16995f64dba831f08",
}
HEAD_SKILL_HASHES = {
    "damage": "76ad9e6b01265a8e325be749df18e9dcf0191cc11bbd4cef8b729187ed0b3f45",
    "heal": "ed14478d6f8f22b161a7b14a90c1dacd11ee1c4d9f495e07a245543e0d36e469",
    "shield": "769bc392363b1e7dc6a9e57f2a37280dd62740a69620c05eed9773187c8bd580",
    "add_resource": "e5b22fbe556b119135c39071332d87d2f56b3e49470f5145a6a3f8a543e70e5a",
    "apply_status": "e5a2e4f748f697833be474946f1eb2b920c4d3fc10edb387dfbec45e8fa71194",
    "modify_field": "28df77031a973163312073dc7464d52f0e9d9e7e4a3be67a233fc853a0b5d054",
    "modify_attractor": "cd29070ee14062d79e54d6b53c3bbe1e64e58734524f1a18cbfc38312a6a1fd6",
    "modify_rate": "ea713517b1e59bc7b2cbe3f5c9e3b019d92ce067bf420a028614acd73e24b53c",
    "grant_trait": "7fb043358165dc072fff141d43b373132ef94f8bb7d69dbf5461e4cdb09168ea",
    "process_start": "7b1e04971403b34032ee5c240643cceffdaf0ad7d0926e49062c9642cb650adb",
    "process_modify": "638af33d5a2ffda35307d55a4ae7c78fbc993a4e7bf1a3ac5b79f76a18fb620e",
    "drive_source": "c3011f55c9ec734f86cbf55373ef321ca7742049953bc21894eb7911591af223",
    "relation_modifier": "552bcf15c17c3804e710b7d873fed57c9e9d99cf933c48a743d07bcdd5533150",
}


def _actor(actor_id: str, *, controller: str, mana: float = 10.0):
    return instantiate_actor(
        parse_actor_blueprint({
            "protocol": "pmw-gameplay-v0.4",
            "kind": "actor_blueprint",
            "id": f"{actor_id}_blueprint",
            "hp": {"max": 50.0, "initial": 50.0},
            "mana": {"max": 20.0, "initial": mana, "dynamics": None},
            "attributes": {
                "power": 4.0,
                "control": 4.0,
                "resilience": 4.0,
                "agility": 4.0,
            },
            "traits": [],
        }),
        actor_id,
        controller=controller,
    )


def _area(area_id: str, initial: float, *, temporary_slots: int = 2):
    return instantiate_area(
        parse_area_blueprint({
            "protocol": "pmw-gameplay-v0.4",
            "kind": "area_blueprint",
            "id": f"{area_id}_blueprint",
            "fields": [{
                "id": FIELD_ID,
                "domain": {"min": 0.0, "max": 1.0},
                "initial": initial,
                "target": 0.8,
                "rate": 0.2,
                "curve": "linear",
                "max_persistent_patches": 2,
                "max_temporary_modifiers": temporary_slots,
            }],
        }),
        area_id,
    )


def _world(*, player_area: str = AREA_A, npc_area: str = AREA_B):
    initial = {AREA_A: 0.2, AREA_B: 0.6}
    areas = {
        AREA_A: _area(AREA_A, initial[AREA_A]),
        AREA_B: _area(AREA_B, initial[AREA_B]),
    }
    actors = {
        PLAYER: _actor(PLAYER, controller="human"),
        NPC: _actor(NPC, controller="ai"),
    }
    world = build_gameplay_world(
        "c44_review_world",
        areas=areas.values(),
        actors=actors.values(),
        placements=((PLAYER, player_area), (NPC, npc_area)),
    )
    world.entities["pmw:v04:clock"] = clock_entity()
    return world


def _material(kind: str = "dynamics_modifier", *, budget: float = 8.0):
    return parse_material({
        "id": MATERIAL_ID,
        "tier": "rare",
        "region_rarity": "scarce",
        "traits": [{
            "id": "c44_heat_control",
            "effect_kinds": [kind],
            "selectors": ["current_area"],
            "budget_points": budget,
        }],
    })


def _effect(**changes):
    effect = {
        "id": "heat_shift",
        "kind": "dynamics_modifier",
        "target": {"kind": "current_area"},
        "commitment": "required",
        "field_id": FIELD_ID,
        "rate_add": 0.1,
        "rate_multiplier": 2.0,
        "curve": "linear",
        "curve_priority": 3,
        "duration": 3,
    }
    effect.update(changes)
    return effect


def _skill_document(*, skill_id: str = SKILL_ID, effect=None, cost=None,
                    kind: str = "skill_blueprint", trigger: str = "on_use"):
    return {
        "protocol": "pmw-gameplay-v0.4",
        "kind": kind,
        "id": skill_id,
        "version": 1,
        "trigger": trigger,
        "condition": None,
        "duration": None,
        "cost": {"duration": 1, "mana": 4.0} if cost is None else cost,
        "scope": {
            "selectors": ["current_area"],
            "relation_types": [],
        },
        "effects": [_effect() if effect is None else effect],
        "budget": {"limit": 8.0},
        "max_firings_per_root": 1,
        "material_ids": [MATERIAL_ID],
    }


def _skill(document=None, *, authority_kind="dynamics_modifier"):
    return parse_skill_blueprint(
        _skill_document() if document is None else document,
        basic_registry().statuses,
        material_authority((_material(authority_kind),)),
    )


def _fixture(*, skills=(), world=None, compiled=None, temporary_slots=2):
    if world is None:
        world = _world()
        if temporary_slots != 2:
            field = world.entities[AREA_A].components[DYNAMICS_COMPONENT]["fields"][FIELD_ID]
            field["temporary_modifiers"] = {
                f"slot_{index}": deepcopy(next(iter(field["temporary_modifiers"].values())))
                for index in range(temporary_slots)
            }
            field_b = world.entities[AREA_B].components[DYNAMICS_COMPONENT]["fields"][FIELD_ID]
            field_b["temporary_modifiers"] = {
                f"slot_{index}": deepcopy(next(iter(field_b["temporary_modifiers"].values())))
                for index in range(temporary_slots)
            }
    base = ActionRegistry(
        basic_registry().actions.values(),
        basic_registry().statuses.values(),
    )
    content = make_content(
        base,
        skills=tuple(skills),
        material_ids=(MATERIAL_ID,),
    )
    detached = initialize_content_world(
        initialize_time_budget(world, 20),
        content,
    )
    active_compiled = compile_content(content) if compiled is None else compiled
    session = build_content_session(detached, active_compiled)
    runtime = MechanismRegistryRuntime.from_compiled_content(
        session,
        active_compiled,
    )
    return {
        "runtime": runtime,
        "session": runtime.session,
        "registry": runtime.action_registry,
        "compiled": active_compiled,
    }


def _equip(runtime, actor_id: str, skill, slot: int = 0):
    change_loadout(
        runtime.session,
        runtime.manifest,
        actor_id=actor_id,
        operation="equip_active",
        skill=skill_ref(skill),
        slot=slot,
    )


def _cast(fixture, request_id: str, actor_id: str, skill_id: str = SKILL_ID):
    return submit_timed_primary_action(
        fixture["session"],
        fixture["registry"],
        ActionRequest(request_id, actor_id, skill_id),
    )


def _json_value(value):
    if hasattr(value, "to_dict"):
        return _json_value(value.to_dict())
    if is_dataclass(value) and not isinstance(value, type):
        return _json_value(asdict(value))
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return deepcopy(value)


def _snapshot(session):
    return {
        "world": _json_value(session.state.to_dict()),
        "stats": _json_value(session.runtime.stats),
        "revision": session.runtime.revision,
        "object_revision": session.runtime.object_revision,
        "state_closure_known": session.runtime.state_closure_known,
        "schedule": _json_value(session.state.scheduled_events),
        "profiles": _json_value(session.profiles),
    }


def _field(session, area_id=FIELD_ID):
    if area_id == FIELD_ID:
        area_id = AREA_A
    return session.state.entities[area_id].components[DYNAMICS_COMPONENT]["fields"][FIELD_ID]


def _budget(session):
    return session.state.entities["pmw:v04:clock"].components[
        TIME_BUDGET_COMPONENT
    ]


def _mana(session, actor_id):
    return session.state.entities[actor_id].components[ACTOR_COMPONENT]["mana"]


def _move(session, actor_id: str, area_id: str):
    relation_id = next(
        relation.id for relation in session.state.relations.values()
        if relation.type == "located_in" and relation.source == actor_id
    )
    del session.state.relations[relation_id]
    new_id = f"located:{actor_id}:{area_id}"
    session.state.relations[new_id] = Relation(
        new_id, "located_in", actor_id, area_id
    )
    session.runtime.revalidate()


def _assert_close(test: unittest.TestCase, actual, expected):
    test.assertAlmostEqual(actual, expected, places=12)


class FormalSharedActionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        REVIEW_TMP.mkdir(parents=True, exist_ok=True)

    def test_same_parsed_skill_player_npc_two_areas_real_ticks(self):
        # A dedicated reviewed Action cost of duration 1 is the real paid path
        # elsewhere. This test intentionally uses the smallest legal Action
        # duration and compares the immediately post-action Tick1 state.
        skill = _skill()
        self.assertEqual(skill.effects[0].kind, "dynamics_modifier")
        self.assertEqual(skill.budget_used, 3.3)
        self.assertEqual(skill.action.cost.mana, 4.0)
        fixture = _fixture(skills=(skill,))
        _equip(fixture["runtime"], PLAYER, skill)
        _equip(fixture["runtime"], NPC, skill)
        self.assertEqual(
            fixture["session"].state.entities[PLAYER].components[
                ACTOR_COMPONENT
            ]["active_equipped"][0],
            skill_ref(skill).to_dict(),
        )
        self.assertEqual(
            fixture["session"].state.entities[NPC].components[
                ACTOR_COMPONENT
            ]["active_equipped"][0],
            skill_ref(skill).to_dict(),
        )

        player = _cast(fixture, "c44_player_cast", PLAYER)
        npc = _cast(fixture, "c44_npc_cast", NPC)
        self.assertEqual((player.action.cost.mana, player.action.cost.duration), (4.0, 1))
        self.assertEqual((npc.action.cost.mana, npc.action.cost.duration), (4.0, 1))
        self.assertEqual((_mana(fixture["session"], PLAYER), _mana(fixture["session"], NPC)), (6.0, 6.0))
        budget = _budget(fixture["session"])
        self.assertEqual((budget["spent_ticks"], budget["remaining_ticks"]), (2, 18))

        a = _field(fixture["session"], AREA_A)
        b = _field(fixture["session"], AREA_B)
        # Each paid Action immediately performs Tick 1. Hand calculation:
        # A: 0.2 + ((0.2 + 0.1) * 2) * 0.6 = 0.56, then .704.
        # B: 0.6 + 0.6 * 0.2 = 0.72, then .736.
        _assert_close(self, a["value"], 0.704)
        _assert_close(self, b["value"], 0.736)
        _assert_close(self, a["diagnostics"]["effective_rate"], 0.6)
        _assert_close(self, b["diagnostics"]["effective_rate"], 0.6)
        self.assertEqual(a["diagnostics"]["effective_curve"], "linear")
        self.assertEqual(b["diagnostics"]["effective_curve"], "linear")
        self.assertNotEqual(a["value"], b["value"])
        advance_world_tick(fixture["session"])
        # Player expires at time3, before this Tick3, and resumes from its
        # CURRENT post-Tick2 value. NPC expires at time4, so its override
        # remains active at Tick3.
        player_field = _field(fixture["session"], AREA_A)
        npc_field = _field(fixture["session"], AREA_B)
        self.assertFalse(player_field["temporary_modifiers"]["slot_0"]["active"])
        self.assertTrue(npc_field["temporary_modifiers"]["slot_0"]["active"])
        _assert_close(self, player_field["value"], 0.7232)
        _assert_close(self, npc_field["value"], 0.7744)
        matched = {
            law.law_id
            for result in (player.time, npc.time)
            for tick in result.ticks
            for event in tick.event_result.trace.events
            for law in event.event_law_matches
        }
        self.assertTrue(any(
            law_id.startswith("pmw.v04.dynamics.200.")
            and "slot_" in law_id
            for law_id in matched
        ))
        self.assertEqual(
            {event.id for event in fixture["session"].state.scheduled_events},
            {
                "pmw:v04:action-expiry:c44_npc_cast:heat_shift",
            },
        )

    def test_add_multiply_hand_value_and_effective_rate_clamp(self):
        # Base 0.2; add 0.25 and multiply 8 -> 3.6, clamped to linear limit 1.
        skill = _skill(_skill_document(effect=_effect(
            rate_add=0.25,
            rate_multiplier=8.0,
            duration=3,
        )))
        fixture = _fixture(skills=(skill,))
        _equip(fixture["runtime"], PLAYER, skill)
        _cast(fixture, "c44_clamp_cast", PLAYER)
        field = _field(fixture["session"])
        # Tick 1: 0.2 + min(1, (0.2+0.25)*8)*(0.8-0.2) = 0.8.
        _assert_close(self, field["value"], 0.8)
        _assert_close(self, field["diagnostics"]["effective_rate"], 1.0)
        self.assertEqual(field["diagnostics"]["effective_curve"], "linear")
        advance_world_tick(fixture["session"])
        _assert_close(self, _field(fixture["session"])["value"], 0.8)

    def test_none_freeze_duration3_expires_before_tick3_current_base(self):
        skill = _skill(_skill_document(effect=_effect(
            rate_add=0.1,
            rate_multiplier=2.0,
            curve="none",
            curve_priority=7,
            duration=3,
        )))
        fixture = _fixture(skills=(skill,))
        _equip(fixture["runtime"], PLAYER, skill)
        cast = _cast(fixture, "c44_none_cast", PLAYER)
        self.assertEqual(cast.time.duration, 1)
        self.assertEqual(cast.time.ticks[0].step, 1)
        # Tick 1 happens during the paid Action, while the actor is still here.
        _assert_close(self, _field(fixture["session"])["value"], 0.2)
        _assert_close(self, _field(fixture["session"], AREA_B)["value"], 0.64)
        # Move after casting: the modifier must remain Area-owned, not actor-owned.
        _move(fixture["session"], PLAYER, AREA_B)
        advance_world_tick(fixture["session"])
        frozen = _field(fixture["session"], AREA_A)
        self.assertTrue(frozen["temporary_modifiers"]["slot_0"]["active"])
        _assert_close(self, frozen["value"], 0.2)
        self.assertEqual(frozen["diagnostics"]["effective_curve"], "none")
        _assert_close(self, _field(fixture["session"], AREA_B)["value"], 0.672)
        # Support fixture: CURRENT baseline changes while the override exists.
        frozen["baseline"]["target"] = 0.9
        fixture["session"].runtime.revalidate()
        advance_world_tick(fixture["session"])
        restored = _field(fixture["session"], AREA_A)
        self.assertFalse(restored["temporary_modifiers"]["slot_0"]["active"])
        self.assertEqual(
            restored["temporary_modifiers"]["slot_0"]["expiry_handle"],
            None,
        )
        # Tick3 uses current baseline 0.9: 0.2 + 0.2 * (0.9 - 0.2).
        _assert_close(self, restored["value"], 0.34)
        self.assertEqual(restored["diagnostics"]["effective_curve"], "linear")
        _assert_close(self, _field(fixture["session"], AREA_B)["value"], 0.6976)
        self.assertEqual(fixture["session"].state.scheduled_events, [])

    def test_lower_and_higher_priority_sources_survive_exact_expiry(self):
        skill = _skill(_skill_document(effect=_effect(
            curve="none",
            curve_priority=5,
            duration=3,
        )))
        fixture = _fixture(skills=(skill,))
        _equip(fixture["runtime"], PLAYER, skill)
        apply_source(
            fixture["session"],
            entity_id=AREA_A,
            field_id=FIELD_ID,
            layer="persistent",
            source=DynamicsSource(
                "lower_curve", "fixture_owner",
                curve="linear", curve_priority=1,
            ),
        )
        cast = _cast(fixture, "c44_priority_stack", PLAYER)
        self.assertEqual(cast.time.duration, 1)
        field = _field(fixture["session"])
        self.assertEqual(field["diagnostics"]["effective_curve"], "none")
        _assert_close(self, field["value"], 0.2)
        advance_world_tick(fixture["session"])
        field = _field(fixture["session"])
        self.assertEqual(field["diagnostics"]["effective_curve"], "none")
        _assert_close(self, field["value"], 0.2)
        # Higher source expires exactly at time3; the lower persistent source
        # survives and becomes the actual Tick3 curve.
        advance_world_tick(fixture["session"])
        field = _field(fixture["session"])
        self.assertFalse(field["temporary_modifiers"]["slot_0"]["active"])
        self.assertTrue(field["persistent_patches"]["slot_0"]["active"])
        self.assertEqual(field["diagnostics"]["effective_curve"], "linear")
        _assert_close(self, field["value"], 0.32)
        remove_source(
            fixture["session"],
            entity_id=AREA_A,
            field_id=FIELD_ID,
            source_id="lower_curve",
            owner="fixture_owner",
        )
        advance_world_tick(fixture["session"])
        field = _field(fixture["session"])
        self.assertEqual(field["diagnostics"]["effective_curve"], "linear")
        self.assertFalse(field["persistent_patches"]["slot_0"]["active"])
        _assert_close(self, field["value"], 0.416)

    def test_duration_one_is_legal_and_expires_before_its_unpaid_tick(self):
        # Scheduler-before-Tick convention: a cast at t0 with duration 1
        # schedules expiry at t1, and the next paid / world Tick also occurs at
        # t1. Expiry is processed first, so the modifier grants no Tick.
        skill = _skill(_skill_document(effect=_effect(
            rate_add=1.0,
            rate_multiplier=8.0,
            curve="none",
            curve_priority=7,
            duration=1,
        )))
        fixture = _fixture(skills=(skill,))
        _equip(fixture["runtime"], PLAYER, skill)
        cast = _cast(fixture, "c44_duration_one", PLAYER)
        self.assertEqual(cast.action.cost.duration, 1)
        self.assertEqual(cast.time.duration, 1)
        self.assertEqual(cast.time.ticks[0].step, 1)
        field = _field(fixture["session"])
        # The paid tick uses the field's current linear baseline, not the
        # duration-1 source: 0.2 + (0.8 - 0.2) * 0.2 = 0.32.
        _assert_close(self, field["value"], 0.32)
        self.assertEqual(field["diagnostics"]["effective_curve"], "linear")
        self.assertFalse(field["temporary_modifiers"]["slot_0"]["active"])
        self.assertIsNone(field["temporary_modifiers"]["slot_0"]["expiry_handle"])
        self.assertEqual(fixture["session"].state.scheduled_events, [])


class AtomicDenialTests(unittest.TestCase):
    def test_duplicate_priority_persistent_and_temporary_reject_without_delta(self):
        skill = _skill(_skill_document(effect=_effect(curve_priority=4)))
        fixture = _fixture(skills=(skill,))
        _equip(fixture["runtime"], PLAYER, skill)
        apply_source(
            fixture["session"],
            entity_id=AREA_A,
            field_id=FIELD_ID,
            layer="persistent",
            source=DynamicsSource(
                "persistent_priority", "fixture",
                curve="linear", curve_priority=4,
            ),
        )
        before = _snapshot(fixture["session"])
        with self.assertRaisesRegex(GameplayContractError, "priority"):
            _cast(fixture, "c44_duplicate_persistent", PLAYER)
        self.assertEqual(_snapshot(fixture["session"]), before)

        fixture = _fixture(skills=(skill,))
        _equip(fixture["runtime"], PLAYER, skill)
        apply_source(
            fixture["session"],
            entity_id=AREA_A,
            field_id=FIELD_ID,
            layer="temporary",
            source=DynamicsSource(
                "temporary_priority", "fixture",
                curve="linear", curve_priority=4, duration_ticks=8,
            ),
        )
        before = _snapshot(fixture["session"])
        with self.assertRaisesRegex(GameplayContractError, "priority"):
            _cast(fixture, "c44_duplicate_temporary", PLAYER)
        self.assertEqual(_snapshot(fixture["session"]), before)

    def test_schema_matrix_rejects_atomically(self):
        cases = []
        fields = {
            "field_id": [None, True, "Heat", "heat.temperature", ""],
            "rate_add": [None, False, True, "0.1", [], math.nan, math.inf, -1.0001, 1.0001],
            "rate_multiplier": [None, False, True, "2", [], math.nan, math.inf, -0.0001, 8.0001],
            "curve": [None, True, "quadratic", "", []],
            "curve_priority": [None, False, True, "4", [], -1, 32, 4.0],
            "duration": [None, False, True, "3", [], 0, 65, 3.0],
        }
        for key, values in fields.items():
            for value in values:
                cases.append((f"{key}={value!r}", _effect(**{key: value})))
        missing = _effect()
        missing.pop("curve_priority")
        cases.append(("missing_curve_priority", missing))
        unknown = _effect(extra="forbidden")
        cases.append(("unknown_extra", unknown))
        cases.append(("self_target", _effect(target={"kind": "self"})))
        cases.append(("actor_target", _effect(target={"kind": "target_actor"})))
        cases.append(("remote_adjacent", _effect(target={"kind": "adjacent_area"})))
        cases.append(("remote_linked", _effect(target={
            "kind": "linked_object",
            "relation_type": "remote_link",
        })))
        cases.append(("conditional", _effect(commitment="conditional")))
        cases.append(("terms", _effect(attribute_terms=[])))
        cases.append(("targeting", _effect(targeting={"sensing": "none", "evadable": False})))

        for label, effect in cases:
            with self.subTest(label=label):
                document = _skill_document(effect=effect)
                with self.assertRaises(GameplayContractError):
                    _skill(document)

        passive = _skill_document(
            kind="passive_blueprint",
            trigger="damage_resolved",
            cost={"duration": 1, "mana": 0.0},
        )
        with self.assertRaisesRegex(GameplayContractError, "active on_use"):
            _skill(passive)

    def test_publication_denial_has_no_cost_time_or_scheduler_delta(self):
        skill = _skill(_skill_document(effect=_effect(curve_priority=9)))
        fixture = _fixture(skills=(skill,))
        _equip(fixture["runtime"], PLAYER, skill)
        _equip(fixture["runtime"], NPC, skill)
        apply_source(
            fixture["session"],
            entity_id=AREA_A,
            field_id=FIELD_ID,
            layer="persistent",
            source=DynamicsSource(
                "publication_guard", "fixture",
                curve="linear", curve_priority=9,
            ),
        )
        before = _snapshot(fixture["session"])
        with self.assertRaisesRegex(GameplayContractError, "priority"):
            _cast(fixture, "c44_publication_denial", PLAYER)
        self.assertEqual(_snapshot(fixture["session"]), before)
        self.assertEqual(_mana(fixture["session"], PLAYER), 10.0)
        self.assertEqual(_mana(fixture["session"], NPC), 10.0)
        self.assertEqual(
            (
                _budget(fixture["session"])["spent_ticks"],
                _budget(fixture["session"])["remaining_ticks"],
            ),
            (0, 20),
        )
        self.assertEqual(fixture["session"].state.sim_time, 0.0)

    def test_material_scope_rejects_without_publication(self):
        with self.assertRaisesRegex(GameplayContractError, "material effect"):
            _skill(authority_kind="damage")

    def test_capacity_and_late_failure_rollback(self):
        skill = _skill()
        fixture = _fixture(skills=(skill,), temporary_slots=1)
        _equip(fixture["runtime"], PLAYER, skill)
        apply_source(
            fixture["session"],
            entity_id=AREA_A,
            field_id=FIELD_ID,
            layer="temporary",
            source=DynamicsSource(
                "capacity_fixture", "fixture", duration_ticks=8,
            ),
        )
        before = _snapshot(fixture["session"])
        with self.assertRaisesRegex(GameplayContractError, "capacity"):
            _cast(fixture, "c44_capacity", PLAYER)
        self.assertEqual(_snapshot(fixture["session"]), before)

        fixture = _fixture(skills=(skill,))
        _equip(fixture["runtime"], PLAYER, skill)
        real_tick = time_ledger.advance_world_tick
        calls = 0

        def fail_tick(working, **kwargs):
            nonlocal calls
            calls += 1
            result = real_tick(working, **kwargs)
            if calls == 1:
                raise RuntimeError("c44 late tick failure")
            return result

        before = _snapshot(fixture["session"])
        with patch.object(time_ledger, "advance_world_tick", side_effect=fail_tick):
            with self.assertRaisesRegex(RuntimeError, "late tick"):
                _cast(fixture, "c44_late_failure", PLAYER)
        self.assertEqual(_snapshot(fixture["session"]), before)

    def test_two_new_writes_do_not_reuse_one_temp_slot(self):
        first = _effect()
        second = _effect(id="heat_shift_two", curve_priority=6)
        document = _skill_document(effect=None)
        document["effects"] = [first, second]
        document["budget"]["limit"] = 8.0
        with self.assertRaisesRegex(GameplayContractError, "conflicting writes"):
            _skill(document)

    def test_dynamics_and_legacy_modifier_footprint_conflict(self):
        document = _skill_document()
        document["effects"] = [
            _effect(),
            {
                "id": "legacy_rate",
                "kind": "modify_rate",
                "target": {"kind": "current_area"},
                "commitment": "required",
                "field_id": FIELD_ID,
                "amount": -0.05,
                "duration": 2,
            },
        ]
        document["budget"]["limit"] = 8.0
        with self.assertRaisesRegex(GameplayContractError, "conflicting writes"):
            parse_action_definition({
                "id": "c44_footprint_conflict",
                "version": 1,
                "action_type": "skill",
                "cost": {"duration": 1, "mana": 0},
                "scope": {
                    "selectors": ["current_area"],
                    "relation_types": [],
                },
                "effects": document["effects"],
            }, basic_registry().statuses)


class ContinuityAndLegacyTests(unittest.TestCase):
    def test_save_load_rebuild_preserves_hashes_and_continuation(self):
        skill = _skill()
        fixture = _fixture(skills=(skill,))
        _equip(fixture["runtime"], PLAYER, skill)
        cast = _cast(fixture, "c44_before_save", PLAYER)
        self.assertEqual(_field(fixture["session"])["value"], 0.56)
        with tempfile.TemporaryDirectory(dir=REVIEW_TMP) as directory:
            path = Path(directory) / "checkpoint.json"
            save_registry_checkpoint(path, fixture["runtime"])
            restored = load_registry_checkpoint(path, fixture["compiled"])
        self.assertEqual(
            restored.blueprints[(SKILL_ID, 1)].canonical_hash,
            skill.canonical_hash,
        )
        self.assertEqual(
            restored.action_registry.actions[SKILL_ID].canonical_hash,
            skill.action.canonical_hash,
        )
        self.assertEqual(
            restored.session.state.to_dict(),
            fixture["session"].state.to_dict(),
        )
        advance_world_tick(fixture["session"])
        advance_world_tick(restored.session)
        _assert_close(self, _field(fixture["session"])["value"], 0.704)
        _assert_close(self, _field(restored.session)["value"], 0.704)
        self.assertEqual(
            fixture["session"].state.to_dict(),
            restored.session.state.to_dict(),
        )
        # No catalog rebuild: the exact restored hash can still submit after
        # the first exact expiry and its handle has been removed.
        advance_world_tick(restored.session)
        second = submit_timed_primary_action(
            restored.session,
            restored.action_registry,
            ActionRequest("c44_after_load", PLAYER, SKILL_ID),
        )
        self.assertEqual(second.action.cost.mana, 4.0)

    def test_old_effect_action_and_skill_hashes_unchanged(self):
        statuses = basic_registry().statuses
        selectors = {"self": ["self"], "current_area": ["current_area"]}
        for kind, expected in HEAD_ACTION_HASHES.items():
            with self.subTest(kind=kind):
                target = {"kind": "current_area"} if kind in {
                    "modify_field", "modify_attractor", "modify_rate",
                    "process_start", "process_modify", "drive_source",
                    "relation_modifier",
                } else {"kind": "self"}
                if kind == "damage":
                    extra = {"amount": 2.0}
                elif kind == "heal":
                    extra = {"amount": 2.0}
                elif kind == "shield":
                    extra = {"amount": 2.0}
                elif kind == "add_resource":
                    extra = {"resource": "mana", "amount": 1.0}
                elif kind == "apply_status":
                    extra = {"status_id": "basic_guarding"}
                elif kind == "modify_field":
                    extra = {"field_id": "heat", "amount": 0.1}
                elif kind == "modify_attractor":
                    extra = {"field_id": "heat", "amount": 0.7, "duration": 2}
                elif kind == "modify_rate":
                    extra = {"field_id": "heat", "amount": -0.05, "duration": 2}
                elif kind == "grant_trait":
                    extra = {"trait_id": "brave", "duration": 2}
                elif kind == "process_start":
                    extra = {"process_template_id": "legacy_process"}
                elif kind == "process_modify":
                    extra = {"process_template_id": "legacy_process", "process_rate": 1.0}
                elif kind == "drive_source":
                    extra = {"drive_profile_id": "legacy_drive", "drive_rate": 1.0, "duration": 2}
                else:
                    extra = {"relation_profile_id": "legacy_relation", "relation_enabled": False, "duration": 2}
                effect = {
                    "id": f"legacy_{kind}",
                    "kind": kind,
                    "target": target,
                    "commitment": "required",
                    **extra,
                }
                action_doc = {
                    "id": f"legacy_{kind}",
                    "version": 1,
                    "action_type": "skill",
                    "cost": {"duration": 1, "mana": 0},
                    "scope": {
                        "selectors": selectors[target["kind"]],
                        "relation_types": [],
                    },
                    "effects": [effect],
                }
                action = parse_action_definition(action_doc, statuses)
                self.assertEqual(action.canonical_hash, expected)
                material = parse_material({
                    "id": "legacy_material",
                    "tier": "rare",
                    "region_rarity": "scarce",
                    "traits": [{
                        "id": "legacy_power",
                        "effect_kinds": [kind],
                        "selectors": selectors[target["kind"]],
                        "budget_points": 6.0,
                    }],
                })
                skill_doc = {
                    "protocol": "pmw-gameplay-v0.4",
                    "kind": "skill_blueprint",
                    "id": f"legacy_{kind}",
                    "version": 1,
                    "trigger": "on_use",
                    "condition": None,
                    "duration": None,
                    "cost": {"duration": 1, "mana": 0},
                    "scope": {
                        "selectors": selectors[target["kind"]],
                        "relation_types": [],
                    },
                    "effects": [effect],
                    "budget": {"limit": 6.0},
                    "max_firings_per_root": 1,
                    "material_ids": ["legacy_material"],
                }
                blueprint = parse_skill_blueprint(
                    skill_doc,
                    statuses,
                    material_authority((material,)),
                )
                self.assertEqual(blueprint.canonical_hash, HEAD_SKILL_HASHES[kind])


if __name__ == "__main__":
    unittest.main()
