from __future__ import annotations

from collections import Counter
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

from experiments.generative_mechanics.analysis import (
    analyze, cross_environment, evaluator_comparison, kill_criteria,
)
from experiments.generative_mechanics.batch import (
    BatchConfig, evaluate_four_baselines, evaluate_sample, load_scenarios,
    run_batch, summarize,
)
from experiments.generative_mechanics.compiler import canonical_json
from experiments.generative_mechanics.figures import render_figures
from experiments.generative_mechanics.generation import (
    DirectEffectSpec, GeneratedSample, balanced_sample, generate_fixture_envelopes,
    ingest_jsonl, prompt_request, validate_envelope, write_fixture_jsonl,
    write_request_jsonl,
)


def samples() -> tuple[GeneratedSample, ...]:
    rows = generate_fixture_envelopes()
    result = ingest_jsonl(canonical_json(row) for row in rows)
    if result.errors:
        raise AssertionError(result.errors)
    return result.samples


class GenerationProtocolTests(unittest.TestCase):
    def test_fixture_is_balanced_240(self):
        rows = generate_fixture_envelopes()
        self.assertEqual(len(rows), 240)
        counts = Counter((row["baseline"], row["target_band"]) for row in rows)
        self.assertEqual(set(counts.values()), {40})

    def test_fixture_is_byte_deterministic(self):
        with tempfile.TemporaryDirectory() as directory:
            one = Path(directory) / "one.jsonl"
            two = Path(directory) / "two.jsonl"
            self.assertEqual(write_fixture_jsonl(one), write_fixture_jsonl(two))
            self.assertEqual(one.read_bytes(), two.read_bytes())

    def test_provider_request_file_is_balanced_and_self_contained(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "requests.jsonl"
            write_request_jsonl(path, per_cell=2)
            rows = [json.loads(line) for line in path.read_text().splitlines()]
        self.assertEqual(len(rows), 12)
        self.assertEqual(set(Counter((row["baseline"], row["target_band"]) for row in rows).values()), {2})
        self.assertTrue(all("response_contract" in row["prompt"] for row in rows))

    def test_prompt_hash_tampering_is_rejected(self):
        row = json.loads(canonical_json(generate_fixture_envelopes()[0]))
        row["provenance"]["prompt_sha256"] = "0" * 64
        result = ingest_jsonl([canonical_json(row)])
        self.assertEqual(len(result.samples), 0)
        self.assertIn("canonical request", result.errors[0].message)

    def test_provider_prompt_is_self_describing(self):
        direct = prompt_request("direct_effect", "Low", 1)["response_contract"]["mechanic"]
        substrate = prompt_request("world_substrate", "High", 1)["response_contract"]["mechanic"]
        self.assertIn("effect_kind", direct)
        self.assertEqual(len(substrate["effects"]["item"]["field"]), 8)
        self.assertIn("mutually exclusive", substrate["periodic"])

    def test_bad_lines_and_duplicates_are_isolated(self):
        good = canonical_json(generate_fixture_envelopes()[0])
        result = ingest_jsonl(["not-json", good, good])
        self.assertEqual(len(result.samples), 1)
        self.assertEqual(len(result.errors), 2)
        self.assertEqual(result.errors[1].message, "sample_id: duplicate")

    def test_direct_and_substrate_mechanics_remain_distinct(self):
        direct, substrate = samples()[0], samples()[120]
        self.assertIsInstance(direct.mechanic, DirectEffectSpec)
        self.assertNotIsInstance(substrate.mechanic, DirectEffectSpec)
        self.assertNotEqual(direct.to_dict()["executable_mechanic"], substrate.to_dict()["executable_mechanic"])

    def test_small_profile_is_stratified_across_all_cells(self):
        chosen = balanced_sample(samples(), 12)
        counts = Counter((sample.baseline, sample.target_band) for sample in chosen)
        self.assertEqual(set(counts.values()), {2})


class Phase3ExecutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.samples = samples()

    def test_direct_effect_is_environment_invariant_and_has_no_downstream(self):
        row = cross_environment(self.samples[0])
        self.assertEqual(row["total_downstream"], 0)
        self.assertFalse(row["environment_difference"])
        self.assertTrue(row["direct_outcome_consistent"])
        outcomes = {
            canonical_json(value["direct_outcome"])
            for value in row["environments"].values()
        }
        self.assertEqual(len(outcomes), 1)

    def test_substrate_fixture_can_have_environment_specific_consequences(self):
        candidates = [sample for sample in self.samples if sample.baseline == "world_substrate"]
        rows = [cross_environment(sample) for sample in candidates[:24]]
        self.assertTrue(any(row["total_downstream"] > 0 for row in rows))
        self.assertTrue(any(row["environment_difference"] for row in rows))

    def test_aftermath_horizons_capture_recovery(self):
        direct_duration = next(
            sample for sample in self.samples
            if isinstance(sample.mechanic, DirectEffectSpec) and sample.mechanic.duration == 8.0
        )
        row = cross_environment(direct_duration)
        self.assertGreater(row["aftermath"]["combat_end"], 0)
        self.assertGreater(row["aftermath"]["short"], 0)
        self.assertEqual(row["aftermath"]["medium"], 0)

    def test_four_evaluator_contract(self):
        result = evaluate_four_baselines(
            self.samples[0], load_scenarios("held_out", 1), (),
        )
        self.assertEqual(set(result), {
            "self_rating", "static_heuristic", "pmw_standard_simulation", "pmw_contextual_search",
        })
        self.assertTrue(all("available" in item for item in result.values()))

    def test_revision_changes_spec_and_is_reexecuted(self):
        original = self.samples[0]
        weak = replace(
            original,
            mechanic=replace(original.mechanic, magnitude=0.01),
            raw_mechanic={**original.raw_mechanic, "magnitude": 0.01},
            target_band="High",
        )
        result = evaluate_sample(
            weak,
            BatchConfig(sample_limit=1, scenario_limit=1, contextual_pool=()),
        )
        self.assertTrue(result["revision_applied"])
        self.assertTrue(result["revision_changed_spec"])
        self.assertNotEqual(
            result["guided_score"],
            result["evaluators"]["pmw_standard_simulation"]["score"],
        )

    def test_resume_is_byte_stable(self):
        config = BatchConfig(sample_limit=2, scenario_limit=1, contextual_pool=())
        with tempfile.TemporaryDirectory() as directory:
            run_batch(self.samples, directory, config)
            before = {path.name: path.read_bytes() for path in Path(directory).iterdir()}
            run_batch(self.samples, directory, config)
            after = {path.name: path.read_bytes() for path in Path(directory).iterdir()}
            self.assertEqual(before, after)

    def test_compile_failure_isolated_from_other_samples(self):
        broken = replace(self.samples[0], sample_id="broken", mechanic=object())
        config = BatchConfig(sample_limit=None, scenario_limit=1, contextual_pool=())
        with tempfile.TemporaryDirectory() as directory:
            result = run_batch((broken, self.samples[1]), directory, config)
        self.assertEqual(result["summary"]["succeeded"], 1)
        self.assertEqual(result["summary"]["failed"], 1)
        self.assertEqual(result["summary"]["compile_rate"], 0.5)
        self.assertEqual({row["status"] for row in result["records"]}, {"ok", "error"})

    def test_summary_uses_stage_specific_denominators(self):
        good = evaluate_sample(
            self.samples[0], BatchConfig(sample_limit=1, scenario_limit=1, contextual_pool=()),
        )
        compile_failure = {
            "sample_id": "bad", "status": "error", "schema_valid": True,
            "compile_valid": False, "execution_valid": False,
        }
        result = summarize([good, compile_failure], [{"line": 3, "message": "bad schema"}])
        self.assertEqual(result["schema_validity"], 2 / 3)
        self.assertEqual(result["compile_rate"], 1 / 2)
        self.assertEqual(result["execution_validity"], 1.0)
        self.assertEqual(set(result["diversity"]), {
            "structural_unique", "structural_ratio",
            "parametric_unique", "parametric_ratio",
        })
        self.assertIn("deterministic_controller_hit_rate", result)


class AnalysisAndFigureTests(unittest.TestCase):
    def test_evaluator_comparison_does_not_invent_ground_truth(self):
        result = evaluator_comparison([])
        self.assertFalse(result["available"])
        self.assertTrue(all(item["mae"] is None for item in result["evaluators"].values()))

    def test_contextual_kill_criterion_is_unavailable_without_ground_truth(self):
        summary = {"schema_validity": 1.0, "compile_rate": 1.0, "execution_validity": 1.0}
        result = kill_criteria(summary, [], [], {"available": False})
        self.assertEqual(result["checks"]["contextual_evaluator_no_gain"]["status"], "UNAVAILABLE")
        self.assertEqual(result["overall"], "FAIL")  # other empty-data criteria fail closed

    def test_ground_truth_enables_real_evaluator_metrics(self):
        def row(sample_id, self_score, static, standard, contextual):
            return {
                "sample_id": sample_id, "status": "ok",
                "evaluators": {
                    "self_rating": {"available": True, "score": self_score},
                    "static_heuristic": {"available": True, "score": static},
                    "pmw_standard_simulation": {"available": True, "score": standard},
                    "pmw_contextual_search": {"available": True, "score": contextual},
                },
            }
        result = evaluator_comparison(
            [row("a", 5, 8, 9, 10), row("b", 30, 24, 21, 20)],
            {
                "IntrinsicPower": {"a": 10, "b": 20},
                "ContextualMarginalPower": {"a": 10, "b": 20},
            },
        )
        self.assertTrue(result["available"])
        self.assertEqual(
            result["tasks"]["ContextualMarginalPower"]["evaluators"]
            ["pmw_contextual_search"]["mae"], 0,
        )
        self.assertNotIn(
            "pmw_contextual_search",
            result["tasks"]["IntrinsicPower"]["evaluators"],
        )
        self.assertFalse(result["cross_estimand_comparisons"])
        self.assertEqual(
            result["tasks"]["ContextualMarginalPower"]["oracle_target"],
            "OraclePersonalizedDelta",
        )

    def test_legacy_ground_truth_is_intrinsic_only(self):
        rows = [{
            "sample_id": sample_id, "status": "ok",
            "evaluators": {
                "self_rating": {"available": True, "score": score},
                "static_heuristic": {"available": True, "score": score},
                "pmw_standard_simulation": {"available": True, "score": score},
                "pmw_contextual_search": {"available": True, "score": score},
            },
        } for sample_id, score in (("a", 1), ("b", 2))]
        result = evaluator_comparison(rows, {"a": 1, "b": 2})
        self.assertTrue(result["tasks"]["IntrinsicPower"]["available"])
        self.assertFalse(result["tasks"]["ContextualMarginalPower"]["available"])

    def test_analysis_marks_fixture_results(self):
        result = analyze([], [], {"schema_validity": 0, "compile_rate": 0, "execution_validity": 0})
        self.assertIn("not model findings", result["fixture_disclaimer"])
        self.assertFalse(result["evaluator_comparison"]["available"])

    def test_five_figures_render_in_three_formats_reproducibly(self):
        record = {
            "sample_id": "fixture", "status": "ok", "baseline": "direct_effect",
            "target_band": "Low",
            "guided_score": 26.0,
            "evaluators": {
                "pmw_standard_simulation": {"score": 24.0},
                "pmw_contextual_search": {"score": 3.0},
            },
        }
        environments = {
            name: {"downstream_count": 0}
            for name in ("mine", "wetland", "industrial_yard", "fragile_bridge")
        }
        analysis_data = {
            "cross_environment": [{"environments": environments}],
            "evaluator_comparison": {"available": False},
        }
        with tempfile.TemporaryDirectory() as directory:
            one, two = Path(directory) / "one", Path(directory) / "two"
            first = render_figures({"records": [record]}, analysis_data, one)
            second = render_figures({"records": [record]}, analysis_data, two)
            self.assertEqual(len(first["artifacts"]), 15)
            self.assertEqual(first["artifacts"], second["artifacts"])
            self.assertEqual(set(path.suffix for path in one.iterdir()), {".pdf", ".svg", ".png", ".json"})


if __name__ == "__main__":
    unittest.main()
