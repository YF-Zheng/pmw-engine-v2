from __future__ import annotations

from copy import deepcopy
from dataclasses import fields, is_dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

from pmw import load_world, save_world

from experiments.generative_mechanics.next_tracks_v06.gameplay_v04 import (
    time_ledger,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.action_compiler import (
    build_action_laws,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.actions import (
    ACTION_EVENT,
    ActionRegistry,
    ActionRequest,
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
    HookDispatchLimits,
    HookDispatchRecord,
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
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.observation import (
    ActorObservationBuilder,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.registry import (
    MechanismRegistryRuntime,
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
    TIME_BUDGET_COMPONENT,
    initialize_time_budget,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.worlds import (
    build_gameplay_world,
)


PROJECT_ROOT = Path(__file__).resolve().parents[5]
REVIEW_TMP = PROJECT_ROOT / "docs" / "agent_bootstrap" / "evidence" / "test_tmp"
PLAYER = "passive_player"
NPC = "passive_npc"
AREA = "passive_area"
REMOTE = "passive_remote"
MATERIAL_ID = "passive_review_crystal"
NOTIFICATION = "pmw.v04.hook.damage_resolved"
ACTOR_COMPONENT = "pmw_gameplay_actor"
SHIELD_COMPONENT = "pmw_gameplay_shields"
HOOK_COMPONENT = "pmw_gameplay_hooks"
REGISTRY_COMPONENT = "pmw_gameplay_mechanism_registry"
REQUEST_ID = re.compile(r"auto_hook_[a-z0-9_]{1,55}\Z")
PRODUCT_REQUEST_ID = re.compile(r"^[a-z][a-z0-9_]{1,63}$")


def _limits(**changes):
    values = {
        "max_depth": 16,
        "max_firings": 32,
        "max_notifications": 64,
        **changes,
    }
    return HookDispatchLimits(**values)


def _material():
    return parse_material({
        "id": MATERIAL_ID,
        "tier": "rare",
        "region_rarity": "scarce",
        "traits": [{
            "id": "passive_review_guard",
            "effect_kinds": ["shield", "damage"],
            "selectors": ["self", "target_actor"],
            "budget_points": 12,
        }],
    })


def _passive_raw(
    skill_id,
    *,
    effects,
    condition=None,
    max_firings=1,
    trigger="damage_resolved",
):
    return {
        "protocol": "pmw-gameplay-v0.4",
        "kind": "passive_blueprint",
        "id": skill_id,
        "version": 1,
        "trigger": trigger,
        "condition": condition,
        "duration": None,
        "cost": {"duration": 1, "mana": 0},
        "scope": {
            "selectors": ["self", "target_actor"],
            "relation_types": [],
        },
        "effects": list(effects),
        "budget": {"limit": 8},
        "max_firings_per_root": max_firings,
        "material_ids": [MATERIAL_ID],
    }


def _shield_effect(effect_id="restore_shield", *, amount=7, target="self"):
    return {
        "id": effect_id,
        "kind": "shield",
        "target": {"kind": target},
        "commitment": "required",
        "amount": amount,
    }


def _damage_effect(
    effect_id="counter",
    *,
    amount=3,
    target="target_actor",
):
    return {
        "id": effect_id,
        "kind": "damage",
        "target": {"kind": target},
        "commitment": "required",
        "amount": amount,
    }


def _shield_passive(skill_id="shield_response", *, amount=7, **changes):
    return _passive_raw(
        skill_id,
        effects=(_shield_effect(amount=amount),),
        **changes,
    )


def _counter_passive(skill_id="counter_strike", *, amount=3, **changes):
    return _passive_raw(
        skill_id,
        effects=(_damage_effect(amount=amount),),
        **changes,
    )


def _active_self_damage(skill_id="self_damage_root", *, amount=2):
    raw = {
        "protocol": "pmw-gameplay-v0.4",
        "kind": "skill_blueprint",
        "id": skill_id,
        "version": 1,
        "trigger": "on_use",
        "condition": None,
        "duration": None,
        "cost": {"duration": 1, "mana": 0},
        "scope": {"selectors": ["self"], "relation_types": []},
        "effects": [{
            "id": "self",
            "kind": "damage",
            "target": {"kind": "self"},
            "commitment": "required",
            "amount": amount,
        }],
        "budget": {"limit": 8},
        "max_firings_per_root": 1,
        "material_ids": [MATERIAL_ID],
    }
    return parse_skill_blueprint(
        raw,
        basic_registry().statuses,
        material_authority((_material(),)),
    )


def _pair_passive(
    skill_id="shield_and_counter",
    *,
    shield=7,
    counter=3,
    **changes,
):
    return _passive_raw(
        skill_id,
        effects=(
            _shield_effect("restore_shield", amount=shield),
            _damage_effect("counter", amount=counter),
        ),
        **changes,
    )


def _parse_passive(raw):
    return parse_skill_blueprint(
        raw,
        basic_registry().statuses,
        material_authority((_material(),)),
    )


def _actor(instance_id, *, controller, hp=50, mana=20):
    blueprint = parse_actor_blueprint({
        "protocol": "pmw-gameplay-v0.4",
        "kind": "actor_blueprint",
        "id": "passive_review_actor",
        "hp": {"max": 50, "initial": hp},
        "mana": {"max": 30, "initial": mana, "dynamics": None},
        "attributes": {
            "power": 4,
            "control": 4,
            "resilience": 4,
            "agility": 4,
        },
        "traits": [],
    })
    return instantiate_actor(blueprint, instance_id, controller=controller)


def _area(instance_id=AREA):
    blueprint = parse_area_blueprint({
        "protocol": "pmw-gameplay-v0.4",
        "kind": "area_blueprint",
        "id": "passive_review_area",
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


def _runtime(
    skills=(),
    *,
    player_area=AREA,
    npc_area=AREA,
    player_hp=50,
    npc_hp=50,
):
    base = ActionRegistry(
        basic_registry().actions.values(),
        basic_registry().statuses.values(),
    )
    content = make_content(
        base,
        skills=tuple(skills),
        material_ids=(MATERIAL_ID,),
    )
    areas = {
        area_id: _area(area_id)
        for area_id in {AREA, REMOTE, player_area, npc_area}
    }
    entities = {
        PLAYER: _actor(PLAYER, controller="human", hp=player_hp),
        NPC: _actor(NPC, controller="ai", hp=npc_hp),
        **areas,
    }
    world = build_gameplay_world(
        "passive_review_world",
        areas=areas.values(),
        actors=(entities[PLAYER], entities[NPC]),
        placements=((PLAYER, player_area), (NPC, npc_area)),
    )
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


def _equipped_pair(skill, *, slot=0, **runtime_changes):
    fixture = _runtime((skill,), **runtime_changes)
    _equip(fixture["runtime"], PLAYER, skill, slot)
    _equip(fixture["runtime"], NPC, skill, slot)
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


def _budget(session):
    return session.state.entities["pmw:v04:clock"].components[
        TIME_BUDGET_COMPONENT
    ]


def _records(outcome):
    records = getattr(outcome, "auto_hooks", None)
    if records is None:
        raise AssertionError("ActionOutcome.auto_hooks is missing")
    return tuple(records)


def _fired_records(outcome):
    return tuple(row for row in _records(outcome) if row.status == "fired")


def _outcome_view(outcome):
    """Enumerate separate, unmodified Engine calls for QA inspection only."""
    calls = [outcome]
    index = 0
    while index < len(calls):
        for record in _records(calls[index]):
            child = record.outcome
            if child is not None and not any(child is item for item in calls):
                calls.append(child)
        index += 1
    return tuple(calls)


def _trace_events(outcome):
    return tuple(
        row
        for call in _outcome_view(outcome)
        for row in call.event_result.trace.events
    )


def _notifications(outcome):
    return tuple(
        row.event for row in _trace_events(outcome)
        if row.event.type == NOTIFICATION
    )


def _record_is_immutable(test, record):
    test.assertTrue(is_dataclass(record))
    test.assertIsInstance(record, HookDispatchRecord)
    test.assertIn("outcome", {field.name for field in fields(record)})
    with test.assertRaises((AttributeError, TypeError)):
        record.status = "mutated"


def _notification_raw(outcome, notification):
    calls = [
        call for call in _outcome_view(outcome)
        if any(row.event.id == notification.id
               for row in call.event_result.trace.events)
    ]
    if len(calls) != 1:
        raise AssertionError("notification Engine-call trace is ambiguous")
    call = calls[0]
    trace = call.event_result.trace
    rows = [row for row in trace.events if row.event.id == notification.id]
    if len(rows) != 1:
        raise AssertionError("notification trace row is missing or ambiguous")
    parent_id = notification.provenance.get("parent_event")
    parents = [row for row in trace.events if row.event.id == parent_id]
    if len(parents) != 1:
        raise AssertionError("notification Action parent is missing or ambiguous")
    proposals = [
        row for row in trace.proposals
        if row.emitted_event_id == notification.id
    ]
    if len(proposals) != 1:
        raise AssertionError("notification accepted emit is missing or ambiguous")
    return call, parents[0], proposals[0]


def _actual_deltas(outcome, notification):
    _, parent, _ = _notification_raw(outcome, notification)
    victim = notification.payload["target_actor_id"]
    decreases = {}
    law_ids = set()
    for commit in parent.commits:
        for delta in commit.state_deltas:
            if delta.address.object_id != victim:
                continue
            path = tuple(delta.address.path)
            if path not in {
                (ACTOR_COMPONENT, "hp"),
                (ACTOR_COMPONENT, "shield"),
            }:
                continue
            decrease = float(delta.old_value) - float(delta.new_value)
            decreases[path] = decreases.get(path, 0.0) + max(0.0, decrease)
            law_ids.update(delta.law_ids)
    hp_loss = decreases.get((ACTOR_COMPONENT, "hp"), 0.0)
    shield_absorbed = decreases.get(
        (ACTOR_COMPONENT, "shield"), 0.0
    )
    if hp_loss + shield_absorbed <= 0:
        raise AssertionError("notification has no positive actual scalar loss")
    return hp_loss, shield_absorbed, law_ids, parent


def _assert_actual_damage(
    test,
    outcome,
    notification,
    *,
    action,
    attacker,
    victim,
    effect_id,
):
    payload = notification.payload
    call, parent, proposal = _notification_raw(outcome, notification)
    effect = next(item for item in action.effects if item.id == effect_id)
    prepared = parent.event.payload["effects"][effect_id]
    test.assertEqual(notification.type, NOTIFICATION)
    test.assertEqual(call.definition.id, action.id)
    test.assertEqual(notification.source, attacker)
    test.assertEqual(notification.target, victim)
    test.assertEqual(notification.time, parent.event.time)
    test.assertEqual(parent.event.type, ACTION_EVENT)
    test.assertEqual(parent.event.source, attacker)
    test.assertEqual(parent.event.payload["action_id"], action.id)
    test.assertEqual(
        parent.event.payload["action_hash"], action.canonical_hash
    )
    test.assertEqual(prepared["kind"], "damage")
    test.assertEqual(prepared["status"], "applied")
    test.assertEqual(prepared["target_id"], victim)
    if effect.target.kind == "self":
        test.assertEqual(victim, parent.event.source)
    else:
        test.assertEqual(effect.target.kind, "target_actor")
        test.assertEqual(victim, prepared["target_id"])
    test.assertEqual(payload["protocol"], "pmw-gameplay-v0.4")
    test.assertEqual(payload["action_id"], action.id)
    test.assertEqual(payload["action_hash"], action.canonical_hash)
    test.assertEqual(payload["effect_id"], effect_id)
    test.assertEqual(payload["actor_id"], attacker)
    test.assertEqual(payload["target_actor_id"], victim)
    test.assertEqual(set(payload), {
        "protocol", "action_id", "action_hash", "effect_id",
        "actor_id", "target_actor_id", "resolved_damage",
        "hp_loss", "shield_absorbed",
    })
    token = f"{action.id}.v{action.version}.{action.canonical_hash[:12]}"
    damage_law = f"pmw.v04.action.{token}.effect.{effect_id}"
    test.assertEqual(proposal.status, "accepted")
    test.assertEqual(proposal.op, "emit_event")
    test.assertEqual(proposal.law_id, damage_law)
    test.assertEqual(proposal.cause_event_id, parent.event.id)
    test.assertTrue(any(
        proposal.proposal_id in commit.accepted_proposal_ids
        for commit in parent.commits
    ))
    hp_loss, shield_absorbed, law_ids, _ = _actual_deltas(
        outcome, notification
    )
    test.assertIn(damage_law, law_ids)
    test.assertAlmostEqual(float(payload["hp_loss"]), hp_loss)
    test.assertAlmostEqual(
        float(payload["shield_absorbed"]), shield_absorbed
    )
    test.assertAlmostEqual(
        float(payload["resolved_damage"]),
        hp_loss + shield_absorbed,
    )
    test.assertGreater(float(payload["resolved_damage"]), 0)
    return call, parent, proposal


def _assert_hook_provenance(test, record, skill):
    hook_outcome = record.outcome
    test.assertIsNotNone(hook_outcome)
    test.assertNotEqual(
        skill.canonical_hash,
        hook_outcome.definition.canonical_hash,
    )
    root_event = hook_outcome.event_result.trace.root_event
    test.assertEqual(root_event.type, ACTION_EVENT)
    test.assertEqual(
        root_event.provenance["parent_event"], record.notification_id
    )
    test.assertEqual(root_event.payload["execution_kind"], "hook")
    test.assertEqual(
        root_event.payload["hook"]["root_event_id"],
        record.root_event_id,
    )
    test.assertEqual(
        root_event.payload["hook"]["notification_id"],
        record.notification_id,
    )
    test.assertEqual(root_event.payload["hook"]["hook_id"], record.hook_id)
    test.assertEqual(root_event.payload["hook"]["depth"], record.depth)
    test.assertEqual(
        root_event.payload["request_id"],
        hook_outcome.request.request_id,
    )
    test.assertRegex(
        hook_outcome.request.request_id,
        PRODUCT_REQUEST_ID,
    )
    test.assertEqual(hook_outcome.cost.mana, 0)
    test.assertEqual(hook_outcome.cost.duration, 1)
    return hook_outcome, root_event


def _manual_lineage(root="manual_review_root"):
    from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.hooks import (
        HookLineage,
    )
    return HookLineage(root, None, 0, 32)


class DispatchSurfaceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        REVIEW_TMP.mkdir(parents=True, exist_ok=True)

    def test_limits_are_canonical_trusted_and_tighten_only(self):
        defaults = HookDispatchLimits()
        self.assertEqual(
            (
                defaults.max_depth,
                defaults.max_firings,
                defaults.max_notifications,
            ),
            (16, 32, 64),
        )
        for values in (
            {"max_depth": 0},
            {"max_depth": True},
            {"max_depth": 1.0},
            {"max_firings": 0},
            {"max_notifications": 0},
            {"max_depth": 17},
            {"max_firings": 33},
            {"max_notifications": 65},
        ):
            with self.subTest(values=values):
                with self.assertRaises(GameplayContractError):
                    HookDispatchLimits(**values)

        fixture = _runtime()
        request = ActionRequest("plain_attack", PLAYER, "basic_attack", NPC)
        outcome = resolve_action(
            fixture["session"], fixture["registry"], request
        )
        self.assertEqual(outcome.auto_hooks, ())
        with self.assertRaises(TypeError):
            resolve_action(
                fixture["session"],
                fixture["registry"],
                ActionRequest(
                    "positional_limits",
                    PLAYER,
                    "basic_attack",
                    NPC,
                ),
                _limits(max_depth=1),
            )
        with self.assertRaises(TypeError):
            submit_timed_primary_action(
                fixture["session"],
                fixture["registry"],
                ActionRequest(
                    "positional_timed_limits",
                    PLAYER,
                    "basic_attack",
                    NPC,
                ),
                _limits(max_depth=1),
            )

    def test_candidate_registry_json_cannot_author_passive_binding(self):
        with self.assertRaises(GameplayContractError):
            ActionRegistry.parse({
                "protocol": "pmw-gameplay-v0.4",
                "statuses": [],
                "actions": [],
                "passive_bindings": [],
            })
        parsed = ActionRegistry.parse({
            "protocol": "pmw-gameplay-v0.4",
            "statuses": [],
            "actions": [],
        })
        self.assertEqual(parsed.passive_bindings, {})


class PassiveDispatchContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        REVIEW_TMP.mkdir(parents=True, exist_ok=True)

    def test_real_equipment_player_and_npc_paid_shield_dispatch(self):
        passive = _parse_passive(_shield_passive(amount=7))
        for attacker, victim in ((NPC, PLAYER), (PLAYER, NPC)):
            with self.subTest(attacker=attacker, victim=victim):
                fixture = _equipped_pair(passive)
                before_attacker = deepcopy(
                    _actor_component(fixture["session"], attacker)
                )
                before_victim = deepcopy(
                    _actor_component(fixture["session"], victim)
                )
                before_tick = fixture["session"].state.tick
                before_sim_time = fixture["session"].state.sim_time
                before_budget = deepcopy(_budget(fixture["session"]))
                outcome = submit_timed_primary_action(
                    fixture["session"],
                    fixture["registry"],
                    ActionRequest(
                        f"paid_{attacker}_{victim}",
                        attacker,
                        "basic_attack",
                        victim,
                    ),
                )
                after_attacker = _actor_component(fixture["session"], attacker)
                after_victim = _actor_component(fixture["session"], victim)
                fired = _fired_records(outcome.action)
                self.assertEqual(len(fired), 1)
                _record_is_immutable(self, fired[0])
                self.assertEqual(fired[0].owner, victim)
                self.assertEqual(fired[0].depth, 1)
                self.assertEqual(
                    fired[0].notification_id,
                    fired[0].parent_event_id,
                )
                self.assertEqual(
                    fired[0].root_event_id,
                    outcome.action.event_result.trace.root_event.id,
                )
                hook_outcome, hook_event = _assert_hook_provenance(
                    self, fired[0], passive
                )
                self.assertEqual(hook_outcome.request.actor_id, victim)
                self.assertEqual(
                    hook_outcome.request.target_actor_id, attacker
                )
                self.assertEqual(
                    after_victim["mana"], before_victim["mana"]
                )
                self.assertEqual(
                    after_attacker["mana"], before_attacker["mana"]
                )
                self.assertEqual(
                    before_victim["hp"] - after_victim["hp"], 10
                )
                self.assertEqual(after_victim["shield"], 7)
                notifications = _notifications(outcome.action)
                self.assertEqual(len(notifications), 1)
                notification = notifications[0]
                self.assertEqual(notification.target, victim)
                _assert_actual_damage(
                    self,
                    outcome.action,
                    notification,
                    action=fixture["registry"].actions["basic_attack"],
                    attacker=attacker,
                    victim=victim,
                    effect_id="strike",
                )
                self.assertNotEqual(
                    passive.canonical_hash,
                    hook_outcome.definition.canonical_hash,
                )
                self.assertFalse(any(
                    row.event.type == ACTION_EVENT
                    and row.event.payload.get("execution_kind") == "hook"
                    for row in outcome.action.event_result.trace.events
                ))
                self.assertEqual(
                    outcome.time.event_result.trace.root_event.type,
                    "pmw.v04.time.spend",
                )
                self.assertEqual(
                    outcome.time.ticks[0].event_result.trace.root_event.type,
                    "pmw.v04.world_tick",
                )
                self.assertEqual(
                    outcome.action.event_result.trace.root_event.time,
                    outcome.time.event_result.trace.root_event.time,
                )
                self.assertEqual(
                    outcome.time.event_result.trace.root_event.time,
                    before_sim_time,
                )
                self.assertEqual(
                    outcome.time.ticks[0].step,
                    before_tick + 1,
                )
                self.assertEqual(
                    fixture["session"].state.sim_time,
                    before_sim_time + 1,
                )
                self.assertEqual(
                    _budget(fixture["session"])["spent_ticks"],
                    before_budget["spent_ticks"] + 1,
                )
                self.assertEqual(
                    _budget(fixture["session"])["remaining_ticks"],
                    before_budget["remaining_ticks"] - 1,
                )
                self.assertIsNone(hook_event.provenance.get("merged_from"))

    def test_auto_hook_request_id_contract(self):
        passive = _parse_passive(_shield_passive("request_identity"))
        fixture = _equipped_pair(passive)
        outcome = resolve_action(
            fixture["session"],
            fixture["registry"],
            ActionRequest("request_identity_hit", NPC, "basic_attack", PLAYER),
        )
        fired = _fired_records(outcome)
        self.assertEqual(len(fired), 1)
        request_id = fired[0].outcome.request.request_id
        self.assertRegex(request_id, REQUEST_ID)
        self.assertNotEqual(request_id, "ah" + hashlib.sha256(
            b"passive-review"
        ).hexdigest())

    def test_same_parsed_skill_other_owner_and_root_dedup(self):
        passive = _parse_passive(_counter_passive(amount=3))
        fixture = _equipped_pair(passive)
        outcome = resolve_action(
            fixture["session"],
            fixture["registry"],
            ActionRequest("same_skill_attack", NPC, "basic_attack", PLAYER),
        )
        records = _records(outcome)
        self.assertEqual(
            [(row.owner, row.status, row.depth) for row in records],
            [
                (PLAYER, "fired", 1),
                (NPC, "fired", 2),
                (PLAYER, "skipped", 3),
            ],
        )
        first, counterpart, duplicate = records
        hook_outcome, _ = _assert_hook_provenance(self, first, passive)
        child_notifications = [
            row.event for row in hook_outcome.event_result.trace.events
            if row.event.type == NOTIFICATION
        ]
        self.assertEqual(len(child_notifications), 1)
        child = child_notifications[0]
        self.assertEqual(child.source, PLAYER)
        self.assertEqual(child.target, NPC)
        self.assertEqual(
            child.payload["action_hash"], passive.action.canonical_hash
        )
        counterpart_outcome, _ = _assert_hook_provenance(
            self,
            counterpart,
            passive,
        )
        self.assertEqual(counterpart.notification_id, child.id)
        sibling_notifications = [
            row for row in counterpart_outcome.event_result.trace.events
            if row.event.type == NOTIFICATION
        ]
        self.assertEqual(len(sibling_notifications), 1)
        self.assertEqual(
            sibling_notifications[0].event.target,
            PLAYER,
        )
        self.assertEqual(duplicate.notification_id, sibling_notifications[0].event.id)
        self.assertIn("duplicate", duplicate.reason)
        self.assertEqual(
            _actor_component(fixture["session"], NPC)["hp"], 47
        )
        self.assertEqual(
            _actor_component(fixture["session"], PLAYER)["hp"], 37
        )
        notifications = _notifications(outcome)
        self.assertEqual(len(notifications), 3)
        for notification in notifications:
            action = (
                fixture["registry"].actions["basic_attack"]
                if notification.payload["action_id"] == "basic_attack"
                else passive.action
            )
            _assert_actual_damage(
                self,
                outcome,
                notification,
                action=action,
                attacker=notification.source,
                victim=notification.target,
                effect_id=notification.payload["effect_id"],
            )
        root_id = outcome.event_result.trace.root_event.id
        self.assertTrue(all(row.root_event_id == root_id for row in records))
        self.assertFalse(any(
            row.event.type == ACTION_EVENT
            and row.event.payload.get("execution_kind") == "hook"
            for row in outcome.event_result.trace.events
        ))

    def test_new_managed_root_resets_dispatch_dedup_and_budget(self):
        passive = _parse_passive(_counter_passive("root_reset", amount=3))
        fixture = _runtime((passive,))
        _equip(fixture["runtime"], PLAYER, passive)
        first = resolve_action(
            fixture["session"],
            fixture["registry"],
            ActionRequest("root_reset_first", NPC, "basic_attack", PLAYER),
        )
        second = resolve_action(
            fixture["session"],
            fixture["registry"],
            ActionRequest("root_reset_second", NPC, "basic_attack", PLAYER),
        )
        for outcome in (first, second):
            fired = _fired_records(outcome)
            self.assertEqual(len(fired), 1)
            self.assertEqual(fired[0].owner, PLAYER)
            self.assertEqual(fired[0].depth, 1)
        self.assertNotEqual(
            first.event_result.trace.root_event.id,
            second.event_result.trace.root_event.id,
        )
        self.assertEqual(
            _actor_component(fixture["session"], NPC)["hp"], 44
        )

    def test_two_siblings_use_current_staged_state(self):
        first = _parse_passive(_shield_passive("first_sibling", amount=5))
        second = _parse_passive(_shield_passive(
            "second_sibling",
            amount=7,
            condition={
                "resource": {
                    "subject": "self",
                    "key": "shield",
                    "comparator": "gte",
                    "value": 4,
                },
            },
        ))
        fixture = _runtime((first, second))
        _equip(fixture["runtime"], PLAYER, first, slot=0)
        _equip(fixture["runtime"], PLAYER, second, slot=1)
        _equip(fixture["runtime"], NPC, first, slot=0)
        outcome = resolve_action(
            fixture["session"],
            fixture["registry"],
            ActionRequest("sibling_attack", NPC, "basic_attack", PLAYER),
        )
        self.assertEqual(
            [(row.hook_id, row.status) for row in _records(outcome)],
            [
                (f"passive_{first.id}_v1", "fired"),
                (f"passive_{second.id}_v1", "fired"),
            ],
        )
        player = _actor_component(fixture["session"], PLAYER)
        self.assertEqual(player["hp"], 40)
        self.assertEqual(player["shield"], 12)
        self.assertEqual(
            _actor_component(fixture["session"], NPC)["shield"], 0
        )
        for record in _records(outcome):
            _assert_hook_provenance(self, record, (
                first if record.hook_id == f"passive_{first.id}_v1"
                else second
            ))

    def test_shield_absorption_quantitative(self):
        fixture = _equipped_pair(
            _parse_passive(_shield_passive("shield_math", amount=7))
        )
        resolve_action(
            fixture["session"],
            fixture["registry"],
            ActionRequest("guard_first", PLAYER, "basic_guard"),
        )
        start = deepcopy(_actor_component(fixture["session"], PLAYER))
        self.assertEqual(start["shield"], 6)
        outcome = resolve_action(
            fixture["session"],
            fixture["registry"],
            ActionRequest("absorb_hit", NPC, "basic_attack", PLAYER),
        )
        notification = _notifications(outcome)[0]
        hp_loss = float(notification.payload["hp_loss"])
        absorbed = float(notification.payload["shield_absorbed"])
        self.assertEqual((hp_loss, absorbed), (4, 6))
        self.assertEqual(
            _actor_component(fixture["session"], PLAYER)["hp"], 46
        )
        self.assertEqual(
            _actor_component(fixture["session"], PLAYER)["shield"], 7
        )

    def test_self_target_damage_parent_target_none(self):
        active = _active_self_damage(amount=2)
        passive = _parse_passive(_shield_passive("self_response", amount=7))
        fixture = _runtime((active, passive))
        change_loadout(
            fixture["session"],
            fixture["runtime"].manifest,
            actor_id=NPC,
            operation="equip_active",
            skill=skill_ref(active),
            slot=0,
        )
        _equip(fixture["runtime"], NPC, passive)
        outcome = resolve_action(
            fixture["session"],
            fixture["registry"],
            ActionRequest("self_damage_root", NPC, active.id, None),
        )
        notifications = _notifications(outcome)
        self.assertEqual(len(notifications), 1)
        primary_notification = notifications[0]
        call, parent, _ = _notification_raw(outcome, primary_notification)
        self.assertIsNone(parent.event.target)
        self.assertEqual(call.definition.id, active.id)
        _assert_actual_damage(
            self,
            outcome,
            primary_notification,
            action=active.action,
            attacker=NPC,
            victim=NPC,
            effect_id="self",
        )
        fired = _fired_records(outcome)
        self.assertEqual(len(fired), 1)
        _assert_hook_provenance(self, fired[0], passive)
        self.assertEqual(
            _actor_component(fixture["session"], NPC)["hp"], 48
        )
        self.assertEqual(
            _actor_component(fixture["session"], NPC)["shield"], 7
        )

    def test_false_condition_and_real_managed_cooldown_skip(self):
        passive = _parse_passive(_shield_passive(
            "false_condition",
            condition={
                "resource": {
                    "subject": "self",
                    "key": "hp",
                    "comparator": "lt",
                    "value": 0,
                },
            },
        ))
        fixture = _equipped_pair(passive)
        outcome = resolve_action(
            fixture["session"],
            fixture["registry"],
            ActionRequest("false_condition_hit", NPC, "basic_attack", PLAYER),
        )
        self.assertEqual(len(_records(outcome)), 1)
        self.assertEqual(_records(outcome)[0].status, "skipped")
        self.assertIn("condition", _records(outcome)[0].reason)
        self.assertIsNone(_records(outcome)[0].outcome)
        self.assertEqual(
            _actor_component(fixture["session"], PLAYER)["shield"], 0
        )

        cooldown = _parse_passive(_shield_passive("managed_cooldown"))
        cool = _equipped_pair(cooldown)
        hook = next(
            item for item in cool["registry"].hooks.values()
            if item.action_id == cooldown.id
        )
        # Privileged support fixture only: passive Skill JSON has no cooldown
        # field in this slice; this does not claim that the schema was added.
        actor = cool["session"].state.entities[PLAYER]
        actor.components.setdefault(HOOK_COMPONENT, {}).setdefault(
            "cooldowns", {}
        )[hook.id] = 99.0
        outcome = resolve_action(
            cool["session"],
            cool["registry"],
            ActionRequest("cooldown_hit", NPC, "basic_attack", PLAYER),
        )
        record = _records(outcome)[0]
        self.assertEqual(record.status, "skipped")
        self.assertIn("cooldown", record.reason)
        self.assertEqual(
            _actor_component(cool["session"], PLAYER)["shield"], 0
        )

    def test_manual_execute_hook_compatibility_and_bare_hook(self):
        passive = _parse_passive(_shield_passive("manual_bare", amount=2))
        bare = _runtime()
        hook = parse_hook({
            "id": "bare_custom_hook",
            "trigger": "damage_resolved",
            "condition": None,
            "effect_ids": [passive.effects[0].id],
            "action_id": passive.id,
            "max_firings_per_root": 1,
        })
        bare_registry = ActionRegistry(
            (*bare["registry"].actions.values(), passive.action),
            bare["registry"].statuses.values(),
            (hook,),
        )
        bare_session = build_runtime(
            deepcopy(bare["session"].state),
            discover_profiles(bare["session"].state),
            build_action_laws(bare_registry),
        )
        outcome = resolve_action(
            bare_session,
            bare_registry,
            ActionRequest("bare_attack", NPC, "basic_attack", PLAYER),
        )
        self.assertEqual(_records(outcome), ())
        self.assertEqual(len(_notifications(outcome)), 1)
        self.assertEqual(
            _actor_component(bare_session, PLAYER)["shield"], 0
        )
        result, lineage = execute_hook(
            bare_session,
            bare_registry,
            hook,
            _manual_lineage("bare_manual"),
            actor_id=PLAYER,
            target_actor_id=NPC,
            trigger="damage_resolved",
        )
        self.assertIsNotNone(result)
        self.assertEqual(lineage.depth, 1)
        self.assertEqual(result.cost.mana, 0)
        self.assertEqual(
            result.event_result.trace.root_event.provenance["kind"],
            "external",
        )
        self.assertEqual(
            _actor_component(bare_session, PLAYER)["shield"], 2
        )
        auto = resolve_action(
            bare_session,
            bare_registry,
            ActionRequest("bare_again", NPC, "basic_attack", PLAYER),
        )
        self.assertEqual(_records(auto), ())

    def test_authority_rejections_do_not_dispatch(self):
        passive = _parse_passive(_shield_passive("authority_probe", amount=4))
        fixture = _equipped_pair(passive)
        actor = _actor_component(fixture["session"], PLAYER)
        actor["passive_equipped"][0] = None
        outcome = resolve_action(
            fixture["session"],
            fixture["registry"],
            ActionRequest("unequipped", NPC, "basic_attack", PLAYER),
        )
        self.assertEqual(_records(outcome), ())

        actor["passive_equipped"][0] = skill_ref(passive).to_dict()
        actor["passive_equipped"][0] = None
        outcome = resolve_action(
            fixture["session"],
            fixture["registry"],
            ActionRequest("unloaded", NPC, "basic_attack", PLAYER),
        )
        self.assertEqual(_records(outcome), ())

        actor["passive_equipped"][0] = skill_ref(passive).to_dict()
        actor["active_stowed"][0] = skill_ref(passive).to_dict()
        actor["passive_equipped"][0] = None
        outcome = resolve_action(
            fixture["session"],
            fixture["registry"],
            ActionRequest("stowed", NPC, "basic_attack", PLAYER),
        )
        self.assertEqual(_fired_records(outcome), ())
        actor["active_stowed"][0] = None

        forged = _runtime((passive,))
        _equip(forged["runtime"], PLAYER, passive)
        ref = skill_ref(passive).to_dict()
        ref["canonical_hash"] = "f" * 64
        _actor_component(forged["session"], PLAYER)["passive_equipped"][0] = ref
        outcome = resolve_action(
            forged["session"],
            forged["registry"],
            ActionRequest("forged", NPC, "basic_attack", PLAYER),
        )
        self.assertEqual(_fired_records(outcome), ())
        self.assertIn("invalid", " ".join(row.reason for row in _records(outcome)))

        wrong_kind = _runtime((passive,))
        _equip(wrong_kind["runtime"], PLAYER, passive)
        ref = skill_ref(passive).to_dict()
        ref["kind"] = "skill_blueprint"
        _actor_component(wrong_kind["session"], PLAYER)["passive_equipped"][0] = ref
        outcome = resolve_action(
            wrong_kind["session"],
            wrong_kind["registry"],
            ActionRequest("wrong_kind", NPC, "basic_attack", PLAYER),
        )
        self.assertEqual(_fired_records(outcome), ())

        disabled = _runtime((passive,))
        _equip(disabled["runtime"], PLAYER, passive)
        registry = next(
            entity for entity in disabled["session"].state.entities.values()
            if REGISTRY_COMPONENT in entity.components
        )
        for entry in registry.components[REGISTRY_COMPONENT]["entries"]:
            if entry["skill_id"] == passive.id:
                entry["enabled"] = False
        outcome = resolve_action(
            disabled["session"],
            disabled["registry"],
            ActionRequest("disabled", NPC, "basic_attack", PLAYER),
        )
        self.assertEqual(_fired_records(outcome), ())

        remote = _equipped_pair(passive, player_area=REMOTE, npc_area=AREA)
        outcome = resolve_action(
            remote["session"],
            remote["registry"],
            ActionRequest("remote", NPC, "basic_attack", PLAYER),
        )
        self.assertEqual(_fired_records(outcome), ())
        self.assertTrue(all(
            row.status == "skipped" and "colocated" in row.reason
            for row in _records(outcome)
        ))
        self.assertEqual(
            _actor_component(remote["session"], PLAYER)["hp"], 40
        )

        dead = _equipped_pair(passive, player_hp=1, npc_hp=50)
        outcome = resolve_action(
            dead["session"],
            dead["registry"],
            ActionRequest("dead", NPC, "basic_attack", PLAYER),
        )
        self.assertEqual(
            _actor_component(dead["session"], PLAYER)["hp"], 0
        )
        self.assertEqual(_fired_records(outcome), ())
        self.assertIn("defeated", " ".join(row.reason for row in _records(outcome)))

        wrong_owner = _runtime((passive,))
        _equip(wrong_owner["runtime"], NPC, passive)
        outcome = resolve_action(
            wrong_owner["session"],
            wrong_owner["registry"],
            ActionRequest("other_owner", NPC, "basic_attack", PLAYER),
        )
        self.assertEqual(_fired_records(outcome), ())

    def test_hard_limits_and_actual_exception_rollback_all_state(self):
        passive = _parse_passive(_counter_passive("limit_counter", amount=1))
        for name, limits in (
            ("depth", _limits(max_depth=1)),
            ("firing", _limits(max_firings=1)),
            ("notifications", _limits(max_notifications=1)),
        ):
            fixture = _equipped_pair(passive)
            before = _snapshot(fixture["session"])
            with self.subTest(limit=name):
                with self.assertRaises(GameplayContractError):
                    resolve_action(
                        fixture["session"],
                        fixture["registry"],
                        ActionRequest(
                            f"limit_{name}", NPC, "basic_attack", PLAYER
                        ),
                        dispatch_limits=limits,
                    )
                self.assertEqual(_snapshot(fixture["session"]), before)

        # Privileged fault injection into a compiled Action Law proves the
        # managed transaction boundary; this is not a normal content fixture.
        exploding = _parse_passive(_counter_passive("explode", amount=1))
        broken = _equipped_pair(exploding)
        exploding_law = next(
            law for law in build_action_laws(broken["registry"])
            if law["id"].startswith(
                "pmw.v04.action."
                + f"{exploding.id}.v1."
            )
            and law["id"].endswith(".effect.counter")
        )
        exploding_law = deepcopy(exploding_law)
        exploding_law["effects"].append({
            "op": "set",
            "target": f"$target.{ACTOR_COMPONENT}.hp",
            "value": {"div": [1, 0]},
        })
        broken_session = build_runtime(
            deepcopy(broken["session"].state),
            discover_profiles(broken["session"].state),
            (*broken["runtime"].static_laws, *(
                exploding_law if law["id"] == exploding_law["id"] else law
                for law in build_action_laws(broken["registry"])
            )),
        )
        before = _snapshot(broken_session)
        with self.assertRaises(ZeroDivisionError):
            resolve_action(
                broken_session,
                broken["registry"],
                ActionRequest("hook_throw", NPC, "basic_attack", PLAYER),
            )
        self.assertEqual(_snapshot(broken_session), before)

    def test_zero_accepted_damage_does_not_notify_or_dispatch(self):
        passive = _parse_passive(_shield_passive("zero_damage", amount=7))
        fixture = _equipped_pair(passive, player_hp=0)
        outcome = resolve_action(
            fixture["session"],
            fixture["registry"],
            ActionRequest("zero_hit", NPC, "basic_attack", PLAYER),
        )
        self.assertEqual(_records(outcome), ())
        self.assertEqual(_notifications(outcome), ())
        self.assertEqual(
            _actor_component(fixture["session"], PLAYER)["hp"], 0
        )
        self.assertEqual(
            _actor_component(fixture["session"], PLAYER)["shield"], 0
        )

    def test_privileged_spoof_notification_is_rejected_atomically(self):
        passive = _parse_passive(_shield_passive("spoof_guard", amount=7))
        fixture = _equipped_pair(passive)
        session = fixture["session"]
        spoof_law = {
            "id": "pmw.v04.review.zz_spoof_damage_notification",
            "mode": "event",
            "priority": 100,
            "bindings": {
                "actor": {
                    "kind": "entity",
                    "requires": [ACTOR_COMPONENT],
                },
            },
            "when": {"all": [
                {"event.type": {"eq": ACTION_EVENT}},
                {"ref": "$event.payload.action_id", "eq": "basic_attack"},
                {"ref": "$actor.id", "eq": "$event.payload.target_actor_id"},
            ]},
            "effects": [{
                "op": "emit_event",
                "event": {
                    "type": NOTIFICATION,
                    "time": "$event.time",
                    "source": "$event.source",
                    "target": "$actor.id",
                    "payload": {
                        "protocol": "pmw-gameplay-v0.4",
                        "action_id": "basic_attack",
                        "action_hash": fixture["registry"].actions[
                            "basic_attack"
                        ].canonical_hash,
                        "effect_id": "strike",
                        "actor_id": "$event.source",
                        "target_actor_id": "$actor.id",
                        "resolved_damage": 10,
                        "hp_loss": 10,
                        "shield_absorbed": 0,
                    },
                },
            }],
        }
        support_state = deepcopy(session.state)
        session.runtime = build_runtime(
            support_state,
            discover_profiles(support_state),
            (*fixture["runtime"].static_laws, spoof_law),
        ).runtime
        before = _snapshot(session)
        with self.assertRaisesRegex(
            GameplayContractError,
            "accepted emit|accepted hp/shield|exact Law",
        ):
            resolve_action(
                session,
                fixture["registry"],
                ActionRequest("spoof_hit", NPC, "basic_attack", PLAYER),
            )
        self.assertEqual(_snapshot(session), before)

    def test_late_paid_tick_failure_preserves_whole_staged_transaction(self):
        passive = _parse_passive(_counter_passive("rollback_counter", amount=2))
        fixture = _equipped_pair(passive)
        session = fixture["session"]
        before = _snapshot(session)
        real_tick = time_ledger.advance_world_tick
        calls = 0

        def fail_after_tick(working, **kwargs):
            nonlocal calls
            calls += 1
            result = real_tick(working, **kwargs)
            if calls == 1:
                raise RuntimeError("late paid Tick failure")
            return result

        with patch.object(
            time_ledger,
            "advance_world_tick",
            side_effect=fail_after_tick,
        ):
            with self.assertRaisesRegex(RuntimeError, "late paid Tick"):
                submit_timed_primary_action(
                    session,
                    fixture["registry"],
                    ActionRequest(
                        "late_tick_rollback",
                        NPC,
                        "basic_attack",
                        PLAYER,
                    ),
                )
        self.assertEqual(calls, 1)
        self.assertEqual(_snapshot(session), before)

    def test_combined_passive_quantitative_order_and_costs(self):
        passive = _parse_passive(_pair_passive(
            "combined_response",
            shield=7,
            counter=4,
        ))
        fixture = _runtime((passive,))
        _equip(fixture["runtime"], PLAYER, passive)
        before_mana = {
            actor: _actor_component(fixture["session"], actor)["mana"]
            for actor in (PLAYER, NPC)
        }
        before_sim_time = fixture["session"].state.sim_time
        before_schedule = deepcopy(
            list(fixture["session"].state.scheduled_events)
        )
        outcome = submit_timed_primary_action(
            fixture["session"],
            fixture["registry"],
            ActionRequest("combined_hit", NPC, "basic_attack", PLAYER),
        )
        self.assertEqual(
            {actor: _actor_component(fixture["session"], actor)["mana"]
             for actor in (PLAYER, NPC)},
            before_mana,
        )
        self.assertEqual(
            _actor_component(fixture["session"], PLAYER)["hp"], 40
        )
        self.assertEqual(
            _actor_component(fixture["session"], PLAYER)["shield"], 7
        )
        self.assertEqual(
            _actor_component(fixture["session"], NPC)["hp"], 46
        )
        self.assertEqual(
            len(_fired_records(outcome.action)), 1
        )
        self.assertGreaterEqual(
            len(_notifications(outcome.action)), 1
        )
        self.assertEqual(
            outcome.time.event_result.trace.root_event.time,
            before_sim_time,
        )
        self.assertEqual(
            outcome.time.ticks[0].event_result.trace.root_event.time,
            before_sim_time + 1,
        )
        self.assertEqual(
            len(fixture["session"].state.scheduled_events),
            len(before_schedule),
        )

    def test_save_load_and_registry_checkpoint_continuation(self):
        passive = _parse_passive(_shield_passive("continuation", amount=6))
        fixture = _equipped_pair(passive)
        with tempfile.TemporaryDirectory(dir=REVIEW_TMP) as directory:
            world_path = Path(directory) / "world.json"
            registry_path = Path(directory) / "registry.json"
            save_world(world_path, fixture["session"].state)
            loaded = load_world(world_path)
            rebuilt_session = build_content_session(
                loaded, fixture["compiled"]
            )
            restored = MechanismRegistryRuntime.from_compiled_content(
                rebuilt_session, fixture["compiled"]
            )
            save_registry_checkpoint(registry_path, fixture["runtime"])
            checkpoint = load_registry_checkpoint(
                registry_path, fixture["compiled"]
            )
        self.assertEqual(restored.manifest, fixture["runtime"].manifest)
        self.assertEqual(checkpoint.manifest, fixture["runtime"].manifest)
        left = resolve_action(
            fixture["session"],
            fixture["registry"],
            ActionRequest("continue_left", NPC, "basic_attack", PLAYER),
            dispatch_limits=_limits(max_depth=2),
        )
        right = resolve_action(
            restored.session,
            restored.action_registry,
            ActionRequest("continue_right", NPC, "basic_attack", PLAYER),
            dispatch_limits=_limits(max_depth=2),
        )
        third = resolve_action(
            checkpoint.session,
            checkpoint.action_registry,
            ActionRequest("continue_third", NPC, "basic_attack", PLAYER),
            dispatch_limits=_limits(max_depth=2),
        )
        self.assertEqual(
            _snapshot(fixture["session"])[0],
            _snapshot(restored.session)[0],
        )
        self.assertEqual(
            _snapshot(fixture["session"])[0],
            _snapshot(checkpoint.session)[0],
        )
        self.assertEqual(
            [row.status for row in _records(left)],
            [row.status for row in _records(right)],
        )
        self.assertEqual(
            [row.status for row in _records(left)],
            [row.status for row in _records(third)],
        )
        self.assertEqual(
            static_law_hash(restored.static_laws),
            static_law_hash(fixture["runtime"].static_laws),
        )
        self.assertIn(
            NOTIFICATION,
            {
                effect.get("event", {}).get("type")
                for law in build_action_laws(restored.action_registry)
                for effect in law["effects"]
            },
        )
        self.assertEqual(
            fixture["runtime"].base_registry.passive_bindings,
            restored.base_registry.passive_bindings,
        )

    def test_projection_has_no_private_dispatch_authority(self):
        passive = _parse_passive(_shield_passive("projection", amount=7))
        fixture = _equipped_pair(passive)
        resolve_action(
            fixture["session"],
            fixture["registry"],
            ActionRequest("projection_hit", NPC, "basic_attack", PLAYER),
        )
        document = ActorObservationBuilder().build(
            fixture["session"], fixture["registry"], PLAYER
        ).to_dict()
        encoded = json.dumps(document, sort_keys=True)
        self.assertIn("actors", document)
        for secret in (
            passive.canonical_hash,
            "passive_equipped",
            "passive_bindings",
            "notification_id",
            "root_event_id",
            "cooldowns",
        ):
            self.assertNotIn(secret, encoded)
        empty = _runtime()
        empty_document = ActorObservationBuilder().build(
            empty["session"], empty["registry"], PLAYER
        ).to_dict()
        self.assertEqual(
            set(document["actors"][PLAYER]),
            set(empty_document["actors"][PLAYER]),
        )


class SourceAndEnvironmentTests(unittest.TestCase):
    def test_review_paths_and_temporary_files_are_pmw_local(self):
        self.assertTrue(Path(__file__).resolve().is_relative_to(PROJECT_ROOT))
        self.assertTrue(REVIEW_TMP.resolve().is_relative_to(PROJECT_ROOT))
        with tempfile.TemporaryDirectory(dir=REVIEW_TMP) as directory:
            path = Path(directory) / "probe.json"
            path.write_text("{}", encoding="utf-8")
            self.assertEqual(path.read_text(encoding="utf-8"), "{}")
        self.assertEqual(os.environ.get("PYTHONDONTWRITEBYTECODE"), "1")
        self.assertRegex(
            "auto_hook_" + hashlib.sha256(b"passive-review").hexdigest()[:32],
            REQUEST_ID,
        )
        self.assertRegex("auto_hook_0dead", REQUEST_ID)
        self.assertRegex("auto_hook_" + "x" * 55, REQUEST_ID)
        self.assertIsNone(REQUEST_ID.fullmatch("auto_hook_" + "x" * 56))
        self.assertIsNone(REQUEST_ID.fullmatch("ah" + "a" * 61))

    def test_known_active_condition_gap_is_standalone(self):
        path = (
            PROJECT_ROOT
            / "docs"
            / "agent_bootstrap"
            / "C4_ACTIVE_CONDITION_DESIGN.md"
        )
        self.assertTrue(path.exists())


if __name__ == "__main__":
    unittest.main()
