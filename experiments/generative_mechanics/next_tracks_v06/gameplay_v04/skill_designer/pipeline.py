"""Offline candidate decode, normalization, parse, and compile boundary."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import math
import re
from typing import Any, Mapping, Sequence

from ..contracts import GameplayContractError
from ..materials import (
    MaterialAuthority,
    MaterialDefinition,
    material_authority,
    parse_material,
)
from ..skill_ir import (
    MAX_JSON_DEPTH,
    CompiledSkillIR,
    SkillIR,
    compile_skill_ir,
    parse_skill_ir,
)
from .context import ExistingSkillInput, GenerationContext, build_generation_context
from .replay import (
    ReplayCall,
    ReplayExhaustedError,
    ReplayProvider,
    ReplayReply,
    ReplayRequest,
)


PIPELINE_PROTOCOL = "pmw-offline-skill-pipeline-v1"
_CANDIDATE_ID = re.compile(r"[a-z][a-z0-9_]{1,63}\Z")
_HEX64 = re.compile(r"[0-9a-f]{64}\Z")
_ROOT_FIELDS = {
    "protocol",
    "identity",
    "origin",
    "capability",
    "targeting",
    "costs",
    "entries",
    "lifecycle",
    "limits",
    "display",
}


@dataclass(frozen=True, slots=True)
class AttemptRecord:
    attempt: int
    stage: str
    reason: str
    context_hash: str
    accepted: bool
    reply_hash: str | None

    def __post_init__(self) -> None:
        if (
            isinstance(self.attempt, bool)
            or not isinstance(self.attempt, int)
            or self.attempt < 1
        ):
            raise GameplayContractError("attempt number must be positive")
        if not isinstance(self.stage, str) or not isinstance(self.reason, str):
            raise GameplayContractError("attempt stage and reason must be text")
        if not isinstance(self.context_hash, str) or _HEX64.fullmatch(
            self.context_hash
        ) is None:
            raise GameplayContractError("attempt context hash is invalid")
        if not isinstance(self.accepted, bool):
            raise GameplayContractError("attempt accepted must be boolean")
        if self.reply_hash is not None and (
            not isinstance(self.reply_hash, str)
            or _HEX64.fullmatch(self.reply_hash) is None
        ):
            raise GameplayContractError("attempt reply hash is invalid")

    def to_dict(self) -> dict[str, object]:
        return {
            "attempt": self.attempt,
            "stage": self.stage,
            "reason": self.reason,
            "context_hash": self.context_hash,
            "accepted": self.accepted,
            "reply_hash": self.reply_hash,
        }


@dataclass(frozen=True, slots=True)
class PipelineResult:
    """Immutable readback for one bounded offline pipeline run."""

    canonical_json: str
    parsed: SkillIR | None
    compiled: CompiledSkillIR | None

    def __post_init__(self) -> None:
        if not isinstance(self.canonical_json, str):
            raise GameplayContractError("pipeline result must be canonical JSON text")
        try:
            document = json.loads(self.canonical_json)
        except (TypeError, ValueError) as error:
            raise GameplayContractError("pipeline result JSON is invalid") from error
        if not isinstance(document, dict):
            raise GameplayContractError("pipeline result must be a JSON object")
        success = document.get("status") == "compiled_unregistered"
        if success != (self.parsed is not None and self.compiled is not None):
            raise GameplayContractError(
                "pipeline result status and compiled output disagree"
            )
        if success:
            if not isinstance(self.parsed, SkillIR) or not isinstance(
                self.compiled, CompiledSkillIR
            ):
                raise GameplayContractError(
                    "compiled result requires parsed and compiled IR"
                )
            if document.get("ir_hash") != self.compiled.canonical_hash:
                raise GameplayContractError("pipeline IR hash does not match compiled IR")
        expected = _readback_hash(document)
        if document.get("result_hash") != expected:
            raise GameplayContractError("pipeline result hash is invalid")
        if json.dumps(
            document, sort_keys=True, separators=(",", ":"), allow_nan=False
        ) != self.canonical_json:
            raise GameplayContractError("pipeline result must use canonical JSON")

    @property
    def hash(self) -> str:
        return hashlib.sha256(self.canonical_json.encode("utf-8")).hexdigest()

    @property
    def accepted(self) -> bool:
        return False

    @property
    def status(self) -> str:
        return json.loads(self.canonical_json)["status"]

    @property
    def attempts(self) -> tuple[AttemptRecord, ...]:
        document = json.loads(self.canonical_json)
        return tuple(
            AttemptRecord(
                row["attempt"],
                row["stage"],
                row["reason"],
                row["context_hash"],
                row["accepted"],
                row["reply_hash"],
            )
            for row in document["attempts"]
        )

    def to_dict(self) -> dict[str, Any]:
        return json.loads(self.canonical_json)


@dataclass(frozen=True, slots=True)
class DecodedCandidate:
    document: dict[str, Any]
    canonical_json: str
    reply_hash: str


def run_offline_pipeline(
    *,
    materials: Sequence[MaterialDefinition],
    statuses: Mapping[str, Any],
    profile: str,
    complexity: int,
    public_known_rules: Sequence[str],
    acquired_capabilities: Sequence[str],
    existing_skills: Sequence[ExistingSkillInput],
    candidate_id: str,
    replay: ReplayProvider,
    max_repairs: int = 0,
) -> PipelineResult:
    """Compile replay text without registering, sandboxing, or mutating a world."""
    selected_candidate = _candidate_id(candidate_id)
    repairs = _max_repairs(max_repairs)
    if not isinstance(replay, ReplayProvider):
        raise GameplayContractError("replay must be a trusted ReplayProvider")
    if not isinstance(statuses, Mapping):
        raise GameplayContractError("statuses must be a trusted mapping")

    try:
        context = build_generation_context(
            profile=profile,
            materials=materials,
            complexity=complexity,
            public_known_rules=public_known_rules,
            acquired_capabilities=acquired_capabilities,
            existing_skills=existing_skills,
        )
        authority = _authority_from_materials(materials)
        context_authority = _authority_from_context(context)
        if context_authority != authority:
            raise GameplayContractError(
                "generated context authority does not match rederived material authority"
            )
    except GameplayContractError:
        raise
    except (AttributeError, TypeError, ValueError, OverflowError, RecursionError) as error:
        raise GameplayContractError(
            f"offline pipeline context failed: {type(error).__name__}"
        ) from error

    feedback = ""
    attempts: list[AttemptRecord] = []
    call_start = len(replay.calls)
    total_calls = repairs + 1
    for attempt_number in range(1, total_calls + 1):
        request = ReplayRequest(attempt_number, feedback, context.context_hash)
        try:
            reply = replay.reply(request)
        except ReplayExhaustedError:
            return _build_result(
                context,
                selected_candidate,
                attempts,
                replay.calls[call_start:],
                failure_stage="provider_exhausted",
                failure_reason="replay provider has no reply for this attempt",
            )
        except GameplayContractError as error:
            return _build_result(
                context,
                selected_candidate,
                attempts,
                replay.calls[call_start:],
                failure_stage="provider_contract",
                failure_reason=_safe_reason(error),
            )
        if not isinstance(reply, ReplayReply):
            return _build_result(
                context,
                selected_candidate,
                attempts,
                replay.calls[call_start:],
                failure_stage="provider_contract",
                failure_reason="replay provider returned a non-ReplayReply value",
            )
        if reply.origin_source != "authored" or reply.origin_model is not None:
            return _build_result(
                context,
                selected_candidate,
                attempts,
                replay.calls[call_start:],
                failure_stage="provider_contract",
                failure_reason="replay provenance must be authored with no model",
            )

        reply_hash = hashlib.sha256(reply.text.encode("utf-8")).hexdigest()
        stage = "decode"
        try:
            decoded = decode_candidate(reply.text)
            stage = "normalize"
            normalized = normalize_candidate(
                decoded.document,
                context=context,
                authority=authority,
                candidate_id=selected_candidate,
            )
            stage = "parse"
            parsed = parse_skill_ir(normalized, statuses, authority)
            stage = "compile"
            compiled = compile_skill_ir(parsed)
        except _CandidateRejection as error:
            attempts.append(
                AttemptRecord(
                    attempt_number,
                    error.stage,
                    error.reason,
                    context.context_hash,
                    False,
                    reply_hash,
                )
            )
            feedback = _feedback(error.stage, error.reason)
            continue
        except GameplayContractError as error:
            attempts.append(
                AttemptRecord(
                    attempt_number,
                    stage,
                    _safe_reason(error),
                    context.context_hash,
                    False,
                    reply_hash,
                )
            )
            feedback = _feedback(stage, _safe_reason(error))
            continue
        except (
            AttributeError,
            TypeError,
            KeyError,
            ValueError,
            OverflowError,
            RecursionError,
        ) as error:
            reason = f"{type(error).__name__}: candidate validation failed"
            attempts.append(
                AttemptRecord(
                    attempt_number,
                    stage,
                    reason,
                    context.context_hash,
                    False,
                    reply_hash,
                )
            )
            feedback = _feedback(stage, reason)
            continue

        attempts.append(
            AttemptRecord(
                attempt_number,
                "compiled",
                "candidate compiled successfully",
                context.context_hash,
                True,
                reply_hash,
            )
        )
        return _build_result(
            context,
            selected_candidate,
            attempts,
            replay.calls[call_start:],
            parsed=parsed,
            compiled=compiled,
        )

    return _build_result(
        context,
        selected_candidate,
        attempts,
        replay.calls[call_start:],
        failure_stage="repairs_exhausted",
        failure_reason=f"candidate validation failed after {repairs} repair(s)",
    )


def decode_candidate(text: str) -> DecodedCandidate:
    """Decode one bounded JSON object, accepting at most one complete fence."""
    if not isinstance(text, str):
        raise _CandidateRejection("decode", "reply must be UTF-8 text")
    try:
        encoded = text.encode("utf-8")
    except UnicodeEncodeError as error:
        raise _CandidateRejection("decode", "reply contains invalid Unicode") from error
    if len(encoded) > 65536:
        raise _CandidateRejection("decode", "reply exceeds 65536 UTF-8 bytes")
    payload = _fenced_payload(text)
    try:
        document = json.loads(
            payload,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except _CandidateRejection:
        raise
    except json.JSONDecodeError as error:
        raise _CandidateRejection(
            "decode", f"invalid JSON at line {error.lineno} column {error.colno}"
        ) from error
    except RecursionError as error:
        raise _CandidateRejection("decode", "JSON nesting is too deep") from error
    except (OverflowError, TypeError, ValueError) as error:
        raise _CandidateRejection(
            "decode", f"invalid JSON numeric or text value: {type(error).__name__}"
        ) from error
    if not isinstance(document, dict):
        raise _CandidateRejection("decode", "root JSON value must be an object")
    _bounded_json(document)
    canonical_json = json.dumps(
        document, sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    return DecodedCandidate(
        document, canonical_json, hashlib.sha256(encoded).hexdigest()
    )


def normalize_candidate(
    document: Mapping[str, Any],
    *,
    context: GenerationContext,
    authority: MaterialAuthority,
    candidate_id: str,
) -> dict[str, Any]:
    """Normalize only server-owned identity/provenance; preserve candidate keys."""
    if not isinstance(document, Mapping):
        raise _CandidateRejection("normalize", "candidate root must be an object")
    if not isinstance(context, GenerationContext):
        raise GameplayContractError("normalize requires GenerationContext")
    if not isinstance(authority, MaterialAuthority):
        raise GameplayContractError("normalize requires MaterialAuthority")
    selected_candidate = _candidate_id(candidate_id)
    normalized = deepcopy(dict(document))

    if set(normalized) != _ROOT_FIELDS:
        raise _CandidateRejection(
            "parse", "root object must contain exactly the Skill IR fields"
        )
    identity = normalized.get("identity")
    if not isinstance(identity, Mapping):
        raise _CandidateRejection("parse", "$.identity must be an object")
    if set(identity) != {"id", "version", "name", "description"}:
        raise _CandidateRejection(
            "parse", "$.identity has missing or unknown fields"
        )
    normalized["identity"] = dict(identity)
    normalized["identity"]["id"] = selected_candidate
    normalized["identity"]["version"] = 1

    origin = normalized.get("origin")
    if not isinstance(origin, Mapping):
        raise _CandidateRejection("parse", "$.origin must be an object")
    if set(origin) != {"source", "model", "context_hash", "material_ids"}:
        raise _CandidateRejection("parse", "$.origin has missing or unknown fields")
    origin_copy = dict(origin)
    raw_material_ids = origin_copy.get("material_ids")
    if (
        not isinstance(raw_material_ids, list)
        or any(not isinstance(item, str) for item in raw_material_ids)
        or len(set(raw_material_ids)) != len(raw_material_ids)
        or tuple(sorted(raw_material_ids)) != authority.material_ids
    ):
        raise _CandidateRejection(
            "validate",
            "$.origin.material_ids must exactly match selected trusted material IDs",
        )
    origin_copy["source"] = "authored"
    origin_copy["model"] = None
    origin_copy["context_hash"] = context.context_hash
    normalized["origin"] = origin_copy
    normalized["origin"]["material_ids"] = list(raw_material_ids)
    return normalized


def _authority_from_materials(
    materials: Sequence[MaterialDefinition],
) -> MaterialAuthority:
    """Revalidate public dataclasses and derive authority from their traits only."""
    try:
        validated = []
        for index, material in enumerate(tuple(materials)):
            if not isinstance(material, MaterialDefinition):
                raise GameplayContractError(
                    f"materials[{index}] must be a trusted MaterialDefinition"
                )
            validated.append(parse_material({
                "id": material.id,
                "tier": material.tier,
                "region_rarity": material.region_rarity,
                "traits": [{
                    "id": trait.id,
                    "effect_kinds": list(trait.effect_kinds),
                    "selectors": list(trait.selectors),
                    "budget_points": trait.budget_points,
                } for trait in material.traits],
            }, f"$.materials[{index}]"))
        authority = material_authority(validated)
        if not math.isfinite(authority.budget_points) or authority.budget_points <= 0:
            raise GameplayContractError(
                "aggregate material authority budget must be finite and positive"
            )
        return authority
    except GameplayContractError:
        raise
    except (
        AttributeError,
        KeyError,
        TypeError,
        ValueError,
        OverflowError,
        RecursionError,
    ) as error:
        raise GameplayContractError(
            "material authority revalidation failed: "
            f"{type(error).__name__}"
        ) from error


def _authority_from_context(context: GenerationContext) -> MaterialAuthority:
    """Read back the Context authority for an exact equality check only."""
    try:
        row = context.to_dict()["authority"]
        material_ids = row["material_ids"]
        effect_kinds = row["effect_kinds"]
        selectors = row["selectors"]
        budget = row["budget_points"]
        if (
            not isinstance(material_ids, list)
            or not material_ids
            or any(not isinstance(item, str) for item in material_ids)
            or len(set(material_ids)) != len(material_ids)
            or not isinstance(effect_kinds, list)
            or any(not isinstance(item, str) for item in effect_kinds)
            or len(set(effect_kinds)) != len(effect_kinds)
            or not isinstance(selectors, list)
            or any(not isinstance(item, str) for item in selectors)
            or len(set(selectors)) != len(selectors)
            or isinstance(budget, bool)
            or not isinstance(budget, (int, float))
            or not math.isfinite(budget)
            or budget <= 0
        ):
            raise GameplayContractError("generated context authority is invalid")
        return MaterialAuthority(
            tuple(material_ids), tuple(effect_kinds), tuple(selectors), float(budget)
        )
    except (KeyError, TypeError, ValueError) as error:
        raise GameplayContractError("generated context authority is invalid") from error


def _build_result(
    context: GenerationContext,
    candidate_id: str,
    attempts: list[AttemptRecord],
    calls: Sequence[ReplayCall],
    *,
    parsed: SkillIR | None = None,
    compiled: CompiledSkillIR | None = None,
    failure_stage: str | None = None,
    failure_reason: str | None = None,
) -> PipelineResult:
    success = parsed is not None and compiled is not None
    document: dict[str, Any] = {
        "protocol": PIPELINE_PROTOCOL,
        "status": "compiled_unregistered" if success else "rejected",
        "candidate_id": candidate_id,
        "candidate_version": 1 if success else None,
        "context_hash": context.context_hash,
        "catalog_hash": context.catalog_hash,
        "replay": {
            "provider": "offline_replay",
            "generated_skills": 0,
            "live_requests": 0,
            "actual_usage": None,
            "actual_cost": None,
            "model": None,
        },
        "gate_state": {
            "accepted": False,
            "sandbox": "not_run",
            "register": "not_available",
            "usable_pool": False,
        },
        "attempts": [item.to_dict() for item in attempts],
        "calls": [item.to_dict() for item in calls],
        "ir_hash": None if compiled is None else compiled.canonical_hash,
        "blueprint_hash": (
            None if compiled is None else _blueprint_hash(compiled)
        ),
        "ir": None if parsed is None else _canonical_ir(parsed),
        "result_hash": None,
    }
    if failure_stage is not None:
        document["failure"] = {
            "stage": failure_stage,
            "reason": failure_reason or failure_stage,
        }
    else:
        document["failure"] = None
    document["result_hash"] = _readback_hash(document)
    canonical_json = json.dumps(
        document, sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    return PipelineResult(canonical_json, parsed, compiled)


def _canonical_ir(parsed: SkillIR) -> dict[str, Any]:
    return json.loads(parsed.canonical_json)


def _blueprint_hash(compiled: CompiledSkillIR) -> str:
    payload = [
        {
            "id": blueprint.id,
            "version": blueprint.version,
            "canonical_hash": blueprint.canonical_hash,
            "material_ids": list(blueprint.material_ids),
            "budget_used": blueprint.budget_used,
        }
        for blueprint in compiled.blueprints
    ]
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _readback_hash(document: Mapping[str, Any]) -> str:
    unhashed = dict(document)
    unhashed.pop("result_hash", None)
    encoded = json.dumps(
        unhashed, sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _fenced_payload(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    if not stripped.endswith("```"):
        raise _CandidateRejection("decode", "JSON fence is incomplete")
    first_newline = stripped.find("\n")
    if first_newline < 0:
        raise _CandidateRejection("decode", "JSON fence requires a language line")
    opener = stripped[:first_newline]
    if opener not in {"```json", "```JSON"}:
        raise _CandidateRejection("decode", "JSON fence language must be json")
    body = stripped[first_newline + 1 : -3]
    if "```" in body:
        raise _CandidateRejection("decode", "only one JSON fence is permitted")
    if not body.strip():
        raise _CandidateRejection("decode", "JSON fence is empty")
    return body.strip()


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _CandidateRejection("decode", f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _reject_constant(value: str) -> Any:
    raise _CandidateRejection("decode", f"non-finite JSON number {value}")


def _bounded_json(root: Any) -> None:
    stack = [(root, 0)]
    values = 0
    while stack:
        value, depth = stack.pop()
        values += 1
        if values > 65536:
            raise _CandidateRejection("decode", "candidate exceeds JSON value limit")
        if isinstance(value, dict):
            if depth + 1 > MAX_JSON_DEPTH:
                raise _CandidateRejection("decode", "candidate exceeds JSON depth limit")
            for key in value:
                if len(key) > 4096:
                    raise _CandidateRejection("decode", "candidate string is too long")
                try:
                    key.encode("utf-8")
                except UnicodeEncodeError as error:
                    raise _CandidateRejection(
                        "decode", "candidate contains invalid Unicode"
                    ) from error
            stack.extend((item, depth + 1) for item in value.values())
        elif isinstance(value, list):
            if depth + 1 > MAX_JSON_DEPTH:
                raise _CandidateRejection("decode", "candidate exceeds JSON depth limit")
            stack.extend((item, depth + 1) for item in value)
        elif isinstance(value, str):
            if len(value) > 4096:
                raise _CandidateRejection("decode", "candidate string is too long")
            try:
                value.encode("utf-8")
            except UnicodeEncodeError as error:
                raise _CandidateRejection(
                    "decode", "candidate contains invalid Unicode"
                ) from error
        elif isinstance(value, float):
            if not math.isfinite(value):
                raise _CandidateRejection("decode", "candidate number is not finite")
        elif value is not None and not isinstance(value, (bool, int)):
            raise _CandidateRejection("decode", "candidate contains a non-JSON value")


def _candidate_id(value: Any) -> str:
    if not isinstance(value, str) or _CANDIDATE_ID.fullmatch(value) is None:
        raise GameplayContractError(
            "candidate_id must be a lowercase identifier of 2..64 characters"
        )
    return value


def _max_repairs(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 2:
        raise GameplayContractError("max_repairs must be an integer in [0, 2]")
    return value


def _feedback(stage: str, reason: str) -> str:
    return f"stage={stage}; reason={reason}"


def _safe_reason(error: BaseException) -> str:
    text = str(error)
    return text if len(text) <= 1000 else text[:997] + "..."


class _CandidateRejection(Exception):
    def __init__(self, stage: str, reason: str) -> None:
        super().__init__(reason)
        self.stage = stage
        self.reason = reason
