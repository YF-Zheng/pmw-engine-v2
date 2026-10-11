from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pmw import Event, load_world, save_world
from pmw.runtime.session import WorldRuntime

from experiments.generative_mechanics.next_tracks_v06.gameplay_v04 import time_ledger
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.actions import (
    ActionCostModifier,
    ActionRegistry,
    ActionRequest,
    resolve_action,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.combat import run_combat_round
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.content_compiler import (
    build_content_session,
    compile_content,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.contracts import GameplayContractError
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.conditions import parse_condition
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.gate3_demo import build_gate3_demo
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.harvest import (
    HarvestRequest,
    resolve_harvest,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.time_ledger import (
    TIME_BUDGET_COMPONENT,
    spend_world_time,
)


class TimeTransactionRegression(unittest.TestCase):
    @staticmethod
    def _budget(session):
        return session.state.entities["pmw:v04:clock"].components[TIME_BUDGET_COMPONENT]

    def test_duration_one_and_three_commit_exactly_once(self):
        one, _, _, _ = build_gate3_demo(time_budget_ticks=4)
        first = spend_world_time(one, 1, reason="move")
        self.assertEqual((first.duration, len(first.ticks)), (1, 1))
        self.assertEqual(one.state.sim_time, 1.0)
        self.assertEqual((self._budget(one)["spent_ticks"], self._budget(one)["remaining_ticks"]), (1, 3))

        three, _, _, _ = build_gate3_demo(time_budget_ticks=3)
        result = spend_world_time(three, 3, reason="rest")
        self.assertEqual((result.duration, len(result.ticks)), (3, 3))
        self.assertEqual([tick.step for tick in result.ticks], [1, 2, 3])
        self.assertEqual(three.state.sim_time, 3.0)
        self.assertEqual((self._budget(three)["spent_ticks"], self._budget(three)["remaining_ticks"]), (3, 0))

    def test_insufficient_budget_has_no_runtime_or_trace_side_effect(self):
        session, _, _, _ = build_gate3_demo(time_budget_ticks=2)
        before_state = deepcopy(session.state.to_dict())
        before_stats = deepcopy(session.runtime.stats)
        before_revision = (session.runtime.revision, session.runtime.object_revision)
        with self.assertRaisesRegex(GameplayContractError, "budget is exhausted"):
            spend_world_time(session, 3, reason="offline")
        self.assertEqual(session.state.to_dict(), before_state)
        self.assertEqual(session.runtime.stats, before_stats)
        self.assertEqual((session.runtime.revision, session.runtime.object_revision), before_revision)

    def test_second_tick_failure_rolls_back_complete_time_request(self):
        session, _, _, _ = build_gate3_demo(time_budget_ticks=4)
        before_state = deepcopy(session.state.to_dict())
        before_runtime = (
            deepcopy(session.runtime.stats),
            session.runtime.revision,
            session.runtime.object_revision,
            session.runtime.state_closure_known,
        )
        real_tick = time_ledger.advance_world_tick
        calls = 0

        def fail_after_second_tick(working, **kwargs):
            nonlocal calls
            calls += 1
            result = real_tick(working, **kwargs)
            if calls == 2:
                raise RuntimeError("injected failure after second Tick")
            return result

        with patch.object(time_ledger, "advance_world_tick", side_effect=fail_after_second_tick):
            with self.assertRaisesRegex(RuntimeError, "after second Tick"):
                spend_world_time(session, 3, reason="move")

        self.assertEqual(session.state.to_dict(), before_state)
        self.assertEqual(
            (
                session.runtime.stats,
                session.runtime.revision,
                session.runtime.object_revision,
                session.runtime.state_closure_known,
            ),
            before_runtime,
        )
        budget = session.state.entities["pmw:v04:clock"].components[TIME_BUDGET_COMPONENT]
        self.assertEqual((budget["spent_ticks"], budget["remaining_ticks"]), (0, 4))

    def test_scheduler_dispatch_failure_restores_pending_queue_and_ledger(self):
        session, _, _, _ = build_gate3_demo(time_budget_ticks=3)
        session.runtime.schedule(Event(
            "pmw:v04:test:scheduled-probe",
            "pmw.v04.test.scheduler_probe",
            2.0,
            "pmw:v04:clock",
            "pmw:v04:clock",
            {},
        ))
        before_state = deepcopy(session.state.to_dict())
        before_stats = deepcopy(session.runtime.stats)
        real_advance = WorldRuntime.advance_to

        def fail_after_scheduler_dispatch(runtime, target_time):
            result = real_advance(runtime, target_time)
            if target_time == 2.0:
                raise RuntimeError("injected Scheduler callback failure")
            return result

        with patch.object(WorldRuntime, "advance_to", new=fail_after_scheduler_dispatch):
            with self.assertRaisesRegex(RuntimeError, "Scheduler callback failure"):
                spend_world_time(session, 3, reason="offline")
        self.assertEqual(session.state.to_dict(), before_state)
        self.assertEqual(session.runtime.stats, before_stats)
        self.assertEqual(len(session.state.scheduled_events), 1)
        self.assertEqual(session.state.scheduled_events[0].id, "pmw:v04:test:scheduled-probe")

    def test_move_rest_and_offline_share_identical_accounting(self):
        results = []
        for reason in ("move", "rest", "offline"):
            session, _, _, _ = build_gate3_demo(time_budget_ticks=2)
            outcome = spend_world_time(session, 2, reason=reason)
            budget = self._budget(session)
            results.append((outcome.duration, len(outcome.ticks), session.state.sim_time,
                            budget["spent_ticks"], budget["remaining_ticks"], budget["last_reason"]))
        self.assertEqual([row[:-1] for row in results], [(2, 2, 2.0, 2, 0)] * 3)
        self.assertEqual([row[-1] for row in results], ["move", "rest", "offline"])

    def test_checkpoint_restores_budget_and_scheduler_continuation(self):
        session, content, _, _ = build_gate3_demo(time_budget_ticks=4)
        session.runtime.schedule(Event(
            "pmw:v04:test:checkpoint-probe", "pmw.v04.test.checkpoint_probe",
            3.0, "pmw:v04:clock", "pmw:v04:clock", {},
        ))
        spend_world_time(session, 1, reason="move")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "world.json"
            save_world(path, session.state)
            restored = build_content_session(load_world(path), compile_content(content))
        left = spend_world_time(session, 2, reason="rest")
        right = spend_world_time(restored, 2, reason="rest")
        self.assertEqual(session.state.to_dict(), restored.state.to_dict())
        self.assertEqual([tick.step for tick in left.ticks], [tick.step for tick in right.ticks])
        self.assertEqual((self._budget(restored)["spent_ticks"], self._budget(restored)["remaining_ticks"]), (3, 1))

    def test_combat_and_harvest_nested_transactions_do_not_double_charge(self):
        combat, content, _, _ = build_gate3_demo(time_budget_ticks=1)
        run_combat_round(
            combat,
            content.action_registry,
            round_index=1,
            actor_order=("hero_actor", "plain_actor"),
            requests={},
        )
        self.assertEqual((self._budget(combat)["spent_ticks"], self._budget(combat)["remaining_ticks"]), (1, 0))

        harvest_session, content, _, harvest = build_gate3_demo(time_budget_ticks=2)
        outcome = resolve_harvest(
            harvest_session,
            content.action_registry,
            harvest,
            HarvestRequest("gate52_single_charge", "hero_actor", harvest.id),
        )
        self.assertEqual(outcome.duration, 2)
        self.assertEqual((self._budget(harvest_session)["spent_ticks"],
                          self._budget(harvest_session)["remaining_ticks"]), (2, 0))

    def test_active_status_modifies_final_harvest_duration_after_checkpoint(self):
        session, content, _, harvest = build_gate3_demo(time_budget_ticks=4)
        resolve_action(
            session,
            content.action_registry,
            ActionRequest("gate52_guard_status", "hero_actor", "basic_guard"),
        )
        action = content.action_registry.actions[harvest.action_id]
        modifier = ActionCostModifier(
            "guarding_takes_longer",
            parse_condition({
                "has_status": {"subject": "self", "id": "basic_guarding"},
            }),
            1,
            0.0,
        )
        modified = replace(action, cost_modifiers=(modifier,))
        registry = ActionRegistry(
            (modified, *(row for row in content.action_registry.actions.values()
                         if row.id != action.id)),
            content.action_registry.statuses.values(),
            content.action_registry.hooks.values(),
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "guarded-world.json"
            save_world(path, session.state)
            restored = build_content_session(load_world(path), compile_content(content))

        outcome = resolve_harvest(
            restored,
            registry,
            harvest,
            HarvestRequest("gate52_guarded_harvest", "hero_actor", harvest.id),
        )
        self.assertEqual((outcome.duration, len(outcome.time_result.ticks)), (3, 3))
        self.assertEqual(restored.state.sim_time, 3.0)
        self.assertEqual((self._budget(restored)["spent_ticks"],
                          self._budget(restored)["remaining_ticks"]), (3, 1))


if __name__ == "__main__":
    unittest.main()
