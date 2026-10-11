from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pmw import load_world, save_world

from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.content_compiler import (
    build_content_session,
    compile_content,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.actions import (
    ActionCost,
    ActionCostModifier,
    ActionRegistry,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.conditions import parse_condition
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.contracts import GameplayContractError
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.gate3_demo import build_gate3_demo
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.harvest import (
    HARVEST_RECEIPT_RELATION,
    HarvestRequest,
    resolve_harvest,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04 import harvest as harvest_module
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.time_ledger import (
    spend_world_time,
)


def _timed_demo(total_ticks: int):
    session, content, _, harvest = build_gate3_demo(time_budget_ticks=total_ticks)
    return session, content, harvest


class HarvestTransactionRegression(unittest.TestCase):
    def test_exhausted_budget_rejects_before_any_harvest_write(self):
        session, content, harvest = _timed_demo(1)
        spend_world_time(session, 1, reason="offline")
        before = deepcopy(session.state.to_dict())
        with self.assertRaises(GameplayContractError):
            resolve_harvest(
                session,
                content.action_registry,
                harvest,
                HarvestRequest("exhausted_harvest", "hero_actor", harvest.id),
            )
        self.assertEqual(session.state.to_dict(), before)

    def test_two_tick_harvest_rejects_one_tick_and_accepts_exact_budget(self):
        short, content, harvest = _timed_demo(1)
        before = deepcopy(short.state.to_dict())
        with self.assertRaises(GameplayContractError):
            resolve_harvest(short, content.action_registry, harvest,
                            HarvestRequest("too_slow", "hero_actor", harvest.id))
        self.assertEqual(short.state.to_dict(), before)

        exact, content, harvest = _timed_demo(2)
        outcome = resolve_harvest(exact, content.action_registry, harvest,
                                  HarvestRequest("exact_time", "hero_actor", harvest.id))
        budget = exact.state.entities["pmw:v04:clock"].components["pmw_gameplay_time_budget"]
        inventory = exact.state.entities["hero_actor"].components["pmw_gameplay_material_inventory"]
        receipts = [row for row in exact.state.relations.values()
                    if row.type == HARVEST_RECEIPT_RELATION]
        self.assertEqual((outcome.duration, len(outcome.time_result.ticks)), (2, 2))
        self.assertEqual((budget["spent_ticks"], budget["remaining_ticks"]), (2, 0))
        self.assertEqual(inventory["quantities"][harvest.material_id], 1.0)
        self.assertEqual(len(receipts), 1)

    def test_lucky_final_duration_controls_budget_and_preserves_threshold_tolerance(self):
        lucky_session, content, harvest = _timed_demo(1)
        outcome = resolve_harvest(
            lucky_session, content.action_registry, harvest,
            HarvestRequest("lucky_time", "hero_actor", harvest.id, True),
            permissions=("lucky_harvest",),
        )
        field = lucky_session.state.entities["mist_forest"].components["pmw_gameplay_dynamics"]["fields"]["herbs"]
        self.assertEqual(outcome.duration, 1)
        self.assertEqual(outcome.yield_amount, 2.0)
        # 0.7 - 0.2 is the boundary, not a degradation below it.
        self.assertEqual(field["baseline"]["target"], 0.7)

    def test_condition_modified_final_duration_is_preflighted(self):
        session, content, harvest = _timed_demo(2)
        action = content.action_registry.actions[harvest.action_id]
        modifier = ActionCostModifier(
            "abundant_takes_longer",
            parse_condition({"field": {"subject": "current_area", "key": "herbs",
                                       "comparator": "gte", "value": 0.0}}),
            1, 0.0,
        )
        modified = replace(action, cost_modifiers=(modifier,))
        registry = ActionRegistry(
            (modified, *(row for row in content.action_registry.actions.values() if row.id != action.id)),
            content.action_registry.statuses.values(), content.action_registry.hooks.values(),
        )
        before = deepcopy(session.state.to_dict())
        with self.assertRaises(GameplayContractError):
            resolve_harvest(session, registry, harvest,
                            HarvestRequest("modified_cost", "hero_actor", harvest.id))
        self.assertEqual(session.state.to_dict(), before)

    def test_validation_failures_are_atomic(self):
        for name, request, permissions in (
            ("permission", HarvestRequest("no_permission", "hero_actor", "forest_herbs", True), ()),
            ("resource", HarvestRequest("no_resource", "hero_actor", "forest_herbs"), ()),
        ):
            with self.subTest(name=name):
                session, content, harvest = _timed_demo(4)
                if name == "resource":
                    session.state.entities["mist_forest"].components["pmw_gameplay_dynamics"]["fields"]["herbs"]["value"] = 0.1
                before = deepcopy(session.state.to_dict())
                with self.assertRaises(GameplayContractError):
                    resolve_harvest(session, content.action_registry, harvest, request,
                                    permissions=permissions)
                self.assertEqual(session.state.to_dict(), before)

        session, content, harvest = _timed_demo(4)
        action = content.action_registry.actions[harvest.action_id]
        costly = replace(action, cost=ActionCost(action.cost.duration, 50.0))
        registry = ActionRegistry(
            (costly, *(row for row in content.action_registry.actions.values() if row.id != action.id)),
            content.action_registry.statuses.values(), content.action_registry.hooks.values(),
        )
        before = deepcopy(session.state.to_dict())
        with self.assertRaises(GameplayContractError):
            resolve_harvest(session, registry, harvest,
                            HarvestRequest("no_mana", "hero_actor", harvest.id))
        self.assertEqual(session.state.to_dict(), before)

    def test_mid_tick_failure_discards_harvest_time_and_scheduler_side_effects(self):
        session, content, harvest = _timed_demo(4)
        before = deepcopy(session.state.to_dict())
        real_spend = harvest_module.spend_world_time

        def fail_after_staged_spend(staged, duration, *, reason):
            real_spend(staged, duration, reason=reason)
            raise RuntimeError("injected failure after staged scheduler work")

        with patch.object(harvest_module, "spend_world_time", side_effect=fail_after_staged_spend):
            with self.assertRaisesRegex(RuntimeError, "injected failure"):
                resolve_harvest(session, content.action_registry, harvest,
                                HarvestRequest("rollback_all", "hero_actor", harvest.id))
        self.assertEqual(session.state.to_dict(), before)

    def test_overharvest_degradation_commits_with_yield(self):
        session, content, harvest = _timed_demo(2)
        field = session.state.entities["mist_forest"].components["pmw_gameplay_dynamics"]["fields"]["herbs"]
        field["value"] = 0.6
        outcome = resolve_harvest(session, content.action_registry, harvest,
                                  HarvestRequest("degrade_once", "hero_actor", harvest.id))
        committed = session.state.entities["mist_forest"].components["pmw_gameplay_dynamics"]["fields"]["herbs"]
        inventory = session.state.entities["hero_actor"].components["pmw_gameplay_material_inventory"]
        self.assertEqual(outcome.yield_amount, 1.0)
        self.assertEqual(inventory["quantities"][harvest.material_id], 1.0)
        deltas = {str(row.address): row.new_value for row in outcome.event_result.state_delta}
        self.assertEqual(deltas["entity:mist_forest/pmw_gameplay_dynamics/fields/herbs/baseline/target"], 0.6)
        self.assertEqual(deltas["entity:mist_forest/pmw_gameplay_dynamics/fields/herbs/baseline/rate"], 0.08)
        # The two atomic ticks then legitimately drive the sampled ecology
        # transition; it is part of the same committed behavior.
        self.assertEqual(committed["baseline"]["target"], 0.2)
        self.assertEqual(committed["baseline"]["rate"], 0.02)

    def test_checkpoint_replay_of_request_is_idempotent(self):
        session, content, harvest = _timed_demo(4)
        request = HarvestRequest("checkpoint_once", "hero_actor", harvest.id)
        resolve_harvest(session, content.action_registry, harvest, request)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "harvest-world.json"
            save_world(path, session.state)
            restored = build_content_session(load_world(path), compile_content(content))
        before = deepcopy(restored.state.to_dict())
        with self.assertRaises(GameplayContractError):
            resolve_harvest(restored, content.action_registry, harvest, request)
        self.assertEqual(restored.state.to_dict(), before)


if __name__ == "__main__":
    unittest.main()
