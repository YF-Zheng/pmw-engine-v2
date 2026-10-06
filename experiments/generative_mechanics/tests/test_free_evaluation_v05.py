from __future__ import annotations

import copy
from collections import Counter
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from experiments.generative_mechanics.adversarial_measurement.run_audit import (
    _base_spec, _law, _root, _run, _structural_specs,
)
from experiments.generative_mechanics.adversarial_measurement.v05_case_registry import CASES as V05_CASES
from experiments.generative_mechanics.adversarial_measurement.v05_run_audit import (
    PRODUCTION_RESULTS,
    PRODUCTION_RESULTS_SHA256,
    _assert_expected,
    _execute,
)
from experiments.generative_mechanics.cli import main as cli_main
from experiments.generative_mechanics.compiler import canonical_json
from experiments.generative_mechanics.free_evaluation_v05.causal import dependency_profile_from_runs
from experiments.generative_mechanics.free_evaluation_v05.environment import summarize_environment_rows
from experiments.generative_mechanics.free_evaluation_v05.environment import normalized_path_signature
from experiments.generative_mechanics.free_evaluation_v05.semantic_contract import validate_semantic_contract
from experiments.generative_mechanics.free_evaluation_v05.structure import evaluate_structural_evidence
from experiments.generative_mechanics.free_evaluation_v05.profile import evaluate_free_invention_profile_v05
from experiments.generative_mechanics.free_invention import build_request_rows
from experiments.generative_mechanics.tests.test_free_evaluation_v04 import _sample


def _causal(present, candidate_laws, world_laws, ablations=None, absent=()):
    return dependency_profile_from_runs(
        _run(*present), _run(*absent), "audit_candidate",
        world_laws=world_laws, candidate_laws=candidate_laws,
        world_law_ablations=ablations or {},
    )


def _row(environment, outcome, path):
    return {
        "environment": environment,
        "net_outcome_effect": outcome,
        "normalized_path_signature": path,
    }


class CausalV05Tests(unittest.TestCase):
    def test_necessary_chain_depths_agree(self):
        candidate = _law("gm.skill.audit.activate", [], "f0")
        laws = tuple(_law(f"gm.world.chain{i}", [f"f{i}"], f"f{i+1}") for i in range(3))
        roots = (_root(0, (candidate,)), *(_root(i + 1, (law,)) for i, law in enumerate(laws)))
        ablations = {law.law_id: _run(*roots[:index + 1]) for index, law in enumerate(laws)}
        result = _causal(roots, (candidate,), laws, ablations)
        self.assertEqual((result["realized_dependency_depth"], result["necessity_backed_depth"]), (3, 3))
        self.assertEqual(result["depth_gap"], 0)

    def test_overdetermination_is_visible_as_gap(self):
        candidate = _law("gm.skill.audit.activate", [], "f0")
        a = _law("gm.world.a", ["f0"], "x")
        b = _law("gm.world.b", ["f0"], "x")
        c = _law("gm.world.c", ["x"], "z")
        present = (_root(0, (candidate,)), _root(1, (a, b)), _root(2, (c,)))
        ablations = {
            a.law_id: _run(_root(0, (candidate,)), _root(1, (b,)), _root(2, (c,))),
            b.law_id: _run(_root(0, (candidate,)), _root(1, (a,)), _root(2, (c,))),
        }
        result = _causal(present, (candidate,), (a, b, c), ablations)
        self.assertEqual(result["realized_dependency_depth"], 2)
        self.assertEqual(result["necessity_backed_depth"], 1)
        self.assertTrue(result["possible_redundant_causation"])

    def test_wide_fanout_does_not_inflate_depth(self):
        candidates = tuple(_law(f"gm.skill.root{i}", [], f"f{i}") for i in range(8))
        worlds = tuple(_law(f"gm.world.fan{i}", [f"f{i}"], f"o{i}") for i in range(8))
        roots = (_root(0, candidates), *(_root(i + 1, (law,)) for i, law in enumerate(worlds)))
        result = _causal(roots, candidates, worlds)
        self.assertEqual(result["realized_dependency_depth"], 1)

    def test_same_law_repeat_does_not_inflate_structure(self):
        candidate = _law("gm.skill.root", [], "f0")
        repeated = _law("gm.world.repeat", ["f0"], "f0")
        result = _causal(
            (_root(0, (candidate,)), _root(1, (repeated,)), _root(2, (repeated,))),
            (candidate,), (repeated,),
        )
        self.assertEqual(result["realized_dependency_depth"], 1)

    def test_event_and_time_identity_are_not_in_semantic_pair_key(self):
        candidate = _law("gm.skill.root", [], "f0")
        world = _law("gm.world.same", ["f0"], "x")
        result = _causal(
            (_root(0, (candidate,)), _root(1, (world,), event_id="present", time=1)),
            (candidate,), (world,),
            absent=(_root(1, (world,), event_id="absent", time=99),),
        )
        self.assertEqual(result["realized_dependency_depth"], 0)

    def test_binding_identity_is_preserved(self):
        candidate = _law("gm.skill.root", [], "f0")
        world = _law("gm.world.same", ["f0"], "x")
        result = _causal(
            (_root(0, (candidate,)), _root(1, (world,), binding="zone:a")),
            (candidate,), (world,),
            absent=(_root(1, (world,), binding="zone:b"),),
        )
        self.assertEqual(result["binding_policy"], "identity_equality")
        self.assertEqual(result["realized_dependency_depth"], 0)  # no matching candidate writer for zone:a


