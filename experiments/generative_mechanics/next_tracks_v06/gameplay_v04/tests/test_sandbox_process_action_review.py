from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from experiments.generative_mechanics.next_tracks_v06.gameplay_v04 import time_ledger
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.action_compiler import (
    build_action_laws,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.actions import (
    ActionCostModifier,
    ActionRegistry,
    ActionRequest,
    resolve_action,
    submit_timed_primary_action,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.basics import (
    basic_registry,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.conditions import (
    parse_condition,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.checkpoint import (
    load_registry_checkpoint,
    save_registry_checkpoint,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.content_compiler import (
    CompiledGate3Content,
    make_content,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.contracts import (
    GameplayContractError,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.observation import (
    ActorObservationBuilder,
    ObservationDisclosure,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.materials import (
    material_authority,
    parse_material,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.processes import (
    PROCESS_COMPONENT,
    PROCESS_START_EVENT,
    ProcessController,
    ProcessLimits,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.registry import (
    MechanismRegistryRuntime,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.runtime import (
    build_runtime,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.simulation import (
    SandboxSimulator,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.skills import (
    parse_skill_blueprint,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.tests.test_sandbox_process_action import (
    AREA_ID,
    PLAYER_ID,
    SKILL_ID,
    _blueprint,
    _component,
    _profile,
    _revision,
    _runtime,
    _state,
)


class ProcessActionIndependentReviewTests(unittest.TestCase):
    def _snapshot(self, session):
        return (
            _state(session),
            _revision(session),
            deepcopy(session.runtime.stats),
            tuple(
                (event.id, event.type, event.time)
                for event in session.state.scheduled_events
            ),
            id(session.runtime),
        )

    def test_compound_field_and_process_start_are_atomic(self):
        raw = json.loads(_blueprint().canonical_document_json)
        raw["effects"].insert(0, {
            "id": "heat_shift",
            "kind": "modify_field",
            "target": {"kind": "current_area"},
            "commitment": "required",
            "field_id": "heat",
            "amount": 2.0,
        })
        raw["budget"]["limit"] = 7.0
        material = parse_material({
            "id": "process_crystal",
            "tier": "rare",
            "region_rarity": "scarce",
            "traits": [{
                "id": "process_shaping",
                "effect_kinds": ["modify_field", "process_start"],
                "selectors": ["current_area"],
                "budget_points": 7.0,
            }],
        })
        compound = parse_skill_blueprint(
            raw,
            basic_registry().statuses,
            material_authority((material,)),
        )
        player = _profile("compound_refining", PLAYER_ID)
        runtime, _, skill = _runtime((player,), skill=compound)
        self.assertEqual(skill.budget_used, 7.0)
        outcome = resolve_action(
            runtime.session,
            runtime.action_registry,
            ActionRequest("compound_success", PLAYER_ID, SKILL_ID),
        )
        self.assertEqual(
            runtime.session.state.entities[AREA_ID]
            .components["pmw_gameplay_dynamics"]["fields"]["heat"]["value"],
            3.0,
        )
        self.assertEqual(_component(runtime.session, player)["state"], "running")
        self.assertEqual(
            [row["kind"] for row in outcome.effect_outcomes],
            ["modify_field", "process_start"],
        )

        player = _profile("compound_rollback", PLAYER_ID)
        runtime, _, skill = _runtime((player,), skill=compound)
        runtime.session.state.entities[
            player.inputs[0].stock.entity_id
        ].components["stock"]["amount"] = 0.0
        before = self._snapshot(runtime.session)
        with self.assertRaisesRegex(GameplayContractError, "input .* empty"):
            resolve_action(
                runtime.session,
                runtime.action_registry,
                ActionRequest("compound_failure", PLAYER_ID, SKILL_ID),
            )
        self.assertEqual(self._snapshot(runtime.session), before)

    def test_real_start_cascade_divide_by_zero_rolls_back_everything(self):
        player = _profile("cascade_refining", PLAYER_ID)
        runtime, _, _ = _runtime((player,))
        controller = ProcessController(
            (player,),
            ProcessLimits(max_instances=8, max_active=8),
        )
        registry = ActionRegistry(
            runtime.action_registry.actions.values(),
            runtime.action_registry.statuses.values(),
            runtime.action_registry.hooks.values(),
            process_controller=controller,
        )
        session = build_runtime(
            runtime.session.state,
            runtime.session.profiles,
            (
                *(
                    law for law in runtime.static_laws
                    if not law["id"].startswith("pmw.v04.sandbox.process.")
                ),
                *build_action_laws(registry),
                *controller.laws,
                {
                    "id": "pmw.v04.review.aa_bridge_start_cascade",
                    "mode": "event",
                    "priority": 100,
                    "bindings": {
                        "process": {
                            "kind": "entity",
                            "requires": [PROCESS_COMPONENT],
                        }
                    },
                    "when": {"all": [{
                        "ref": "$process.id",
                        "eq": player.process_entity_id,
                    }, {
                        "event.type": {"eq": PROCESS_START_EVENT},
                    }]},
                    "effects": [{
                        "op": "emit_event",
                        "event": {
                            "type": "pmw.v04.review.after_start",
                            "time": "$event.time",
                            "source": "$event.source",
                            "target": "$process.id",
                            "payload": {},
                        },
                    }],
                },
                {
                    "id": "pmw.v04.review.zz_late_divide_by_zero",
                    "mode": "event",
                    "priority": 100,
                    "bindings": {
                        "process": {
                            "kind": "entity",
                            "requires": [PROCESS_COMPONENT],
                        }
                    },
                    "when": {"all": [
                        {"event.type": {"eq": "pmw.v04.review.after_start"}},
                        {"ref": "$process.id", "eq": "$event.target"},
                        {
                            "ref": f"$process.{PROCESS_COMPONENT}.state",
                            "eq": "running",
                        },
                    ]},
                    "effects": [{
                        "op": "set",
                        "target": f"$process.{PROCESS_COMPONENT}.last_failure",
                        "value": {"div": [1, 0]},
                    }],
                },
            ),
        )
        before = self._snapshot(session)
        with self.assertRaises(ZeroDivisionError):
            resolve_action(
                session,
                registry,
                ActionRequest("cascade_failure", PLAYER_ID, SKILL_ID),
            )
        self.assertEqual(self._snapshot(session), before)

    def test_final_quoted_duration_and_second_tick_failure_roll_back(self):
        # Trusted action-level quote test: current data SkillBlueprints cannot
        # express cost_modifiers.
        player = _profile("modifier_rollback", PLAYER_ID)
        runtime, _, skill = _runtime((player,), time_budget=4)
        original_skill = skill.action
        action = replace(
            original_skill,
            cost_modifiers=(
                ActionCostModifier(
                    "review_long_action",
                    parse_condition({
                        "attribute": {
                            "subject": "self",
                            "key": "control",
                            "comparator": "gte",
                            "value": 1,
                        }
                    }),
                    1,
                    0.0,
                ),
            ),
        )
        self.assertEqual(action.canonical_hash, original_skill.canonical_hash)
        registry = ActionRegistry(
            (
                action,
                *(row for row in runtime.action_registry.actions.values()
                  if row.id != action.id),
            ),
            runtime.action_registry.statuses.values(),
            runtime.action_registry.hooks.values(),
            process_controller=runtime.action_registry.process_controller,
        )
        runtime.session = build_runtime(
            runtime.session.state,
            runtime.session.profiles,
            (
                *(
                    law for law in runtime.static_laws
                    if not law["id"].startswith("pmw.v04.action.")
                ),
                *build_action_laws(registry),
            ),
        )
        before = self._snapshot(runtime.session)
        original_tick = time_ledger.advance_world_tick
        calls = 0

        def fail_second_tick(working, **kwargs):
            nonlocal calls
            calls += 1
            result = original_tick(working, **kwargs)
            if calls == 2:
                raise RuntimeError("review injected second tick failure")
            return result

        with patch.object(
            time_ledger, "advance_world_tick", side_effect=fail_second_tick
        ), patch.object(
            time_ledger,
            "spend_world_time",
            wraps=time_ledger.spend_world_time,
        ) as spend:
            with self.assertRaisesRegex(RuntimeError, "second tick"):
                submit_timed_primary_action(
                    runtime.session,
                    registry,
                    ActionRequest("modifier_failure", PLAYER_ID, SKILL_ID),
                )
        self.assertEqual(calls, 2)
        self.assertEqual(spend.call_args.args[1], 3)
        self.assertEqual(self._snapshot(runtime.session), before)

    def test_checkpoint_rejects_changed_compiled_process_profile(self):
        player = _profile("checkpoint_swapped", PLAYER_ID)
        runtime, compiled, _ = _runtime((player,), time_budget=5)
        stale = _profile(
            "checkpoint_swapped",
            PLAYER_ID,
            stock_prefix="checkpoint_changed",
            amount=11.0,
        )
        stale_controller = ProcessController(
            (stale,),
            ProcessLimits(max_instances=8, max_active=8),
        )
        changed = CompiledGate3Content(
            make_content(
                ActionRegistry(
                    (
                        row for row in runtime.action_registry.actions.values()
                        if row.id != SKILL_ID
                    ),
                    runtime.action_registry.statuses.values(),
                    runtime.action_registry.hooks.values(),
                    process_controller=stale_controller,
                ),
                skills=(runtime.blueprints[(SKILL_ID, 1)],),
                material_ids=("process_crystal",),
            ),
            (
                *(
                    law for law in compiled.laws
                    if not law["id"].startswith("pmw.v04.sandbox.process.")
                ),
                *stale_controller.laws,
            ),
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "process_checkpoint.json"
            save_registry_checkpoint(path, runtime)
            with self.assertRaisesRegex(
                GameplayContractError, "static Law configuration"
            ):
                load_registry_checkpoint(path, changed)
            restored = load_registry_checkpoint(path, compiled)

        direct_player = _profile("checkpoint_swapped", PLAYER_ID)
        direct, _, _ = _runtime((direct_player,), time_budget=5)
        restored_outcome = submit_timed_primary_action(
            restored.session,
            restored.action_registry,
            ActionRequest("checkpoint_continuation", PLAYER_ID, SKILL_ID),
        )
        direct_outcome = submit_timed_primary_action(
            direct.session,
            direct.action_registry,
            ActionRequest("checkpoint_continuation", PLAYER_ID, SKILL_ID),
        )
        self.assertEqual(restored_outcome.action.cost, direct_outcome.action.cost)
        self.assertEqual(
            [tick.step for tick in restored_outcome.time.ticks],
            [tick.step for tick in direct_outcome.time.ticks],
        )
        self.assertEqual(
            restored.session.state.to_dict(),
            direct.session.state.to_dict(),
        )

    def test_projection_hides_private_process_and_basic_action_still_simulates(self):
        player = _profile("projection_review", PLAYER_ID)
        runtime, _, _ = _runtime((player,))
        observation = ActorObservationBuilder().build(
            runtime.session,
            runtime.action_registry,
            PLAYER_ID,
            ObservationDisclosure.create(),
        )
        document = observation.to_dict()
        rendered = str(document)
        self.assertNotIn(player.process_entity_id, rendered)
        self.assertNotIn(player.inputs[0].stock.entity_id, rendered)
        self.assertNotIn(player.outputs[0].stock.entity_id, rendered)
        self.assertNotIn(SKILL_ID, document["known_actions"][PLAYER_ID])
        simulator = SandboxSimulator(runtime.action_registry)
        projected, registry, _ = simulator._build(observation)
        self.assertIsNone(registry.process_controller)
        self.assertNotIn(
            player.process_entity_id,
            projected.state.entities,
        )
        result = simulator.simulate(
            observation,
            ActionRequest("basic_action", PLAYER_ID, "basic_wait"),
        )
        self.assertTrue(result.legal, result.rejection)
        self.assertTrue(result.next_observation.to_dict()["area"]["fields"])


if __name__ == "__main__":
    unittest.main()
