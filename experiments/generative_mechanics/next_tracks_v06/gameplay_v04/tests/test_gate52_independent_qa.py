from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import unittest
from unittest.mock import patch

from experiments.generative_mechanics.next_tracks_v06.gameplay_v04 import time_ledger
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.actions import (
    ActionCostModifier,
    ActionRegistry,
    ActionRequest,
    _resolve_action,
    resolve_action,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.conditions import (
    parse_condition,
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
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.shields import (
    migrate_status_shield_ownership,
    validate_status_shield_ownership,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.tests.test_gate2_actions import (
    make_session,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.tests.test_gate52_status_shield import (
    shared_status_registry,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.time_ledger import (
    TIME_BUDGET_COMPONENT,
    spend_world_time,
)


class Gate52IndependentStatusShieldQA(unittest.TestCase):
    def test_malformed_owner_and_source_lineage_fail_closed(self):
        for field, bad_value in (
            ("owner_id", "different_actor"),
            ("source_id", "different_action:layer"),
        ):
            with self.subTest(field=field):
                registry = shared_status_registry()
                session, _ = make_session(registry, actors=1)
                resolve_action(session, registry, ActionRequest(
                    "owner_probe", "actor_0", "aegis_a",
                ))
                entity = session.state.entities["actor_0"]
                layer = next(
                    row
                    for row in entity.components["pmw_gameplay_shields"]["slots"].values()
                    if row["active"]
                )
                layer[field] = bad_value

                with self.assertRaisesRegex(GameplayContractError, "owner"):
                    validate_status_shield_ownership(
                        entity.components["pmw_gameplay_statuses"],
                        entity.components["pmw_gameplay_shields"],
                    )
                before = deepcopy(session.state.to_dict())
                with self.assertRaises(GameplayContractError):
                    resolve_action(session, registry, ActionRequest(
                        "fail_closed", "actor_0", "basic_wait",
                    ))
                self.assertEqual(session.state.to_dict(), before)

    def test_migration_drops_corrupt_temporary_layer_but_keeps_persistent(self):
        registry = shared_status_registry(persistent=True)
        session, _ = make_session(registry, actors=1)
        resolve_action(session, registry, ActionRequest(
            "persistent", "actor_0", "persistent_aegis",
        ))
        resolve_action(session, registry, ActionRequest(
            "temporary", "actor_0", "aegis_a",
        ))
        entity = session.state.entities["actor_0"]
        layers = entity.components["pmw_gameplay_shields"]
        temporary = next(
            row for row in layers["slots"].values()
            if row["active"] and row["status_instance_id"] is not None
        )
        temporary["source_id"] = "corrupt:source"

        migrate_status_shield_ownership(
            entity.components["pmw_gameplay_actor"],
            entity.components["pmw_gameplay_statuses"],
            layers,
        )
        active = [row for row in layers["slots"].values() if row["active"]]
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]["remaining"], 23.0)
        self.assertIsNone(active[0]["status_instance_id"])
        self.assertEqual(entity.components["pmw_gameplay_actor"]["shield"], 23.0)

    def test_damage_then_cross_source_refresh_never_restores_capacity(self):
        registry = shared_status_registry(duration=2)
        session, _ = make_session(registry, actors=2)
        resolve_action(session, registry, ActionRequest("a1", "actor_0", "aegis_a"))
        resolve_action(session, registry, ActionRequest("b1", "actor_0", "aegis_b"))
        _resolve_action(session, registry, ActionRequest(
            "hit", "actor_1", "basic_attack", "actor_0",
        ))
        resolve_action(session, registry, ActionRequest("a2", "actor_0", "aegis_a"))
        resolve_action(session, registry, ActionRequest("b2", "actor_0", "aegis_b"))
        entity = session.state.entities["actor_0"]
        self.assertEqual(entity.components["pmw_gameplay_actor"]["shield"], 24.0)
        validate_status_shield_ownership(
            entity.components["pmw_gameplay_statuses"],
            entity.components["pmw_gameplay_shields"],
        )


class Gate52IndependentTimeTransactionQA(unittest.TestCase):
    @staticmethod
    def _runtime_snapshot(session):
        return (
            deepcopy(session.state.to_dict()),
            deepcopy(session.runtime.stats),
            session.runtime.revision,
            session.runtime.object_revision,
            session.runtime.state_closure_known,
            id(session.runtime),
        )

    def test_failure_after_each_tick_position_never_publishes(self):
        for fail_at in (1, 2, 3):
            with self.subTest(fail_at=fail_at):
                session, _, _, _ = build_gate3_demo(time_budget_ticks=4)
                before = self._runtime_snapshot(session)
                real_tick = time_ledger.advance_world_tick
                calls = 0

                def injected(working, **kwargs):
                    nonlocal calls
                    calls += 1
                    result = real_tick(working, **kwargs)
                    if calls == fail_at:
                        raise RuntimeError(f"failure after tick {fail_at}")
                    return result

                with patch.object(time_ledger, "advance_world_tick", side_effect=injected):
                    with self.assertRaisesRegex(RuntimeError, f"tick {fail_at}"):
                        spend_world_time(session, 3, reason="offline")
                self.assertEqual(self._runtime_snapshot(session), before)

    def test_status_modified_harvest_consumes_final_duration(self):
        session, content, _, harvest = build_gate3_demo(time_budget_ticks=4)
        resolve_action(session, content.action_registry, ActionRequest(
            "guard_before_harvest", "hero_actor", "basic_guard",
        ))
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
            (
                modified,
                *(row for row in content.action_registry.actions.values()
                  if row.id != action.id),
            ),
            content.action_registry.statuses.values(),
            content.action_registry.hooks.values(),
        )

        outcome = resolve_harvest(
            session,
            registry,
            harvest,
            HarvestRequest("status_modified_harvest", "hero_actor", harvest.id),
        )
        budget = session.state.entities["pmw:v04:clock"].components[
            TIME_BUDGET_COMPONENT
        ]
        self.assertEqual((outcome.duration, len(outcome.time_result.ticks)), (3, 3))
        self.assertEqual((budget["spent_ticks"], budget["remaining_ticks"]), (3, 1))
        self.assertEqual(session.state.sim_time, 3.0)


if __name__ == "__main__":
    unittest.main()
