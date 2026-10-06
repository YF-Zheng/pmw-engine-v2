"""Human-authored preregistration for the v0.4 adversarial audit.

The registry contains semantic expectations only. Runtime observations and
judgements are deliberately produced by ``run_audit.py`` after registration.
"""

from __future__ import annotations

from typing import Any


def _case(
    case_id: str,
    target_metric: str,
    fixture: str,
    expected_semantic_behavior: str,
    expected_metric_relation: str,
    attack_rationale: str,
    *,
    parameters: dict[str, Any] | None = None,
    tags: list[str] | None = None,
    expected_outcome: str = "pass",
) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "target_metric": target_metric,
        "mechanic/spec": {"fixture": fixture, "parameters": parameters or {}},
        "expected_semantic_behavior": expected_semantic_behavior,
        "expected_metric_relation": expected_metric_relation,
        "attack_rationale": attack_rationale,
        "expected_outcome": expected_outcome,
        "tags": tags or [],
    }


CAUSAL_CASES = [
    _case("CD-01", "downstream_causal_depth", "parallel", "Two directly triggered world laws are siblings, not a chain.", "depth(parallel_2) == 1", "Parallel fan-out must not inflate path depth.", parameters={"width": 2}),
    _case("CD-02", "downstream_causal_depth", "parallel", "Four directly triggered world laws remain one downstream layer.", "depth(parallel_4) == depth(parallel_2)", "Wider fan-out must not inflate depth.", parameters={"width": 4}),
    _case("CD-03", "downstream_causal_depth", "parallel_delayed", "Sibling laws occurring at different timestamps remain causally parallel.", "depth(delayed_parallel) == 1", "Elapsed time and event count are excluded from depth.", parameters={"width": 3}),
    _case("CD-04", "downstream_causal_depth", "chain", "One world law reads the candidate write.", "depth(chain_1) == 1", "Positive depth-one anchor.", parameters={"depth": 1}),
    _case("CD-05", "downstream_causal_depth", "chain", "A two-law write/read chain has two downstream layers.", "depth(chain_2) > depth(chain_1)", "Positive depth staircase.", parameters={"depth": 2}),
    _case("CD-06", "downstream_causal_depth", "chain", "A three-law write/read chain has three downstream layers.", "depth(chain_3) > depth(chain_2)", "Positive depth staircase.", parameters={"depth": 3}, tags=["cross_metric", "deep_environment_invariant"]),
    _case("CD-07", "downstream_causal_depth", "repeat_same_law", "Repeated executions of one law are one structural layer.", "depth(repeated_same_law) == 1", "Occurrence multiplicity must not become topology."),
    _case("CD-08", "downstream_causal_depth", "redundant_paths", "Two sufficient same-order writers jointly overdetermine a downstream law; removing either leaves it.", "depth(redundant_paths) should retain downstream C", "Law-by-law necessity ablation may erase overdetermined but genuinely downstream effects.", expected_outcome="suspect"),
    _case("CD-09", "downstream_causal_depth", "identity_shift", "After ablating A, an alternative event with a new id produces the same downstream law and semantic state.", "edge(A,C) == absent", "pair_key includes event id; non-semantic identity drift may create a false ablation edge.", parameters={"shift": "event_id"}, expected_outcome="fail"),
    _case("CD-10", "downstream_causal_depth", "identity_shift", "After ablating A, the same downstream consequence occurs at a shifted timestamp via an alternative path.", "edge(A,C) == absent", "pair_key includes timestamp; timing drift can look like occurrence removal even when semantic outcome is conserved.", parameters={"shift": "timestamp"}, expected_outcome="fail"),
    _case("CD-11", "downstream_causal_depth", "identity_shift", "After ablating A, an equivalent replacement binding writes the same observed zone consequence.", "edge(A,C) == absent", "pair_key includes bindings; equivalent execution identity may be mistaken for causal removal.", parameters={"shift": "binding"}, expected_outcome="suspect"),
    _case("CD-12", "downstream_causal_depth", "last_writer_overwrite", "B overwrites A on the address read by C; only B is the last effective writer.", "edge(A,C) == absent and edge(B,C) == present", "Checks overwrite attribution."),
    _case("CD-13", "downstream_causal_depth", "last_writer_unrelated", "B writes an unrelated field; A remains the last writer of C's input.", "edge(A,C) == present and edge(B,C) == absent", "Unrelated later writes must not steal attribution."),
    _case("CD-14", "downstream_causal_depth", "clamped_no_commit", "A matched candidate rule whose clamped delta commits no state write is not an activated causal root.", "depth(clamped_no_effect) == unavailable", "Matched laws without effective commits must not create depth.", tags=["cross_metric", "novel_but_inert"]),
    _case("CD-15", "downstream_causal_depth", "delayed_chain", "A real write/read chain crossing event times remains a two-layer chain.", "depth(delayed_chain) == 2", "Real delayed causation must survive while time itself adds nothing."),
    _case("CD-16", "downstream_causal_depth", "waiting_only", "Extra empty time points after a single downstream law add no structure.", "depth(waiting_only) == depth(chain_1)", "Pure waiting must not inflate depth."),
]


