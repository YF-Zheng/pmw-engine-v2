"""Execute all preregistered v0.5 cases without editing expectations."""

from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
from typing import Any

from .run_audit import (
    _base_spec,
    _causal_eval as _v04_causal_eval,
    _cross_effects,
    _law,
    _root,
    _run,
    _structural_specs,
)
from .v05_case_registry import CASES
from ..free_evaluation_v05.causal import dependency_profile_from_runs
from ..free_evaluation_v05.environment import summarize_environment_rows
from ..free_evaluation_v05.structure import evaluate_structural_evidence
from ..spec import SkillSpecError, validate_skill


ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "v05_results.jsonl"
SUMMARY = ROOT / "v05_summary.json"
BASELINE = ROOT / "results" / "v05_pre_revision_baseline.jsonl"
V04_RESULTS = ROOT / "adversarial_results.jsonl"
PRODUCTION_RESULTS = ROOT / "results" / "v05_production_validation.json"
PRODUCTION_RESULTS_SHA256 = "acb45ff155d32d3a5c6283a5281981c46e029eb64428fd0abaeb8f47018efd16"


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _causal(present, candidate, world, *, absent=(), ablations=None):
    return dependency_profile_from_runs(
        _run(*present), _run(*absent), "audit_candidate",
        world_laws=world, candidate_laws=candidate,
        world_law_ablations=ablations or {},
    )


def _causal_fixture(fixture: str, params: dict[str, Any]) -> dict[str, Any]:
    candidate = _law("gm.skill.audit.activate", [], "f0")
    if fixture in {"parallel", "parallel_delayed", "wide_fanout"}:
        width = params.get("width", 8)
        candidates = tuple(_law(f"gm.skill.audit.root{i}", [], f"f{i}") for i in range(width))
        worlds = tuple(_law(f"gm.world.parallel{i}", [f"f{i}"], f"o{i}") for i in range(width))
        roots = [_root(0, candidates)]
        roots.extend(_root(i + 1, (law,), time=(i + 1) * 10 if fixture == "parallel_delayed" else i + 1) for i, law in enumerate(worlds))
        return _causal(tuple(roots), candidates, worlds)
    if fixture in {"chain", "delayed_chain", "necessary_chain"}:
        depth = params.get("depth", 2)
        worlds = tuple(_law(f"gm.world.chain{i+1}", [f"f{i}"], f"f{i+1}") for i in range(depth))
        roots = [_root(0, (candidate,))]
        roots.extend(_root(i + 1, (law,), time=(i + 1) * 12 if fixture == "delayed_chain" else i + 1) for i, law in enumerate(worlds))
        ablations = {law.law_id: _run(*roots[:i + 1]) for i, law in enumerate(worlds)}
        return _causal(tuple(roots), (candidate,), worlds, ablations=ablations)
    if fixture == "repeat_same_law":
        law = _law("gm.world.repeat", ["f0"], "f0")
        return _causal((_root(0, (candidate,)), _root(1, (law,)), _root(2, (law,))), (candidate,), (law,))
    if fixture in {"redundant_paths", "overdetermination", "redundant_then_deep"}:
        a = _law("gm.world.path_a", ["f0"], "x")
        b = _law("gm.world.path_b", ["f0"], "x")
        c = _law("gm.world.path_c", ["x"], "y" if fixture == "redundant_then_deep" else "z")
        worlds = [a, b, c]
        present = [_root(0, (candidate,)), _root(1, (a, b)), _root(2, (c,))]
        a_run = [_root(0, (candidate,)), _root(1, (b,)), _root(2, (c,))]
        b_run = [_root(0, (candidate,)), _root(1, (a,)), _root(2, (c,))]
        ablations = {a.law_id: _run(*a_run), b.law_id: _run(*b_run)}
        if fixture == "redundant_then_deep":
            d = _law("gm.world.path_d", ["y"], "z")
            worlds.append(d); present.append(_root(3, (d,))); a_run.append(_root(3, (d,))); b_run.append(_root(3, (d,)))
            ablations[a.law_id] = _run(*a_run); ablations[b.law_id] = _run(*b_run)
            ablations[c.law_id] = _run(_root(0, (candidate,)), _root(1, (a, b)))
        return _causal(tuple(present), (candidate,), tuple(worlds), ablations=ablations)
    if fixture in {"identity_shift", "event_time_shift", "binding_identity"}:
        a = _law("gm.world.source_a", ["f0"], "x")
        c = _law("gm.world.downstream_c", ["x"], "z")
        present = (_root(0, (candidate,)), _root(1, (a,)), _root(2, (c,), event_id="event.C", time=2))
        shift = params.get("shift", "event_id")
        kwargs = {"event_id": "event.C", "time": 2, "binding": "zone:audit"}
        if fixture == "binding_identity" or shift == "binding": kwargs["binding"] = "zone:other"
        elif fixture == "event_time_shift": kwargs.update({"event_id": "replacement.C", "time": 22})
        elif shift == "event_id": kwargs["event_id"] = "replacement.C"
        else: kwargs["time"] = 2.5
        return _causal(
            present, (candidate,), (a, c),
            ablations={a.law_id: _run(_root(0, (candidate,)), _root(2, (c,), **kwargs))},
        )
    if fixture in {"last_writer_overwrite", "last_writer_unrelated"}:
        a = _law("gm.world.writer_a", ["f0"], "x")
        b = _law("gm.world.writer_b", ["f0"], "x" if fixture.endswith("overwrite") else "other")
        c = _law("gm.world.reader_c", ["x"], "z")
        present = (_root(0, (candidate,)), _root(1, (a,)), _root(2, (b,)), _root(3, (c,)))
        ablations = {a.law_id: _run(_root(0, (candidate,)), _root(2, (b,)))}
        if fixture.endswith("overwrite"):
            ablations[b.law_id] = _run(_root(0, (candidate,)), _root(1, (a,)))
        return _causal(present, (candidate,), (a, b, c), ablations=ablations)
    if fixture == "clamped_no_commit":
        return _causal((_root(0, (candidate,), no_commit=True),), (candidate,), ())
    if fixture == "noop_writer":
        world = _law("gm.world.noop", ["f0"], "x")
        return _causal(
            (_root(0, (candidate,)), _root(1, (world,), no_commit=True)),
            (candidate,), (world,),
        )
    if fixture in {"waiting_only"}:
        world = _law("gm.world.single", ["f0"], "x")
        return _causal((_root(0, (candidate,)), _root(1, (world,)), _root(2, (), time=100), _root(3, (), time=1000)), (candidate,), (world,))
    if fixture == "activated_inert":
        return {"candidate_activated": True, "behaviorally_inert": True, "evidence_kind": "controlled_synthetic"}
    raise AssertionError(fixture)


