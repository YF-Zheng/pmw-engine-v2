from __future__ import annotations

import json
from pathlib import Path
import unittest

from experiments.pmw_creative_skilllab.build_synergy_v01.runners.run_builds import run_all


ROOT = Path(__file__).resolve().parents[1]


class BuildSynergyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.results = {row["build_id"]: row for row in run_all(write=False)}

    def arm(self, build_id: str, variant_id: str, arm_id: str):
        return self.results[build_id]["variants"][variant_id]["arms"][arm_id]

    def test_six_builds_use_six_equal_time_arms(self) -> None:
        self.assertEqual(set(self.results), {f"build_{letter}" for letter in "abcdef"})
        expected = {"no_skill", "a_only", "b_only", "a_then_b", "b_then_a", "matched_alternative"}
        for build in self.results.values():
            for variant in build["variants"].values():
                self.assertEqual(set(variant["arms"]), expected)
                self.assertEqual(
                    {arm["metrics"]["final_sim_time"] for arm in variant["arms"].values()},
                    {4.0},
                )

    def test_build_a_real_status_enables_followup_but_loses_to_attacks(self) -> None:
        combo = self.arm("build_a", "primary", "a_then_b")
        granted = {
            trait
            for status in combo["timeline"][1]["target"]["statuses"]
            for trait in status["granted_traits"]
        }
        self.assertIn("recently_spared", granted)
        self.assertEqual(combo["timeline"][0]["target"]["traits"], [])
        self.assertEqual(combo["metrics"]["target_damage"], 3.0)
        self.assertEqual(self.arm("build_a", "primary", "b_only")["metrics"]["target_damage"], 0.0)
        self.assertEqual(self.arm("build_a", "primary", "matched_alternative")["metrics"]["target_damage"], 24.0)

    def test_build_b_creates_real_wetness_window_but_guard_is_better(self) -> None:
        no_skill = self.arm("build_b", "threshold_dry", "no_skill")
        b_only = self.arm("build_b", "threshold_dry", "b_only")
        combo = self.arm("build_b", "threshold_dry", "a_then_b")
        alternative = self.arm("build_b", "threshold_dry", "matched_alternative")
        self.assertEqual(b_only["metrics"]["hero_final_hp"], no_skill["metrics"]["hero_final_hp"])
        self.assertGreater(combo["metrics"]["hero_final_hp"], no_skill["metrics"]["hero_final_hp"])
        self.assertGreater(alternative["metrics"]["hero_final_hp"], combo["metrics"]["hero_final_hp"])
        self.assertGreaterEqual(combo["timeline"][1]["fields"]["wetness"]["value"], 0.7)

    def test_build_c_dispatches_only_real_weather_changed_events(self) -> None:
        combo = self.arm("build_c", "storm_threshold", "a_then_b")
        a_only = self.arm("build_c", "storm_threshold", "a_only")
        b_only = self.arm("build_c", "storm_threshold", "b_only")
        alternative = self.arm("build_c", "storm_threshold", "matched_alternative")
        dispatches = [item for row in combo["rounds"] for item in row["manual_hook_dispatches"]]
        self.assertEqual(len(dispatches), 2)
        self.assertTrue(all(row["source_event"]["type"] == "pmw.v04.weather.changed" for row in dispatches))
        self.assertEqual(b_only["metrics"]["manual_hook_dispatch_count"], 0)
        self.assertGreater(combo["metrics"]["hero_final_hp"], alternative["metrics"]["hero_final_hp"])
        self.assertLess(combo["metrics"]["final_electric_field"], a_only["metrics"]["final_electric_field"])

    def test_build_d_is_redundant_and_weather_absent_case_has_no_feedback(self) -> None:
        combo = self.arm("build_d", "sensitive_threshold", "a_then_b")
        a_only = self.arm("build_d", "sensitive_threshold", "a_only")
        b_only = self.arm("build_d", "sensitive_threshold", "b_only")
        absent = self.arm("build_d", "weather_absent_counterexample", "a_then_b")
        absent_none = self.arm("build_d", "weather_absent_counterexample", "no_skill")
        self.assertEqual(combo["metrics"]["hero_final_hp"], a_only["metrics"]["hero_final_hp"])
        self.assertEqual(combo["metrics"]["target_damage"], b_only["metrics"]["target_damage"])
        self.assertNotIn("smoke_heat_front", absent["metrics"]["active_weather_seen"])
        self.assertNotIn("heat_haze", absent["metrics"]["active_weather_seen"])
        self.assertEqual(
            absent["metrics"]["final_temperature"],
            absent_none["metrics"]["final_temperature"],
        )

    def test_build_e_adds_rates_but_not_a_new_threshold_outcome(self) -> None:
        no_skill = self.arm("build_e", "collapse_edge", "no_skill")
        a_only = self.arm("build_e", "collapse_edge", "a_only")
        b_only = self.arm("build_e", "collapse_edge", "b_only")
        combo = self.arm("build_e", "collapse_edge", "a_then_b")
        self.assertEqual(no_skill["metrics"]["final_ecology"], "stressed")
        self.assertEqual({a_only["metrics"]["final_ecology"], b_only["metrics"]["final_ecology"], combo["metrics"]["final_ecology"]}, {"balanced"})
        self.assertEqual(combo["metrics"]["hero_final_hp"], b_only["metrics"]["hero_final_hp"])
        far_none = self.arm("build_e", "far_from_threshold", "no_skill")
        far_combo = self.arm("build_e", "far_from_threshold", "a_then_b")
        self.assertLess(far_combo["metrics"]["final_biomass"], far_none["metrics"]["final_biomass"])

    def test_build_f_resource_enabler_is_dominated_by_waiting(self) -> None:
        useful = self.arm("build_f", "near_high_hp_low_mana", "a_then_b")
        blocked = self.arm("build_f", "near_high_hp_low_mana", "b_only")
        lethal = self.arm("build_f", "near_low_hp_low_mana", "a_then_b")
        full_combo = self.arm("build_f", "near_high_hp_full_mana", "a_then_b")
        full_b = self.arm("build_f", "near_high_hp_full_mana", "b_only")
        far_combo = self.arm("build_f", "far_high_hp_low_mana", "a_then_b")
        alternative = self.arm("build_f", "near_high_hp_low_mana", "matched_alternative")
        self.assertIn("heat_haze", useful["metrics"]["active_weather_seen"])
        self.assertGreater(useful["metrics"]["hero_final_hp"], 0)
        self.assertIn("heat_haze", alternative["metrics"]["active_weather_seen"])
        self.assertEqual(
            alternative["metrics"]["final_temperature"],
            useful["metrics"]["final_temperature"],
        )
        self.assertGreater(alternative["metrics"]["hero_final_hp"], useful["metrics"]["hero_final_hp"])
        self.assertEqual(blocked["metrics"]["rejected_action_count"], 1)
        self.assertEqual(lethal["metrics"]["hero_final_hp"], 0)
        self.assertLess(full_combo["metrics"]["hero_final_hp"], full_b["metrics"]["hero_final_hp"])
        self.assertNotIn("heat_haze", far_combo["metrics"]["active_weather_seen"])

    def test_every_round_retains_real_traces_and_atomic_rejections(self) -> None:
        rejection_count = 0
        for build in self.results.values():
            for variant in build["variants"].values():
                for arm in variant["arms"].values():
                    for row in arm["rounds"]:
                        self.assertTrue(row["world_tick_trace"]["events"])
                        self.assertTrue(row["time_spend_trace"]["events"])
                        self.assertTrue(all(outcome["trace"]["events"] for outcome in row["outcomes"]))
                        if row["rejected"]:
                            rejection_count += 1
                            self.assertTrue(row["rejected"]["state_unchanged"])
        self.assertGreaterEqual(rejection_count, 4)

    def test_published_evidence_matches_fresh_engine_runs(self) -> None:
        for build_id, result in self.results.items():
            published = json.loads((ROOT / "evidence" / f"{build_id}.json").read_text())
            canonical_fresh = json.loads(json.dumps(result, ensure_ascii=False, sort_keys=True))
            self.assertEqual(published, canonical_fresh)

    def test_published_catalog_freezes_reviewed_classifications(self) -> None:
        rows = [json.loads(line) for line in (ROOT / "build_catalog.jsonl").read_text().splitlines()]
        self.assertEqual(
            {row["build_id"]: row["classification"] for row in rows},
            {
                "build_a": "MECHANICALLY_INTERESTING",
                "build_b": "MECHANICALLY_INTERESTING",
                "build_c": "PLAYABLE_BUILD",
                "build_d": "EXECUTABLE_ONLY",
                "build_e": "EXECUTABLE_ONLY",
                "build_f": "MECHANICALLY_INTERESTING",
            },
        )


if __name__ == "__main__":
    unittest.main()
