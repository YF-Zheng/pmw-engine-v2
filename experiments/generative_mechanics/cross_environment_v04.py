"""Matched-quartet cross-environment differentiation for Free-Invention v0.4.

The estimand is a difference-in-differences (DiD).  In each environment we
first subtract a candidate-absent run from the candidate-present run.  We then
compare those candidate effects across environments.  Consequently, ordinary
differences between the four environments are not attributed to the mechanic.

This module reports an evidence profile, not a creativity score.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Callable, Iterable

from .baseline_v02 import MatchedDirectOutcomeSpec, compile_matched_direct_outcome
from .compiler import canonical_json, compile_skill
from .free_invention import FreeInventionSample
from .generation import DirectEffectSpec, compile_direct_effect, prepare_direct_world
from .runner import ScenarioRun, run_scenario
from .substrate import CHANNELS, SUBSTRATE_SYSTEM_LAWS


PROTOCOL_VERSION = "gm-free-evaluation-v0.4-candidate"
QUARTET_ENVIRONMENTS = (
    "fragile_bridge",
    "industrial_yard",
    "mine",
    "wetland",
)
PUBLIC_INITIAL_FIELDS = {
    "temperature": 0.5,
    "wetness": 0.5,
    "electric_field": 0.5,
    "fire_intensity": 0.5,
    "sound_level": 0.5,
    "ground_stability": 0.5,
    "water_level": 0.5,
    "visibility": 0.5,
}
PUBLIC_LEVELS = {"low": 0.15, "neutral": 0.5, "high": 0.85}


@dataclass(frozen=True, slots=True)
class PublicFieldContext:
    id: str
    public_initial_fields: dict[str, float]

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "public_initial_fields": self.public_initial_fields}


def _level_context(context_id: str, value: float) -> PublicFieldContext:
    return PublicFieldContext(context_id, {channel: value for channel in CHANNELS})


REGISTERED_CONTEXTS = (
    _level_context("all_low", PUBLIC_LEVELS["low"]),
    PublicFieldContext("neutral", dict(PUBLIC_INITIAL_FIELDS)),
    _level_context("all_high", PUBLIC_LEVELS["high"]),
    PublicFieldContext("alternating_a", {
        channel: PUBLIC_LEVELS["low" if index % 2 == 0 else "high"]
        for index, channel in enumerate(CHANNELS)
    }),
    PublicFieldContext("alternating_b", {
        channel: PUBLIC_LEVELS["high" if index % 2 == 0 else "low"]
        for index, channel in enumerate(CHANNELS)
    }),
    PublicFieldContext("gradient", {
        channel: PUBLIC_LEVELS[("low", "neutral", "high")[index % 3]]
        for index, channel in enumerate(CHANNELS)
    }),
)
MANIFEST_PATH = Path(__file__).with_name("evaluation") / "protocol_v0.4.json"
WORLD_LAWS_PATH = Path(__file__).with_name("substrate") / "world_laws.json"
ENVIRONMENTS_DIR = Path(__file__).with_name("environments")
ENVIRONMENT_VARIANT = "standard"
TARGET_COUNT = 1
ACTIVE_BUILD_POLICY = "candidate-only-present; empty-candidate-absent"
SEMANTIC_SOURCE_FILES = (
    "baseline_v02.py",
    "compiler.py",
    "cross_environment_v04.py",
    "generation.py",
    "runner.py",
    "substrate.py",
)
PROGRAM = (
    {"op": "cast", "skill": "candidate", "target": "zone"},
    {"op": "step", "repeats": 10},
)
HORIZONS = {"combat_end": 0.0, "short": 12.0, "medium": 48.0}

# These are the numeric zone surfaces on which a legal consequence can appear.
# ``zone.kind`` and object ids identify the environment and are design metadata,
# not outcomes.  Candidate bookkeeping on actor/skill entities is also excluded.
OBSERVED_COMPONENTS = (
    "direct_outcome",
    "fields",
    "material",
    "outcome",
    "process",
)


@dataclass(frozen=True, slots=True)
class EnvironmentEffect:
    environment: str
    public_initial_fields: dict[str, float]
    hidden_initial_material: dict[str, float]
    candidate_present_observation: dict[str, float]
    candidate_absent_observation: dict[str, float]
    candidate_present_world_laws: dict[str, int]
    candidate_absent_world_laws: dict[str, int]
    candidate_effect: dict[str, float]
    candidate_world_law_effect: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "environment": self.environment,
            "public_initial_fields": self.public_initial_fields,
            "hidden_initial_material": self.hidden_initial_material,
            "candidate_present_observation": self.candidate_present_observation,
            "candidate_absent_observation": self.candidate_absent_observation,
            "candidate_present_world_laws": self.candidate_present_world_laws,
            "candidate_absent_world_laws": self.candidate_absent_world_laws,
            "candidate_effect": self.candidate_effect,
            "candidate_world_law_effect": self.candidate_world_law_effect,
        }


@dataclass(frozen=True, slots=True)
class PairwiseContrast:
    left_environment: str
    right_environment: str
    state_difference_in_differences: dict[str, float]
    world_law_difference_in_differences: dict[str, int]
    state_l1: float
    world_law_l1: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "environments": [self.left_environment, self.right_environment],
            "state_difference_in_differences": self.state_difference_in_differences,
            "world_law_difference_in_differences": self.world_law_difference_in_differences,
            "state_l1": self.state_l1,
            "world_law_l1": self.world_law_l1,
        }


@dataclass(frozen=True, slots=True)
class CrossEnvironmentDifferentiation:
    sample_id: str
    baseline: str
    candidate_mechanic_id: str
    context_id: str
    public_initial_fields: dict[str, float]
    environments: tuple[str, ...]
    environment_effects: tuple[EnvironmentEffect, ...]
    pairwise_contrasts: tuple[PairwiseContrast, ...]

    def to_dict(self) -> dict[str, Any]:
        state_coordinates = {
            coordinate
            for pair in self.pairwise_contrasts
            for coordinate in pair.state_difference_in_differences
        }
        law_coordinates = {
            coordinate
            for pair in self.pairwise_contrasts
            for coordinate in pair.world_law_difference_in_differences
        }
        state_distances = [item.state_l1 for item in self.pairwise_contrasts]
        law_distances = [item.world_law_l1 for item in self.pairwise_contrasts]
        signatures = {
            json.dumps(
                {
                    "state": item.candidate_effect,
                    "world_laws": item.candidate_world_law_effect,
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            for item in self.environment_effects
        }
        differentiated_contexts = sorted({
            environment
            for item in self.pairwise_contrasts
            if item.state_l1 or item.world_law_l1
            for environment in (item.left_environment, item.right_environment)
        })
        pairwise_matrix = {
            left: {
                right: (
                    {"state_l1": 0.0, "world_law_l1": 0}
                    if left == right
                    else next(
                        {
                            "state_l1": item.state_l1,
                            "world_law_l1": item.world_law_l1,
                        }
                        for item in self.pairwise_contrasts
                        if {item.left_environment, item.right_environment} == {left, right}
                    )
                )
                for right in self.environments
            }
            for left in self.environments
        }
        return {
            "protocol_version": PROTOCOL_VERSION,
            "dimension": "cross_environment_differentiation",
            "sample_id": self.sample_id,
            "baseline": self.baseline,
            "available": True,
            "estimand": (
                "pairwise difference-in-differences of candidate-present minus "
                "candidate-absent consequences across a matched environment quartet"
            ),
            "design": {
                "environments": list(self.environments),
                "category": "environmental_hazard",
                "environment_variant": "standard",
                "context_id": self.context_id,
                "public_initial_fields": dict(self.public_initial_fields),
                "program": [
                    {**command, "skill": self.candidate_mechanic_id}
                    if command["op"] == "cast" else dict(command)
                    for command in PROGRAM
                ],
                "horizons": dict(HORIZONS),
                "target_count": 1,
                "active_build": [self.candidate_mechanic_id],
                "candidate_absent_counterfactual": True,
                "background_environment_difference_subtracted": True,
            },
            "summary": {
                "environmentally_differentiated": any(state_distances) or any(law_distances),
                "distinct_net_signature_count": len(signatures),
                "differentiated_contexts": differentiated_contexts,
                "differentiating_state_coordinate_count": len(state_coordinates),
                "differentiating_world_law_count": len(law_coordinates),
                "mean_pairwise_state_l1": (
                    math.fsum(state_distances) / len(state_distances)
                    if state_distances else 0.0
                ),
                "max_pairwise_state_l1": max(state_distances, default=0.0),
                "mean_pairwise_world_law_l1": (
                    math.fsum(law_distances) / len(law_distances)
                    if law_distances else 0.0
                ),
                "max_pairwise_world_law_l1": max(law_distances, default=0),
            },
            "environment_effects": [item.to_dict() for item in self.environment_effects],
            "pairwise_contrasts": [item.to_dict() for item in self.pairwise_contrasts],
            "pairwise_difference_matrix": pairwise_matrix,
            "interpretation": (
                "This is one dimension of a capability profile; it is not a "
                "creativity score or a model ranking."
            ),
        }


@dataclass(frozen=True, slots=True)
class CrossEnvironmentPanel:
    sample_id: str
    baseline: str
    panel_digest: str
    semantic_contract_digest: str
    contexts: tuple[CrossEnvironmentDifferentiation, ...]

    def to_dict(self) -> dict[str, Any]:
        reports = [context.to_dict() for context in self.contexts]
        distributions = [
            {
                "context_id": report["design"]["context_id"],
                **report["summary"],
            }
            for report in reports
        ]
        differentiated = [
            item["context_id"] for item in distributions
            if item["environmentally_differentiated"]
        ]
        return {
            "protocol_version": PROTOCOL_VERSION,
            "dimension": "cross_environment_differentiation",
            "sample_id": self.sample_id,
            "baseline": self.baseline,
            "available": True,
            "panel": {
                "selection": "registered-stratified-public-fields-v1",
                "digest": self.panel_digest,
                "semantic_contract_digest": self.semantic_contract_digest,
                "context_count": len(reports),
                "environment_count_per_context": len(QUARTET_ENVIRONMENTS),
                "public_field_coverage": public_field_coverage(self.contexts),
            },
            "distribution": {
                "differentiated_context_count": len(differentiated),
                "differentiated_context_ids": differentiated,
                "per_context": distributions,
            },
            "context_quartets": reports,
            "interpretation": (
                "The complete per-context distribution is one capability-profile "
                "dimension; no context or aggregate is a creativity score."
            ),
        }


def mechanic_runtime(sample: FreeInventionSample) -> tuple[Callable, Callable | None]:
    if isinstance(sample.mechanic, DirectEffectSpec):
        return compile_direct_effect, prepare_direct_world
    if isinstance(sample.mechanic, MatchedDirectOutcomeSpec):
        return compile_matched_direct_outcome, prepare_direct_world
    return compile_skill, None


def matched_quartet_scenario(
    sample: FreeInventionSample,
    environment: str,
    *,
    public_initial_fields: dict[str, float] | None = None,
) -> dict[str, Any]:
    """Return one registered arm; only ``environment`` varies in the quartet."""
    return {
        "id": f"free_v04_{environment}",
        "split": "oracle",
        "category": "environmental_hazard",
        "environment": environment,
        "environment_variant": ENVIRONMENT_VARIANT,
        "initial_fields": dict(public_initial_fields or PUBLIC_INITIAL_FIELDS),
        # The declared build and program are identical throughout the quartet.
        # The absent arm is selected explicitly by the runner invocation.
        "build": {"backpack": (sample.mechanic.id,), "active": (sample.mechanic.id,)},
        "program": tuple(
            {**command, "skill": sample.mechanic.id}
            if command["op"] == "cast" else dict(command)
            for command in PROGRAM
        ),
        "horizons": dict(HORIZONS),
        "target_count": TARGET_COUNT,
    }


def _zone_components(state: dict[str, Any]) -> dict[str, Any]:
    zones = [
        item["components"] for item in state["entities"]
        if "zone" in item.get("components", {})
    ]
    if len(zones) != 1:
        raise ValueError("v0.4 matched quartet requires exactly one zone")
    return zones[0]


def _numeric_leaves(value: Any, prefix: str) -> dict[str, float]:
    if isinstance(value, dict):
        result: dict[str, float] = {}
        for key in sorted(value):
            result.update(_numeric_leaves(value[key], f"{prefix}.{key}"))
        return result
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return {}
    return {prefix: float(value)}


def _observations(run: ScenarioRun) -> dict[str, float]:
    snapshots = {**run.horizons, "final": run.final_state}
    result: dict[str, float] = {}
    for horizon in sorted(snapshots):
        components = _zone_components(snapshots[horizon])
        for component in OBSERVED_COMPONENTS:
            if component in components:
                result.update(_numeric_leaves(
                    components[component], f"{horizon}/{component}",
                ))
    return result


def _world_laws(run: ScenarioRun) -> Counter[str]:
    return Counter(
        law_id
        for root in run.roots
        for law_id in root.triggered_law_ids
        if law_id.startswith("gm.world.")
    )


def _subtract(
    left: dict[str, float] | Counter[str],
    right: dict[str, float] | Counter[str],
) -> dict[str, float]:
    result = {
        key: round(float(left.get(key, 0)) - float(right.get(key, 0)), 12)
        for key in sorted(set(left) | set(right))
    }
    return {key: value for key, value in result.items() if value != 0.0}


def _environment_effect(
    sample: FreeInventionSample,
    environment: str,
    public_initial_fields: dict[str, float],
) -> EnvironmentEffect:
    compiler, world_setup = mechanic_runtime(sample)
    scenario = matched_quartet_scenario(
        sample, environment, public_initial_fields=public_initial_fields,
    )
    catalog = {sample.mechanic.id: sample.mechanic}
    present = run_scenario(
        scenario, (sample.mechanic.id,), catalog=catalog,
        compile_mechanic=compiler, world_setup=world_setup,
    )
    absent = run_scenario(
        scenario, (), catalog=catalog,
        compile_mechanic=compiler, world_setup=world_setup,
    )
    present_initial = _zone_components(present.initial_state)
    absent_initial = _zone_components(absent.initial_state)
    if present_initial["fields"] != absent_initial["fields"]:
        raise ValueError("candidate arms do not share public initial fields")
    if present_initial["fields"] != public_initial_fields:
        raise ValueError("quartet public initial fields are not matched")
    present_observation = _observations(present)
    absent_observation = _observations(absent)
    present_world_laws = _world_laws(present)
    absent_world_laws = _world_laws(absent)
    law_delta = _subtract(present_world_laws, absent_world_laws)
    return EnvironmentEffect(
        environment=environment,
        public_initial_fields=dict(present_initial["fields"]),
        hidden_initial_material=dict(present_initial["material"]),
        candidate_present_observation=present_observation,
        candidate_absent_observation=absent_observation,
        candidate_present_world_laws=dict(sorted(present_world_laws.items())),
        candidate_absent_world_laws=dict(sorted(absent_world_laws.items())),
        candidate_effect=_subtract(present_observation, absent_observation),
        candidate_world_law_effect={key: int(value) for key, value in law_delta.items()},
    )


def _pairwise(left: EnvironmentEffect, right: EnvironmentEffect) -> PairwiseContrast:
    state = _subtract(left.candidate_effect, right.candidate_effect)
    laws = _subtract(
        Counter(left.candidate_world_law_effect),
        Counter(right.candidate_world_law_effect),
    )
    return PairwiseContrast(
        left.environment,
        right.environment,
        state,
        {key: int(value) for key, value in laws.items()},
        math.fsum(abs(value) for value in state.values()),
        sum(abs(int(value)) for value in laws.values()),
    )


def evaluate_cross_environment_differentiation(
    sample: FreeInventionSample,
    *,
    environments: Iterable[str] = QUARTET_ENVIRONMENTS,
    context_id: str = "neutral",
    public_initial_fields: dict[str, float] | None = None,
) -> CrossEnvironmentDifferentiation:
    """Evaluate one candidate in one matched quartet.

    This remains a useful audit primitive. Confirmatory v0.4 reporting uses
    :func:`evaluate_cross_environment_panel`, never one quartet alone.
    """
    requested = tuple(environments)
    if len(requested) != len(set(requested)) or set(requested) != set(QUARTET_ENVIRONMENTS):
        raise ValueError("environments must contain the frozen four-environment quartet once")
    fields = dict(PUBLIC_INITIAL_FIELDS if public_initial_fields is None else public_initial_fields)
    if set(fields) != set(CHANNELS) or any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not 0.0 <= float(value) <= 1.0
        for value in fields.values()
    ):
        raise ValueError("public_initial_fields must define all eight normalized channels")
    fields = {key: float(fields[key]) for key in CHANNELS}
    canonical = tuple(sorted(requested))
    effects = tuple(
        _environment_effect(sample, environment, fields) for environment in canonical
    )
    pairs = tuple(
        _pairwise(effects[left], effects[right])
        for left in range(len(effects))
        for right in range(left + 1, len(effects))
    )
    return CrossEnvironmentDifferentiation(
        sample.sample_id, sample.baseline, sample.mechanic.id, context_id, fields,
        canonical, effects, pairs,
    )


def _context_projection(contexts: Iterable[PublicFieldContext]) -> list[dict[str, Any]]:
    return [
        context.to_dict()
        for context in sorted(contexts, key=lambda item: item.id)
    ]


def context_panel_digest(contexts: Iterable[PublicFieldContext] = REGISTERED_CONTEXTS) -> str:
    payload = json.dumps(
        _context_projection(contexts), sort_keys=True, separators=(",", ":"),
    ).encode("ascii")
    return hashlib.sha256(payload).hexdigest()


def semantic_contract_projection(
    contexts: Iterable[PublicFieldContext] = REGISTERED_CONTEXTS,
    *,
    world_laws_path: str | Path = WORLD_LAWS_PATH,
    environments_dir: str | Path = ENVIRONMENTS_DIR,
    substrate_system_laws: Iterable[dict[str, Any]] = SUBSTRATE_SYSTEM_LAWS,
) -> dict[str, Any]:
    """Project every frozen input that defines the differentiation estimand."""
    environment_root = Path(environments_dir)
    source_root = Path(__file__).resolve().parent
    return {
        "program": [dict(command) for command in PROGRAM],
        "horizons": dict(HORIZONS),
        "observed_components": list(OBSERVED_COMPONENTS),
        "environments": list(QUARTET_ENVIRONMENTS),
        "environment_asset_sha256": {
            environment: hashlib.sha256(
                (environment_root / f"{environment}.json").read_bytes()
            ).hexdigest()
            for environment in QUARTET_ENVIRONMENTS
        },
        "environment_variant": ENVIRONMENT_VARIANT,
        "target_count": TARGET_COUNT,
        "active_build_policy": ACTIVE_BUILD_POLICY,
        "context_panel_sha256": context_panel_digest(contexts),
        "world_laws_sha256": hashlib.sha256(Path(world_laws_path).read_bytes()).hexdigest(),
        "substrate_system_laws_sha256": hashlib.sha256(
            canonical_json(list(substrate_system_laws)).encode("utf-8")
        ).hexdigest(),
        "experiment_source_sha256": {
            name: hashlib.sha256((source_root / name).read_bytes()).hexdigest()
            for name in SEMANTIC_SOURCE_FILES
        },
    }


def semantic_contract_digest(projection: dict[str, Any]) -> str:
    payload = json.dumps(
        projection, sort_keys=True, separators=(",", ":"),
    ).encode("ascii")
    return hashlib.sha256(payload).hexdigest()


def public_field_coverage(
    contexts: Iterable[PublicFieldContext | CrossEnvironmentDifferentiation],
) -> dict[str, list[str]]:
    values = {
        channel: {
            (
                "low" if context.public_initial_fields[channel] <= 0.25
                else "high" if context.public_initial_fields[channel] >= 0.75
                else "neutral"
            )
            for context in contexts
        }
        for channel in CHANNELS
    }
    return {channel: sorted(levels) for channel, levels in values.items()}


def _validate_registered_panel(
    contexts: Iterable[PublicFieldContext],
    *,
    manifest_path: str | Path = MANIFEST_PATH,
    world_laws_path: str | Path = WORLD_LAWS_PATH,
    environments_dir: str | Path = ENVIRONMENTS_DIR,
    substrate_system_laws: Iterable[dict[str, Any]] = SUBSTRATE_SYSTEM_LAWS,
) -> tuple[PublicFieldContext, ...]:
    supplied = tuple(contexts)
    if len(supplied) != len({context.id for context in supplied}):
        raise ValueError("registered context ids must be unique")
    canonical = tuple(sorted(supplied, key=lambda context: context.id))
    registered = tuple(sorted(REGISTERED_CONTEXTS, key=lambda context: context.id))
    if canonical != registered:
        raise ValueError("contexts must equal the preregistered v0.4 context panel")
    coverage = public_field_coverage(canonical)
    if any(set(levels) != {"high", "low", "neutral"} for levels in coverage.values()):
        raise ValueError("every public field must cover low, neutral, and high")
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    panel = manifest["metrics"]["cross_environment_differentiation"]["context_panel"]
    if panel["selection"] != "registered-stratified-public-fields-v1":
        raise ValueError("unsupported v0.4 context panel selection")
    if panel["contexts"] != _context_projection(canonical):
        raise ValueError("v0.4 manifest context panel does not match implementation")
    actual_digest = context_panel_digest(canonical)
    if panel["sha256"] != actual_digest:
        raise ValueError("v0.4 context panel digest mismatch")
    semantic = panel.get("semantic_contract")
    actual_projection = semantic_contract_projection(
        canonical,
        world_laws_path=world_laws_path,
        environments_dir=environments_dir,
        substrate_system_laws=substrate_system_laws,
    )
    if not isinstance(semantic, dict) or set(semantic) != {"canonical_projection", "sha256"}:
        raise ValueError("v0.4 semantic contract is missing or malformed")
    if semantic["canonical_projection"] != actual_projection:
        raise ValueError("v0.4 semantic contract projection mismatch")
    actual_semantic_digest = semantic_contract_digest(actual_projection)
    if semantic["sha256"] != actual_semantic_digest:
        raise ValueError("v0.4 semantic contract digest mismatch")
    return canonical


def evaluate_cross_environment_panel(
    sample: FreeInventionSample,
    *,
    contexts: Iterable[PublicFieldContext] = REGISTERED_CONTEXTS,
    manifest_path: str | Path = MANIFEST_PATH,
    world_laws_path: str | Path = WORLD_LAWS_PATH,
    environments_dir: str | Path = ENVIRONMENTS_DIR,
    substrate_system_laws: Iterable[dict[str, Any]] = SUBSTRATE_SYSTEM_LAWS,
) -> CrossEnvironmentPanel:
    """Evaluate the complete preregistered stratified context panel."""
    canonical = _validate_registered_panel(
        contexts,
        manifest_path=manifest_path,
        world_laws_path=world_laws_path,
        environments_dir=environments_dir,
        substrate_system_laws=substrate_system_laws,
    )
    quartets = tuple(
        evaluate_cross_environment_differentiation(
            sample,
            context_id=context.id,
            public_initial_fields=context.public_initial_fields,
        )
        for context in canonical
    )
    return CrossEnvironmentPanel(
        sample.sample_id,
        sample.baseline,
        context_panel_digest(canonical),
        semantic_contract_digest(semantic_contract_projection(canonical)),
        quartets,
    )
