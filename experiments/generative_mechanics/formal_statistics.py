"""Deterministic mechanism-level statistics for the formal experiment.

The functions in this module operate on one mapping per generated mechanism.
They never flatten arms or contexts into independent observations.  Inputs may
be either the normalized mechanism rows emitted by ``formal_experiment`` or
raw formal rows containing a frozen v0.5 ``profile``.

Public API:

* :func:`endpoint_value` and :func:`endpoint_estimate` implement P1--P6.
* :func:`percentile_bootstrap` estimates a per-model percentile interval.
* :func:`matched_pairwise_bootstrap` resamples complete base-sample blocks.
* :func:`within_block_permutation_omnibus` performs the preregistered omnibus.
* :func:`holm_adjust` and :func:`benjamini_hochberg_adjust` adjust p-values.

All randomness uses a local ``random.Random`` instance.  The production
defaults are 10,000 bootstrap replicates and 100,000 permutations; callers may
pass smaller counts for tests only.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from itertools import permutations as label_permutations, product
import hashlib
import math
import random
import statistics
from typing import Any, Iterable, Mapping, Sequence


P1 = "end_to_end_executable_validity"
P2 = "activation_rate"
P3 = "median_realized_dependency_depth"
P4 = "abstract_topology_collision_probability"
P5 = "outcome_differentiation_rate"
P6 = "path_differentiation_rate"
PRIMARY_ENDPOINTS = (P1, P2, P3, P4, P5, P6)

DEFAULT_BOOTSTRAP_REPLICATES = 10_000
DEFAULT_PERMUTATIONS = 100_000
DEFAULT_CONFIDENCE_LEVEL = 0.95


class FormalStatisticsError(ValueError):
    """The requested analysis violates the preregistered statistical design."""


def _profile(row: Mapping[str, Any]) -> Mapping[str, Any]:
    value = row.get("profile")
    return value if isinstance(value, Mapping) else {}


def _is_execution_valid(row: Mapping[str, Any]) -> bool:
    return row.get("execution_valid") is True


def _finite_number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _mean(values: Sequence[float]) -> float | None:
    return math.fsum(values) / len(values) if values else None


def _direct_or_none(row: Mapping[str, Any], key: str) -> float | None:
    return _finite_number(row.get(key)) if key in row else None


def _contexts(row: Mapping[str, Any]) -> Sequence[Mapping[str, Any]]:
    environment = _profile(row).get("environmental_behavior", {})
    values = environment.get("contexts", []) if isinstance(environment, Mapping) else []
    return values if isinstance(values, list) else []


def _structural_fingerprint(row: Mapping[str, Any]) -> Any | None:
    direct = row.get("abstract_fingerprint")
    if direct is not None:
        return direct
    structural = _profile(row).get("structural_evidence", {})
    if not isinstance(structural, Mapping) or structural.get("available") is False:
        return None
    abstract = structural.get("abstract_topology", {})
    return abstract.get("fingerprint") if isinstance(abstract, Mapping) else None


def endpoint_value(row: Mapping[str, Any], endpoint: str) -> Any | None:
    """Return one mechanism's P1/P2/P3/P5/P6 value, or P4 fingerprint.

    P4 deliberately returns the eligible mechanism's fingerprint rather than a
    row-level score; :func:`endpoint_estimate` computes the U-statistic.  Invalid
    mechanisms are zero for P1 and NA for P2--P6.  A valid, never-activated
    mechanism is zero for P2 and NA for P3.
    """
    if endpoint not in PRIMARY_ENDPOINTS:
        raise FormalStatisticsError(f"unknown primary endpoint: {endpoint!r}")
    if endpoint == P1:
        return 1.0 if _is_execution_valid(row) else 0.0
    if not _is_execution_valid(row):
        return None

    profile = _profile(row)
    dynamic = profile.get("dynamic_reach", {})
    if not isinstance(dynamic, Mapping):
        dynamic = {}
    if endpoint == P2:
        direct = _direct_or_none(row, P2)
        value = direct if direct is not None else _finite_number(dynamic.get("activation_rate"))
        if value is not None and not 0.0 <= value <= 1.0:
            raise FormalStatisticsError(f"activation rate outside [0, 1]: {value!r}")
        return value
    if endpoint == P3:
        direct = _direct_or_none(row, P3)
        if direct is not None:
            return direct
        conditional = dynamic.get("conditional_on_activation", {})
        if not isinstance(conditional, Mapping) or conditional.get("available") is False:
            return None
        distribution = conditional.get("realized_dependency_depth_distribution", [])
        values = [_finite_number(value) for value in distribution] if isinstance(distribution, list) else []
        clean = [value for value in values if value is not None]
        return float(statistics.median(clean)) if clean else None
    if endpoint == P4:
        return _structural_fingerprint(row)

    direct = _direct_or_none(row, endpoint)
    if direct is not None:
        return direct
    contexts = _contexts(row)
    if len(contexts) != 6:
        raise FormalStatisticsError(
            f"{endpoint} requires exactly 6 registered contexts; got {len(contexts)}"
        )
    key = "outcome_differentiated" if endpoint == P5 else "causal_path_differentiated"
    if any(not isinstance(context.get(key), bool) for context in contexts):
        raise FormalStatisticsError(f"{endpoint} requires a boolean value in every context")
    return math.fsum(1.0 if context[key] is True else 0.0 for context in contexts) / len(contexts)


def collision_probability(fingerprints: Sequence[Any]) -> float | None:
    """Return equal-fingerprint unordered pairs divided by all unordered pairs."""
    eligible = [value for value in fingerprints if value is not None]
    if len(eligible) < 2:
        return None
    counts = Counter(eligible)
    collisions = sum(count * (count - 1) // 2 for count in counts.values())
    pair_count = len(eligible) * (len(eligible) - 1) // 2
    return collisions / pair_count


def endpoint_estimate(rows: Iterable[Mapping[str, Any]], endpoint: str) -> float | None:
    """Compute the preregistered model-level P1--P6 point estimate."""
    if endpoint not in PRIMARY_ENDPOINTS:
        raise FormalStatisticsError(f"unknown primary endpoint: {endpoint!r}")
    values = [endpoint_value(row, endpoint) for row in rows]
    if endpoint == P4:
        return collision_probability(values)
    eligible = [float(value) for value in values if value is not None]
    if not eligible:
        return None
    if endpoint == P3:
        return float(statistics.median(eligible))
    return _mean(eligible)


def _percentile(sorted_values: Sequence[float], probability: float) -> float:
    if not sorted_values:
        raise FormalStatisticsError("percentile requires observations")
    position = (len(sorted_values) - 1) * probability
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return sorted_values[low]
    fraction = position - low
    return sorted_values[low] + fraction * (sorted_values[high] - sorted_values[low])


def _seed_for(seed: int, *parts: str) -> int:
    material = "|".join((str(seed), *parts)).encode("utf-8")
    return int(hashlib.sha256(material).hexdigest()[:16], 16)


def _interval_result(
    *, estimate: float | None, replicates: Sequence[float], requested: int,
    confidence_level: float, minimum_valid_fraction: float,
) -> dict[str, Any]:
    valid = len(replicates)
    omitted = requested - valid
    enough = requested > 0 and valid / requested >= minimum_valid_fraction
    ordered = sorted(replicates)
    tail = (1.0 - confidence_level) / 2.0
    return {
        "estimate": estimate,
        "confidence_level": confidence_level,
        "ci_low": _percentile(ordered, tail) if enough and ordered else None,
        "ci_high": _percentile(ordered, 1.0 - tail) if enough and ordered else None,
        "replicates_requested": requested,
        "replicates_valid": valid,
        "replicates_omitted": omitted,
        "status": "ESTIMATED" if estimate is not None and enough else "NOT_ESTIMABLE",
    }


def percentile_bootstrap(
    rows: Iterable[Mapping[str, Any]], endpoint: str, *,
    replicates: int = DEFAULT_BOOTSTRAP_REPLICATES, seed: int = 20261007,
    confidence_level: float = DEFAULT_CONFIDENCE_LEVEL,
    minimum_valid_fraction: float = 0.95,
) -> dict[str, Any]:
    """Bootstrap whole mechanisms within one model and return a percentile CI.

    P4 is recomputed from the resampled fingerprint multiset on every replicate.
    """
    material = tuple(rows)
    _validate_resampling_options(replicates, confidence_level, minimum_valid_fraction)
    estimate = endpoint_estimate(material, endpoint)
    if not material:
        return _interval_result(
            estimate=estimate, replicates=(), requested=replicates,
            confidence_level=confidence_level, minimum_valid_fraction=minimum_valid_fraction,
        ) | {"endpoint": endpoint, "resampling_unit": "generated_mechanism"}
    rng = random.Random(_seed_for(seed, "percentile", endpoint))
    sampled_estimates: list[float] = []
    for _ in range(replicates):
        sample = [material[rng.randrange(len(material))] for _ in material]
        value = endpoint_estimate(sample, endpoint)
        if value is not None:
            sampled_estimates.append(value)
    return _interval_result(
        estimate=estimate, replicates=sampled_estimates, requested=replicates,
        confidence_level=confidence_level, minimum_valid_fraction=minimum_valid_fraction,
    ) | {"endpoint": endpoint, "resampling_unit": "generated_mechanism", "seed": seed}


def _validate_resampling_options(replicates: int, confidence_level: float, minimum_valid_fraction: float) -> None:
    if isinstance(replicates, bool) or not isinstance(replicates, int) or replicates < 1:
        raise FormalStatisticsError("replicates must be a positive integer")
    if not 0.0 < confidence_level < 1.0:
        raise FormalStatisticsError("confidence_level must be between zero and one")
    if not 0.0 <= minimum_valid_fraction <= 1.0:
        raise FormalStatisticsError("minimum_valid_fraction must be in [0, 1]")


def _complete_blocks(
    rows: Iterable[Mapping[str, Any]], model_ids: Sequence[str],
) -> tuple[tuple[Mapping[str, Any], ...], ...]:
    if len(model_ids) < 2 or len(set(model_ids)) != len(model_ids):
        raise FormalStatisticsError("at least two unique model IDs are required")
    grouped: dict[Any, dict[str, Mapping[str, Any]]] = defaultdict(dict)
    for row in rows:
        block = row.get("base_sample_index")
        model = row.get("model_id", row.get("model_blind_label"))
        if block is None or model not in model_ids:
            continue
        if model in grouped[block]:
            raise FormalStatisticsError(f"duplicate model row in base_sample_index {block!r}")
        grouped[block][str(model)] = row
    return tuple(
        tuple(grouped[block][model] for model in model_ids)
        for block in sorted(grouped, key=lambda value: (str(type(value)), str(value)))
        if set(grouped[block]) == set(model_ids)
    )


def matched_pairwise_bootstrap(
    rows: Iterable[Mapping[str, Any]], first_model: str, second_model: str,
    endpoint: str, *, replicates: int = DEFAULT_BOOTSTRAP_REPLICATES,
    seed: int = 20261007, confidence_level: float = DEFAULT_CONFIDENCE_LEVEL,
    minimum_valid_fraction: float = 0.95,
) -> dict[str, Any]:
    """Bootstrap complete matched blocks; contrast is first minus second.

    Conditional NA remains attached to its mechanism.  P4 collision estimates
    are recomputed independently for each model on every block-bootstrap draw.
    """
    _validate_resampling_options(replicates, confidence_level, minimum_valid_fraction)
    blocks = _complete_blocks(rows, (first_model, second_model))
    first = [block[0] for block in blocks]
    second = [block[1] for block in blocks]
    first_estimate = endpoint_estimate(first, endpoint)
    second_estimate = endpoint_estimate(second, endpoint)
    estimate = (
        first_estimate - second_estimate
        if first_estimate is not None and second_estimate is not None else None
    )
    sampled: list[float] = []
    if blocks:
        rng = random.Random(_seed_for(seed, "matched-pair", endpoint, first_model, second_model))
        for _ in range(replicates):
            draw = [blocks[rng.randrange(len(blocks))] for _ in blocks]
            left = endpoint_estimate((block[0] for block in draw), endpoint)
            right = endpoint_estimate((block[1] for block in draw), endpoint)
            if left is not None and right is not None:
                sampled.append(left - right)
    result = _interval_result(
        estimate=estimate, replicates=sampled, requested=replicates,
        confidence_level=confidence_level, minimum_valid_fraction=minimum_valid_fraction,
    )
    return result | {
        "endpoint": endpoint,
        "contrast": f"{first_model} - {second_model}",
        "complete_block_count": len(blocks),
        "resampling_unit": "base_sample_index_block",
        "seed": seed,
    }


def _omnibus_statistic(groups: Mapping[str, Sequence[Mapping[str, Any]]], endpoint: str) -> float | None:
    estimates = {model: endpoint_estimate(rows, endpoint) for model, rows in groups.items()}
    available = {model: value for model, value in estimates.items() if value is not None}
    if len(available) < 2:
        return None
    if endpoint == P4:
        weights: dict[str, int] = {}
        for model, model_rows in groups.items():
            n = sum(endpoint_value(row, P4) is not None for row in model_rows)
            weights[model] = n * (n - 1) // 2
        total_weight = sum(weights[model] for model in available)
        if total_weight == 0:
            return None
        pooled = math.fsum(weights[model] * value for model, value in available.items()) / total_weight
        return math.fsum(weights[model] * (value - pooled) ** 2 for model, value in available.items())
    eligible_values = {
        model: [endpoint_value(row, endpoint) for row in model_rows]
        for model, model_rows in groups.items()
    }
    weights = {model: sum(value is not None for value in values) for model, values in eligible_values.items()}
    pooled_values = [float(value) for values in eligible_values.values() for value in values if value is not None]
    if not pooled_values:
        return None
    pooled = float(statistics.median(pooled_values)) if endpoint == P3 else (_mean(pooled_values) or 0.0)
    return math.fsum(weights[model] * (value - pooled) ** 2 for model, value in available.items())


def within_block_permutation_omnibus(
    rows: Iterable[Mapping[str, Any]], model_ids: Sequence[str], endpoint: str, *,
    permutations: int = DEFAULT_PERMUTATIONS, seed: int = 20261007,
) -> dict[str, Any]:
    """Permute labels within complete ``base_sample_index`` blocks.

    Exact enumeration is used when ``factorial(K) ** blocks <= permutations``;
    otherwise ``permutations`` deterministic Monte Carlo draws are used with
    the preregistered add-one p-value.  Whole mechanism records, including NA,
    move together.  P4 is recalculated after every label assignment.
    """
    if isinstance(permutations, bool) or not isinstance(permutations, int) or permutations < 1:
        raise FormalStatisticsError("permutations must be a positive integer")
    models = tuple(model_ids)
    blocks = _complete_blocks(rows, models)
    groups = {model: [block[index] for block in blocks] for index, model in enumerate(models)}
    observed = _omnibus_statistic(groups, endpoint)
    base = {
        "endpoint": endpoint,
        "analysis_unit": "generated_mechanism",
        "permutation_unit": "labels_within_base_sample_index_block",
        "complete_block_count": len(blocks),
        "observed_statistic": observed,
        "seed": seed,
    }
    if not blocks or observed is None:
        return base | {
            "status": "NOT_ESTIMABLE", "p_value": None,
            "permutations_evaluated": 0, "exact": False,
        }

    assignments = tuple(label_permutations(range(len(models))))
    exact_count = len(assignments) ** len(blocks)
    exceedances = 0
    evaluated = 0

    def statistic_for(block_assignments: Iterable[Sequence[int]]) -> float | None:
        permuted: dict[str, list[Mapping[str, Any]]] = {model: [] for model in models}
        for block, assignment in zip(blocks, block_assignments):
            for target_index, source_index in enumerate(assignment):
                permuted[models[target_index]].append(block[source_index])
        return _omnibus_statistic(permuted, endpoint)

    exact = exact_count <= permutations
    if exact:
        iterator = product(assignments, repeat=len(blocks))
        for assignment_set in iterator:
            value = statistic_for(assignment_set)
            if value is not None:
                evaluated += 1
                if value >= observed - 1e-15:
                    exceedances += 1
        p_value = exceedances / evaluated if evaluated else None
    else:
        rng = random.Random(_seed_for(seed, "omnibus", endpoint, *models))
        for _ in range(permutations):
            assignment_set = [assignments[rng.randrange(len(assignments))] for _ in blocks]
            value = statistic_for(assignment_set)
            if value is not None:
                evaluated += 1
                if value >= observed - 1e-15:
                    exceedances += 1
        p_value = (exceedances + 1) / (evaluated + 1) if evaluated else None
    return base | {
        "status": "ESTIMATED" if p_value is not None else "NOT_ESTIMABLE",
        "p_value": p_value,
        "permutations_evaluated": evaluated,
        "exact": exact,
        "admissible_permutations": exact_count,
    }


def _validate_p_values(p_values: Mapping[str, float | None]) -> None:
    for name, value in p_values.items():
        if value is not None and (not math.isfinite(value) or not 0.0 <= value <= 1.0):
            raise FormalStatisticsError(f"invalid p-value for {name!r}: {value!r}")


def holm_adjust(p_values: Mapping[str, float | None]) -> dict[str, float | None]:
    """Holm step-down FWER adjustment, preserving NA entries."""
    _validate_p_values(p_values)
    present = sorted(((name, value) for name, value in p_values.items() if value is not None), key=lambda x: (x[1], x[0]))
    count = len(present)
    adjusted: dict[str, float | None] = {name: None for name in p_values}
    running = 0.0
    for rank, (name, value) in enumerate(present):
        running = max(running, (count - rank) * value)
        adjusted[name] = min(1.0, running)
    return adjusted


def benjamini_hochberg_adjust(p_values: Mapping[str, float | None]) -> dict[str, float | None]:
    """Benjamini-Hochberg FDR adjustment, preserving NA entries."""
    _validate_p_values(p_values)
    present = sorted(((name, value) for name, value in p_values.items() if value is not None), key=lambda x: (x[1], x[0]))
    count = len(present)
    adjusted: dict[str, float | None] = {name: None for name in p_values}
    running = 1.0
    for rank in range(count, 0, -1):
        name, value = present[rank - 1]
        running = min(running, value * count / rank)
        adjusted[name] = min(1.0, running)
    return adjusted


__all__ = [
    "P1", "P2", "P3", "P4", "P5", "P6", "PRIMARY_ENDPOINTS",
    "DEFAULT_BOOTSTRAP_REPLICATES", "DEFAULT_PERMUTATIONS",
    "FormalStatisticsError", "endpoint_value", "endpoint_estimate",
    "collision_probability", "percentile_bootstrap",
    "matched_pairwise_bootstrap", "within_block_permutation_omnibus",
    "holm_adjust", "benjamini_hochberg_adjust",
]