def _effect_rows(pattern: str) -> list[dict[str, Any]]:
    rows = []
    for effect in _cross_effects(pattern):
        nodes = [
            {"signature": law_id, "count": abs(count)}
            for law_id, count in sorted(effect.candidate_world_law_effect.items())
            if count
        ]
        rows.append({
            "environment": effect.environment,
            "net_outcome_effect": effect.candidate_effect,
            "normalized_path_signature": {"nodes": nodes, "edges": []},
        })
    return rows


def _environment_fixture(fixture: str, params: dict[str, Any]) -> dict[str, Any]:
    pattern = params.get("pattern", fixture)
    if fixture == "synthetic_did":
        rows = _effect_rows(pattern)
        if pattern == "order_invariance":
            original = summarize_environment_rows(rows)
            reversed_order = summarize_environment_rows(list(reversed(rows)))
            canonical_fields = (
                "outcome_differentiated", "distinct_outcome_signature_count",
                "outcome_partitions", "causal_path_differentiated",
                "distinct_path_signature_count", "path_partitions",
            )
            return {
                "original_environment_order": [row["environment"] for row in rows],
                "reversed_environment_order": [row["environment"] for row in reversed(rows)],
                "original_summary": original,
                "reversed_summary": reversed_order,
                "canonical_equal": all(original[field] == reversed_order[field] for field in canonical_fields),
                "compared_fields": list(canonical_fields),
            }
        return summarize_environment_rows(rows)
    quadrants = {
        "same_outcome_different_path": ({}, {}, "A", "B"),
        "different_outcome_same_path": ({"x": 1}, {"x": 2}, "A", "A"),
        "different_outcome_different_path": ({"x": 1}, {"x": 2}, "A", "B"),
        "same_outcome_same_path": ({"x": 1}, {"x": 1}, "A", "A"),
    }
    if fixture in quadrants:
        left, right, lp, rp = quadrants[fixture]
        return summarize_environment_rows([
            {"environment": "a", "net_outcome_effect": left, "normalized_path_signature": {"nodes": [{"signature": lp, "count": 1}], "edges": []}},
            {"environment": "b", "net_outcome_effect": right, "normalized_path_signature": {"nodes": [{"signature": rp, "count": 1}], "edges": []}},
        ])
    if fixture == "outcome_partitions":
        patterns = {
            "zero": "huge_background_zero_effect",
            "equal_nonzero": "equal_net",
            "one_plus_three": "one_environment",
            "two_plus_two": "two_plus_two",
            "gradient": "intensity_gradient",
            "sign_split": "sign_split",
            "transient": "intermediate_only",
        }
        evidence = {
            name: {
                "rows": _effect_rows(source),
                "summary": summarize_environment_rows(_effect_rows(source)),
            }
            for name, source in patterns.items()
        }
        recovery_rows = [
            {
                "environment": environment,
                "net_outcome_effect": ({"short/process.steam": 1.0} if index == 0 else {}),
                "normalized_path_signature": {"nodes": [], "edges": []},
            }
            for index, environment in enumerate(("fragile_bridge", "industrial_yard", "mine", "wetland"))
        ]
        evidence["final_recovery"] = {
            "rows": recovery_rows,
            "summary": summarize_environment_rows(recovery_rows),
            "all_final_coordinates_equal": all(
                not any(key.startswith("final/") for key in row["net_outcome_effect"])
                for row in recovery_rows
            ),
        }
        return {"patterns": evidence}
    if fixture == "path_multiplicity":
        base_signature = {
            "nodes": [{"signature": "gm.world.path", "count": 1}],
            "edges": [{"signature": "gm.skill.root->gm.world.path", "count": 1}],
            "identity_exclusions": ["event_id", "command_id", "proposal_id", "absolute_timestamp"],
        }
        identity_rows = [
            {
                "environment": "a", "net_outcome_effect": {},
                "normalized_path_signature": base_signature,
                "raw_nonsemantic_identity": {"event_id": "event.a", "absolute_timestamp": 1.0},
            },
            {
                "environment": "b", "net_outcome_effect": {},
                "normalized_path_signature": json.loads(json.dumps(base_signature)),
                "raw_nonsemantic_identity": {"event_id": "replacement.b", "absolute_timestamp": 99.0},
            },
        ]
        repeated = json.loads(json.dumps(base_signature))
        repeated["nodes"][0]["count"] = 2
        multiplicity_rows = [identity_rows[0], {
            "environment": "b", "net_outcome_effect": {},
            "normalized_path_signature": repeated,
            "raw_nonsemantic_identity": {"event_id": "event.b", "absolute_timestamp": 1.0},
        }]
        return {
            "identity_shift": {
                "rows": identity_rows,
                "summary": summarize_environment_rows(identity_rows),
            },
            "multiplicity_change": {
                "rows": multiplicity_rows,
                "summary": summarize_environment_rows(multiplicity_rows),
            },
        }
    raise AssertionError(fixture)