class EnvironmentV05Tests(unittest.TestCase):
    def test_four_quadrants_are_independent(self):
        same_path = {"nodes": [{"signature": "A", "count": 1}], "edges": []}
        other_path = {"nodes": [{"signature": "B", "count": 1}], "edges": []}
        cases = (
            ([{}, {}], [same_path, other_path], (False, True)),
            ([{"x": 1}, {"x": 2}], [same_path, same_path], (True, False)),
            ([{"x": 1}, {"x": 2}], [same_path, other_path], (True, True)),
            ([{"x": 1}, {"x": 1}], [same_path, same_path], (False, False)),
        )
        for outcomes, paths, expected in cases:
            report = summarize_environment_rows([
                _row("a", outcomes[0], paths[0]), _row("b", outcomes[1], paths[1]),
            ])
            self.assertEqual((report["outcome_differentiated"], report["causal_path_differentiated"]), expected)

    def test_path_multiplicity_matters(self):
        left = {"nodes": [{"signature": "A", "count": 1}], "edges": []}
        right = {"nodes": [{"signature": "A", "count": 2}], "edges": []}
        report = summarize_environment_rows([_row("a", {}, left), _row("b", {}, right)])
        self.assertFalse(report["outcome_differentiated"])
        self.assertTrue(report["causal_path_differentiated"])

    def test_normalized_path_signature_ignores_event_id_and_absolute_time(self):
        candidate = _law("gm.skill.audit.root", [], "f0")
        world = _law("gm.world.audit.path", ["f0"], "x")
        left = _run(
            _root(0, (candidate,), event_id="candidate.left", time=0.0),
            _root(1, (world,), event_id="world.left", time=1.0),
        )
        right = _run(
            _root(0, (candidate,), event_id="candidate.reidentified", time=50.0),
            _root(1, (world,), event_id="world.reidentified", time=99.0),
        )
        absent = _run()
        left_signature = normalized_path_signature(
            left, absent, world_laws=(world,), candidate_laws=(candidate,),
            candidate_skill="audit_candidate",
        )
        right_signature = normalized_path_signature(
            right, absent, world_laws=(world,), candidate_laws=(candidate,),
            candidate_skill="audit_candidate",
        )
        self.assertEqual(left_signature, right_signature)
        self.assertEqual(
            left_signature["identity_exclusions"],
            ["event_id", "command_id", "proposal_id", "absolute_timestamp"],
        )

    def test_normalized_path_signature_preserves_occurrence_multiplicity(self):
        candidate = _law("gm.skill.audit.root", [], "f0")
        world = _law("gm.world.audit.path", ["f0"], "x")
        once = _run(_root(0, (candidate,)), _root(1, (world,)))
        twice = _run(
            _root(0, (candidate,)), _root(1, (world,)),
            _root(2, (world,), event_id="world.second", time=2.0),
        )
        absent = _run()
        once_signature = normalized_path_signature(
            once, absent, world_laws=(world,), candidate_laws=(candidate,),
            candidate_skill="audit_candidate",
        )
        twice_signature = normalized_path_signature(
            twice, absent, world_laws=(world,), candidate_laws=(candidate,),
            candidate_skill="audit_candidate",
        )
        self.assertNotEqual(once_signature, twice_signature)
        self.assertEqual([row["count"] for row in once_signature["nodes"]], [1])
        self.assertEqual([row["count"] for row in twice_signature["nodes"]], [2])
        self.assertTrue(twice_signature["occurrence_multiplicity_preserved"])