CROSS_ENVIRONMENT_CASES = [
    _case("CE-01", "cross_environment_differentiation", "synthetic_did", "Large environment baselines with zero candidate effect are fully subtracted.", "environment_difference(inert) == 0", "Basic DiD background subtraction.", parameters={"pattern": "huge_background_zero_effect"}),
    _case("CE-02", "cross_environment_differentiation", "synthetic_did", "Identical +0.2 candidate net effects over different final states are invariant.", "environment_difference(equal_net) == 0", "Metric must compare net effects, not finals.", parameters={"pattern": "equal_net"}),
    _case("CE-03", "cross_environment_differentiation", "synthetic_did", "Only wetland gains one extra consequence.", "environment_difference(one_environment) > 0", "Single-environment positive anchor.", parameters={"pattern": "one_environment"}),
    _case("CE-04", "cross_environment_differentiation", "synthetic_did", "Mine/yard and wetland/bridge form two net-effect groups.", "distinct_net_signature_count == 2", "Differentiation must not require all four environments to differ.", parameters={"pattern": "two_plus_two"}),
    _case("CE-05", "cross_environment_differentiation", "synthetic_did", "Final state effects are equal but world-law paths differ.", "state_difference == 0 and world_law_difference > 0", "Construct-definition case: implementation mixes outcome and path differentiation.", parameters={"pattern": "same_final_different_path"}, expected_outcome="suspect"),
    _case("CE-06", "cross_environment_differentiation", "synthetic_did", "A short-horizon difference later recovers to an equal final state.", "environment_difference(intermediate_only) > 0", "Registered multi-horizon observations should retain transient differences.", parameters={"pattern": "intermediate_only"}),
    _case("CE-07", "cross_environment_differentiation", "synthetic_did", "The same outcome channel has net magnitudes 0.1/0.2/0.4/0.8.", "environment_difference(intensity_gradient) > 0", "Quantitative sensitivity positive anchor.", parameters={"pattern": "intensity_gradient"}),
    _case("CE-08", "cross_environment_differentiation", "synthetic_did", "Large environment-specific state noise is identical in present and absent arms.", "environment_difference(background_state_noise) == 0", "State background noise must cancel.", parameters={"pattern": "background_state_noise"}),
    _case("CE-09", "cross_environment_differentiation", "synthetic_did", "Large environment-specific law activity is identical in present and absent arms.", "environment_difference(background_law_noise) == 0", "Law-count background noise must cancel.", parameters={"pattern": "background_law_noise"}),
    _case("CE-10", "cross_environment_differentiation", "synthetic_did", "Sub-precision floating residue is normalized away by the registered 12-decimal arithmetic.", "environment_difference(roundoff) == 0", "Numerical dust must not create differentiation.", parameters={"pattern": "roundoff"}),
    _case("CE-11", "cross_environment_differentiation", "synthetic_did", "A missing sparse coordinate and explicit zero are semantically equal.", "environment_difference(sparse_zero) == 0", "Sparse representation must not alter outcome.", parameters={"pattern": "sparse_zero"}),
    _case("CE-12", "cross_environment_differentiation", "synthetic_did", "Two environments receive +0.2 and two receive -0.2.", "environment_difference(sign_split) > 0", "Opposite directional response positive anchor.", parameters={"pattern": "sign_split"}, tags=["cross_metric", "environment_sensitive_shallow"]),
    _case("CE-13", "cross_environment_differentiation", "synthetic_did", "Permuting environment declaration order changes no pairwise evidence.", "metric(original_order) == metric(permuted_order)", "Non-semantic ordering invariance.", parameters={"pattern": "order_invariance"}),
    _case("CE-14", "cross_environment_differentiation", "synthetic_did", "An inert candidate over four very different backgrounds remains invariant.", "environment_difference(novel_inert) == 0", "Cross-metric inertness check.", parameters={"pattern": "huge_background_zero_effect"}, tags=["cross_metric", "novel_but_inert"]),
    _case("CE-15", "cross_environment_differentiation", "synthetic_did", "Equal state net effects with unequal repeated law counts are path-differentiated only.", "state_difference == 0 and world_law_difference > 0", "Separates causal-path sensitivity from outcome sensitivity.", parameters={"pattern": "equal_state_unequal_law_count"}, expected_outcome="suspect"),
    _case("CE-16", "cross_environment_differentiation", "synthetic_did", "Different backgrounds plus the same powerful candidate effect remain invariant.", "environment_difference(old_powerful_equal_net) == 0", "Power must not be confused with environment sensitivity.", parameters={"pattern": "powerful_equal_net"}, tags=["cross_metric", "old_but_powerful"]),
]