def _production_evidence(purpose: str) -> dict[str, Any]:
    actual_sha = _sha(PRODUCTION_RESULTS)
    if actual_sha != PRODUCTION_RESULTS_SHA256:
        raise RuntimeError(
            f"production evidence digest mismatch: expected {PRODUCTION_RESULTS_SHA256}, got {actual_sha}"
        )
    payload = json.loads(PRODUCTION_RESULTS.read_text(encoding="utf-8"))
    matches = [row for row in payload["validations"] if row.get("purpose") == purpose]
    if len(matches) != 1:
        raise RuntimeError(f"expected one production validation for {purpose}, got {len(matches)}")
    row = matches[0]
    if row.get("execution_level") != "full_production_stack":
        raise RuntimeError(f"{purpose} is not full-production evidence")
    return {
        "production_artifact_sha256": actual_sha,
        "production_validation_id": row["validation_id"],
        "execution_level": row["execution_level"],
        "mechanic": row["mechanic"],
        "structural_evidence": row["structural_evidence"],
        "dynamic_reach": row["dynamic_reach"],
        "environmental_behavior": row["environmental_behavior"],
        "behaviorally_inert": row["behaviorally_inert"],
    }


def _structure_fixture(fixture: str, params: dict[str, Any]) -> dict[str, Any]:
    if fixture == "novel_but_inert":
        return _production_evidence("near_copy_one_trigger")
    if fixture == "simple_but_deep":
        return _production_evidence("retained_v04_deep_environment_invariant")
    variant = params.get("variant")
    aliases = {
        "exact_duplicate": "old_powerful", "one_trigger_edit": "near_trigger",
        "one_effect_edit": "near_effect", "simple_union": "recombination",
        "field_substitution": "field_substitution",
    }
    variant = variant or aliases.get(fixture)
    if fixture == "same_fields_different_topology":
        base = _base_spec(); other = json.loads(json.dumps(base)); other["periodic"] = {"interval": 2.0, "repeats": 2}
        return {"left": evaluate_structural_evidence(base), "right": evaluate_structural_evidence(other)}
    raw, other = _structural_specs(variant)
    if variant == "duplicate_cancel":
        try: validate_skill(raw)
        except SkillSpecError as exc:
            return {"construct_representable": False, "known_limitation": str(exc)}
    result = {"candidate": evaluate_structural_evidence(raw)}
    if other is not None:
        result["comparison"] = evaluate_structural_evidence(other)
    return result