class StructuralV05Tests(unittest.TestCase):
    def test_exact_duplicate(self):
        raw = json.loads((Path(__file__).parents[1] / "skills" / "ember_pulse.json").read_text())
        result = evaluate_structural_evidence(raw)
        self.assertTrue(result["exact_match"])
        self.assertIn("ember_pulse", result["matched_reference_ids"])

    def test_one_trigger_near_copy(self):
        _, raw = _structural_specs("near_trigger")
        result = evaluate_structural_evidence(raw)
        self.assertTrue(result["near_copy"])
        self.assertEqual(result["near_copy_edits"][0]["kind"], "add_trigger")

    def test_one_effect_near_copy(self):
        _, raw = _structural_specs("near_effect")
        result = evaluate_structural_evidence(raw)
        self.assertTrue(result["near_copy"])
        self.assertEqual(result["near_copy_edits"][0]["kind"], "add_effect")

    def test_field_substitution_preserves_abstract_topology(self):
        left, right = _structural_specs("field_substitution")
        a = evaluate_structural_evidence(left)
        b = evaluate_structural_evidence(right)
        self.assertNotEqual(a["semantic_structure"]["fingerprint"], b["semantic_structure"]["fingerprint"])
        self.assertEqual(a["abstract_topology"]["fingerprint"], b["abstract_topology"]["fingerprint"])

    def test_simple_union_recombination(self):
        raw, _ = _structural_specs("recombination")
        result = evaluate_structural_evidence(raw)
        self.assertTrue(result["recombination"]["recombination_detected"])
        self.assertEqual(result["recombination"]["coverage"], 1.0)
        self.assertEqual(result["recombination"]["purity"], 1.0)
        self.assertTrue(result["recombination"]["each_source_has_independent_contribution"])

    def test_static_inertness_does_not_erase_structure(self):
        raw, _ = _structural_specs("impossible_trigger")
        result = evaluate_structural_evidence(raw)
        self.assertFalse(result["available"])
        self.assertTrue(result["structural_projection_available"])
        self.assertTrue(result["excluded_from_novelty_rate"])
        self.assertFalse(result["static_guard"]["passed"])
        self.assertTrue(result["static_guard"]["statically_unreachable_triggers"])

    def test_abstract_topology_exposes_unweighted_nearest_edits(self):
        raw, _ = _structural_specs("genuine_periodic")
        result = evaluate_structural_evidence(raw)
        abstract = result["abstract_topology"]
        self.assertIsInstance(abstract["nearest_reference"], str)
        self.assertEqual(abstract["nearest_edit_count"], len(abstract["nearest_edits"]))
        self.assertIn("unweighted", abstract["edit_policy"])


class ContractAndCliV05Tests(unittest.TestCase):
    def test_whole_semantic_contract_validates(self):
        contract = validate_semantic_contract()
        self.assertGreaterEqual(len(contract["registered_paths"]), 70)

    def test_whole_semantic_contract_fails_closed_on_asset_drift(self):
        source = Path(__file__).parents[1]
        with tempfile.TemporaryDirectory() as directory:
            copied = Path(directory) / "generative_mechanics"
            shutil.copytree(source, copied)
            asset = copied / "environments" / "mine.json"
            asset.write_text(asset.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "projection mismatch"):
                validate_semantic_contract(
                    manifest_path=copied / "free_evaluation_v05" / "semantic_contract.json",
                    root=copied,
                )

    def test_whole_semantic_contract_fails_closed_on_shared_source_drift(self):
        source = Path(__file__).parents[1]
        with tempfile.TemporaryDirectory() as directory:
            copied = Path(directory) / "generative_mechanics"
            shutil.copytree(source, copied)
            shared = copied / "structural_novelty.py"
            shared.write_text(shared.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "projection mismatch"):
                validate_semantic_contract(
                    manifest_path=copied / "free_evaluation_v05" / "semantic_contract.json",
                    root=copied,
                )

    def test_cli_version_is_explicit_and_v04_remains_selectable(self):
        parser_out = io.StringIO()
        with self.assertRaises(SystemExit):
            with redirect_stdout(parser_out):
                cli_main(["evaluate-free-invention", "--help"])
        self.assertIn("--evaluation-version", parser_out.getvalue())

    def test_preregistration_has_48_plus_22_cases(self):
        root = Path(__file__).parents[1] / "adversarial_measurement"
        metadata = json.loads((root / "v05_preregistration.json").read_text())
        self.assertEqual(metadata["retained_v04_case_count"], 48)
        self.assertEqual(metadata["new_v05_case_count"], 22)
        self.assertTrue(metadata["expectations_written_before_execution"])

    def test_integrated_profile_keeps_constructs_separate(self):
        profile = evaluate_free_invention_profile_v05(_sample("world_substrate"))
        self.assertEqual(profile["aggregation_policy"], "capability_profile_only_no_score_no_rank")
        dynamic = profile["dynamic_reach"]["conditional_on_activation"]
        self.assertIn("realized_dependency_depth_distribution", dynamic)
        self.assertIn("necessity_backed_depth_distribution", dynamic)
        environment = profile["environmental_behavior"]
        self.assertIn("outcome_differentiated_context_count", environment)
        self.assertIn("causal_path_differentiated_context_count", environment)
        self.assertIn("semantic_structure", profile["structural_evidence"])
        self.assertIn("abstract_topology", profile["structural_evidence"])

    def test_integrated_profile_contains_no_total_or_rank(self):
        profile = evaluate_free_invention_profile_v05(_sample("world_substrate"))
        forbidden = {"creativity_score", "invention_score", "overall_novelty_score", "model_rank", "rank", "ranking"}
        def keys(value):
            if isinstance(value, dict):
                for key, child in value.items():
                    yield key
                    yield from keys(child)
            elif isinstance(value, list):
                for child in value: yield from keys(child)
        self.assertFalse(forbidden & set(keys(profile)))


