from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pmw import load_world, save_world

from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.action_compiler import (
    build_action_session,
    build_action_laws,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.actions import (
    ActionRegistry,
    ActionRequest,
    _resolve_action,
    parse_action_request,
    resolve_action,
    submit_primary_action,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.basics import (
    basic_registry_document,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.combat import (
    run_combat_round,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.contracts import (
    GameplayContractError,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.gate3_demo import (
    build_gate3_demo,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.harvest import (
    HarvestRequest,
    resolve_harvest,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04 import time_ledger
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.runtime import (
    advance_world_tick,
    build_runtime,
    discover_profiles,
    run_phase_event,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.tests.test_gate2_actions import (
    make_session,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.time_ledger import (
    TIME_BUDGET_COMPONENT,
    build_time_budget_laws,
    initialize_time_budget,
)


def _timed_basic(total_ticks: int, actors: int = 2):
    original, registry = make_session(actors=actors)
    world = initialize_time_budget(original.state, total_ticks)
    laws = (*build_action_laws(registry), *build_time_budget_laws())
    return build_runtime(world, discover_profiles(world), laws), registry


def _two_expiring_shields():
    document = basic_registry_document()
    document["statuses"].extend((
        {
            "id": "short_owner_shield", "version": 1, "polarity": "buff",
            "max_stacks": 1, "stack_policy": "refresh",
            "duration": {"unit": "owner_turn", "amount": 1},
            "granted_traits": [],
            "on_expire_resource": {"resource": "shield", "value": 0.0},
        },
        {
            "id": "short_world_shield", "version": 1, "polarity": "buff",
            "max_stacks": 1, "stack_policy": "refresh",
            "duration": {"unit": "world_tick", "amount": 1},
            "granted_traits": [],
            "on_expire_resource": {"resource": "shield", "value": 0.0},
        },
    ))
    for action_id, amount, status_id in (
        ("owner_aegis", 11.0, "short_owner_shield"),
        ("world_aegis", 17.0, "short_world_shield"),
    ):
        document["actions"].append({
            "id": action_id, "version": 1, "action_type": "skill",
            "cost": {"duration": 1, "mana": 0.0},
            "scope": {"selectors": ["self"], "relation_types": []},
            "effects": [
                {"id": f"{action_id}_layer", "kind": "shield",
                 "target": {"kind": "self"}, "commitment": "required",
                 "amount": amount},
                {"id": f"{action_id}_status", "kind": "apply_status",
                 "target": {"kind": "self"}, "commitment": "required",
                 "status_id": status_id},
            ],
        })
    registry = ActionRegistry.parse(document)
    session, _ = make_session(registry, actors=1)
    return session, registry


class Gate51IndependentQATests(unittest.TestCase):
    def test_failed_round_after_owner_turn_candidate_is_fully_atomic(self):
        session, registry = _timed_basic(2)
        submit_primary_action(
            session, registry,
            ActionRequest("qa_guard", "actor_0", "basic_guard"),
        )
        before = deepcopy(session.state.to_dict())
        with self.assertRaises(GameplayContractError):
            run_combat_round(
                session, registry, round_index=1,
                actor_order=("actor_0", "actor_1"),
                requests={"actor_0": ActionRequest(
                    "qa_bad_target", "actor_0", "basic_attack", "missing_actor"
                )},
            )
        self.assertEqual(session.state.to_dict(), before)

    def test_exhausted_round_preserves_status_scheduler_and_budget(self):
        session, registry = _timed_basic(1, actors=1)
        submit_primary_action(
            session, registry,
            ActionRequest("qa_guard_exhaust", "actor_0", "basic_guard"),
        )
        run_combat_round(
            session, registry, round_index=1,
            actor_order=("actor_0",), requests={},
        )
        before = deepcopy(session.state.to_dict())
        with self.assertRaises(GameplayContractError):
            run_combat_round(
                session, registry, round_index=2,
                actor_order=("actor_0",),
                requests={"actor_0": ActionRequest(
                    "qa_wait_exhaust", "actor_0", "basic_wait"
                )},
            )
        self.assertEqual(session.state.to_dict(), before)
        budget = session.state.entities["pmw:v04:clock"].components[TIME_BUDGET_COMPONENT]
        self.assertEqual((budget["spent_ticks"], budget["remaining_ticks"]), (1, 0))

    def test_second_tick_failure_rolls_back_harvest_and_scheduler(self):
        session, content, _, harvest = build_gate3_demo(time_budget_ticks=3)
        before = deepcopy(session.state.to_dict())
        real_tick = time_ledger.advance_world_tick
        calls = 0

        def fail_on_second(staged, **kwargs):
            nonlocal calls
            calls += 1
            result = real_tick(staged, **kwargs)
            if calls == 2:
                raise RuntimeError("qa injected second-tick failure")
            return result

        with patch.object(time_ledger, "advance_world_tick", side_effect=fail_on_second):
            with self.assertRaisesRegex(RuntimeError, "second-tick"):
                resolve_harvest(
                    session, content.action_registry, harvest,
                    HarvestRequest("qa_second_tick", "hero_actor", harvest.id),
                )
        self.assertEqual(calls, 2)
        self.assertEqual(session.state.to_dict(), before)

    def test_committed_combat_and_harvest_keep_formal_trace_boundaries(self):
        session, content, _, harvest = build_gate3_demo(time_budget_ticks=4)
        combat = run_combat_round(
            session, content.action_registry, round_index=1,
            actor_order=("hero_actor", "plain_actor"),
            requests={"hero_actor": ActionRequest(
                "qa_traced_wait", "hero_actor", "basic_wait"
            )},
        )
        self.assertEqual(
            combat.outcomes[0].event_result.trace.events[0].event.type,
            "pmw.v04.action.resolve",
        )
        self.assertEqual(
            combat.combat_phase_result.trace.events[0].event.type,
            "pmw.v04.combat_round",
        )
        self.assertEqual(
            combat.time_spend_result.event_result.trace.events[0].event.type,
            "pmw.v04.time.spend",
        )
        self.assertEqual(
            combat.world_tick_result.event_result.trace.events[0].event.type,
            "pmw.v04.world_tick",
        )

        gathered = resolve_harvest(
            session, content.action_registry, harvest,
            HarvestRequest("qa_traced_harvest", "hero_actor", harvest.id),
        )
        self.assertEqual(
            gathered.event_result.trace.events[0].event.type,
            "pmw.v04.resource.harvest",
        )
        self.assertEqual(
            gathered.time_result.event_result.trace.events[0].event.type,
            "pmw.v04.time.spend",
        )
        budget = session.state.entities["pmw:v04:clock"].components[TIME_BUDGET_COMPONENT]
        self.assertEqual((budget["spent_ticks"], budget["remaining_ticks"]), (3, 1))

    def test_public_primary_resolver_cannot_bypass_equipment(self):
        session, content, skill, _ = build_gate3_demo(time_budget_ticks=3)
        before = deepcopy(session.state.to_dict())
        with self.assertRaises(GameplayContractError):
            resolve_action(
                session, content.action_registry,
                ActionRequest("qa_public_bypass", "hero_actor", skill.id, "plain_actor"),
            )
        self.assertEqual(session.state.to_dict(), before)

    def test_request_cannot_claim_builtin_and_nonbasic_builtin_is_not_slot_free(self):
        with self.assertRaises(GameplayContractError):
            parse_action_request({
                "request_id": "qa_builtin_field", "actor_id": "actor_0",
                "action_id": "basic_wait", "builtin": True,
            })

        document = basic_registry_document()
        forged = deepcopy(document["actions"][2])
        forged.update({"id": "forged_wait", "action_type": "skill", "builtin": True})
        document["actions"].append(forged)
        registry = ActionRegistry.parse(document)
        session, _ = make_session(registry, actors=1)
        before = deepcopy(session.state.to_dict())
        with self.assertRaises(GameplayContractError):
            submit_primary_action(
                session, registry,
                ActionRequest("qa_forged_builtin", "actor_0", "forged_wait"),
            )
        self.assertEqual(session.state.to_dict(), before)

    def test_public_caller_cannot_self_declare_hook_execution(self):
        session, content, skill, _ = build_gate3_demo(time_budget_ticks=3)
        before = deepcopy(session.state.to_dict())
        with self.assertRaises((GameplayContractError, TypeError)):
            resolve_action(
                session, content.action_registry,
                ActionRequest("qa_forged_hook", "hero_actor", skill.id, "plain_actor"),
                execution_kind="hook", hook_context={"fake": True},
            )
        self.assertEqual(session.state.to_dict(), before)

    def test_two_owned_shields_expire_independently_in_both_orders(self):
        for first in ("owner", "world"):
            with self.subTest(first=first):
                session, registry = _two_expiring_shields()
                _resolve_action(session, registry, ActionRequest(
                    f"qa_{first}_owner", "actor_0", "owner_aegis"
                ))
                _resolve_action(session, registry, ActionRequest(
                    f"qa_{first}_world", "actor_0", "world_aegis"
                ))
                def shield():
                    return session.state.entities["actor_0"].components[
                        "pmw_gameplay_actor"
                    ]["shield"]

                self.assertEqual(shield(), 28.0)
                if first == "owner":
                    run_phase_event(session, "owner_turn", actor_id="actor_0")
                    self.assertEqual(shield(), 17.0)
                    advance_world_tick(session)
                else:
                    advance_world_tick(session)
                    self.assertEqual(shield(), 11.0)
                    run_phase_event(session, "owner_turn", actor_id="actor_0")
                self.assertEqual(shield(), 0.0)

    def test_shield_layers_checkpoint_and_trace_are_exact(self):
        session, registry = _two_expiring_shields()
        outcome = _resolve_action(
            session, registry,
            ActionRequest("qa_checkpoint_aegis", "actor_0", "owner_aegis"),
        )
        self.assertTrue(outcome.event_result.trace.events)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "qa-shields.json"
            save_world(path, session.state)
            restored = build_action_session(
                load_world(path), discover_profiles(load_world(path)), registry
            )
        self.assertEqual(session.state.to_dict(), restored.state.to_dict())
        for candidate in (session, restored):
            run_phase_event(candidate, "owner_turn", actor_id="actor_0")
        self.assertEqual(session.state.to_dict(), restored.state.to_dict())

    def test_pre_gate51_checkpoint_status_schema_is_migrated_safely(self):
        session, registry = make_session(actors=1)
        _resolve_action(
            session, registry,
            ActionRequest("qa_legacy_guard", "actor_0", "basic_guard"),
        )
        legacy = deepcopy(session.state)
        actor = legacy.entities["actor_0"]
        actor.components.pop("pmw_gameplay_shields", None)
        for slot in actor.components["pmw_gameplay_statuses"]["slots"].values():
            slot.pop("shield_layer_slot", None)

        # Exercise the shared gameplay attach boundary used by content and
        # registry checkpoints, not only the action-only test constructor.
        restored = build_runtime(
            legacy, discover_profiles(legacy), build_action_laws(registry)
        )
        run_phase_event(restored, "owner_turn", actor_id="actor_0")
        migrated = restored.state.entities["actor_0"].components
        self.assertFalse(any(
            slot["active"]
            for slot in migrated["pmw_gameplay_statuses"]["slots"].values()
        ))
        # Old aggregate provenance is unknowable. Migration keeps it as a
        # legacy layer instead of allowing Guard expiry to erase unrelated HP.
        self.assertEqual(migrated["pmw_gameplay_actor"]["shield"], 8.0)


if __name__ == "__main__":
    unittest.main()
