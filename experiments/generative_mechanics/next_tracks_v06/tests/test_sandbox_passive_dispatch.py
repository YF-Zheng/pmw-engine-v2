from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError, fields, is_dataclass
from pathlib import Path
import json
import os
import tempfile
import unittest
from unittest.mock import patch

from pmw import Event

from experiments.generative_mechanics.next_tracks_v06.gameplay_v04 import actions
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.action_compiler import (
    build_action_laws,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.actions import (
    parse_action_definition,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.actions import (
    ACTION_EVENT,
    ACTOR_COMPONENT,
    ActionOutcome,
    ActionRegistry,
    ActionRequest,
    PassiveSkillBinding,
    resolve_action,
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
    GameplayContractError,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.hooks import (
    DAMAGE_NOTIFICATION,
    HookDispatchLimits,
    HookDispatchRecord,
    HookLineage,
    _validate_notification,
    execute_hook,
    parse_hook,
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
    REGISTRY_COMPONENT,
    static_law_hash,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.runtime import (
    build_runtime,
    clock_entity,
    discover_profiles,
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


PMW_ROOT = Path(__file__).resolve().parents[4]
TEMP_ROOT = PMW_ROOT / "docs" / "agent_bootstrap" / "evidence" / "test_tmp"
PLAYER = "c42_player"
NPC = "c42_npc"
AREA = "c42_area"
MATERIAL_ID = "c42_crystal"
NOTIFICATION = DAMAGE_NOTIFICATION


def _passive_raw(
    skill_id,
    effect,
    *,
    condition=None,
    max_firings=1,
):
    return {
        "protocol": "pmw-gameplay-v0.4",
        "kind": "passive_blueprint",
        "id": skill_id,
        "version": 1,
        "trigger": "damage_resolved",
        "condition": condition,
        "duration": None,
        "cost": {"duration": 1, "mana": 0},
        "scope": {"selectors": ["self", "target_actor"], "relation_types": []},
        "effects": [effect],
        "budget": {"limit": 8},
        "max_firings_per_root": max_firings,
        "material_ids": [MATERIAL_ID],
    }


def _shield_passive(skill_id="c42_shield", amount=7):
    return _passive_raw(
        skill_id,
        {
            "id": "restore_shield",
            "kind": "shield",
            "target": {"kind": "self"},
            "commitment": "required",
            "amount": amount,
        },
    )


def _counter_passive(skill_id="c42_counter", amount=4):
    return _passive_raw(
        skill_id,
        {
            "id": "counter",
            "kind": "damage",
            "target": {"kind": "target_actor"},
            "commitment": "required",
            "amount": amount,
        },
    )


def _self_damage_passive(skill_id="c42_self_damage", amount=25):
    return _passive_raw(
        skill_id,
        {
            "id": "self_damage",
            "kind": "damage",
            "target": {"kind": "self"},
            "commitment": "required",
            "amount": amount,
        },
    )


def _parse_passive(raw):
    material = parse_material(
        {
            "id": MATERIAL_ID,
            "tier": "rare",
            "region_rarity": "scarce",
            "traits": [
                {
                    "id": "c42_guard",
                    "effect_kinds": ["shield", "damage"],
                    "selectors": ["self", "target_actor"],
                    "budget_points": 12,
                }
            ],
        }
    )
    return parse_skill_blueprint(
        raw,
        basic_registry().statuses,
        material_authority((material,)),
    )


def _actor(instance_id, *, controller, hp=50, mana=20):
    blueprint = parse_actor_blueprint(
        {
            "protocol": "pmw-gameplay-v0.4",
            "kind": "actor_blueprint",
            "id": "c42_actor",
            "hp": {"max": max(50, hp), "initial": hp},
            "mana": {"max": 30, "initial": mana, "dynamics": None},
            "attributes": {
                "power": 4,
                "control": 4,
                "resilience": 4,
                "agility": 4,
            },
            "traits": [],
        }
    )
    return instantiate_actor(blueprint, instance_id, controller=controller)


def _area(instance_id=AREA):
    blueprint = parse_area_blueprint(
        {
            "protocol": "pmw-gameplay-v0.4",
            "kind": "area_blueprint",
            "id": "c42_area_blueprint",
            "fields": [
                {
                    "id": "heat",
                    "domain": {"min": 0, "max": 10},
                    "initial": 1,
                    "target": 1,
                    "rate": 0.1,
                    "curve": "linear",
                    "max_persistent_patches": 2,
                    "max_temporary_modifiers": 2,
                }
            ],
        }
    )
    return instantiate_area(blueprint, instance_id)


def _runtime(
    skills=(),
    *,
    player_area=AREA,
    npc_area=AREA,
    player_hp=50,
    npc_hp=50,
    actions=(),
):
    base = ActionRegistry(
        (*basic_registry().actions.values(), *actions),
        basic_registry().statuses.values(),
    )
    content = make_content(
        base,
        skills=tuple(skills),
        material_ids=(MATERIAL_ID,),
    )
    areas = {AREA: _area()}
    for area_id in {player_area, npc_area}:
        areas.setdefault(area_id, _area(area_id))
    entities = {
        PLAYER: _actor(PLAYER, controller="human", hp=player_hp),
        NPC: _actor(NPC, controller="ai", hp=npc_hp),
        **areas,
    }
    world = build_gameplay_world(
        "c42_world",
        areas=areas.values(),
        actors=(entities[PLAYER], entities[NPC]),
        placements=((PLAYER, player_area), (NPC, npc_area)),
    )
    for entity_id, entity in entities.items():
        world.entities.setdefault(entity_id, entity)
    world.entities["pmw:v04:clock"] = clock_entity()
    world = initialize_time_budget(world, 12)
    world = initialize_content_world(world, content)
    compiled = compile_content(content)
    session = build_content_session(world, compiled)
    runtime = MechanismRegistryRuntime.from_compiled_content(session, compiled)
    return {
        "runtime": runtime,
        "session": runtime.session,
        "registry": runtime.action_registry,
        "content": content,
        "compiled": compiled,
    }


def _equip(runtime, actor_id, skill, slot=0):
    change_loadout(
        runtime.session,
        runtime.manifest,
        actor_id=actor_id,
        operation="equip_passive",
        skill=skill_ref(skill),
        slot=slot,
    )


def _equipped(skill, **runtime_changes):
    fixture = _runtime((skill,), **runtime_changes)
    _equip(fixture["runtime"], PLAYER, skill)
    _equip(fixture["runtime"], NPC, skill)
    return fixture


def _actor_component(session, actor_id):
    return session.state.entities[actor_id].components[ACTOR_COMPONENT]


def _snapshot(session):
    return (
        deepcopy(session.state.to_dict()),
        deepcopy(session.runtime.stats),
        session.runtime.revision,
        session.runtime.object_revision,
        session.runtime.state_closure_known,
        deepcopy(list(session.state.scheduled_events)),
        deepcopy(session.profiles),
    )


def _events(outcome):
    return tuple(outcome.event_result.trace.events)


def _notifications(outcome):
    return tuple(
        row.event for row in _events(outcome)
        if row.event.type == NOTIFICATION
    )


def _records(outcome):
    records = getattr(outcome, "auto_hooks", None)
    if records is None:
        raise AssertionError("ActionOutcome.auto_hooks is missing")
    if not isinstance(records, tuple):
        raise AssertionError("auto_hooks must be an immutable tuple")
    return records


def _primary_row(outcome):
    """Return the exact primary Engine event and its response trace."""
    rows = [
        row for row in _events(outcome)
        if row.event.type == ACTION_EVENT
        and row.event.id == outcome.event_result.trace.root_event.id
    ]
    if len(rows) != 1:
        raise AssertionError("primary Engine trace is not intact")
    return rows[0]


def _notification_parent(outcome, notification):
    trace = outcome.event_result.trace
    notifications = [
        row for row in trace.events if row.event.id == notification.id
    ]
    if len(notifications) != 1:
        raise AssertionError("notification is not in its exact Engine trace")
    parent_id = notification.provenance.get("parent_event")
    parents = [
        row for row in trace.events if row.event.id == parent_id
    ]
    if len(parents) != 1:
        raise AssertionError("notification parent is missing")
    return parents[0], notifications[0]


def _damage_law(action, notification):
    token = (
        f"{action.id}.v{action.version}."
        f"{action.canonical_hash[:12]}"
    )
    return (
        f"pmw.v04.action.{token}.effect."
        f"{notification.payload['effect_id']}"
    )


def _assert_actual_notification(
    test,
    outcome,
    notification,
    *,
    action,
    source,
    target,
    hp_loss,
    shield_absorbed,
):
    parent, row = _notification_parent(outcome, notification)
    test.assertEqual(row.event.type, NOTIFICATION)
    test.assertEqual(notification.provenance["kind"], "derived")
    test.assertEqual(notification.provenance["parent_event"], parent.event.id)
    test.assertEqual(parent.event.type, ACTION_EVENT)
    test.assertEqual(parent.event.source, source)
    test.assertEqual(parent.event.time, notification.time)
    test.assertEqual(notification.source, source)
    test.assertEqual(notification.target, target)
    test.assertEqual(notification.payload["actor_id"], source)
    test.assertEqual(notification.payload["target_actor_id"], target)
    test.assertEqual(notification.payload["action_id"], action.id)
    test.assertEqual(notification.payload["action_hash"], action.canonical_hash)
    prepared = parent.event.payload["effects"][notification.payload["effect_id"]]
    test.assertEqual(prepared["kind"], "damage")
    test.assertEqual(prepared["status"], "applied")
    test.assertEqual(prepared["target_id"], target)
    law = _damage_law(action, notification)
    proposals = [
        proposal for proposal in outcome.event_result.trace.proposals
        if proposal.emitted_event_id == notification.id
    ]
    test.assertEqual(len(proposals), 1)
    proposal = proposals[0]
    test.assertEqual(proposal.status, "accepted")
    test.assertEqual(proposal.op, "emit_event")
    test.assertEqual(proposal.law_id, law)
    test.assertEqual(proposal.cause_event_id, parent.event.id)
    committed = [
        commit for commit in parent.commits
        if proposal.proposal_id in commit.accepted_proposal_ids
    ]
    test.assertTrue(committed)
    actual_hp = 0.0
    actual_shield = 0.0
    attributed = False
    for commit in parent.commits:
        for delta in commit.state_deltas:
            if delta.address.object_id != target:
                continue
            if delta.address.path == (ACTOR_COMPONENT, "hp"):
                if law in delta.law_ids:
                    actual_hp += float(delta.old_value) - float(delta.new_value)
                    attributed = True
            elif delta.address.path == (ACTOR_COMPONENT, "shield"):
                if law in delta.law_ids:
                    actual_shield += (
                        float(delta.old_value) - float(delta.new_value)
                    )
                    attributed = True
    test.assertTrue(attributed)
    test.assertAlmostEqual(actual_hp, hp_loss)
    test.assertAlmostEqual(actual_shield, shield_absorbed)
    test.assertAlmostEqual(
        float(notification.payload["hp_loss"]),
        hp_loss,
    )
    test.assertAlmostEqual(
        float(notification.payload["shield_absorbed"]),
        shield_absorbed,
    )
    test.assertAlmostEqual(
        float(notification.payload["resolved_damage"]),
        hp_loss + shield_absorbed,
    )
    test.assertGreater(float(notification.payload["resolved_damage"]), 0.0)


def _hook_event(record):
    if record.outcome is None:
        raise AssertionError("fired record has no hook ActionOutcome")
    rows = [
        row for row in record.outcome.event_result.trace.events
        if row.event.type == ACTION_EVENT
    ]
    if len(rows) != 1:
        raise AssertionError("hook ActionOutcome must contain one root Action")
    return rows[0]


class PassiveDispatchOwnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        TEMP_ROOT.mkdir(parents=True, exist_ok=True)
        os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
        os.environ["PYTHONPYCACHEPREFIX"] = str(TEMP_ROOT / "pycache")
        os.environ["TEMP"] = str(TEMP_ROOT)
        os.environ["TMP"] = str(TEMP_ROOT)
        os.environ["TMPDIR"] = str(TEMP_ROOT)

    def test_limits_default_and_default_auto_hooks(self):
        defaults = HookDispatchLimits()
        self.assertEqual(
            (
                defaults.max_depth,
                defaults.max_firings,
                defaults.max_notifications,
            ),
            (16, 32, 64),
        )
        self.assertEqual(
            set(HookDispatchLimits.__dataclass_fields__),
            {"max_depth", "max_firings", "max_notifications"},
        )
        for values in (
            {"max_depth": 0},
            {"max_depth": True},
            {"max_depth": 1.0},
            {"max_firings": 0},
            {"max_notifications": 65},
        ):
            with self.subTest(values=values):
                with self.assertRaises(
                    (TypeError, ValueError, GameplayContractError)
                ):
                    HookDispatchLimits(**values)

        fixture = _runtime()
        outcome = resolve_action(
            fixture["session"],
            fixture["registry"],
            ActionRequest("plain_attack", PLAYER, "basic_attack", NPC),
        )
        self.assertEqual(_records(outcome), ())
        self.assertIsInstance(outcome, ActionOutcome)
        self.assertEqual(
            tuple(field.name for field in fields(ActionOutcome)),
            (
                "request",
                "definition",
                "cost",
                "effect_outcomes",
                "event_result",
                "auto_hooks",
            ),
        )
        with self.assertRaises(TypeError):
            resolve_action(
                fixture["session"],
                fixture["registry"],
                ActionRequest("positional", PLAYER, "basic_attack", NPC),
                HookDispatchLimits(),
            )

    def test_same_parsed_counter_equipped_by_both_owners(self):
        passive = _parse_passive(_counter_passive("same_counter", amount=4))
        fixture = _equipped(passive)
        binding = fixture["registry"].passive_bindings[(passive.id, 1)]
        self.assertIsInstance(binding, PassiveSkillBinding)
        self.assertEqual(binding.skill_hash, passive.canonical_hash)
        self.assertEqual(binding.action_hash, passive.action.canonical_hash)
        self.assertNotEqual(
            passive.canonical_hash,
            passive.action.canonical_hash,
        )
        self.assertEqual(
            fixture["registry"].hooks[binding.hook.id],
            binding.hook,
        )
        self.assertEqual(
            fixture["registry"].actions[passive.id].canonical_hash,
            binding.action_hash,
        )

        before_time = deepcopy(
            fixture["session"].state.entities["pmw:v04:clock"].components
        )
        before_mana = {
            actor_id: _actor_component(fixture["session"], actor_id)["mana"]
            for actor_id in (PLAYER, NPC)
        }
        timed = submit_timed_primary_action(
            fixture["session"],
            fixture["registry"],
            ActionRequest("same_root", NPC, "basic_attack", PLAYER),
        )
        outcome = timed.action
        primary_notification = _notifications(outcome)[0]
        _assert_actual_notification(
            self,
            outcome,
            primary_notification,
            action=outcome.definition,
            source=NPC,
            target=PLAYER,
            hp_loss=10.0,
            shield_absorbed=0.0,
        )
        primary_rows = _events(outcome)
        self.assertFalse(
            any(
                row.event.type == ACTION_EVENT
                and row.event.payload.get("execution_kind") == "hook"
                for row in primary_rows
            ),
            "primary Engine trace must not be merged with hook roots",
        )
        self.assertEqual(
            outcome.event_result.trace.root_event.id,
            "pmw:v04:action:same_root",
        )
        self.assertEqual(timed.time.duration, 1)
        self.assertEqual(outcome.cost.duration, 1)
        self.assertEqual(
            timed.time.after_remaining,
            deepcopy(
                before_time["pmw_gameplay_time_budget"]["remaining_ticks"]
            ) - 1,
        )
        for actor_id, mana in before_mana.items():
            self.assertEqual(
                _actor_component(fixture["session"], actor_id)["mana"],
                mana,
            )

        records = _records(outcome)
        fired = [row for row in records if row.status == "fired"]
        skipped = [row for row in records if row.status == "skipped"]
        self.assertEqual(
            [(row.owner, row.status) for row in records],
            [
                (PLAYER, "fired"),
                (NPC, "fired"),
                (PLAYER, "skipped"),
            ],
        )
        self.assertEqual(len(fired), 2)
        self.assertEqual(len(skipped), 1)
        self.assertEqual(skipped[0].reason, "duplicate owner+hook source in this root")
        self.assertEqual(
            {row.root_event_id for row in records},
            {outcome.event_result.trace.root_event.id},
        )
        for record in fired:
            self.assertIsInstance(record, HookDispatchRecord)
            self.assertTrue(is_dataclass(record))
            hook_event = _hook_event(record)
            self.assertEqual(hook_event.event.payload["execution_kind"], "hook")
            self.assertEqual(
                hook_event.event.provenance,
                {
                    "kind": "derived",
                    "parent_event": record.parent_event_id,
                },
            )
            self.assertEqual(
                hook_event.event.payload["request_id"][:2],
                "ah",
            )
            self.assertRegex(
                hook_event.event.payload["request_id"],
                r"^[a-z][a-z0-9_]{1,63}$",
            )
            self.assertEqual(
                hook_event.event.payload["hook"]["root_event_id"],
                outcome.event_result.trace.root_event.id,
            )
            self.assertEqual(
                hook_event.event.payload["hook"]["notification_id"],
                record.notification_id,
            )
            self.assertEqual(
                hook_event.event.payload["hook"]["hook_id"],
                record.hook_id,
            )
        first_notification = _notifications(fired[0].outcome)[0]
        _assert_actual_notification(
            self,
            fired[0].outcome,
            first_notification,
            action=fired[0].outcome.definition,
            source=PLAYER,
            target=NPC,
            hp_loss=4.0,
            shield_absorbed=0.0,
        )
        with self.assertRaises(FrozenInstanceError):
            fired[0].status = "changed"

    def test_shield_absorption_is_from_the_primary_damage_commit(self):
        passive = _parse_passive(_shield_passive("absorb_shield", amount=7))
        fixture = _equipped(passive)
        resolve_action(
            fixture["session"],
            fixture["registry"],
            ActionRequest("guard_before_hit", PLAYER, "basic_guard"),
        )
        self.assertEqual(
            _actor_component(fixture["session"], PLAYER)["shield"],
            6.0,
        )
        timed = submit_timed_primary_action(
            fixture["session"],
            fixture["registry"],
            ActionRequest("absorbing_hit", NPC, "basic_attack", PLAYER),
        )
        outcome = timed.action
        self.assertEqual(
            _actor_component(fixture["session"], PLAYER)["hp"],
            46.0,
        )
        self.assertEqual(
            _actor_component(fixture["session"], PLAYER)["shield"],
            7.0,
        )
        notification = _notifications(outcome)[0]
        _assert_actual_notification(
            self,
            outcome,
            notification,
            action=outcome.definition,
            source=NPC,
            target=PLAYER,
            hp_loss=4.0,
            shield_absorbed=6.0,
        )
        fired = [row for row in _records(outcome) if row.status == "fired"]
        self.assertEqual(len(fired), 1)
        self.assertEqual(fired[0].owner, PLAYER)
        hook_outcome = fired[0].outcome
        hook_event = _hook_event(fired[0])
        self.assertEqual(hook_event.event.target, NPC)
        prepared = hook_event.event.payload["effects"]["restore_shield"]
        self.assertEqual(prepared["target_id"], PLAYER)
        self.assertEqual(
            hook_event.event.payload["hook"]["cooldown_until"],
            hook_outcome.event_result.trace.root_event.time,
        )

    def test_ascending_slot_order_and_current_stage_reauthorization(self):
        first = _parse_passive(_self_damage_passive("stage_first", amount=25))
        second = _parse_passive(_shield_passive("stage_second", amount=3))
        fixture = _runtime((first, second), player_hp=20)
        _equip(fixture["runtime"], PLAYER, first, slot=0)
        _equip(fixture["runtime"], PLAYER, second, slot=1)
        outcome = resolve_action(
            fixture["session"],
            fixture["registry"],
            ActionRequest("stage_order", NPC, "basic_attack", PLAYER),
        )
        records = _records(outcome)
        self.assertEqual(
            [row.hook_id for row in records if row.status == "fired"],
            ["passive_stage_first_v1"],
        )
        self.assertTrue(
            any(
                row.hook_id == "passive_stage_second_v1"
                and row.status == "skipped"
                and "defeated" in row.reason
                for row in records
            )
        )

        shield_a = _parse_passive(_shield_passive("slot_a", amount=2))
        shield_b = _parse_passive(_shield_passive("slot_b", amount=3))
        ordered = _runtime((shield_a, shield_b))
        _equip(ordered["runtime"], PLAYER, shield_b, slot=1)
        _equip(ordered["runtime"], PLAYER, shield_a, slot=0)
        ordered_outcome = resolve_action(
            ordered["session"],
            ordered["registry"],
            ActionRequest("slot_order", NPC, "basic_attack", PLAYER),
        )
        self.assertEqual(
            [row.hook_id for row in _records(ordered_outcome) if row.status == "fired"],
            ["passive_slot_a_v1", "passive_slot_b_v1"],
        )

    def test_equipment_authority_and_bare_hook_are_not_automatic(self):
        no_equipment = _runtime()
        no_equipment_outcome = resolve_action(
            no_equipment["session"],
            no_equipment["registry"],
            ActionRequest("no_equipment", NPC, "basic_attack", PLAYER),
        )
        self.assertEqual(_records(no_equipment_outcome), ())

        passive = _parse_passive(_counter_passive("authority_counter"))
        forged_fixture = _equipped(passive)
        forged = deepcopy(
            _actor_component(forged_fixture["session"], PLAYER)["passive_equipped"]
        )
        forged[0]["canonical_hash"] = "0" * 64
        _actor_component(forged_fixture["session"], PLAYER)["passive_equipped"] = forged
        forged_outcome = resolve_action(
            forged_fixture["session"],
            forged_fixture["registry"],
            ActionRequest("forged", NPC, "basic_attack", PLAYER),
        )
        self.assertFalse(
            any(row.status == "fired" for row in _records(forged_outcome))
        )

        wrong_kind_fixture = _equipped(passive)
        wrong = deepcopy(
            _actor_component(wrong_kind_fixture["session"], PLAYER)["passive_equipped"]
        )
        wrong[0]["kind"] = "skill_blueprint"
        _actor_component(wrong_kind_fixture["session"], PLAYER)["passive_equipped"] = wrong
        wrong_outcome = resolve_action(
            wrong_kind_fixture["session"],
            wrong_kind_fixture["registry"],
            ActionRequest("wrong_kind", NPC, "basic_attack", PLAYER),
        )
        self.assertFalse(
            any(row.status == "fired" for row in _records(wrong_outcome))
        )

        unloaded_fixture = _equipped(passive)
        change_loadout(
            unloaded_fixture["session"],
            unloaded_fixture["runtime"].manifest,
            actor_id=PLAYER,
            operation="unload_passive",
            slot=0,
        )
        unloaded_outcome = resolve_action(
            unloaded_fixture["session"],
            unloaded_fixture["registry"],
            ActionRequest("unloaded", NPC, "basic_attack", PLAYER),
        )
        self.assertFalse(
            any(row.status == "fired" for row in _records(unloaded_outcome))
        )

        disabled_fixture = _equipped(passive)
        registry_entity = next(
            entity for entity in disabled_fixture["session"].state.entities.values()
            if REGISTRY_COMPONENT in entity.components
        )
        entry = registry_entity.components[REGISTRY_COMPONENT]["entries"][0]
        entry["enabled"] = False
        disabled_outcome = resolve_action(
            disabled_fixture["session"],
            disabled_fixture["registry"],
            ActionRequest("disabled", NPC, "basic_attack", PLAYER),
        )
        self.assertFalse(
            any(row.status == "fired" for row in _records(disabled_outcome))
        )

        remote = _runtime((passive,), player_area="remote_area")
        _equip(remote["runtime"], PLAYER, passive)
        remote_outcome = resolve_action(
            remote["session"],
            remote["registry"],
            ActionRequest("remote", NPC, "basic_attack", PLAYER),
        )
        self.assertFalse(
            any(row.status == "fired" for row in _records(remote_outcome))
        )

        dead = _runtime((passive,), player_hp=1)
        _equip(dead["runtime"], PLAYER, passive)
        dead_outcome = resolve_action(
            dead["session"],
            dead["registry"],
            ActionRequest("dead", NPC, "basic_attack", PLAYER),
        )
        self.assertFalse(
            any(row.status == "fired" for row in _records(dead_outcome))
        )

        bare = _runtime((passive,))
        _equip(bare["runtime"], PLAYER, passive)
        manual_hook = parse_hook(
            {
                "id": "manual_only_counter",
                "trigger": "damage_resolved",
                "condition": None,
                "effect_ids": ["counter"],
                "action_id": passive.id,
                "max_firings_per_root": 1,
            }
        )
        bare_registry = ActionRegistry(
            (*bare["registry"].actions.values(),),
            bare["registry"].statuses.values(),
            (manual_hook,),
        )
        bare_session = build_runtime(
            deepcopy(bare["session"].state),
            discover_profiles(bare["session"].state),
            build_action_laws(bare_registry),
        )
        bare_outcome = resolve_action(
            bare_session,
            bare_registry,
            ActionRequest("bare_hook", NPC, "basic_attack", PLAYER),
        )
        self.assertFalse(
            any(row.status == "fired" for row in _records(bare_outcome))
        )
        manual, lineage = execute_hook(
            bare_session,
            bare_registry,
            manual_hook,
            HookLineage("manual_root", None, 0, 32),
            actor_id=PLAYER,
            target_actor_id=NPC,
            trigger="damage_resolved",
        )
        self.assertIsNotNone(manual)
        self.assertEqual(lineage.depth, 1)

    def test_false_condition_and_cooldown_are_explainable_skips(self):
        condition = {
            "resource": {
                "subject": "self",
                "key": "hp",
                "comparator": "lt",
                "value": 0,
            }
        }
        passive = _parse_passive(
            _shield_passive("false_condition") | {"condition": condition}
        )
        fixture = _equipped(passive)
        outcome = resolve_action(
            fixture["session"],
            fixture["registry"],
            ActionRequest("false_condition_root", NPC, "basic_attack", PLAYER),
        )
        records = _records(outcome)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].status, "skipped")
        self.assertIn("condition", records[0].reason)
        self.assertIsNone(records[0].outcome)

        cooldown_passive = _parse_passive(
            _shield_passive("cooldown_condition")
        )
        hook = parse_hook(
            {
                "id": "passive_cooldown_condition_v1",
                "trigger": "damage_resolved",
                "condition": None,
                "effect_ids": ["restore_shield"],
                "action_id": cooldown_passive.id,
                "max_firings_per_root": 1,
                "cooldown": 5,
            }
        )
        binding = PassiveSkillBinding(
            cooldown_passive.id,
            cooldown_passive.version,
            cooldown_passive.canonical_hash,
            cooldown_passive.kind,
            cooldown_passive.action.canonical_hash,
            hook,
        )
        trusted_registry = ActionRegistry(
            (*fixture["registry"].actions.values(), cooldown_passive.action),
            fixture["registry"].statuses.values(),
            (hook,),
            _passive_bindings=(binding,),
        )
        # This privileged fixture injects the trusted cooldown HookSpec; the
        # canonical passive Skill JSON still does not expose cooldown.
        cooldown_state = deepcopy(fixture["session"].state)
        cooldown_entity = cooldown_state.entities[PLAYER]
        cooldown_entity.components["pmw_gameplay_hooks"]["cooldowns"][hook.id] = 99.0
        cooldown_entity.components[ACTOR_COMPONENT]["passive_equipped"][0] = (
            skill_ref(cooldown_passive).to_dict()
        )
        registry_entity = next(
            entity for entity in cooldown_state.entities.values()
            if REGISTRY_COMPONENT in entity.components
        )
        registry_entity.components[REGISTRY_COMPONENT]["entries"] = [
            {
                "skill_id": cooldown_passive.id,
                "version": cooldown_passive.version,
                "canonical_hash": cooldown_passive.canonical_hash,
                "kind": cooldown_passive.kind,
                "enabled": True,
            }
        ]
        cooldown_session = build_runtime(
            cooldown_state,
            discover_profiles(cooldown_state),
            build_action_laws(trusted_registry),
        )
        cooldown_outcome = resolve_action(
            cooldown_session,
            trusted_registry,
            ActionRequest("cooldown_root", NPC, "basic_attack", PLAYER),
        )
        cooldown_records = _records(cooldown_outcome)
        self.assertEqual(len(cooldown_records), 1)
        self.assertEqual(cooldown_records[0].status, "skipped")
        self.assertIn("cooldown", cooldown_records[0].reason)
        self.assertIsNone(cooldown_records[0].outcome)

    def test_two_counters_use_shared_owner_hook_dedup(self):
        passive = _parse_passive(_counter_passive("two_counter", amount=4))
        fixture = _equipped(passive)
        outcome = resolve_action(
            fixture["session"],
            fixture["registry"],
            ActionRequest("two_counter_root", NPC, "basic_attack", PLAYER),
        )
        records = _records(outcome)
        self.assertEqual(
            [row.owner for row in records if row.status == "fired"],
            [PLAYER, NPC],
        )
        self.assertEqual(
            sum(row.status == "skipped" for row in records),
            1,
        )
        self.assertEqual(
            records[-1].reason,
            "duplicate owner+hook source in this root",
        )
        new_root = resolve_action(
            fixture["session"],
            fixture["registry"],
            ActionRequest("new_root", NPC, "basic_attack", PLAYER),
        )
        self.assertEqual(
            [row.owner for row in _records(new_root) if row.status == "fired"],
            [PLAYER, NPC],
        )

    def test_low_hard_limits_roll_back_resolve_and_timed_action(self):
        passive = _parse_passive(_counter_passive("limits_counter", amount=4))
        for limits in (
            HookDispatchLimits(max_depth=1),
            HookDispatchLimits(max_firings=1),
            HookDispatchLimits(max_notifications=1),
        ):
            with self.subTest(limits=limits):
                fixture = _equipped(passive)
                before = _snapshot(fixture["session"])
                with self.assertRaises(GameplayContractError):
                    resolve_action(
                        fixture["session"],
                        fixture["registry"],
                        ActionRequest("limit_root", NPC, "basic_attack", PLAYER),
                        dispatch_limits=limits,
                    )
                self.assertEqual(_snapshot(fixture["session"]), before)

        fixture = _equipped(passive)
        before = _snapshot(fixture["session"])
        with self.assertRaises(GameplayContractError):
            submit_timed_primary_action(
                fixture["session"],
                fixture["registry"],
                ActionRequest("timed_limit", NPC, "basic_attack", PLAYER),
                dispatch_limits=HookDispatchLimits(max_notifications=1),
            )
        self.assertEqual(_snapshot(fixture["session"]), before)

    def test_hook_failure_and_late_tick_failure_rollback_whole_transaction(self):
        passive = _parse_passive(_shield_passive("rollback_shield", amount=7))
        fixture = _equipped(passive)
        real_resolve = actions._resolve_action

        def fail_hook(session, registry, request, **kwargs):
            if kwargs.get("execution_kind") == "hook":
                raise RuntimeError("trusted hook child failure")
            return real_resolve(session, registry, request, **kwargs)

        before = _snapshot(fixture["session"])
        # Privileged fault injection proves the staged boundary; it does not
        # replace the independent QA's real child-failure test.
        with patch.object(actions, "_resolve_action", side_effect=fail_hook):
            with self.assertRaisesRegex(RuntimeError, "hook child"):
                submit_timed_primary_action(
                    fixture["session"],
                    fixture["registry"],
                    ActionRequest("hook_failure", NPC, "basic_attack", PLAYER),
                )
        self.assertEqual(_snapshot(fixture["session"]), before)

        late_fixture = _equipped(passive)
        late_before = _snapshot(late_fixture["session"])
        from experiments.generative_mechanics.next_tracks_v06.gameplay_v04 import (
            time_ledger,
        )

        real_tick = time_ledger.advance_world_tick

        def fail_after_tick(session, **kwargs):
            real_tick(session, **kwargs)
            raise RuntimeError("late paid tick failure")

        with patch.object(
            time_ledger,
            "advance_world_tick",
            side_effect=fail_after_tick,
        ):
            with self.assertRaisesRegex(RuntimeError, "late paid tick"):
                submit_timed_primary_action(
                    late_fixture["session"],
                    late_fixture["registry"],
                    ActionRequest("late_tick", NPC, "basic_attack", PLAYER),
                )
        self.assertEqual(_snapshot(late_fixture["session"]), late_before)

    def test_checkpoint_rebuild_regenerates_trusted_binding(self):
        passive = _parse_passive(_shield_passive("checkpoint_shield", amount=5))
        fixture = _equipped(passive)
        with tempfile.TemporaryDirectory(dir=TEMP_ROOT) as directory:
            path = Path(directory) / "c42-checkpoint.json"
            save_registry_checkpoint(path, fixture["runtime"])
            raw = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(
                raw["schema"],
                "pmw-gameplay-checkpoint-v0.4",
            )
            self.assertEqual(
                set(raw),
                {
                    "schema",
                    "world",
                    "blueprints",
                    "runtime_config",
                    "payload_sha256",
                },
            )
            self.assertEqual(
                set(raw["runtime_config"]),
                {
                    "status_slots",
                    "dynamics_slots",
                    "base_registry_hash",
                    "static_laws",
                    "static_laws_hash",
                },
            )
            restored = load_registry_checkpoint(path, fixture["compiled"])
        self.assertEqual(
            restored.session.state.to_dict(),
            fixture["session"].state.to_dict(),
        )
        self.assertEqual(
            static_law_hash(restored.static_laws),
            static_law_hash(fixture["runtime"].static_laws),
        )
        self.assertEqual(
            restored.action_registry.passive_bindings[(passive.id, 1)].hook,
            fixture["registry"].passive_bindings[(passive.id, 1)].hook,
        )
        left = resolve_action(
            fixture["session"],
            fixture["registry"],
            ActionRequest("checkpoint_left", NPC, "basic_attack", PLAYER),
        )
        right = resolve_action(
            restored.session,
            restored.action_registry,
            ActionRequest("checkpoint_right", NPC, "basic_attack", PLAYER),
        )
        self.assertEqual(
            [row.status for row in _records(left)],
            [row.status for row in _records(right)],
        )
        self.assertEqual(
            left.event_result.trace.root_event.type,
            right.event_result.trace.root_event.type,
        )

    def test_spoofed_notification_is_rejected(self):
        passive = _parse_passive(_shield_passive("spoof_shield", amount=7))
        fixture = _equipped(passive)
        outcome = resolve_action(
            fixture["session"],
            fixture["registry"],
            ActionRequest("spoof_root", NPC, "basic_attack", PLAYER),
        )
        notification = _notifications(outcome)[0]
        tampered = deepcopy(notification)
        tampered.payload["resolved_damage"] += 1.0
        with self.assertRaises(GameplayContractError):
            _validate_notification(
                tampered,
                outcome.event_result.trace,
                fixture["registry"],
            )
        typed = Event(
            "typed:spoof",
            NOTIFICATION,
            notification.time,
            notification.source,
            notification.target,
            deepcopy(notification.payload),
            {"kind": "derived", "parent_event": notification.provenance["parent_event"]},
        )
        with self.assertRaises(GameplayContractError):
            _validate_notification(
                typed,
                outcome.event_result.trace,
                fixture["registry"],
            )

    def test_zero_accepted_damage_emits_no_notification(self):
        passive = _parse_passive(_counter_passive("zero_damage_counter", amount=0))
        zero_action = parse_action_definition(
            {
                "id": "zero_damage_probe",
                "version": 1,
                "action_type": "skill",
                "cost": {"duration": 1, "mana": 0.0},
                "scope": {
                    "selectors": ["target_actor"],
                    "relation_types": [],
                },
                "effects": [{
                    "id": "zero_strike",
                    "kind": "damage",
                    "target": {"kind": "target_actor"},
                    "commitment": "required",
                    "amount": 0,
                }],
            },
            basic_registry().statuses,
        )
        fixture = _runtime((passive,), actions=(zero_action,))
        _equip(fixture["runtime"], PLAYER, passive)
        _equip(fixture["runtime"], NPC, passive)
        for actor_id in (PLAYER, NPC):
            _actor_component(fixture["session"], actor_id)["active_equipped"][0] = {
                "id": zero_action.id,
                "version": zero_action.version,
                "canonical_hash": zero_action.canonical_hash,
                "kind": "skill_blueprint",
            }
        registry_entity = next(
            entity for entity in fixture["session"].state.entities.values()
            if REGISTRY_COMPONENT in entity.components
        )
        registry_entity.components[REGISTRY_COMPONENT]["entries"] = [{
            "skill_id": zero_action.id,
            "version": zero_action.version,
            "canonical_hash": zero_action.canonical_hash,
            "kind": "skill_blueprint",
            "enabled": True,
        }]
        outcome = resolve_action(
            fixture["session"],
            fixture["registry"],
            ActionRequest("zero_damage_root", NPC, zero_action.id, PLAYER),
        )

        self.assertEqual(_notifications(outcome), ())
        self.assertEqual(_records(outcome), ())
        self.assertEqual(
            _actor_component(fixture["session"], NPC)["hp"],
            50.0,
        )

        dead = _equipped(passive, player_hp=1)
        dead_outcome = resolve_action(
            dead["session"],
            dead["registry"],
            ActionRequest("overkill_dead_root", NPC, "basic_attack", PLAYER),
        )
        self.assertEqual(_actor_component(dead["session"], PLAYER)["hp"], 0.0)
        self.assertEqual(len(_notifications(dead_outcome)), 1)
        notification = _notifications(dead_outcome)[0]
        self.assertEqual(notification.payload["hp_loss"], 1.0)
        self.assertEqual(notification.payload["resolved_damage"], 1.0)
        self.assertTrue(
            any(row.status == "skipped" and "defeated" in row.reason
                for row in _records(dead_outcome))
        )

    def test_dispatch_uses_recorded_damage_deltas_not_final_state_closure(self):
        passive = _parse_passive(_shield_passive("closure_shield", amount=7))
        fixture = _equipped(passive)
        state_law = {
            "id": "pmw.v04.test.closure.restore_player_hp",
            "mode": "state",
            "priority": 100,
            "bindings": {
                "actor": {
                    "kind": "entity",
                    "requires": [ACTOR_COMPONENT],
                }
            },
            "when": {"all": [
                {"ref": "$actor.id", "eq": PLAYER},
                {"ref": f"$actor.{ACTOR_COMPONENT}.hp", "lt": 50},
            ]},
            "effects": [{
                "op": "set",
                "target": f"$actor.{ACTOR_COMPONENT}.hp",
                "value": 50,
            }],
        }
        with_laws = build_runtime(
            fixture["session"].state,
            fixture["session"].profiles,
            (*fixture["runtime"].static_laws,
             *build_action_laws(fixture["registry"]), state_law),
        )
        outcome = resolve_action(
            with_laws,
            fixture["registry"],
            ActionRequest("closure_root", NPC, "basic_attack", PLAYER),
        )
        self.assertEqual(_actor_component(with_laws, PLAYER)["hp"], 50.0)
        notification = _notifications(outcome)[0]
        self.assertEqual(notification.payload["hp_loss"], 10.0)
        _assert_actual_notification(
            self,
            outcome,
            notification,
            action=outcome.definition,
            source=NPC,
            target=PLAYER,
            hp_loss=10.0,
            shield_absorbed=0.0,
        )
        self.assertEqual(
            [row.status for row in _records(outcome) if row.status == "fired"],
            ["fired"],
        )


if __name__ == "__main__":
    unittest.main()
