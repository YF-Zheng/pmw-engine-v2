from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from pmw import parse_law

from experiments.generative_mechanics.next_tracks_v06.benchmarks.locality import run as run_locality
from experiments.generative_mechanics.next_tracks_v06.canonical import canonical_json
from experiments.generative_mechanics.next_tracks_v06.demos.run_demos import ROOT as DEMO_ROOT, run_all, run_demo
from experiments.generative_mechanics.next_tracks_v06.execution import build_runtime, run_steps
from experiments.generative_mechanics.next_tracks_v06.worlds import build_electric_world, build_structural_world, build_thermal_world


def _assert_semantically_equal(test, actual, expected, path="$", *, tolerance=1e-12):
    test.assertIs(type(actual), type(expected), path)
    if isinstance(actual, dict):
        test.assertEqual(set(actual), set(expected), path)
        for key in sorted(actual):
            _assert_semantically_equal(test, actual[key], expected[key], f"{path}.{key}", tolerance=tolerance)
    elif isinstance(actual, list):
        test.assertEqual(len(actual), len(expected), path)
        for index, (left, right) in enumerate(zip(actual, expected)):
            _assert_semantically_equal(test, left, right, f"{path}[{index}]", tolerance=tolerance)
    elif isinstance(actual, float):
        test.assertAlmostEqual(actual, expected, delta=tolerance, msg=path)
    else:
        test.assertEqual(actual, expected, path)


class WorldTests(unittest.TestCase):
    def test_three_worlds_build_and_step(self):
        for builder in (build_thermal_world, build_electric_world, build_structural_world):
            world, laws, _ = builder()
            runtime = build_runtime(world, laws)
            self.assertEqual(len(run_steps(runtime, 2)), 2)

    def test_every_world_law_parses(self):
        for builder in (build_thermal_world, build_electric_world, build_structural_world):
            _, laws, _ = builder()
            for law in laws:
                parse_law(dict(law))

    def test_thermal_stock_depletes_and_process_stops(self):
        result = run_demo(DEMO_ROOT / "drive_depletion.json")
        trajectory = result["trajectory"]
        self.assertEqual(trajectory[-1]["coolant"], 0.0)
        self.assertEqual(trajectory[-1]["pump"], "stopped")

    def test_electric_relation_controls_propagation(self):
        trajectory = run_demo(DEMO_ROOT / "relation_propagation.json")["trajectory"]
        self.assertTrue(trajectory[1]["connected"])
        self.assertFalse(trajectory[3]["connected"])
        self.assertEqual(trajectory[3]["battery"], trajectory[-1]["battery"])

    def test_structural_derived_is_world_law_output(self):
        world, laws, _ = build_structural_world()
        runtime = build_runtime(world, laws)
        run_steps(runtime, 4)
        self.assertTrue(runtime.state.entities["frame"].components["derived"]["operational"])


class DemoTests(unittest.TestCase):
    def test_exactly_five_demo_inputs(self):
        self.assertEqual(len(list(DEMO_ROOT.glob("*.json"))), 5)

    def test_all_demos_run(self):
        with tempfile.TemporaryDirectory() as directory:
            summary = run_all(Path(directory))
        self.assertEqual(len(summary), 5)

    def test_demo_output_is_byte_deterministic(self):
        with tempfile.TemporaryDirectory() as one, tempfile.TemporaryDirectory() as two:
            run_all(Path(one)); run_all(Path(two))
            first = Path(one); second = Path(two)
            names = sorted(path.name for path in first.glob("*.json"))
            self.assertEqual(names, sorted(path.name for path in second.glob("*.json")))
            for name in names:
                self.assertEqual((first / name).read_bytes(), (second / name).read_bytes(), name)

    def test_impulse_and_attractor_trajectories_differ(self):
        branches = run_demo(DEMO_ROOT / "impulse_vs_attractor.json")["branches"]
        impulse = branches["cold_impulse"]["trajectory"]
        anchor = branches["cold_anchor"]["trajectory"]
        self.assertLess(impulse[0]["temperature"], anchor[0]["temperature"])
        self.assertGreater(impulse[-1]["temperature"], anchor[-1]["temperature"])

    def test_competing_attractors_expire_separately(self):
        result = run_demo(DEMO_ROOT / "competing_attractors.json")
        dispatches = [item for step in result["steps"] for item in step["scheduled_dispatches"]]
        self.assertEqual(len(dispatches), 2)
        self.assertNotEqual(dispatches[0], dispatches[1])

    def test_each_demo_contains_full_audit_chain(self):
        for path in DEMO_ROOT.glob("*.json"):
            result = run_demo(path)
            branches = result.get("branches", {"single": result})
            for branch in branches.values():
                self.assertIn("initial_world", branch)
                self.assertIn("compiled_law_ids", branch)
                self.assertIn("activations", branch)
                self.assertIn("steps", branch)
                self.assertIn("final_world", branch)
                self.assertTrue(branch["activations"][0]["result"]["trace"])

    def test_checked_in_results_match_rebuild(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            run_all(output)
            for checked_path in sorted((DEMO_ROOT / "results").glob("*.json")):
                rebuilt_path = output / checked_path.name
                checked = json.loads(checked_path.read_text(encoding="utf-8"))
                rebuilt = json.loads(rebuilt_path.read_text(encoding="utf-8"))
                _assert_semantically_equal(self, rebuilt, checked, checked_path.name)


class LocalityTests(unittest.TestCase):
    def test_warm_candidate_work_is_independent_of_unrelated_objects(self):
        rows = run_locality((1_000, 10_000))
        self.assertEqual(rows[0]["candidate_rows"], rows[1]["candidate_rows"])
        self.assertEqual(rows[0]["partial_bindings"], rows[1]["partial_bindings"])
        self.assertEqual(rows[0]["index_builds"], 0)
        self.assertEqual(rows[1]["index_builds"], 0)


if __name__ == "__main__":
    unittest.main()