STRUCTURAL_CASES = [
    _case("SN-01", "structural_novelty", "mechanic", "Changing id/name only preserves canonical structure.", "novelty(renamed_seed) == novelty(seed)", "Identity text must be ignored.", parameters={"variant": "rename"}),
    _case("SN-02", "structural_novelty", "mechanic", "Changing effect magnitude and duration magnitude without temporal-class change preserves structure.", "fingerprint(retuned_seed) == fingerprint(seed)", "Continuous parameters must not create novelty.", parameters={"variant": "numeric"}),
    _case("SN-03", "structural_novelty", "mechanic", "Changing cost, charges, and slot cost preserves structure.", "fingerprint(economy_change) == fingerprint(seed)", "Economy parameters are excluded.", parameters={"variant": "economy"}),
    _case("SN-04", "structural_novelty", "mechanic", "Permuting independent effects preserves structure.", "fingerprint(A,B) == fingerprint(B,A)", "List order is non-semantic for SkillSpec effects.", parameters={"variant": "effect_order"}),
    _case("SN-05", "structural_novelty", "mechanic", "Reversing effect sign changes direction-sensitive structure.", "fingerprint(positive) != fingerprint(negative)", "Documents polarity-sensitive rather than field-only topology.", parameters={"variant": "polarity"}),
    _case("SN-06", "structural_novelty", "mechanic", "Substituting sound for wetness preserves abstract graph shape but changes semantic channel.", "abstract_topology equal; canonical fingerprint different", "Boundary between topology and channel semantics.", parameters={"variant": "field_substitution"}, expected_outcome="suspect"),
    _case("SN-07", "structural_novelty", "mechanic", "An impossible trigger makes all nonzero effects behaviorally inert.", "behavioral_novelty == unavailable", "Dead trigger must not produce an unqualified novelty success.", parameters={"variant": "impossible_trigger"}, expected_outcome="fail", tags=["cross_metric", "novel_but_inert"]),
    _case("SN-08", "structural_novelty", "mechanic", "An all-zero mechanic has no effective write topology.", "novelty(all_zero) == unavailable", "Registered zero-effect guard.", parameters={"variant": "all_zero"}),
    _case("SN-09", "structural_novelty", "mechanic", "Adding a zero write to a known effective mechanism preserves fingerprint.", "fingerprint(seed+zero) == fingerprint(seed)", "Zero-write padding must not create novelty.", parameters={"variant": "mixed_zero"}),
    _case("SN-10", "structural_novelty", "mechanic", "Two opposite effects on different fields are a simple recombination of registered modules.", "exact_novel == true but recombinational novelty unresolved", "Tests whether exact novelty overstates compositional recombination.", parameters={"variant": "recombination"}, expected_outcome="suspect", tags=["cross_metric", "complex_self_contained"]),
    _case("SN-11", "structural_novelty", "mechanic", "Adding one reachable trigger to a seed is a near-copy.", "exact_novel(near_copy_trigger) == true", "Measures exact-novel saturation from one tiny edit.", parameters={"variant": "near_trigger"}, expected_outcome="suspect"),
    _case("SN-12", "structural_novelty", "mechanic", "Adding one second effect to a seed is a near-copy.", "exact_novel(near_copy_effect) == true", "Measures exact-novel saturation from one tiny edit.", parameters={"variant": "near_effect"}, expected_outcome="suspect"),
    _case("SN-13", "structural_novelty", "mechanic", "A conditional multi-field periodic mechanism differs on several registered dimensions.", "novelty(genuine_periodic_conditional) > near_copy evidence breadth", "Clearly new positive anchor without scalar score.", parameters={"variant": "genuine_periodic"}),
    _case("SN-14", "structural_novelty", "mechanic", "A sustained conditional multi-effect mechanism differs on reads, writes, and temporal shape.", "novelty(genuine_sustained) > near_copy evidence breadth", "Second clearly new positive anchor.", parameters={"variant": "genuine_sustained"}),
    _case("SN-15", "structural_novelty", "mechanic", "Two equal and opposite declarations on the same field would be behaviorally inert, but SkillSpec rejects duplicate fields.", "setup/payoff cancellation is unrepresentable", "Construct-language ceiling, not evaluator implementation failure.", parameters={"variant": "duplicate_cancel"}, expected_outcome="suspect"),
    _case("SN-16", "structural_novelty", "mechanic", "A large retuning of a registered structure can be powerful while remaining structurally old.", "exact_novel(old_powerful) == false", "Separates realized strength from novelty.", parameters={"variant": "old_powerful"}, tags=["cross_metric", "old_but_powerful", "simple_but_emergent"]),
]


CASES = CAUSAL_CASES + CROSS_ENVIRONMENT_CASES + STRUCTURAL_CASES