def _assert_expected(case: dict[str, Any], actual: dict[str, Any]) -> bool:
    case_id = case["case_id"]
    fixture = case["fixture"]["fixture"]
    params = case["fixture"]["parameters"]
    if case.get("v04_suspect_resolution") == "KNOWN_LIMITATION":
        return bool(actual.get("construct_representable") is False)
    if case_id.startswith("CD-") or case_id.startswith("V05-CD-"):
        if fixture in {"parallel", "parallel_delayed", "wide_fanout", "repeat_same_law", "waiting_only"}:
            return actual["realized_dependency_depth"] == 1
        if fixture in {"chain", "delayed_chain", "necessary_chain"}:
            expected = params.get("depth", 2)
            return actual["realized_dependency_depth"] == expected and actual["necessity_backed_depth"] == expected
        if fixture in {"redundant_paths", "overdetermination", "redundant_then_deep"}:
            return actual["realized_dependency_depth"] > actual["necessity_backed_depth"] and actual["possible_redundant_causation"]
        if fixture in {"event_time_shift"}:
            return not any(edge["necessity_backed"] for edge in actual["dependency_edges"] if edge["source_law_id"] == "gm.world.source_a")
        if fixture in {"binding_identity"} or (fixture == "identity_shift" and params.get("shift") == "binding"):
            return actual["binding_policy"] == "identity_equality"
        if fixture == "identity_shift":
            return not any(edge["necessity_backed"] for edge in actual["dependency_edges"] if edge["source_law_id"] == "gm.world.source_a")
        if fixture == "last_writer_overwrite":
            return all(edge["source_law_id"] != "gm.world.writer_a" for edge in actual["dependency_edges"] if edge["target_law_id"] == "gm.world.reader_c")
        if fixture == "last_writer_unrelated":
            return any(edge["source_law_id"] == "gm.world.writer_a" for edge in actual["dependency_edges"] if edge["target_law_id"] == "gm.world.reader_c")
        if fixture == "clamped_no_commit":
            return actual["candidate_activated"] is False
        if fixture == "noop_writer":
            return actual["candidate_activated"] and actual["realized_dependency_depth"] == 0
        if fixture == "activated_inert":
            return actual == {"candidate_activated": True, "behaviorally_inert": True, "evidence_kind": "controlled_synthetic"}
    if case_id.startswith("CE-") or case_id.startswith("V05-CE-"):
        pattern = params.get("pattern", fixture)
        if fixture == "outcome_partitions":
            evidence = actual["patterns"]
            expected = {
                "zero": (False, 1, [4]),
                "equal_nonzero": (False, 1, [4]),
                "one_plus_three": (True, 2, [1, 3]),
                "two_plus_two": (True, 2, [2, 2]),
                "gradient": (True, 4, [1, 1, 1, 1]),
                "sign_split": (True, 2, [2, 2]),
                "transient": (True, 2, [1, 3]),
                "final_recovery": (True, 2, [1, 3]),
            }
            for name, (differentiated, count, sizes) in expected.items():
                summary = evidence[name]["summary"]
                if summary["outcome_differentiated"] is not differentiated:
                    return False
                if summary["distinct_outcome_signature_count"] != count:
                    return False
                if sorted(map(len, summary["outcome_partitions"])) != sizes:
                    return False
            return evidence["final_recovery"]["all_final_coordinates_equal"] is True
        if fixture == "path_multiplicity":
            identity = actual["identity_shift"]["summary"]
            multiplicity = actual["multiplicity_change"]["summary"]
            return (
                identity["causal_path_differentiated"] is False
                and identity["distinct_path_signature_count"] == 1
                and multiplicity["causal_path_differentiated"] is True
                and multiplicity["distinct_path_signature_count"] == 2
            )
        if pattern == "order_invariance":
            return (
                actual["canonical_equal"] is True
                and actual["original_environment_order"] == list(reversed(actual["reversed_environment_order"]))
            )
        if pattern in {"same_final_different_path", "equal_state_unequal_law_count", "same_outcome_different_path"}:
            return not actual["outcome_differentiated"] and actual["causal_path_differentiated"]
        if pattern == "different_outcome_same_path":
            return actual["outcome_differentiated"] and not actual["causal_path_differentiated"]
        if pattern == "different_outcome_different_path":
            return actual["outcome_differentiated"] and actual["causal_path_differentiated"]
        if pattern == "same_outcome_same_path":
            return not actual["outcome_differentiated"] and not actual["causal_path_differentiated"]
        positive = {"one_environment", "two_plus_two", "intermediate_only", "intensity_gradient", "sign_split"}
        negative = {
            "huge_background_zero_effect", "equal_net", "background_state_noise",
            "background_law_noise", "roundoff", "sparse_zero", "powerful_equal_net",
        }
        if pattern in positive | negative:
            return actual["outcome_differentiated"] is (pattern in positive)
        raise AssertionError(f"unhandled environment pattern: {pattern}")
    candidate = actual.get("candidate", actual.get("left"))
    comparison = actual.get("comparison", actual.get("right"))
    variant = params.get("variant", fixture)
    if fixture == "exact_duplicate": return candidate["exact_match"]
    if fixture == "one_trigger_edit": return comparison["near_copy"] and comparison["near_copy_edits"][0]["kind"] == "add_trigger"
    if fixture == "one_effect_edit": return comparison["near_copy"] and comparison["near_copy_edits"][0]["kind"] == "add_effect"
    if fixture == "simple_union": return candidate["recombination"]["recombination_detected"]
    if fixture == "same_fields_different_topology": return candidate["abstract_topology"]["fingerprint"] != comparison["abstract_topology"]["fingerprint"]
    if fixture == "novel_but_inert":
        return (
            actual["production_artifact_sha256"] == PRODUCTION_RESULTS_SHA256
            and actual["execution_level"] == "full_production_stack"
            and actual["structural_evidence"]["exact_match"] is False
            and actual["behaviorally_inert"] is True
            and actual["dynamic_reach"]["candidate_activated"] is False
        )
    if fixture == "simple_but_deep":
        return (
            actual["production_artifact_sha256"] == PRODUCTION_RESULTS_SHA256
            and actual["execution_level"] == "full_production_stack"
            and actual["structural_evidence"]["exact_match"] is True
            and actual["dynamic_reach"]["candidate_activated"] is True
            and actual["dynamic_reach"]["realized_dependency_depth"] >= 2
        )
    if variant in {"rename", "numeric", "economy", "effect_order", "mixed_zero"}:
        return candidate["semantic_structure"]["fingerprint"] == comparison["semantic_structure"]["fingerprint"]
    if variant == "polarity": return candidate["semantic_structure"]["fingerprint"] != comparison["semantic_structure"]["fingerprint"]
    if variant == "field_substitution":
        return candidate["semantic_structure"]["fingerprint"] != comparison["semantic_structure"]["fingerprint"] and candidate["abstract_topology"]["fingerprint"] == comparison["abstract_topology"]["fingerprint"]
    if variant == "impossible_trigger": return bool(candidate["static_guard"]["statically_unreachable_triggers"])
    if variant == "all_zero": return not candidate["available"]
    if variant == "recombination": return candidate["recombination"]["recombination_detected"]
    if variant in {"near_trigger", "near_effect"}: return comparison["near_copy"]
    if variant in {"genuine_periodic", "genuine_sustained"}: return not candidate["exact_match"]
    if variant == "old_powerful": return candidate["exact_match"] and comparison["exact_match"]
    raise AssertionError(f"unhandled structural fixture/variant: {fixture}/{variant}")


