"""Register and execute the adversarial v0.4 measurement suite.

Registration and execution are separate commands so expectations are hashed on
disk before any evaluator is called. The executor never edits the production
metrics; it records their original ``de5451c`` behavior verbatim.
"""

from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from typing import Any

from pmw import parse_law

from experiments.generative_mechanics.causal_depth_v04 import causal_depth_from_runs
from experiments.generative_mechanics.cross_environment_v04 import (
    CrossEnvironmentDifferentiation,
    EnvironmentEffect,
    PUBLIC_INITIAL_FIELDS,
    QUARTET_ENVIRONMENTS,
    _pairwise,
    _subtract,
)
from experiments.generative_mechanics.runner import RootExecution, ScenarioRun
from experiments.generative_mechanics.spec import SkillSpecError, validate_skill
from experiments.generative_mechanics.structural_novelty import (
    canonical_structure,
    evaluate_structural_novelty,
    structure_fingerprint,
)

from .case_registry import CASES


ROOT = Path(__file__).resolve().parent
CASES_PATH = ROOT / "adversarial_cases.jsonl"
RESULTS_PATH = ROOT / "adversarial_results.jsonl"
RAW_PATH = ROOT / "results" / "pre_fix_raw.jsonl"
SUMMARY_PATH = ROOT / "summary.json"
BASE_COMMIT = "de5451ceaeb020b2ceac1ce6b87752ade0988244"
ZONE = "zone:audit"


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def register() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    (ROOT / "cases").mkdir(exist_ok=True)
    (ROOT / "results").mkdir(exist_ok=True)
    if len(CASES) != 48 or len({case["case_id"] for case in CASES}) != 48:
        raise RuntimeError("the preregistered audit must contain exactly 48 unique cases")
    lines = [canonical_json(case) for case in CASES]
    CASES_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    metadata = {
        "base_commit": BASE_COMMIT,
        "case_count": len(CASES),
        "by_metric": dict(sorted(Counter(case["target_metric"] for case in CASES).items())),
        "cross_metric_case_ids": [case["case_id"] for case in CASES if "cross_metric" in case["tags"]],
        "adversarial_cases_sha256": sha256(CASES_PATH),
        "execution_status": "not_run",
    }
    (ROOT / "cases" / "preregistration.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _law(law_id: str, reads: list[str], write: str):
    conditions: list[dict[str, Any]] = [{"event.type": {"eq": "lab.step"}}]
    conditions.extend({"ref": f"$zone.fields.{field}", "gt": 0} for field in reads)
    return parse_law({
        "id": law_id,
        "mode": "event",
        "priority": 0,
        "bindings": {"zone": {"kind": "entity", "requires": ["fields"]}},
        "when": {"all": conditions},
        "effects": [{"op": "delta", "target": f"$zone.fields.{write}", "value": 1}],
    })


def _root(
    index: int,
    rules: tuple[Any, ...],
    *,
    event_id: str | None = None,
    time: float | None = None,
    binding: str = ZONE,
    no_commit: bool = False,
) -> RootExecution:
    event_id = event_id or f"event.{index:03d}"
    proposals, matches, deltas = [], [], []
    for serial, rule in enumerate(rules, 1):
        proposal_id = f"p:{event_id}:{serial}"
        target = rule.effects[0]["target"].removeprefix("$zone.").replace(".", "/")
        address = f"entity:{binding}/{target}"
        matches.append({
            "law_id": rule.law_id,
            "mode": "event",
            "bindings": {"zone": binding},
            "proposal_ids": [proposal_id],
        })
        proposals.append({"proposal_id": proposal_id, "law_id": rule.law_id})
        if not no_commit:
            deltas.append({
                "address": address,
                "old": 0,
                "new": 1,
                "proposal_ids": [proposal_id],
                "law_ids": [rule.law_id],
            })
    accepted = [] if no_commit else [item["proposal_id"] for item in proposals]
    event = {
        "id": event_id,
        "type": "lab.step",
        "time": float(index if time is None else time),
        "source": None,
        "target": binding,
        "payload": {},
        "provenance": {"kind": "external", "parent_event": None},
    }
    trace = {
        "root_event": event,
        "events": [{
            "event": event,
            "event_law_matches": matches,
            "state_law_matches": [],
            "commits": [{
                "microstep": 0,
                "phase": "event",
                "accepted_proposal_ids": accepted,
                "rejected_proposal_ids": [],
                "state_deltas": deltas,
                "derived_event_ids": [],
                "scheduled_event_ids": [],
                "cancelled_event_ids": [],
                "rescheduled_events": [],
            }],
        }],
        "proposals": proposals,
        "conflicts": [],
    }
    return RootExecution(f"cmd.{index:03d}", event_id, "lab.step", tuple(rule.law_id for rule in rules), trace)


def _run(*roots: RootExecution) -> ScenarioRun:
    return ScenarioRun("audit.scenario", "audit", "mine", (), {}, tuple(roots), {}, {})


def _causal_eval(
    present: tuple[RootExecution, ...],
    candidate_laws: tuple[Any, ...],
    world_laws: tuple[Any, ...],
    *,
    absent: tuple[RootExecution, ...] = (),
    ablations: dict[str, ScenarioRun] | None = None,
):
    return causal_depth_from_runs(
        _run(*present),
        _run(*absent),
        "audit_candidate",
        world_laws=world_laws,
        candidate_laws=candidate_laws,
        world_law_ablations=ablations or {},
    )


def execute_causal(case: dict[str, Any]) -> tuple[dict[str, Any], str, str | None]:
    fixture = case["mechanic/spec"]["fixture"]
    params = case["mechanic/spec"]["parameters"]
    candidate = _law("gm.skill.audit.activate", [], "f0")
    evidence: dict[str, Any]

    if fixture in {"parallel", "parallel_delayed"}:
        width = params["width"]
        candidates = tuple(_law(f"gm.skill.audit.root{i}", [], f"f{i}") for i in range(width))
        worlds = tuple(_law(f"gm.world.parallel{i}", [f"f{i}"], f"o{i}") for i in range(width))
        roots = [_root(0, candidates)]
        roots.extend(_root(i + 1, (law,), time=(i + 1) * 10 if fixture.endswith("delayed") else i + 1) for i, law in enumerate(worlds))
        result = _causal_eval(tuple(roots), candidates, worlds)
        ok = result.depth == 1
        evidence = result.to_dict()
    elif fixture in {"chain", "delayed_chain"}:
        depth = params.get("depth", 2)
        worlds = tuple(_law(f"gm.world.chain{i+1}", [f"f{i}"], f"f{i+1}") for i in range(depth))
        roots = [_root(0, (candidate,))]
        roots.extend(_root(i + 1, (law,), time=(i + 1) * 12 if fixture == "delayed_chain" else i + 1) for i, law in enumerate(worlds))
        ablations = {
            law.law_id: _run(*roots[: i + 1])
            for i, law in enumerate(worlds)
        }
        result = _causal_eval(tuple(roots), (candidate,), worlds, ablations=ablations)
        ok = result.depth == depth
        evidence = result.to_dict()
    elif fixture == "repeat_same_law":
        repeated = _law("gm.world.repeat", ["f0"], "f0")
        result = _causal_eval(
            (_root(0, (candidate,)), _root(1, (repeated,)), _root(2, (repeated,))),
            (candidate,), (repeated,),
            ablations={repeated.law_id: _run(_root(0, (candidate,)))},
        )
        ok = result.depth == 1
        evidence = result.to_dict()
    elif fixture == "redundant_paths":
        a = _law("gm.world.path_a", ["f0"], "x")
        b = _law("gm.world.path_b", ["f0"], "x")
        c = _law("gm.world.path_c", ["x"], "z")
        present = (_root(0, (candidate,)), _root(1, (a, b)), _root(2, (c,)))
        ablations = {
            a.law_id: _run(_root(0, (candidate,)), _root(1, (b,)), _root(2, (c,))),
            b.law_id: _run(_root(0, (candidate,)), _root(1, (a,)), _root(2, (c,))),
        }
        result = _causal_eval(present, (candidate,), (a, b, c), ablations=ablations)
        retained_c = "gm.world.path_c" in result.reached_world_law_ids
        ok = retained_c
        evidence = {**result.to_dict(), "semantic_downstream_c_still_occurs_in_both_ablations": True}
        if not ok:
            return evidence, "SUSPECT", "construct limitation: single-law necessity ablation loses overdetermined downstream causation"
    elif fixture == "identity_shift":
        a = _law("gm.world.source_a", ["f0"], "x")
        c = _law("gm.world.downstream_c", ["x"], "z")
        present = (_root(0, (candidate,)), _root(1, (a,)), _root(2, (c,), event_id="event.C", time=2))
        shift = params["shift"]
        kwargs: dict[str, Any] = {"event_id": "event.C", "time": 2, "binding": ZONE}
        if shift == "event_id":
            kwargs["event_id"] = "replacement.C"
        elif shift == "timestamp":
            kwargs["time"] = 2.5
        else:
            kwargs["binding"] = "zone:audit:equivalent"
        ablated_c = _root(2, (c,), **kwargs)
        result = _causal_eval(
            present, (candidate,), (a, c),
            ablations={a.law_id: _run(_root(0, (candidate,)), ablated_c)},
        )
        false_edge = any(edge.ablation.get("excluded") == a.law_id for edge in result.edges)
        evidence = {
            **result.to_dict(),
            "ablation_semantic_outcome_preserved": True,
            "identity_shift": shift,
            "false_source_to_downstream_edge": false_edge,
        }
        if false_edge:
            classification = "FAIL" if shift in {"event_id", "timestamp"} else "SUSPECT"
            return evidence, classification, "measurement failure: occurrence identity drift is treated as semantic removal"
        ok = True
    elif fixture in {"last_writer_overwrite", "last_writer_unrelated"}:
        a = _law("gm.world.writer_a", ["f0"], "x")
        b_write = "x" if fixture.endswith("overwrite") else "other"
        b = _law("gm.world.writer_b", ["f0"], b_write)
        c = _law("gm.world.reader_c", ["x"], "z")
        present = (_root(0, (candidate,)), _root(1, (a,)), _root(2, (b,)), _root(3, (c,)))
        if fixture.endswith("overwrite"):
            ablations = {
                a.law_id: _run(_root(0, (candidate,)), _root(2, (b,)), _root(3, (c,))),
                b.law_id: _run(_root(0, (candidate,)), _root(1, (a,))),
            }
            expected_parent = b.law_id
        else:
            ablations = {a.law_id: _run(_root(0, (candidate,)), _root(2, (b,)))}
            expected_parent = a.law_id
        result = _causal_eval(present, (candidate,), (a, b, c), ablations=ablations)
        parents = {
            next(node.law_id for node in result.nodes if node.node_id == edge.source)
            for edge in result.edges
            if next(node.law_id for node in result.nodes if node.node_id == edge.target) == c.law_id
        }
        ok = parents == {expected_parent}
        evidence = {**result.to_dict(), "actual_c_parents": sorted(parents), "expected_c_parent": expected_parent}
    elif fixture == "clamped_no_commit":
        result = _causal_eval((_root(0, (candidate,), no_commit=True),), (candidate,), ())
        ok = not result.available and result.candidate_activated is False
        evidence = result.to_dict()
    elif fixture == "waiting_only":
        world = _law("gm.world.single", ["f0"], "x")
        result = _causal_eval(
            (_root(0, (candidate,)), _root(1, (world,)), _root(2, (), time=100), _root(3, (), time=1000)),
            (candidate,), (world,),
        )
        ok = result.depth == 1
        evidence = result.to_dict()
    else:
        raise AssertionError(fixture)
    return evidence, "PASS" if ok else "FAIL", None if ok else "observed result violates preregistered semantic relation"


def _effect(
    environment: str,
    present: dict[str, float],
    absent: dict[str, float],
    present_laws: dict[str, int] | None = None,
    absent_laws: dict[str, int] | None = None,
) -> EnvironmentEffect:
    p_laws = present_laws or {}
    a_laws = absent_laws or {}
    return EnvironmentEffect(
        environment,
        dict(PUBLIC_INITIAL_FIELDS),
        {"background": float(QUARTET_ENVIRONMENTS.index(environment))},
        present,
        absent,
        p_laws,
        a_laws,
        _subtract(present, absent),
        {key: int(value) for key, value in _subtract(Counter(p_laws), Counter(a_laws)).items()},
    )


def _cross_report(effects: list[EnvironmentEffect]) -> dict[str, Any]:
    ordered = tuple(effects)
    pairs = tuple(_pairwise(ordered[left], ordered[right]) for left in range(4) for right in range(left + 1, 4))
    return CrossEnvironmentDifferentiation(
        "audit", "world_substrate", "candidate", "audit", dict(PUBLIC_INITIAL_FIELDS),
        tuple(item.environment for item in ordered), ordered, pairs,
    ).to_dict()


def _cross_effects(pattern: str) -> list[EnvironmentEffect]:
    effects: list[EnvironmentEffect] = []
    for index, env in enumerate(QUARTET_ENVIRONMENTS):
        background = 100.0 * index
        present = {"final/outcome.x": background}
        absent = {"final/outcome.x": background}
        p_laws: dict[str, int] = {}
        a_laws: dict[str, int] = {}
        if pattern in {"equal_net", "powerful_equal_net"}:
            present["final/outcome.x"] += 0.9 if pattern.startswith("powerful") else 0.2
        elif pattern == "one_environment" and env == "wetland":
            present["final/outcome.x"] += 1
            p_laws["gm.world.extra"] = 1
        elif pattern == "two_plus_two":
            present["final/outcome.x"] += 1 if env in {"mine", "industrial_yard"} else -1
        elif pattern in {"same_final_different_path", "equal_state_unequal_law_count"}:
            present["final/outcome.x"] += 1
            p_laws[f"gm.world.path_{index % 2}"] = (index + 1 if pattern.endswith("law_count") else 1)
        elif pattern == "intermediate_only":
            present["final/outcome.x"] += 0
            present["short/process.steam"] = 1 if index == 0 else 0
            absent["short/process.steam"] = 0
        elif pattern == "intensity_gradient":
            present["final/outcome.x"] += (0.1, 0.2, 0.4, 0.8)[index]
        elif pattern == "background_state_noise":
            present["final/outcome.noise"] = index * 50
            absent["final/outcome.noise"] = index * 50
            present["final/outcome.x"] += 0.2
        elif pattern == "background_law_noise":
            p_laws[f"gm.world.background_{index}"] = 100 + index
            a_laws[f"gm.world.background_{index}"] = 100 + index
        elif pattern == "roundoff":
            present["final/outcome.x"] += index * 1e-14
        elif pattern == "sparse_zero":
            if index % 2:
                present["final/outcome.optional"] = 0.0
        elif pattern == "sign_split":
            present["final/outcome.x"] += 0.2 if index < 2 else -0.2
        effects.append(_effect(env, present, absent, p_laws, a_laws))
    return effects


def execute_cross(case: dict[str, Any]) -> tuple[dict[str, Any], str, str | None]:
    pattern = case["mechanic/spec"]["parameters"]["pattern"]
    effects = _cross_effects(pattern)
    report = _cross_report(effects)
    summary = report["summary"]
    if pattern == "order_invariance":
        left = _cross_report(effects)
        right = _cross_report(list(reversed(effects)))
        left_pairs = sorted((p["environments"], p["state_l1"], p["world_law_l1"]) for p in left["pairwise_contrasts"])
        right_pairs = sorted((sorted(p["environments"]), p["state_l1"], p["world_law_l1"]) for p in right["pairwise_contrasts"])
        left_pairs = sorted((sorted(envs), s, w) for envs, s, w in left_pairs)
        ok = left_pairs == right_pairs
        evidence = {"original": left, "permuted": right, "canonical_pairwise_equal": ok}
    elif pattern in {"same_final_different_path", "equal_state_unequal_law_count"}:
        state_zero = summary["max_pairwise_state_l1"] == 0
        law_positive = summary["max_pairwise_world_law_l1"] > 0
        evidence = report
        if state_zero and law_positive:
            return evidence, "SUSPECT", "construct limitation: one boolean combines outcome differentiation with causal-path-count differentiation"
        ok = False
    elif pattern in {"one_environment", "two_plus_two", "intermediate_only", "intensity_gradient", "sign_split"}:
        ok = summary["environmentally_differentiated"] is True
        if pattern == "two_plus_two":
            ok = ok and summary["distinct_net_signature_count"] == 2
        evidence = report
    else:
        ok = summary["environmentally_differentiated"] is False
        evidence = report
    return evidence, "PASS" if ok else "FAIL", None if ok else "observed DiD evidence violates preregistered relation"


def _base_spec() -> dict[str, Any]:
    return {
        "id": "audit_seed",
        "name": "Audit Seed",
        "target_scope": "zone",
        "effects": [{"field": "temperature", "delta": 0.3}],
        "duration": 0.0,
        "periodic": None,
        "trigger_conditions": [],
        "resource_cost": 5.0,
        "charges": 3,
        "slot_cost": 1,
    }


def _structural_specs(variant: str) -> tuple[dict[str, Any], dict[str, Any] | None]:
    base = _base_spec()
    other: dict[str, Any] | None = deepcopy(base)
    if variant == "rename":
        base["id"], base["name"] = "boiler_field", "Boiler Field"
        other["id"], other["name"] = "renamed_boiler", "Entirely Different Text"
    elif variant == "numeric":
        base.update({"id": "bedrock_memory", "duration": 6.0})
        base["effects"] = [{"field": "ground_stability", "delta": 0.45}]
        other = deepcopy(base); other["id"] = "retuned"; other["duration"] = 37.0; other["effects"][0]["delta"] = 0.71
    elif variant == "economy":
        other.update({"id": "economy_change", "resource_cost": 99.0, "charges": 91, "slot_cost": 2})
    elif variant == "effect_order":
        base["effects"] = [{"field": "temperature", "delta": 0.3}, {"field": "wetness", "delta": -0.4}]
        other["effects"] = list(reversed(base["effects"]))
    elif variant == "polarity":
        other["effects"][0]["delta"] = -0.3
    elif variant == "field_substitution":
        base["effects"] = [{"field": "wetness", "delta": 0.4}]
        other["effects"] = [{"field": "sound_level", "delta": 0.4}]
    elif variant == "impossible_trigger":
        base.update({"id": "dead_trigger", "effects": [{"field": "temperature", "delta": 0.4}], "trigger_conditions": [{"field": "temperature", "op": "gt", "value": 1.0}]})
        other = None
    elif variant == "all_zero":
        base.update({"id": "all_zero", "effects": [{"field": "temperature", "delta": 0.0}, {"field": "wetness", "delta": 0.0}]})
        other = None
    elif variant == "mixed_zero":
        base["id"] = "boiler_field"
        other = deepcopy(base); other["id"] = "mixed_zero"; other["effects"].append({"field": "wetness", "delta": 0.0})
    elif variant == "recombination":
        base.update({"id": "recombined", "effects": [{"field": "temperature", "delta": 0.3}, {"field": "wetness", "delta": -0.4}]})
        other = None
    elif variant == "near_trigger":
        base["id"] = "boiler_field"
        other = deepcopy(base); other["id"] = "near_trigger"; other["trigger_conditions"] = [{"field": "wetness", "op": "gt", "value": 0.5}]
    elif variant == "near_effect":
        base["id"] = "boiler_field"
        other = deepcopy(base); other["id"] = "near_effect"; other["effects"].append({"field": "wetness", "delta": 0.2})
    elif variant == "genuine_periodic":
        base.update({"id": "periodic_conditional", "effects": [{"field": "temperature", "delta": 0.2}, {"field": "electric_field", "delta": -0.2}, {"field": "visibility", "delta": 0.1}], "periodic": {"interval": 3.0, "repeats": 4}, "trigger_conditions": [{"field": "wetness", "op": "gt", "value": 0.4}, {"field": "sound_level", "op": "lt", "value": 0.7}]})
        other = None
    elif variant == "genuine_sustained":
        base.update({"id": "sustained_conditional", "effects": [{"field": "water_level", "delta": 0.2}, {"field": "ground_stability", "delta": -0.3}, {"field": "fire_intensity", "delta": -0.2}], "duration": 23.0, "trigger_conditions": [{"field": "temperature", "op": "gte", "value": 0.6}, {"field": "visibility", "op": "neq", "value": 0.2}]})
        other = None
    elif variant == "duplicate_cancel":
        base.update({"id": "duplicate_cancel", "effects": [{"field": "temperature", "delta": 0.5}, {"field": "temperature", "delta": -0.5}]})
        other = None
    elif variant == "old_powerful":
        base.update({"id": "thermal_lance", "effects": [{"field": "temperature", "delta": 0.5}], "resource_cost": 9.0})
        other = deepcopy(base); other["id"] = "overclocked_lance"; other["effects"][0]["delta"] = 1.0; other["resource_cost"] = 100.0
    else:
        raise AssertionError(variant)
    return base, other


def execute_structural(case: dict[str, Any]) -> tuple[dict[str, Any], str, str | None]:
    variant = case["mechanic/spec"]["parameters"]["variant"]
    base, other = _structural_specs(variant)
    if variant == "duplicate_cancel":
        try:
            validate_skill(base)
        except SkillSpecError as exc:
            return {"validation_error": str(exc), "construct_representable": False}, "SUSPECT", "construct limitation: SkillSpec cannot express same-field setup/payoff cancellation"
        return {"construct_representable": True}, "FAIL", "duplicate-field cancellation unexpectedly accepted"

    base_result = evaluate_structural_novelty(base)
    evidence: dict[str, Any] = {"candidate": base_result}
    ok = True
    if other is not None:
        other_result = evaluate_structural_novelty(other)
        evidence["comparison"] = other_result
        same = base_result["structural_fingerprint"] == other_result["structural_fingerprint"]
        if variant in {"rename", "numeric", "economy", "effect_order", "mixed_zero"}:
            ok = same
        elif variant in {"polarity", "field_substitution"}:
            ok = not same
            if variant == "field_substitution" and ok:
                return evidence, "SUSPECT", "construct limitation: canonical structure is semantic-channel-sensitive, not abstract graph topology"
        elif variant == "near_trigger" or variant == "near_effect":
            saturated = other_result["exact_novel_against_registry"] is True
            evidence["near_copy_exact_novel"] = saturated
            return evidence, "SUSPECT" if saturated else "PASS", "construct limitation: exact novelty saturates after one small edit" if saturated else None
        elif variant == "old_powerful":
            ok = not base_result["exact_novel_against_registry"] and not other_result["exact_novel_against_registry"]
    elif variant == "impossible_trigger":
        declared = base_result.get("available") and base_result.get("exact_novel_against_registry")
        evidence["behaviorally_inert_by_public_domain"] = True
        if declared:
            return evidence, "FAIL", "measurement failure: unreachable dead code is reported as available exact structural novelty"
        ok = base_result.get("available") is False and base_result.get("excluded_from_novelty_rate") is True
    elif variant == "all_zero":
        ok = base_result["available"] is False and base_result["excluded_from_novelty_rate"] is True
    elif variant == "recombination":
        exact = base_result.get("exact_novel_against_registry") is True
        evidence["known_module_recombination"] = ["positive temperature seed", "negative wetness seed"]
        return evidence, "SUSPECT" if exact else "PASS", "construct limitation: exact novelty does not distinguish recombination from genuinely new topology" if exact else None
    elif variant in {"genuine_periodic", "genuine_sustained"}:
        frontier = base_result["pareto_reference_frontier"]
        nonzero_components = max(sum(bool(value) for value in item["difference_components"].values()) for item in frontier)
        evidence["maximum_nonzero_difference_components_on_frontier"] = nonzero_components
        ok = base_result["exact_novel_against_registry"] is True and nonzero_components >= 3
    return evidence, "PASS" if ok else "FAIL", None if ok else "observed structural evidence violates preregistered relation"


def execute() -> None:
    prereg = json.loads((ROOT / "cases" / "preregistration.json").read_text(encoding="utf-8"))
    if prereg["execution_status"] != "not_run" or prereg["adversarial_cases_sha256"] != sha256(CASES_PATH):
        raise RuntimeError("preregistration is missing, modified, or already consumed")
    registered = [json.loads(line) for line in CASES_PATH.read_text(encoding="utf-8").splitlines()]
    rows = []
    raw_rows = []
    for case in registered:
        if case["target_metric"] == "downstream_causal_depth":
            evidence, judgement, issue = execute_causal(case)
        elif case["target_metric"] == "cross_environment_differentiation":
            evidence, judgement, issue = execute_cross(case)
        else:
            evidence, judgement, issue = execute_structural(case)
        raw = {
            "case_id": case["case_id"],
            "base_commit": BASE_COMMIT,
            "preregistration_sha256": prereg["adversarial_cases_sha256"],
            "raw_evaluator_result": evidence,
        }
        raw_rows.append(raw)
        rows.append({
            **case,
            "actual_result": evidence,
            "judgement": judgement,
            "issue_classification": issue,
            "pre_fix_result": evidence,
            "proposed_correction": None,
            "post_fix_result": None,
        })
    RAW_PATH.write_text("\n".join(canonical_json(row) for row in raw_rows) + "\n", encoding="utf-8")
    RESULTS_PATH.write_text("\n".join(canonical_json(row) for row in rows) + "\n", encoding="utf-8")
    counts = Counter(row["judgement"] for row in rows)
    issues = {
        "implementation bug": [],
        "measurement failure": [],
        "construct limitation": [],
    }
    for row in rows:
        issue = row["issue_classification"] or ""
        for kind in issues:
            if issue.startswith(kind):
                issues[kind].append({"case_id": row["case_id"], "reason": issue})
    summary = {
        "base_commit": BASE_COMMIT,
        "preregistration_sha256": prereg["adversarial_cases_sha256"],
        "raw_results_sha256": sha256(RAW_PATH),
        "total_cases": len(rows),
        "by_metric": dict(sorted(Counter(row["target_metric"] for row in rows).items())),
        "cross_metric_case_count": sum("cross_metric" in row["tags"] for row in rows),
        "cross_metric_case_ids": [row["case_id"] for row in rows if "cross_metric" in row["tags"]],
        "pass": counts["PASS"],
        "suspect": counts["SUSPECT"],
        "fail": counts["FAIL"],
        "confirmed_implementation_bugs": issues["implementation bug"],
        "confirmed_measurement_failures": issues["measurement failure"],
        "construct_limitations": issues["construct limitation"],
        "changes_made": [],
        "freeze_recommendation": "pending_manual_review",
    }
    SUMMARY_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    prereg["execution_status"] = "executed_once"
    prereg["raw_results_sha256"] = summary["raw_results_sha256"]
    (ROOT / "cases" / "preregistration.json").write_text(json.dumps(prereg, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def post_fix() -> None:
    """Append post-fix observations without mutating preregistration or raw data."""
    prereg = json.loads((ROOT / "cases" / "preregistration.json").read_text(encoding="utf-8"))
    if prereg.get("execution_status") != "executed_once":
        raise RuntimeError("post-fix execution requires preserved pre-fix evidence")
    if prereg["adversarial_cases_sha256"] != sha256(CASES_PATH):
        raise RuntimeError("preregistered cases changed after execution")
    if prereg.get("raw_results_sha256") != sha256(RAW_PATH):
        raise RuntimeError("pre-fix raw results changed")
    rows = [json.loads(line) for line in RESULTS_PATH.read_text(encoding="utf-8").splitlines()]
    post_raw = []
    for row in rows:
        if row["target_metric"] == "downstream_causal_depth":
            evidence, judgement, issue = execute_causal(row)
        elif row["target_metric"] == "cross_environment_differentiation":
            evidence, judgement, issue = execute_cross(row)
        else:
            evidence, judgement, issue = execute_structural(row)
        row["post_fix_result"] = evidence
        row["post_fix_judgement"] = judgement
        if row["case_id"] in {"CD-09", "CD-10"}:
            row["proposed_correction"] = "pair occurrences by semantic event type/phase/law/bindings/read-write/committed-result signature with Counter multiplicity; exclude generated ids and absolute time"
        elif row["case_id"] == "SN-07":
            row["proposed_correction"] = "mark triggers provably unreachable at normalized domain boundaries unavailable and excluded from novelty rate"
        post_raw.append({"case_id": row["case_id"], "post_fix_evaluator_result": evidence, "post_fix_judgement": judgement, "remaining_issue": issue})
    post_path = ROOT / "results" / "post_fix_raw.jsonl"
    post_path.write_text("\n".join(canonical_json(row) for row in post_raw) + "\n", encoding="utf-8")
    RESULTS_PATH.write_text("\n".join(canonical_json(row) for row in rows) + "\n", encoding="utf-8")
    summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    post_counts = Counter(row["post_fix_judgement"] for row in rows)
    summary["post_fix"] = {
        "raw_results_sha256": sha256(post_path),
        "pass": post_counts["PASS"],
        "suspect": post_counts["SUSPECT"],
        "fail": post_counts["FAIL"],
    }
    summary["changes_made"] = [
        {
            "component": "causal occurrence matching",
            "reason": "remove non-semantic command/event identity and absolute time while retaining law, bindings, read/write and committed-result signatures, phase, event type, and Counter multiplicity",
            "fixed_cases": ["CD-09", "CD-10"],
        },
        {
            "component": "structural novelty no-op guard",
            "reason": "fail closed for triggers provably unreachable at normalized [0,1] boundaries",
            "fixed_cases": ["SN-07"],
        },
    ]
    SUMMARY_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("register", "execute", "post-fix"))
    args = parser.parse_args()
    if args.command == "register":
        register()
    elif args.command == "execute":
        execute()
    else:
        post_fix()


if __name__ == "__main__":
    main()
