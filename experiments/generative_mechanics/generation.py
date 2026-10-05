"""Versioned generation protocol, baseline contracts, and deterministic fixtures."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path
import random
from typing import Any, Iterable, Protocol

from pmw import parse_law

from .compiler import canonical_json
from .spec import ID_PATTERN, SkillSpec, SkillSpecError, validate_skill
from .substrate import CHANNELS

PROTOCOL_VERSION = "gm-generation-v0.1"
BASELINES = ("direct_effect", "world_substrate")
SOURCE_KINDS = ("model_response", "deterministic_fixture")
POWER_BANDS = {"Low": (20.0, 30.0), "Mid": (40.0, 50.0), "High": (60.0, 70.0)}
ENVELOPE_FIELDS = frozenset({
    "protocol_version", "sample_id", "baseline", "target_band", "source_kind",
    "provenance", "response",
})
PROVENANCE_FIELDS = frozenset({"provider", "model", "prompt_sha256", "seed", "raw_id"})
RESPONSE_FIELDS = frozenset({"mechanic", "declared_power"})
DIRECT_FIELDS = frozenset({
    "id", "name", "effect_kind", "magnitude", "duration", "resource_cost",
    "charges", "slot_cost",
})
DIRECT_KINDS = ("damage", "heal", "buff", "debuff")


class GenerationContractError(ValueError):
    """A request/response violates the frozen generation protocol."""


@dataclass(frozen=True, slots=True)
class Provenance:
    provider: str
    model: str
    prompt_sha256: str
    seed: int
    raw_id: str


@dataclass(frozen=True, slots=True)
class DirectEffectSpec:
    id: str
    name: str
    effect_kind: str
    magnitude: float
    duration: float
    resource_cost: float
    charges: int
    slot_cost: int

    @property
    def periodic(self) -> None:
        return None


@dataclass(frozen=True, slots=True)
class GeneratedSample:
    sample_id: str
    baseline: str
    target_band: str
    source_kind: str
    provenance: Provenance
    mechanic: SkillSpec | DirectEffectSpec
    raw_mechanic: dict[str, Any]
    declared_power: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "sample_id": self.sample_id,
            "baseline": self.baseline,
            "target_band": self.target_band,
            "source_kind": self.source_kind,
            "provenance": asdict(self.provenance),
            "declared_power": self.declared_power,
            "executable_mechanic": (
                skill_to_dict(self.mechanic) if isinstance(self.mechanic, SkillSpec)
                else asdict(self.mechanic)
            ),
        }


@dataclass(frozen=True, slots=True)
class IngestionError:
    line: int
    sample_id: str | None
    error_type: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class IngestionResult:
    samples: tuple[GeneratedSample, ...]
    errors: tuple[IngestionError, ...]


class ProviderAdapter(Protocol):
    """Online providers implement this without adding an SDK dependency here."""

    def generate(self, request: dict[str, Any]) -> dict[str, Any]: ...


# v0.1 above is frozen for replaying the checked-in fixture study. New model
# collection must opt in to v0.2 through the explicitly suffixed APIs below.
PROTOCOL_VERSION_V02 = "gm-generation-v0.2"
BASELINES_V02 = (
    "isolated_direct_effect",
    "world_substrate",
    "matched_direct_outcome",
)
V02_ENVELOPE_FIELDS = frozenset({
    "protocol_version", "sample_id", "sample_nonce", "baseline", "target_band",
    "source_kind", "provenance", "response",
})

CHANNEL_SEMANTICS = {
    "temperature": "normalized local thermal intensity; larger means hotter",
    "wetness": "normalized surface saturation; larger means wetter",
    "electric_field": "normalized ambient electrical potential",
    "fire_intensity": "normalized active combustion intensity",
    "sound_level": "normalized acoustic energy",
    "ground_stability": "normalized structural ground integrity",
    "water_level": "normalized standing-water depth",
    "visibility": "normalized visual clarity",
}


def _world_law_path() -> Path:
    return Path(__file__).with_name("substrate") / "world_laws.json"


def _walk(value: Any) -> Iterable[Any]:
    yield value
    if isinstance(value, dict):
        for item in value.values():
            yield from _walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk(item)


def public_rule_summary() -> dict[str, Any]:
    """Derive a compact public-channel graph without exposing world instances.

    Entity material/process predicates and all environment initial values are
    intentionally omitted. The source digest lets an authoritative scorer prove
    which frozen generic-law set produced the disclosure.
    """
    source = _world_law_path().read_bytes()
    laws = json.loads(source)["laws"]
    summaries: list[dict[str, Any]] = []
    for index, law in enumerate(laws):
        reads: set[str] = set()
        writes: set[str] = set()
        event_types: set[str] = set()
        predicates: list[dict[str, Any]] = []
        mutations: list[dict[str, Any]] = []
        has_private_guards = False
        for node in _walk(law.get("when", {})):
            if isinstance(node, str) and node.startswith("$zone.fields."):
                field = node.removeprefix("$zone.fields.")
                if field in CHANNELS:
                    reads.add(field)
            elif isinstance(node, str) and node.startswith("$zone."):
                has_private_guards = True
            if isinstance(node, dict) and "event.type" in node:
                condition = node["event.type"]
                if isinstance(condition, dict) and isinstance(condition.get("eq"), str):
                    event_types.add(condition["eq"])
            if isinstance(node, dict) and isinstance(node.get("ref"), str):
                ref = node["ref"]
                if ref.startswith("$zone.fields."):
                    field = ref.removeprefix("$zone.fields.")
                    for operator in ("eq", "neq", "gt", "gte", "lt", "lte"):
                        if operator in node and isinstance(node[operator], (int, float)):
                            predicates.append({"field": field, "op": operator, "value": node[operator]})
        for effect in law.get("effects", []):
            target = effect.get("target", "")
            if isinstance(target, str) and target.startswith("$zone.fields."):
                field = target.removeprefix("$zone.fields.")
                if field in CHANNELS:
                    writes.add(field)
                    value = effect.get("value")
                    if isinstance(value, (int, float)) and not isinstance(value, bool):
                        mutations.append({"field": field, "op": effect.get("op"), "value": value})
        # Rules with no public channel edge add no useful generator information.
        if reads or writes:
            summaries.append({
                "rule": index + 1,
                "events": sorted(event_types),
                "reads": sorted(reads),
                "writes": sorted(writes),
                "public_predicates": sorted(predicates, key=lambda row: (row["field"], row["op"], row["value"])),
                "public_mutations": sorted(mutations, key=lambda row: (row["field"], str(row["op"]), row["value"])),
                "has_undisclosed_guards": has_private_guards,
            })
    return {
        "schema": "gm-public-rule-summary-v0.1",
        "source_sha256": hashlib.sha256(source).hexdigest(),
        "rules": summaries,
    }


def calibration_examples_v02() -> tuple[dict[str, Any], ...]:
    """Return scored seed examples sourced exclusively from calibration.

    Scores are frozen artifacts of ``evaluate_power`` over all six calibration
    scenarios. A regression test rebuilds them through the authoritative scorer.
    """
    selected = {
        "Low": (("bedrock_memory", 22.621255584726), ("mud_anchor", 26.734121491106134)),
        "Mid": (("floodgate", 46.38383359857627), ("flash_flood", 49.1890896022264)),
        "High": (("kindling_arc", 67.35574800081066), ("ash_bloom", 68.95506862139733)),
    }
    skill_root = Path(__file__).with_name("skills")
    rows: list[dict[str, Any]] = []
    for band in POWER_BANDS:
        for example_index, (skill_id, realized_score) in enumerate(selected[band]):
            mechanic = json.loads((skill_root / f"{skill_id}.json").read_text(encoding="utf-8"))
            rows.append({
                "example_version": "gm-calibration-example-v0.1",
                "example_id": f"calibration.{band.lower()}.{example_index + 1}",
                "target_band": band,
                "mechanic": mechanic,
                "realized_score": realized_score,
                "provenance": {
                    "split": "calibration",
                    "scenario_id": "calibration/all-six",
                    "scorer_interface": "gm-authoritative-scorer-v0.1",
                    "score_rebuild_key": f"calibration/all-six::{skill_id}::gm-power-scale-v0.2",
                },
            })
    return tuple(rows)


def _v02_mechanic_contract(baseline: str) -> dict[str, Any]:
    common = {
        "id": "lowercase local identifier [a-z][a-z0-9_]{1,47}",
        "name": "non-empty string, at most 80 characters",
        "resource_cost": [0.0, 100.0], "charges": "integer [1,99]", "slot_cost": [1, 2],
    }
    if baseline == "isolated_direct_effect":
        return {
            **common, "strict_fields": sorted(DIRECT_FIELDS),
            "effect_kind": list(DIRECT_KINDS), "magnitude": [0.01, 1.0], "duration": [0.0, 300.0],
        }
    effect_fields = list(CHANNELS) if baseline == "world_substrate" else ["damage", "heal", "buff", "debuff"]
    return {
        **common,
        "strict_fields": [
            "id", "name", "target_scope", "effects", "duration", "periodic",
            "trigger_conditions", "resource_cost", "charges", "slot_cost",
        ],
        "target_scope": "zone",
        "effects": {"min_items": 1, "unique_field": True, "item": {"field": effect_fields, "delta": [-1.0, 1.0]}},
        "duration": [0.0, 300.0],
        "periodic": "null or {interval: positive finite <=300, repeats: integer [1,12]}; exclusive with duration",
        "trigger_conditions": {"item": {"field": list(CHANNELS), "op": ["eq", "neq", "gt", "gte", "lt", "lte"], "value": [0.0, 1.0]}},
        "write_surface": "public_channels" if baseline == "world_substrate" else "direct_outcome_only",
    }


def derive_sample_identity(
    master_seed: int, baseline: str, target_band: str, sample_index: int,
) -> tuple[str, int, str]:
    if baseline not in BASELINES_V02 or target_band not in POWER_BANDS or sample_index < 0:
        raise GenerationContractError("invalid v0.2 sample coordinates")
    coordinates = f"{PROTOCOL_VERSION_V02}|{master_seed}|{baseline}|{target_band}|{sample_index}"
    digest = hashlib.sha256(coordinates.encode("ascii")).hexdigest()
    sample_id = f"{baseline}.{target_band.lower()}.{sample_index:04d}.{digest[:10]}"
    derived_seed = int(digest[10:26], 16) & ((1 << 63) - 1)
    sample_nonce = digest[26:58]
    return sample_id, derived_seed, sample_nonce


def prompt_request_v02(
    baseline: str,
    target_band: str,
    derived_seed: int,
    sample_id: str,
    sample_nonce: str,
) -> dict[str, Any]:
    if baseline not in BASELINES_V02 or target_band not in POWER_BANDS:
        raise GenerationContractError("unknown v0.2 baseline or target band")
    if not sample_id or not sample_nonce:
        raise GenerationContractError("sample_id and sample_nonce must be non-empty")
    return {
        "protocol_version": PROTOCOL_VERSION_V02,
        "sample_id": sample_id,
        "sample_nonce": sample_nonce,
        "derived_seed": derived_seed,
        "baseline": baseline,
        "target_band": {"name": target_band, "range": list(POWER_BANDS[target_band])},
        "public_world_model": {
            "channel_semantics": CHANNEL_SEMANTICS,
            "generic_rule_summary": public_rule_summary(),
        },
        "calibration_examples": list(calibration_examples_v02()),
        "response_contract": {
            "strict_fields": ["mechanic", "declared_power"],
            "declared_power": "finite number or null",
            "mechanic": _v02_mechanic_contract(baseline),
        },
        "constraints": {
            "json_only": True,
            "pmw_laws_allowed": False,
            "private_world_instances_disclosed": False,
        },
    }


def prompt_hash_v02(request: dict[str, Any]) -> str:
    return hashlib.sha256(render_prompt(request).encode("utf-8")).hexdigest()


def build_request_rows_v02(master_seed: int = 2602, per_cell: int = 40) -> tuple[dict[str, Any], ...]:
    if isinstance(per_cell, bool) or not isinstance(per_cell, int) or per_cell < 1:
        raise GenerationContractError("per_cell must be a positive integer")
    rows: list[dict[str, Any]] = []
    for baseline in BASELINES_V02:
        for band in POWER_BANDS:
            for index in range(per_cell):
                sample_id, seed, nonce = derive_sample_identity(master_seed, baseline, band, index)
                request = prompt_request_v02(baseline, band, seed, sample_id, nonce)
                rows.append({
                    "protocol_version": PROTOCOL_VERSION_V02,
                    "sample_id": sample_id,
                    "sample_nonce": nonce,
                    "baseline": baseline,
                    "target_band": band,
                    "seed": seed,
                    "prompt": render_prompt(request),
                    "prompt_sha256": prompt_hash_v02(request),
                })
    return tuple(rows)


def write_request_jsonl_v02(
    path: str | Path, master_seed: int = 2602, per_cell: int = 40,
) -> str:
    rows = build_request_rows_v02(master_seed, per_cell)
    content = "".join(canonical_json(row) + "\n" for row in rows)
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8")
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def validate_envelope_v02(raw: Any) -> GeneratedSample:
    from .baseline_v02 import validate_matched_direct_outcome

    data = _strict(raw, V02_ENVELOPE_FIELDS, "$")
    if data["protocol_version"] != PROTOCOL_VERSION_V02:
        raise GenerationContractError("protocol_version: expected gm-generation-v0.2")
    if data["baseline"] not in BASELINES_V02 or data["target_band"] not in POWER_BANDS:
        raise GenerationContractError("unknown v0.2 baseline or target band")
    if data["source_kind"] not in SOURCE_KINDS:
        raise GenerationContractError("source_kind: unknown source kind")
    if not isinstance(data["sample_id"], str) or not data["sample_id"]:
        raise GenerationContractError("sample_id: must be a non-empty string")
    if not isinstance(data["sample_nonce"], str) or not data["sample_nonce"]:
        raise GenerationContractError("sample_nonce: must be a non-empty string")
    prov = _strict(data["provenance"], PROVENANCE_FIELDS, "provenance")
    if not all(isinstance(prov[key], str) and prov[key] for key in ("provider", "model", "prompt_sha256", "raw_id")):
        raise GenerationContractError("provenance: string fields must be non-empty")
    if isinstance(prov["seed"], bool) or not isinstance(prov["seed"], int):
        raise GenerationContractError("provenance.seed: must be an integer")
    request = prompt_request_v02(
        data["baseline"], data["target_band"], prov["seed"], data["sample_id"], data["sample_nonce"],
    )
    if prov["prompt_sha256"] != prompt_hash_v02(request):
        raise GenerationContractError("provenance.prompt_sha256: does not match the canonical v0.2 request")
    response = _strict(data["response"], RESPONSE_FIELDS, "response")
    declared = response["declared_power"]
    if declared is not None:
        declared = _finite(declared, "response.declared_power", -10000, 10000)
    try:
        if data["baseline"] == "isolated_direct_effect":
            mechanic = validate_direct_effect(response["mechanic"])
        elif data["baseline"] == "world_substrate":
            mechanic = validate_skill(response["mechanic"])
        else:
            mechanic = validate_matched_direct_outcome(response["mechanic"])
    except SkillSpecError as exc:
        raise GenerationContractError(str(exc)) from exc
    return GeneratedSample(
        data["sample_id"], data["baseline"], data["target_band"], data["source_kind"],
        Provenance(**prov), mechanic, response["mechanic"], declared,
    )


def _strict(value: Any, fields: frozenset[str], path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise GenerationContractError(f"{path}: must be an object")
    unknown, missing = set(value) - fields, fields - set(value)
    if unknown or missing:
        raise GenerationContractError(
            f"{path}: strict fields required; unknown={sorted(unknown)} missing={sorted(missing)}"
        )
    return value


def _finite(value: Any, path: str, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise GenerationContractError(f"{path}: must be a finite number")
    result = float(value)
    if not low <= result <= high:
        raise GenerationContractError(f"{path}: must be in [{low}, {high}]")
    return result


def validate_direct_effect(raw: Any) -> DirectEffectSpec:
    data = _strict(raw, DIRECT_FIELDS, "response.mechanic")
    if not isinstance(data["id"], str) or not ID_PATTERN.fullmatch(data["id"]) or data["id"].startswith(("gm_", "pmw_", "lab_")):
        raise GenerationContractError("response.mechanic.id: invalid or reserved identifier")
    if not isinstance(data["name"], str) or not data["name"].strip() or len(data["name"]) > 80:
        raise GenerationContractError("response.mechanic.name: must be a non-empty string of at most 80 characters")
    kind = data["effect_kind"]
    if kind not in DIRECT_KINDS:
        raise GenerationContractError(f"response.mechanic.effect_kind: must be one of {DIRECT_KINDS}")
    # Reuse SkillSpec's identifier/name constraints through the trusted adapter below.
    magnitude = _finite(data["magnitude"], "response.mechanic.magnitude", 0.01, 1.0)
    duration = _finite(data["duration"], "response.mechanic.duration", 0.0, 300.0)
    resource_cost = _finite(data["resource_cost"], "response.mechanic.resource_cost", 0.0, 100.0)
    charges, slot_cost = data["charges"], data["slot_cost"]
    if isinstance(charges, bool) or not isinstance(charges, int) or not 1 <= charges <= 99:
        raise GenerationContractError("response.mechanic.charges: must be an integer in [1, 99]")
    if isinstance(slot_cost, bool) or slot_cost not in (1, 2):
        raise GenerationContractError("response.mechanic.slot_cost: must be 1 or 2")
    return DirectEffectSpec(
        data["id"], data["name"].strip(), kind, magnitude, duration, resource_cost, charges, slot_cost,
    )


def prepare_direct_world(world: Any) -> None:
    """Install a direct-only outcome surface that generic world laws never read."""
    for entity in world.entities.values():
        if "zone" in entity.components:
            entity.components["direct_outcome"] = {kind: 0.0 for kind in DIRECT_KINDS}


def compile_direct_effect(spec: DirectEffectSpec) -> dict[str, Any]:
    """Compile the isolated direct baseline without touching substrate fields."""
    prefix = f"gm.baseline.direct.{spec.id}"
    bindings = {
        "actor": {"kind": "entity", "requires": ["resource"]},
        "skill": {"kind": "entity", "requires": ["skill"]},
        "zone": {"kind": "entity", "requires": ["direct_outcome", "zone"]},
    }
    common = [
        {"event.source": {"eq": "$actor.id"}},
        {"event.target": {"eq": "$zone.id"}},
        {"ref": "$event.payload.skill_id", "eq": spec.id},
        {"ref": "$event.payload.skill_instance_id", "eq": "$skill.id"},
        {"ref": "$skill.skill.spec_id", "eq": spec.id},
        {"ref": "$skill.skill.owner", "eq": "$actor.id"},
    ]
    effects: list[dict[str, Any]] = [
        {"op": "delta", "target": f"$zone.direct_outcome.{spec.effect_kind}", "value": spec.magnitude},
        {"op": "delta", "target": "$actor.resource.energy", "value": -spec.resource_cost},
        {"op": "delta", "target": "$skill.skill.charges", "value": -1},
    ]
    if spec.duration > 0:
        effects.append({"op": "schedule_event", "event": {
            "id": "$event.payload.expiry_event_id", "type": f"{prefix}.expire",
            "time": {"add": ["$event.time", spec.duration]}, "source": "$actor.id",
            "target": "$zone.id", "payload": {"skill_id": spec.id, "skill_instance_id": "$skill.id"},
        }})
    laws: list[dict[str, Any]] = [{
        "id": f"{prefix}.activate", "mode": "event", "priority": 100,
        "bindings": bindings,
        "when": {"all": [{"event.type": {"eq": "lab.skill.activate"}}, *common,
                         {"ref": "$actor.resource.energy", "gte": spec.resource_cost},
                         {"ref": "$skill.skill.charges", "gt": 0}]},
        "effects": effects,
    }]
    if spec.duration > 0:
        laws.append({
            "id": f"{prefix}.expire", "mode": "event", "priority": 100,
            "bindings": bindings,
            "when": {"all": [{"event.type": {"eq": f"{prefix}.expire"}}, *common]},
            "effects": [{"op": "delta", "target": f"$zone.direct_outcome.{spec.effect_kind}",
                         "value": -spec.magnitude}],
        })
    for law in laws:
        parse_law(law)
    return {"schema_version": "2.0", "laws": laws}


def skill_to_dict(spec: SkillSpec) -> dict[str, Any]:
    return {
        "id": spec.id, "name": spec.name, "target_scope": spec.target_scope,
        "effects": [asdict(item) for item in spec.effects], "duration": spec.duration,
        "periodic": asdict(spec.periodic) if spec.periodic else None,
        "trigger_conditions": [asdict(item) for item in spec.trigger_conditions],
        "resource_cost": spec.resource_cost, "charges": spec.charges,
        "slot_cost": spec.slot_cost,
    }


def prompt_request(baseline: str, target_band: str, seed: int) -> dict[str, Any]:
    if baseline not in BASELINES or target_band not in POWER_BANDS:
        raise GenerationContractError("unknown baseline or target band")
    if baseline == "direct_effect":
        mechanic_contract = {
            "strict_fields": sorted(DIRECT_FIELDS),
            "id": "lowercase local identifier [a-z][a-z0-9_]{1,47}",
            "name": "non-empty string, at most 80 characters",
            "effect_kind": list(DIRECT_KINDS), "magnitude": [0.01, 1.0],
            "duration": [0.0, 300.0], "resource_cost": [0.0, 100.0],
            "charges": "integer [1,99]", "slot_cost": [1, 2],
        }
    else:
        mechanic_contract = {
            "strict_fields": [
                "id", "name", "target_scope", "effects", "duration", "periodic",
                "trigger_conditions", "resource_cost", "charges", "slot_cost",
            ],
            "id": "lowercase local identifier [a-z][a-z0-9_]{1,47}",
            "name": "non-empty string, at most 80 characters", "target_scope": "zone",
            "effects": {"min_items": 1, "item": {"field": list(CHANNELS), "delta": [-1.0, 1.0]}},
            "duration": [0.0, 300.0],
            "periodic": "null or {interval: positive finite <=300, repeats: integer [1,12]}; mutually exclusive with positive duration",
            "trigger_conditions": {"item": {"field": list(CHANNELS), "op": ["eq", "gt", "gte", "lt", "lte"], "value": [0.0, 1.0]}},
            "resource_cost": [0.0, 100.0], "charges": "integer [1,99]",
            "slot_cost": [1, 2],
        }
    return {
        "protocol_version": PROTOCOL_VERSION,
        "baseline": baseline,
        "target_band": {"name": target_band, "range": list(POWER_BANDS[target_band])},
        "seed": seed,
        "response_contract": {
            "strict_fields": ["mechanic", "declared_power"],
            "declared_power": "finite number or null",
            "mechanic": mechanic_contract,
        },
        "constraints": {
            "json_only": True, "pmw_laws_allowed": False,
            "public_channels": list(CHANNELS) if baseline == "world_substrate" else [],
        },
    }


def render_prompt(request: dict[str, Any]) -> str:
    return (
        "Generate exactly one executable game mechanic. Return one JSON object matching "
        f"the versioned request below.\n{canonical_json(request)}"
    )


def prompt_hash(request: dict[str, Any]) -> str:
    return hashlib.sha256(render_prompt(request).encode("utf-8")).hexdigest()


def validate_envelope(raw: Any) -> GeneratedSample:
    if isinstance(raw, dict) and raw.get("protocol_version") == PROTOCOL_VERSION_V02:
        return validate_envelope_v02(raw)
    data = _strict(raw, ENVELOPE_FIELDS, "$")
    if data["protocol_version"] != PROTOCOL_VERSION:
        raise GenerationContractError("protocol_version: unsupported version")
    if data["baseline"] not in BASELINES:
        raise GenerationContractError("baseline: unknown baseline")
    if data["target_band"] not in POWER_BANDS:
        raise GenerationContractError("target_band: unknown power band")
    if data["source_kind"] not in SOURCE_KINDS:
        raise GenerationContractError("source_kind: unknown source kind")
    if not isinstance(data["sample_id"], str) or not data["sample_id"]:
        raise GenerationContractError("sample_id: must be a non-empty string")
    prov = _strict(data["provenance"], PROVENANCE_FIELDS, "provenance")
    if not all(isinstance(prov[key], str) and prov[key] for key in ("provider", "model", "prompt_sha256", "raw_id")):
        raise GenerationContractError("provenance: string fields must be non-empty")
    if not isinstance(prov["seed"], int) or isinstance(prov["seed"], bool):
        raise GenerationContractError("provenance.seed: must be an integer")
    if len(prov["prompt_sha256"]) != 64 or any(char not in "0123456789abcdef" for char in prov["prompt_sha256"]):
        raise GenerationContractError("provenance.prompt_sha256: must be a SHA-256 hex digest")
    expected_prompt_hash = prompt_hash(prompt_request(data["baseline"], data["target_band"], prov["seed"]))
    if prov["prompt_sha256"] != expected_prompt_hash:
        raise GenerationContractError("provenance.prompt_sha256: does not match the canonical request")
    response = _strict(data["response"], RESPONSE_FIELDS, "response")
    declared = response["declared_power"]
    if declared is not None:
        declared = _finite(declared, "response.declared_power", -10000.0, 10000.0)
    try:
        if data["baseline"] == "direct_effect":
            mechanic = validate_direct_effect(response["mechanic"])
        else:
            mechanic = validate_skill(response["mechanic"])
    except SkillSpecError as exc:
        raise GenerationContractError(str(exc)) from exc
    provenance = Provenance(**prov)
    return GeneratedSample(
        data["sample_id"], data["baseline"], data["target_band"], data["source_kind"],
        provenance, mechanic, response["mechanic"], declared,
    )


def ingest_jsonl(lines: Iterable[str]) -> IngestionResult:
    samples: list[GeneratedSample] = []
    errors: list[IngestionError] = []
    seen: set[str] = set()
    v02_identity: dict[str, set[Any]] = {
        "sample_nonce": set(), "seed": set(), "prompt_sha256": set(),
    }
    for line_number, line in enumerate(lines, 1):
        sample_id = None
        try:
            raw = json.loads(line)
            sample_id = raw.get("sample_id") if isinstance(raw, dict) else None
            sample = validate_envelope(raw)
            if sample.sample_id in seen:
                raise GenerationContractError("sample_id: duplicate")
            if raw.get("protocol_version") == PROTOCOL_VERSION_V02:
                identities = {
                    "sample_nonce": raw["sample_nonce"],
                    "seed": raw["provenance"]["seed"],
                    "prompt_sha256": raw["provenance"]["prompt_sha256"],
                }
                duplicate = next(
                    (name for name, value in identities.items() if value in v02_identity[name]),
                    None,
                )
                if duplicate:
                    raise GenerationContractError(f"{duplicate}: duplicate v0.2 request identity")
                for name, value in identities.items():
                    v02_identity[name].add(value)
            seen.add(sample.sample_id)
            samples.append(sample)
        except (json.JSONDecodeError, GenerationContractError) as exc:
            errors.append(IngestionError(line_number, sample_id, type(exc).__name__, str(exc)))
    return IngestionResult(tuple(samples), tuple(errors))


def ingest_path(path: str | Path) -> IngestionResult:
    return ingest_jsonl(Path(path).read_text(encoding="utf-8").splitlines())


def _fixture_mechanic(baseline: str, band: str, index: int, rng: random.Random) -> dict[str, Any]:
    code = {"Low": "low", "Mid": "mid", "High": "high"}[band]
    magnitude = {"Low": 0.22, "Mid": 0.48, "High": 0.78}[band]
    magnitude = round(min(1.0, magnitude + rng.choice((-0.03, -0.01, 0.01, 0.03))), 2)
    skill_id = f"fixture_{'de' if baseline == 'direct_effect' else 'ws'}_{code}_{index:03d}"
    common = {
        "id": skill_id, "name": f"Fixture {baseline} {band} {index:03d}",
        "resource_cost": float({"Low": 8, "Mid": 18, "High": 30}[band]),
        "charges": 3, "slot_cost": 1 if band != "High" else 2,
    }
    if baseline == "direct_effect":
        duration = (0.0, 8.0, 25.0)[index % 3]
        return {**common, "effect_kind": DIRECT_KINDS[index % len(DIRECT_KINDS)],
                "magnitude": magnitude, "duration": duration}
    channel = CHANNELS[(index + (0 if band == "Low" else 2 if band == "Mid" else 5)) % len(CHANNELS)]
    sign = -1.0 if index % 5 == 0 and channel not in ("ground_stability", "visibility") else 1.0
    duration = 12.0 if index % 6 == 1 else 0.0
    periodic = {"interval": 5.0, "repeats": 3} if index % 6 == 2 else None
    return {
        **common, "target_scope": "zone",
        "effects": [{"field": channel, "delta": round(sign * magnitude, 2)}],
        "duration": duration, "periodic": periodic, "trigger_conditions": [],
    }


def generate_fixture_envelopes(seed: int = 2601, per_cell: int = 40) -> tuple[dict[str, Any], ...]:
    """Return balanced deterministic fixtures; defaults to 2 * 3 * 40 = 240."""
    rng = random.Random(seed)
    rows: list[dict[str, Any]] = []
    for baseline in BASELINES:
        for band in POWER_BANDS:
            request = prompt_request(baseline, band, seed)
            for index in range(per_cell):
                sample_id = f"{baseline}.{band.lower()}.{index:03d}"
                rows.append({
                    "protocol_version": PROTOCOL_VERSION,
                    "sample_id": sample_id,
                    "baseline": baseline,
                    "target_band": band,
                    "source_kind": "deterministic_fixture",
                    "provenance": {
                        "provider": "pmw-fixture", "model": "deterministic-v0.1",
                        "prompt_sha256": prompt_hash(request), "seed": seed,
                        "raw_id": sample_id,
                    },
                    "response": {
                        "mechanic": _fixture_mechanic(baseline, band, index, rng),
                        "declared_power": float(sum(POWER_BANDS[band]) / 2 + rng.choice((-2, -1, 0, 1, 2))),
                    },
                })
    return tuple(rows)


def balanced_sample(
    samples: Iterable[GeneratedSample], limit: int | None,
) -> tuple[GeneratedSample, ...]:
    """Select deterministically across baseline/target cells for small profiles."""
    rows = tuple(samples)
    if limit is None or limit >= len(rows):
        return rows
    cells: dict[tuple[str, str], list[GeneratedSample]] = {}
    for sample in rows:
        cells.setdefault((sample.baseline, sample.target_band), []).append(sample)
    ordered_cells = sorted(cells)
    selected: list[GeneratedSample] = []
    index = 0
    while len(selected) < limit:
        progressed = False
        for cell in ordered_cells:
            if index < len(cells[cell]):
                selected.append(cells[cell][index])
                progressed = True
                if len(selected) == limit:
                    break
        if not progressed:
            break
        index += 1
    return tuple(selected)


def write_fixture_jsonl(path: str | Path, seed: int = 2601, per_cell: int = 40) -> str:
    rows = generate_fixture_envelopes(seed, per_cell)
    content = "".join(canonical_json(row) + "\n" for row in rows)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(content, encoding="utf-8")
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def write_request_jsonl(path: str | Path, seed: int = 2601, per_cell: int = 40) -> str:
    """Write provider-neutral requests; adapters return response envelopes separately."""
    rows = []
    for baseline in BASELINES:
        for band in POWER_BANDS:
            request = prompt_request(baseline, band, seed)
            for index in range(per_cell):
                sample_id = f"{baseline}.{band.lower()}.{index:03d}"
                rows.append({
                    "protocol_version": PROTOCOL_VERSION,
                    "sample_id": sample_id,
                    "baseline": baseline,
                    "target_band": band,
                    "seed": seed,
                    "prompt": render_prompt(request),
                    "prompt_sha256": prompt_hash(request),
                })
    content = "".join(canonical_json(row) + "\n" for row in rows)
    output = Path(path); output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8")
    return hashlib.sha256(content.encode("utf-8")).hexdigest()
