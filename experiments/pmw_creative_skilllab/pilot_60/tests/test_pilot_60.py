from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import unittest

from experiments.pmw_creative_skilllab.pilot_60.runners.run_pilot import (
    EVIDENCE,
    load_cases,
    run_all,
)


class PilotAssetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cases = load_cases()

    def test_exactly_sixty_unique_cases_from_six_creators(self) -> None:
        self.assertEqual(len(self.cases), 60)
        self.assertEqual(len({case["case_id"] for case in self.cases}), 60)
        self.assertEqual(len({case["blueprint"]["id"] for case in self.cases}), 60)
        self.assertEqual(
            Counter(case["creator"] for case in self.cases),
            Counter({f"Creator {letter}": 10 for letter in "ABCDEF"}),
        )

    def test_assets_include_active_passive_temporal_and_world_effects(self) -> None:
        kinds = Counter(case["blueprint"]["kind"] for case in self.cases)
        effects = Counter(
            effect["kind"]
            for case in self.cases
            for effect in case["blueprint"]["effects"]
        )
        self.assertGreaterEqual(kinds["passive_blueprint"], 5)
        self.assertGreaterEqual(effects["modify_field"], 20)
        self.assertGreaterEqual(effects["modify_attractor"], 5)
        self.assertGreaterEqual(effects["modify_rate"], 5)
        self.assertGreaterEqual(sum(bool(case["statuses"]) for case in self.cases), 10)

    def test_published_evidence_matches_assets(self) -> None:
        self.assertEqual(len(list(EVIDENCE.glob("skill_*.json"))), 60)
        for case in self.cases:
            row = json.loads((EVIDENCE / f"{case['case_id']}.json").read_text())
            self.assertEqual(row["case_id"], case["case_id"])
            self.assertEqual(row["skill_id"], case["blueprint"]["id"])
            self.assertEqual(row["result"], "validated")
            self.assertEqual(set(row["legality"].values()), {"pass"})


class PilotExecutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cases = load_cases()
        cls.results = run_all(write_evidence=False)

    def test_all_sixty_execute_through_real_runtime(self) -> None:
        self.assertEqual(len(self.results), 60)
        self.assertTrue(all(row["result"] == "validated" for row in self.results))
        self.assertTrue(all(row["changed_steps"] for row in self.results))

    def test_baseline_and_treatment_use_equal_time_horizons(self) -> None:
        for row in self.results:
            left = row["baseline"]["timeline"]
            right = row["treatment"]["timeline"]
            self.assertEqual(len(left), len(right), row["case_id"])
            self.assertEqual(
                [step["sim_time"] for step in left],
                [step["sim_time"] for step in right],
                row["case_id"],
            )

    def test_every_case_has_traces_and_atomic_negative_control(self) -> None:
        for row in self.results:
            events = row["baseline"]["events"] + row["treatment"]["events"]
            self.assertTrue(events, row["case_id"])
            self.assertTrue(all(event["trace"] is not None for event in events), row["case_id"])
            self.assertTrue(row["counterexample"]["rejected"], row["case_id"])
            self.assertTrue(row["counterexample"]["state_unchanged"], row["case_id"])

    def test_passives_follow_a_source_event_and_trusted_hook(self) -> None:
        passive_ids = {
            case["case_id"]
            for case in self.cases
            if case["blueprint"]["kind"] == "passive_blueprint"
        }
        self.assertGreaterEqual(len(passive_ids), 5)
        for row in self.results:
            if row["case_id"] not in passive_ids:
                continue
            labels = [event["label"] for event in row["treatment"]["events"]]
            self.assertIn("passive_hook", labels, row["case_id"])
            self.assertTrue(
                any(label.startswith("trigger_") or label.startswith("weather_trigger_")
                    for label in labels),
                row["case_id"],
            )


if __name__ == "__main__":
    unittest.main()
