"""Protocol v0.3: unconstrained-power, free mechanic invention.

This track is intentionally separate from the v0.2 power-band experiment.  It
shares the public world model and trusted mechanic validators, but discloses no
score targets, scored examples, or revision policy to the generator.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from .baseline_v02 import (
    MatchedDirectOutcomeSpec,
    compile_matched_direct_outcome,
    validate_matched_direct_outcome,
)
from .compiler import canonical_json, compile_skill
from .diversity import structural_fingerprint
from .generation import (
    BASELINES_V02,
    CHANNEL_SEMANTICS,
    DIRECT_FIELDS,
    DIRECT_KINDS,
    PROVENANCE_FIELDS,
    SOURCE_KINDS,
    DirectEffectSpec,
    GenerationContractError,
    IngestionError,
    Provenance,
    _strict,
    compile_direct_effect,
    public_rule_summary,
    render_prompt,
    validate_direct_effect,
)
from .spec import SkillSpec, SkillSpecError, validate_skill
from .substrate import CHANNELS


PROTOCOL_VERSION = "gm-free-invention-v0.3"
BASELINES = BASELINES_V02
ENVELOPE_FIELDS = frozenset({
    "protocol_version", "sample_id", "sample_nonce", "baseline",
    "request_coordinates", "source_kind", "provenance", "response",
})
REQUEST_COORDINATE_FIELDS = frozenset({"master_seed", "sample_index"})
RESPONSE_FIELDS = frozenset({"mechanic"})
EVALUATION_DIMENSIONS = (
    "structural_novelty",
    "interaction_surface",
    "causal_depth",
    "cross_environment_differentiation",
    "downstream_consequences",
    "combinatorial_potential",
    "self_containment",
)


@dataclass(frozen=True, slots=True)
class FreeInventionSample:
    sample_id: str
    baseline: str
    master_seed: int
    sample_index: int
    source_kind: str
    provenance: Provenance
    mechanic: SkillSpec | DirectEffectSpec | MatchedDirectOutcomeSpec
    raw_mechanic: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        mechanic = (
            self.mechanic.to_dict()
            if isinstance(self.mechanic, MatchedDirectOutcomeSpec)
            else asdict(self.mechanic)
        )
        return {
            "sample_id": self.sample_id,
            "baseline": self.baseline,
            "request_coordinates": {
                "master_seed": self.master_seed,
                "sample_index": self.sample_index,
            },
            "source_kind": self.source_kind,
            "provenance": asdict(self.provenance),
            "executable_mechanic": mechanic,
            "evaluation_dimensions": list(EVALUATION_DIMENSIONS),
        }


@dataclass(frozen=True, slots=True)
class FreeInventionIngestionResult:
    samples: tuple[FreeInventionSample, ...]
    errors: tuple[IngestionError, ...]


def _mechanic_contract(baseline: str) -> dict[str, Any]:
    common = {
        "id": "lowercase local identifier [a-z][a-z0-9_]{1,47}",
        "name": "non-empty string, at most 80 characters",
        "resource_cost": [0.0, 100.0],
        "charges": "integer [1,99]",
        "slot_cost": [1, 2],
    }
    if baseline == "isolated_direct_effect":
        return {
            **common,
            "strict_fields": sorted(DIRECT_FIELDS),
            "effect_kind": list(DIRECT_KINDS),
            "magnitude": [0.01, 1.0],
            "duration": [0.0, 300.0],
        }
    fields = list(CHANNELS) if baseline == "world_substrate" else [
        "damage", "heal", "buff", "debuff",
    ]
    return {
        **common,
        "strict_fields": [
            "id", "name", "target_scope", "effects", "duration", "periodic",
            "trigger_conditions", "resource_cost", "charges", "slot_cost",
        ],
        "target_scope": "zone",
        "effects": {
            "min_items": 1,
            "unique_field": True,
            "item": {"field": fields, "delta": [-1.0, 1.0]},
        },
        "duration": [0.0, 300.0],
        "periodic": (
            "null or {interval: positive finite <=300, repeats: integer [1,12]}; "
            "exclusive with duration"
        ),
        "trigger_conditions": {
            "item": {
                "field": list(CHANNELS),
                "op": ["eq", "neq", "gt", "gte", "lt", "lte"],
                "value": [0.0, 1.0],
            },
        },
        "write_surface": (
            "public_channels" if baseline == "world_substrate" else "direct_outcome_only"
        ),
    }


def derive_identity(
    master_seed: int, baseline: str, sample_index: int,
) -> tuple[str, int, str]:
    if baseline not in BASELINES or sample_index < 0:
        raise GenerationContractError("invalid v0.3 sample coordinates")
    coordinates = f"{PROTOCOL_VERSION}|{master_seed}|{baseline}|{sample_index}"
    digest = hashlib.sha256(coordinates.encode("ascii")).hexdigest()
    sample_id = f"free.{baseline}.{sample_index:04d}.{digest[:10]}"
    derived_seed = int(digest[10:26], 16) & ((1 << 63) - 1)
    return sample_id, derived_seed, digest[26:58]


def prompt_request(
    baseline: str, derived_seed: int, sample_id: str, sample_nonce: str,
) -> dict[str, Any]:
    if baseline not in BASELINES:
        raise GenerationContractError("unknown v0.3 baseline")
    if not sample_id or not sample_nonce:
        raise GenerationContractError("sample_id and sample_nonce must be non-empty")
    return {
        "protocol_version": PROTOCOL_VERSION,
        "sample_id": sample_id,
        "sample_nonce": sample_nonce,
        "derived_seed": derived_seed,
        "experimental_condition": {"baseline": baseline},
        "task": (
            "Invent one executable mechanic with an interesting identity and behavior. "
            "Choose its parameters freely within the response contract."
        ),
        "public_world_model": {
            "channel_semantics": CHANNEL_SEMANTICS,
            "generic_rule_summary": public_rule_summary(),
        },
        "response_contract": {
            "strict_fields": ["mechanic"],
            "mechanic": _mechanic_contract(baseline),
        },
        "constraints": {
            "json_only": True,
            "pmw_laws_allowed": False,
            "private_world_instances_disclosed": False,
            "independent_single_pass_generation": True,
        },
    }


def prompt_hash(request: dict[str, Any]) -> str:
    return hashlib.sha256(render_prompt(request).encode("utf-8")).hexdigest()


def build_request_rows(
    master_seed: int = 2603, per_baseline: int = 40,
) -> tuple[dict[str, Any], ...]:
    if isinstance(per_baseline, bool) or not isinstance(per_baseline, int) or per_baseline < 1:
        raise GenerationContractError("per_baseline must be a positive integer")
    rows: list[dict[str, Any]] = []
    for baseline in BASELINES:
        for index in range(per_baseline):
            sample_id, seed, nonce = derive_identity(master_seed, baseline, index)
            request = prompt_request(baseline, seed, sample_id, nonce)
            rows.append({
                "protocol_version": PROTOCOL_VERSION,
                "sample_id": sample_id,
                "sample_nonce": nonce,
                "baseline": baseline,
                "request_coordinates": {
                    "master_seed": master_seed,
                    "sample_index": index,
                },
                "seed": seed,
                "prompt": render_prompt(request),
                "prompt_sha256": prompt_hash(request),
            })
    return tuple(rows)


def write_request_jsonl(
    path: str | Path, master_seed: int = 2603, per_baseline: int = 40,
) -> str:
    content = "".join(
        canonical_json(row) + "\n"
        for row in build_request_rows(master_seed, per_baseline)
    )
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8")
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def validate_envelope(raw: Any) -> FreeInventionSample:
    data = _strict(raw, ENVELOPE_FIELDS, "$")
    if data["protocol_version"] != PROTOCOL_VERSION:
        raise GenerationContractError(f"protocol_version: expected {PROTOCOL_VERSION}")
    if data["baseline"] not in BASELINES:
        raise GenerationContractError("baseline: unknown v0.3 baseline")
    if data["source_kind"] not in SOURCE_KINDS:
        raise GenerationContractError("source_kind: unknown source kind")
    for field in ("sample_id", "sample_nonce"):
        if not isinstance(data[field], str) or not data[field]:
            raise GenerationContractError(f"{field}: must be a non-empty string")
    coordinates = _strict(
        data["request_coordinates"], REQUEST_COORDINATE_FIELDS, "request_coordinates",
    )
    master_seed = coordinates["master_seed"]
    sample_index = coordinates["sample_index"]
    if isinstance(master_seed, bool) or not isinstance(master_seed, int):
        raise GenerationContractError("request_coordinates.master_seed: must be an integer")
    if (
        isinstance(sample_index, bool)
        or not isinstance(sample_index, int)
        or sample_index < 0
    ):
        raise GenerationContractError(
            "request_coordinates.sample_index: must be a non-negative integer"
        )
    provenance = _strict(data["provenance"], PROVENANCE_FIELDS, "provenance")
    if not all(
        isinstance(provenance[key], str) and provenance[key]
        for key in ("provider", "model", "prompt_sha256", "raw_id")
    ):
        raise GenerationContractError("provenance: string fields must be non-empty")
    if isinstance(provenance["seed"], bool) or not isinstance(provenance["seed"], int):
        raise GenerationContractError("provenance.seed: must be an integer")
    expected_id, expected_seed, expected_nonce = derive_identity(
        master_seed, data["baseline"], sample_index,
    )
    issued = {
        "sample_id": (data["sample_id"], expected_id),
        "provenance.seed": (provenance["seed"], expected_seed),
        "sample_nonce": (data["sample_nonce"], expected_nonce),
    }
    mismatch = next(
        (name for name, (actual, expected) in issued.items() if actual != expected), None,
    )
    if mismatch:
        raise GenerationContractError(f"{mismatch}: does not match request coordinates")
    request = prompt_request(
        data["baseline"], provenance["seed"], data["sample_id"], data["sample_nonce"],
    )
    if provenance["prompt_sha256"] != prompt_hash(request):
        raise GenerationContractError(
            "provenance.prompt_sha256: does not match the canonical v0.3 request"
        )
    response = _strict(data["response"], RESPONSE_FIELDS, "response")
    try:
        if data["baseline"] == "isolated_direct_effect":
            mechanic = validate_direct_effect(response["mechanic"])
        elif data["baseline"] == "world_substrate":
            mechanic = validate_skill(response["mechanic"])
        else:
            mechanic = validate_matched_direct_outcome(response["mechanic"])
    except SkillSpecError as exc:
        raise GenerationContractError(str(exc)) from exc
    return FreeInventionSample(
        data["sample_id"], data["baseline"], master_seed, sample_index, data["source_kind"],
        Provenance(**provenance), mechanic, response["mechanic"],
    )


def ingest_jsonl(lines: Iterable[str]) -> FreeInventionIngestionResult:
    samples: list[FreeInventionSample] = []
    errors: list[IngestionError] = []
    identities: dict[str, set[Any]] = {
        "sample_id": set(), "sample_nonce": set(), "seed": set(), "prompt_sha256": set(),
    }
    for line_number, line in enumerate(lines, 1):
        sample_id = None
        try:
            raw = json.loads(line)
            sample_id = raw.get("sample_id") if isinstance(raw, dict) else None
            sample = validate_envelope(raw)
            values = {
                "sample_id": sample.sample_id,
                "sample_nonce": raw["sample_nonce"],
                "seed": raw["provenance"]["seed"],
                "prompt_sha256": raw["provenance"]["prompt_sha256"],
            }
            duplicate = next(
                (name for name, value in values.items() if value in identities[name]), None,
            )
            if duplicate:
                raise GenerationContractError(f"{duplicate}: duplicate v0.3 request identity")
            for name, value in values.items():
                identities[name].add(value)
            samples.append(sample)
        except (json.JSONDecodeError, GenerationContractError) as exc:
            errors.append(IngestionError(line_number, sample_id, type(exc).__name__, str(exc)))
    return FreeInventionIngestionResult(tuple(samples), tuple(errors))


def ingest_path(path: str | Path) -> FreeInventionIngestionResult:
    return ingest_jsonl(Path(path).read_text(encoding="utf-8").splitlines())


def compile_sample(sample: FreeInventionSample) -> dict[str, Any]:
    """Compile a validated sample through the existing trusted compiler path."""
    if isinstance(sample.mechanic, DirectEffectSpec):
        return compile_direct_effect(sample.mechanic)
    if isinstance(sample.mechanic, MatchedDirectOutcomeSpec):
        return compile_matched_direct_outcome(sample.mechanic)
    return compile_skill(sample.mechanic)


def _seed_structures(sample: FreeInventionSample) -> set[str] | None:
    """Return compatible checked-in seed structures, if that baseline has any."""
    if sample.baseline != "world_substrate":
        return None
    root = Path(__file__).with_name("skills")
    return {
        structural_fingerprint(json.loads(path.read_text(encoding="utf-8")))
        for path in root.glob("*.json")
        if path.name != "manifest.json"
    }


def evaluate_free_invention_sample(sample: FreeInventionSample) -> dict[str, Any]:
    """Emit only evidence available before the dynamic experiment stage.

    A numeric zero is never used as a placeholder for unavailable evidence.
    Dynamic evaluators may replace unavailable entries after scenario execution.
    """
    compiled = compile_sample(sample)
    fingerprint = structural_fingerprint(sample.raw_mechanic)
    seed_structures = _seed_structures(sample)
    raw = sample.raw_mechanic
    effects = raw.get("effects")
    effect_fields = (
        sorted(item["field"] for item in effects)
        if isinstance(effects, list)
        else [raw["effect_kind"]]
    )
    trigger_fields = sorted({
        item["field"] for item in raw.get("trigger_conditions", [])
    })
    return {
        "protocol_version": PROTOCOL_VERSION,
        "sample_id": sample.sample_id,
        "declared_dimensions": list(EVALUATION_DIMENSIONS),
        "static_evidence": {
            "declared_write_surface": (
                "public_world_channels"
                if sample.baseline == "world_substrate"
                else "isolated_direct_outcome"
            ),
            "effect_fields": effect_fields,
            "trigger_fields": trigger_fields,
            "has_duration": bool(raw.get("duration", 0)),
            "has_periodic": raw.get("periodic") is not None,
        },
        "contract_safety": {
            "strict_validation_passed": True,
            "trusted_compiler_passed": True,
            "compiled_law_count": len(compiled["laws"]),
            "network_access": False,
            "model_authored_pmw_laws": False,
        },
        "dimensions": {
            "structural_novelty": (
                {
                    "available": True,
                    "structural_fingerprint": fingerprint,
                    "reference_catalog": "checked_in_world_substrate_seeds",
                    "reference_count": len(seed_structures),
                    "novel_against_reference": fingerprint not in seed_structures,
                }
                if seed_structures is not None
                else {
                    "available": False,
                    "reason": "no compatible checked-in seed catalog for this baseline",
                    "structural_fingerprint": fingerprint,
                }
            ),
            "interaction_surface": {
                "available": False,
                "reason": "requires paired execution to count additional triggered gm.world laws",
            },
            "causal_depth": {
                "available": False,
                "reason": "requires paired scenario execution and trace comparison",
            },
            "cross_environment_differentiation": {
                "available": False,
                "reason": "requires execution in the frozen environment panel",
            },
            "downstream_consequences": {
                "available": False,
                "reason": "requires paired world-state and causal-trace evidence",
            },
            "combinatorial_potential": {
                "available": False,
                "reason": "requires exact backpack search",
            },
            "self_containment": {
                "available": False,
                "reason": "requires paired execution; defined by zero dynamic interaction surface",
            },
        },
    }
