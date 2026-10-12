from __future__ import annotations

import json
from pathlib import Path
import unittest

from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.contracts import GameplayContractError
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.time_ledger import spend_world_time
from experiments.gccp.f2_engine_pilot_v01.actions import (
    execute_preparation,
    execute_repair,
    legal_actions,
)
from experiments.gccp.f2_engine_pilot_v01.belief_solver import solve_equivalent, solve_native
from experiments.gccp.f2_engine_pilot_v01.engine_scenario import (
    AREA_ID,
    F2_COMPONENT,
    ROOTS,
    build_f2_runtime,
)
from experiments.gccp.f2_engine_pilot_v01.observation import observation_key, public_observation
from experiments.gccp.f2_engine_pilot_v01.reference_model import reference_optimum


ROOT = Path(__file__).resolve().parents[1]


class F2EngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.solutions = {
            (.10, .03): solve_equivalent(.10, .03),
            (.10, .23): solve_equivalent(.10, .23),
            (.40, .03): solve_equivalent(.40, .03),
        }
        cls.native = solve_native()
        cls.ablated = solve_equivalent(.10, .03, information_ablation=True)

    def test_real_world_tick_matches_f2_physics(self) -> None:
        for root in ROOTS:
            runtime = build_f2_runtime(root, "water")
            result = spend_world_time(runtime.session, 1, reason="exploration")
            private = runtime.session.state.entities[AREA_ID].components[F2_COMPONENT]
            self.assertEqual(private["damage"], 1.0)
            self.assertEqual(private["stability"], 98.0)
            laws = {
                match["law_id"]
                for event in result.ticks[0].event_result.trace.to_dict()["events"]
                for match in event["event_law_matches"]
            }
            self.assertIn(f"gccp.f2.physics.{root}", laws)

    def test_probe_has_real_correct_wrong_and_incompatible_effects(self) -> None:
        results = {}
        for root in ROOTS:
            for interface in ROOTS:
                runtime = build_f2_runtime(root, interface)
                execute_preparation(runtime, "forge_water")
                transition = execute_preparation(runtime, "probe")
                results[(root, interface)] = transition.response
                self.assertEqual(transition.after["water"], 4.0)
        self.assertEqual(results[("water", "water")]["stability_delta"], 2.0)
        self.assertEqual(results[("resonance", "water")]["stability_delta"], -2.0)
        self.assertEqual(results[("water", "resonance")]["stability_delta"], -2.0)
        self.assertFalse(results[("water", "resonance")]["probe_implemented"])

    def test_four_tick_terminal_is_physical_not_answer_comparison(self) -> None:
        for root in ROOTS:
            for repair in ROOTS:
                runtime = build_f2_runtime(root, "water")
                transition, success = execute_repair(runtime, f"repair_{repair}")
                self.assertEqual(success, root == repair)
                self.assertEqual(len(transition.world_ticks), 4)
                self.assertEqual(transition.after["stability"], 116.5 if success else 92.0)
                before = runtime.session.state.to_dict()
                with self.assertRaises(GameplayContractError):
                    execute_repair(runtime, f"repair_{repair}")
                self.assertEqual(runtime.session.state.to_dict(), before)

    def test_initial_observation_and_actions_are_hidden_world_invariant(self) -> None:
        observations = []
        actions = []
        for root in ROOTS:
            for interface in ROOTS:
                runtime = build_f2_runtime(root, interface)
                observations.append(observation_key(public_observation(runtime)))
                actions.append(legal_actions(runtime))
        self.assertEqual(len(set(observations)), 1)
        self.assertEqual(len(set(actions)), 1)
        self.assertNotIn("hidden_root", observations[0])
        self.assertNotIn("hidden_interface", observations[0])
        self.assertNotIn("damage", observations[0])

    def test_calibration_reveals_interface_not_root(self) -> None:
        for interface in ROOTS:
            rows = []
            for root in ROOTS:
                runtime = build_f2_runtime(root, interface)
                rows.append(execute_preparation(runtime, "calibrate").after)
            self.assertEqual(rows[0], rows[1])
            self.assertEqual(rows[0]["calibrated_interface"], interface)

    def test_forge_consumes_once_registers_and_ticks_once(self) -> None:
        runtime = build_f2_runtime("water", "water")
        transition = execute_preparation(runtime, "forge_water")
        self.assertEqual(transition.before["resources"]["diagnostic_blanks"], 1)
        self.assertEqual(transition.after["resources"]["diagnostic_blanks"], 0)
        self.assertIn("probe", transition.after["known_actions"])
        self.assertEqual(transition.after["clock"]["world_tick"], 1)
        before = runtime.session.state.to_dict()
        manifest = runtime.runtime.manifest
        with self.assertRaises(GameplayContractError):
            execute_preparation(runtime, "forge_resonance")
        self.assertEqual(runtime.session.state.to_dict(), before)
        self.assertEqual(runtime.runtime.manifest, manifest)

    def test_probe_is_one_shot_and_failed_interface_still_consumes_time(self) -> None:
        runtime = build_f2_runtime("water", "resonance")
        execute_preparation(runtime, "forge_water")
        transition = execute_preparation(runtime, "probe")
        self.assertFalse(transition.response["probe_implemented"])
        self.assertEqual(transition.after["clock"]["world_tick"], 2)
        before = runtime.session.state.to_dict()
        with self.assertRaises(GameplayContractError):
            execute_preparation(runtime, "probe")
        self.assertEqual(runtime.session.state.to_dict(), before)

    def test_equivalent_solver_matches_three_reference_optima(self) -> None:
        for costs, solution in self.solutions.items():
            expected_actions, expected_value = reference_optimum(*costs)
            self.assertEqual(solution.optimal_actions, expected_actions)
            self.assertAlmostEqual(solution.value, expected_value)
        self.assertAlmostEqual(self.solutions[(.10, .03)].q_values["calibrate"], .870)
        self.assertAlmostEqual(self.solutions[(.10, .23)].q_values["forge_water"], .725)

    def test_solver_can_abandon_exploration_after_observation(self) -> None:
        expensive = self.solutions[(.40, .03)]
        self.assertEqual(expensive.optimal_actions, ("repair_water",))
        self.assertAlmostEqual(expensive.q_values["calibrate"], .62)
        self.assertGreater(expensive.q_values["calibrate"], 1 - .03 - .40)

    def test_information_ablation_removes_investment_value(self) -> None:
        self.assertEqual(self.ablated.optimal_actions, ("repair_water",))
        self.assertEqual(self.ablated.value, .65)
        self.assertLess(self.ablated.q_values["calibrate"], .65)

    def test_native_resources_remove_normalized_cost_flip(self) -> None:
        self.assertEqual(self.native.optimal_actions, ("calibrate",))
        self.assertEqual(self.native.value, 1.0)
        self.assertEqual(self.native.q_values["forge_water"], .825)

    def test_published_solver_evidence_matches_fresh_results(self) -> None:
        published = json.loads((ROOT / "evidence" / "solver_results.json").read_text())
        for (cf, ci), solution in self.solutions.items():
            row = published["equivalent_mode"][f"cf={cf:.2f},ci={ci:.2f}"]["engine_solver"]
            self.assertEqual(row["optimal_actions"], list(solution.optimal_actions))
            self.assertEqual(row["q_values"], solution.q_values)
        self.assertEqual(published["native_resource_mode"]["q_values"], self.native.q_values)
        self.assertEqual(published["information_ablation"]["q_values"], self.ablated.q_values)

    def test_solver_replay_is_deterministic_and_branch_local(self) -> None:
        repeated = solve_equivalent(.10, .03)
        self.assertEqual(repeated.to_dict(), self.solutions[(.10, .03)].to_dict())


if __name__ == "__main__":
    unittest.main()