class AuditEvidenceGateV05Tests(unittest.TestCase):
    @staticmethod
    def case(case_id):
        return next(case for case in V05_CASES if case["case_id"] == case_id)

    def test_every_preregistered_case_has_an_explicit_passing_branch(self):
        outcomes = {case["case_id"]: _execute(case)[1] for case in V05_CASES}
        self.assertEqual(len(outcomes), 70)
        self.assertEqual(Counter(outcomes.values()), Counter({"PASS": 69, "KNOWN_LIMITATION": 1}))

    def test_production_artifact_matches_audit_binding_and_contract(self):
        import hashlib

        self.assertEqual(hashlib.sha256(PRODUCTION_RESULTS.read_bytes()).hexdigest(), PRODUCTION_RESULTS_SHA256)
        artifact = json.loads(PRODUCTION_RESULTS.read_text(encoding="utf-8"))
        self.assertEqual(artifact["protocol_version"], "gm-free-evaluation-v0.5-candidate")
        self.assertEqual(
            (artifact["validation_count"], artifact["full_production_stack_count"], artifact["synthetic_only_count"]),
            (20, 18, 2),
        )
        self.assertTrue(artifact["construct_checks"])
        self.assertTrue(all(artifact["construct_checks"].values()))

    def test_unhandled_fixture_fails_closed(self):
        case = {
            "case_id": "V05-SN-UNKNOWN",
            "fixture": {"fixture": "mechanic", "parameters": {"variant": "unknown"}},
            "v04_suspect_resolution": None,
        }
        with self.assertRaisesRegex(AssertionError, "unhandled structural"):
            _assert_expected(case, {"candidate": {}, "comparison": {}})

    def test_order_invariance_tamper_fails(self):
        case = self.case("CE-13")
        actual, status = _execute(case)
        self.assertEqual(status, "PASS")
        actual["canonical_equal"] = False
        self.assertFalse(_assert_expected(case, actual))

    def test_outcome_partition_tamper_fails(self):
        case = self.case("V05-CE-05")
        actual, status = _execute(case)
        self.assertEqual(status, "PASS")
        actual["patterns"]["gradient"]["summary"]["distinct_outcome_signature_count"] = 3
        self.assertFalse(_assert_expected(case, actual))

    def test_path_multiplicity_tamper_fails(self):
        case = self.case("V05-CE-06")
        actual, status = _execute(case)
        self.assertEqual(status, "PASS")
        actual["multiplicity_change"]["summary"]["causal_path_differentiated"] = False
        self.assertFalse(_assert_expected(case, actual))

    def test_novel_but_inert_production_tamper_fails(self):
        case = self.case("V05-SN-07")
        actual, status = _execute(case)
        self.assertEqual(status, "PASS")
        actual["behaviorally_inert"] = False
        self.assertFalse(_assert_expected(case, actual))

    def test_simple_but_deep_production_tamper_fails(self):
        case = self.case("V05-SN-08")
        actual, status = _execute(case)
        self.assertEqual(status, "PASS")
        actual["dynamic_reach"]["realized_dependency_depth"] = 1
        self.assertFalse(_assert_expected(case, actual))


if __name__ == "__main__":
    unittest.main()