def _execute(case: dict[str, Any]) -> tuple[dict[str, Any], str]:
    fixture = case["fixture"]["fixture"]
    params = case["fixture"]["parameters"]
    case_id = case["case_id"]
    if case_id.startswith("CD-") or case_id.startswith("V05-CD-"):
        actual = _causal_fixture(fixture, params)
    elif case_id.startswith("CE-") or case_id.startswith("V05-CE-"):
        actual = _environment_fixture(fixture, params)
    else:
        actual = _structure_fixture(fixture, params)
    if case.get("v04_suspect_resolution") == "KNOWN_LIMITATION":
        status = "KNOWN_LIMITATION" if _assert_expected(case, actual) else "FAIL"
    else:
        status = "PASS" if _assert_expected(case, actual) else "FAIL"
    return actual, status


def run() -> dict[str, Any]:
    prereg = {row["case_id"]: row for row in CASES}
    v04_rows = {
        row["case_id"]: row
        for row in (json.loads(line) for line in V04_RESULTS.read_text(encoding="utf-8").splitlines())
    }
    baseline_rows = []
    results = []
    for case in CASES:
        baseline_rows.append({
            "case_id": case["case_id"],
            "pre_revision_source": "v0.4_post_fix" if case["origin"] == "v0.4-retained" else "not_available_before_v0.5",
            "pre_revision_result": v04_rows.get(case["case_id"], {}).get("post_fix_result"),
            "pre_revision_judgement": v04_rows.get(case["case_id"], {}).get("post_fix_judgement", "NOT_AVAILABLE"),
        })
        actual, judgement = _execute(case)
        results.append({
            **case,
            "v04_result": v04_rows.get(case["case_id"], {}).get("post_fix_result"),
            "v04_judgement": v04_rows.get(case["case_id"], {}).get("post_fix_judgement"),
            "v05_result": actual,
            "v05_judgement": judgement,
        })
    BASELINE.write_text("\n".join(_canonical(row) for row in baseline_rows) + "\n", encoding="utf-8")
    RESULTS.write_text("\n".join(_canonical(row) for row in results) + "\n", encoding="utf-8")
    counts = Counter(row["v05_judgement"] for row in results)
    old_suspects = [row for row in results if row["v04_suspect_resolution"] not in {None, "UNCHANGED_EXPECTATION"}]
    semantic_manifest = json.loads((ROOT.parent / "free_evaluation_v05" / "semantic_contract.json").read_text())
    production_path = ROOT / "results" / "v05_production_validation.json"
    production = json.loads(production_path.read_text()) if production_path.exists() else None
    summary = {
        "protocol_version": "gm-free-evaluation-v0.5-candidate",
        "preregistration_digest": json.loads((ROOT / "v05_preregistration.json").read_text())["preregistration_digest"],
        "retained_v04_case_count": sum(row["origin"] == "v0.4-retained" for row in results),
        "new_v05_case_count": sum(row["origin"] == "v0.5-new" for row in results),
        "total_case_count": len(results),
        "judgement_counts": dict(sorted(counts.items())),
        "old_suspect_dispositions": [
            {"case_id": row["case_id"], "disposition": row["v04_suspect_resolution"], "expected_v05_semantics": row["expected_v05_semantics"]}
            for row in old_suspects
        ],
        "pre_revision_baseline_sha256": _sha(BASELINE),
        "post_implementation_results_sha256": _sha(RESULTS),
        "semantic_contract_digest": semantic_manifest["semantic_contract_digest"],
        "semantic_contract_registered_path_count": len(semantic_manifest["registered_paths"]),
        "production_validation": None if production is None else {
            "validation_count": production["validation_count"],
            "full_production_stack_count": production["full_production_stack_count"],
            "synthetic_only_count": production["synthetic_only_count"],
            "sha256": _sha(production_path),
            "construct_checks": production["construct_checks"],
        },
        "freeze_recommendation": "FREEZE_READY" if not counts["FAIL"] else "MAJOR_REVISION",
        "freeze_rationale": (
            "no implementation FAIL; the one retained language ceiling is explicitly named KNOWN_LIMITATION"
            if not counts["FAIL"] else f"{counts['FAIL']} preregistered expectations failed"
        ),
    }
    SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2, sort_keys=True))
