#!/usr/bin/env python3
"""Build a safe, reproducible Codex token-cost ledger from rollout JSONL.

Only allowlisted routing and usage metadata is exported. Prompt text, tool
arguments, configuration, and other rollout payloads are never copied to the
report or printed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence


REFERENCE_DATE = "2026-10-28"
SCHEMA_VERSION = 2
UNKNOWN_MODEL = "unknown"
DEFAULT_SESSION_ROOT = "~/.codex/sessions"
DEFAULT_MAIN_SESSION = "01a181f1-8fad-7161-a01f-04678ebd7df0"
DEFAULT_PROJECT_TURN = "01a1826b-6e9a-7721-bd53-b5464c3829d4"
DEFAULT_OUTPUT = "docs/agent_bootstrap/evidence"
OUTPUT_FILENAME = "agent_cost_ledger.json"

CACHE_ASSUMPTION = Decimal("0.97")
USD_CNY_REFERENCE = Decimal("6.6664")
USD_CNY_RESERVE = Decimal("7.0")
SAFETY_MULTIPLIER = Decimal("1.20")
BUDGET_LIMITS_CNY = {
    "P0": Decimal("100"),
    "P1": Decimal("400"),
    "P2": Decimal("350"),
    "P3": Decimal("200"),
    "P4": Decimal("400"),
    "P5": Decimal("400"),
    "Reserve": Decimal("150"),
    "MAX": Decimal("2000"),
}
STAGE_LIMITS_CNY = {
    stage: limit for stage, limit in BUDGET_LIMITS_CNY.items() if stage != "MAX"
}
STAGE_NAMES = tuple(STAGE_LIMITS_CNY)
DEFAULT_PHASE = "P0"

TOKEN_KEYS = (
    "input_tokens",
    "cached_input_tokens",
    "cache_write_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
)

PRICING_SOURCES = (
    {
        "name": "OpenAI Developers - GPT-6.1-Sol model reference",
        "url": "https://developers.openai.com/api/docs/models/gpt-6.1-sol",
    },
    {
        "name": "DeepSeek API pricing",
        "url": "https://api-docs.deepseek.com/quick_start/pricing",
    },
    {
        # Verified 2026-10-30: Opus 5.5 standard input $4, cache hit $0.20,
        # output $20 per MTok; 1M context at standard pricing (no long tier).
        "name": "Claude Platform Docs - Pricing (Claude Opus 5.5), checked 2026-10-30",
        "url": "https://platform.claude.com/docs/en/about-claude/pricing",
    },
    {
        "name": "Investing.com - USD/CNY historical data",
        "url": "https://www.investing.com/currencies/usd-cny-historical-data",
    },
)


@dataclass(frozen=True)
class PriceSpec:
    family: str
    mapped_model: str
    uncached_input_usd_per_million: Decimal
    cached_input_usd_per_million: Decimal
    output_usd_per_million: Decimal
    long_context_threshold: int | None = None
    long_input_multiplier: Decimal = Decimal("1")
    long_output_multiplier: Decimal = Decimal("1")


PRICE_BOOK: dict[str, PriceSpec] = {
    "tencent/gpt-6.1-sol": PriceSpec(
        family="GPT",
        mapped_model="gpt-6.1-sol",
        uncached_input_usd_per_million=Decimal("2"),
        cached_input_usd_per_million=Decimal("0.10"),
        output_usd_per_million=Decimal("10"),
        long_context_threshold=272_000,
        long_input_multiplier=Decimal("2"),
        long_output_multiplier=Decimal("1.5"),
    ),
    "tencent/deepseek-v4.1-flash": PriceSpec(
        family="DeepSeek",
        mapped_model="DeepSeek-V4.1-Flash (peak standard)",
        uncached_input_usd_per_million=Decimal("0.30"),
        cached_input_usd_per_million=Decimal("0.006"),
        output_usd_per_million=Decimal("1.20"),
    ),
    "tencent/deepseek-v4-pro-ioa": PriceSpec(
        family="DeepSeek",
        mapped_model="DeepSeek-V4-Pro (peak)",
        uncached_input_usd_per_million=Decimal("1.32"),
        cached_input_usd_per_million=Decimal("0.044"),
        output_usd_per_million=Decimal("3.96"),
    ),
    "tencent/claude-opus-5.5": PriceSpec(
        family="Claude",
        mapped_model="claude-opus-5-5 (standard, global)",
        uncached_input_usd_per_million=Decimal("4"),
        cached_input_usd_per_million=Decimal("0.20"),
        output_usd_per_million=Decimal("20"),
    ),
}

UUID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class UsageEvent:
    source_session_id: str
    source_role: str
    inclusion: str
    source_ordinal: int
    source_line: int
    observed_timestamp: str | None
    thread_id: str | None
    turn_id: str | None
    response_id: str | None
    model: str
    stage: str
    usage: dict[str, int | None]
    usage_issues: tuple[str, ...]

    @property
    def dedupe_key(self) -> tuple[str, ...]:
        if self.thread_id and self.response_id:
            return ("thread-response", self.thread_id, self.response_id)
        return (
            "ordinal",
            self.source_session_id,
            str(self.source_ordinal),
            str(self.source_line),
            self.source_role,
        )


def _as_nonempty_str(value: Any) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None


def _as_nonnegative_int(value: Any) -> int:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return 0


def _safe_usage(value: Any) -> tuple[dict[str, int | None], tuple[str, ...]]:
    """Retain valid raw counters, but never turn malformed usage into zero."""
    safe: dict[str, int | None] = {}
    issues: list[str] = []
    if not isinstance(value, Mapping):
        return ({key: None for key in TOKEN_KEYS}, ("usage_not_object",))
    for key in TOKEN_KEYS:
        raw = value.get(key)
        if (
            isinstance(raw, int)
            and not isinstance(raw, bool)
            and raw >= 0
        ):
            safe[key] = raw
        else:
            safe[key] = None
            issues.append(f"usage_invalid:{key}")

    input_tokens = safe.get("input_tokens")
    cached_input_tokens = safe.get("cached_input_tokens")
    output_tokens = safe.get("output_tokens")
    reasoning_output_tokens = safe.get("reasoning_output_tokens")
    if (
        input_tokens is not None
        and cached_input_tokens is not None
        and cached_input_tokens > input_tokens
    ):
        issues.append("usage_invalid:cached_input_tokens_gt_input_tokens")
    if (
        output_tokens is not None
        and reasoning_output_tokens is not None
        and reasoning_output_tokens > output_tokens
    ):
        issues.append("usage_invalid:reasoning_output_tokens_gt_output_tokens")
    return safe, tuple(issues)


def _event_type(event: Mapping[str, Any], payload: Mapping[str, Any]) -> str | None:
    value = event.get("type")
    if isinstance(value, str):
        return value
    value = payload.get("type")
    return value if isinstance(value, str) else None


def _source_session_id(path: Path) -> str:
    matches = UUID_RE.findall(path.stem)
    if matches:
        return matches[-1].lower()
    digest = hashlib.sha256(path.name.encode("utf-8")).hexdigest()[:16]
    return f"file-{digest}"


def find_session_files(session_root: Path, session_id: str) -> list[Path]:
    """Locate rollout files by an allowlisted session ID substring."""
    root = session_root.expanduser()
    if root.is_file():
        candidates = [root]
    elif root.is_dir():
        candidates = list(root.rglob("*.jsonl"))
    else:
        raise FileNotFoundError("session root is unavailable")
    return sorted(
        (path for path in candidates if session_id in path.name),
        key=lambda path: (path.name, str(path.parent)),
    )


def _parse_event_line(line: str) -> Mapping[str, Any] | None:
    try:
        event = json.loads(line)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    return event if isinstance(event, Mapping) else None


def iter_rollout_events(
    path: Path,
    *,
    source_role: str,
    project_turns: frozenset[str],
    agent_ids: frozenset[str],
    default_stage: str,
    agent_stages: Mapping[str, str],
    turn_stages: Mapping[str, str],
    is_main: bool,
) -> Iterator[UsageEvent]:
    """Yield selected usage events while retaining only allowlisted fields."""
    source_session_id = _source_session_id(path)
    nearest_model = UNKNOWN_MODEL
    with path.open("r", encoding="utf-8", errors="strict") as handle:
        for line_number, line in enumerate(handle, 1):
            event = _parse_event_line(line)
            if event is None:
                continue
            payload_value = event.get("payload")
            payload: Mapping[str, Any] = (
                payload_value if isinstance(payload_value, Mapping) else {}
            )
            kind = _event_type(event, payload)
            if kind == "turn_context":
                nearest_model = _as_nonempty_str(payload.get("model")) or UNKNOWN_MODEL
                continue
            if kind != "token_usage_record":
                continue

            thread_id = _as_nonempty_str(payload.get("thread_id"))
            turn_id = _as_nonempty_str(payload.get("turn_id"))
            is_agent_thread = thread_id in agent_ids if thread_id else False
            if is_main and turn_id not in project_turns and not is_agent_thread:
                continue

            inclusion = (
                "agent_full"
                if source_role == "agent" or is_agent_thread
                else "main_project_turn"
            )
            inherited_stage = (
                agent_stages.get(thread_id, default_stage)
                if thread_id
                else default_stage
            )
            stage = (
                turn_stages.get(turn_id, inherited_stage)
                if turn_id
                else inherited_stage
            )
            ordinal = _as_nonnegative_int(event.get("ordinal"))
            if ordinal == 0:
                ordinal = line_number
            event_usage, usage_issues = _safe_usage(payload.get("usage"))
            yield UsageEvent(
                source_session_id=source_session_id,
                source_role=source_role,
                inclusion=inclusion,
                source_ordinal=ordinal,
                source_line=line_number,
                observed_timestamp=_as_nonempty_str(event.get("timestamp")),
                thread_id=thread_id,
                turn_id=turn_id,
                response_id=_as_nonempty_str(payload.get("response_id")),
                model=nearest_model,
                stage=stage,
                usage=event_usage,
                usage_issues=usage_issues,
            )


def normalize_project_turns(
    project_turn: str | None,
    project_turns: Sequence[str] = (),
) -> list[str]:
    values = list(project_turns)
    if project_turn:
        values.insert(0, project_turn)
    normalized = sorted({value for value in values if value})
    if not normalized:
        normalized = [DEFAULT_PROJECT_TURN]
    return normalized


def normalize_stage(value: str) -> str:
    for stage in STAGE_NAMES:
        if value.casefold() == stage.casefold():
            return stage
    raise ValueError(f"unknown budget stage: {value}")


def parse_agent_stages(values: Sequence[str]) -> dict[str, str]:
    stages: dict[str, str] = {}
    for value in values:
        agent_id, separator, stage_value = value.partition("=")
        if not separator or not agent_id or not stage_value:
            raise ValueError("agent stage must use ID=P0..P5 or ID=Reserve")
        stages[agent_id] = normalize_stage(stage_value)
    return stages


def parse_turn_stages(values: Sequence[str]) -> dict[str, str]:
    stages: dict[str, str] = {}
    for value in values:
        turn_id, separator, stage_value = value.partition("=")
        if not separator or not turn_id or not stage_value:
            raise ValueError("turn stage must use TURN_ID=P0..P5 or TURN_ID=Reserve")
        stages[turn_id] = normalize_stage(stage_value)
    return stages


def collect_events(
    session_root: Path,
    *,
    main_session: str,
    project_turns: Sequence[str],
    agent_ids: Sequence[str] = (),
    phase: str = DEFAULT_PHASE,
    agent_stages: Mapping[str, str] | None = None,
    turn_stages: Mapping[str, str] | None = None,
) -> tuple[list[UsageEvent], list[str]]:
    """Collect main project-turn usage and full child-agent usage."""
    main_files = find_session_files(session_root, main_session)
    if not main_files:
        raise FileNotFoundError("main session rollout was not found")

    normalized_agent_ids = sorted({value for value in agent_ids if value})
    agent_id_set = frozenset(normalized_agent_ids)
    selected_turns = frozenset(normalize_project_turns(None, project_turns))
    stage_map = dict(agent_stages or {})
    turn_stage_map = dict(turn_stages or {})
    files: list[tuple[Path, str, bool, str]] = []
    main_file_set = set(main_files)
    for path in main_files:
        files.append((path, "main", True, phase))
    for agent_id in normalized_agent_ids:
        agent_stage = stage_map.get(agent_id, phase)
        for path in find_session_files(session_root, agent_id):
            if path not in main_file_set:
                files.append((path, "agent", False, agent_stage))

    deduped: dict[tuple[str, ...], UsageEvent] = {}
    supplied_agent_ids: set[str] = set()
    for path, source_role, is_main, default_stage in files:
        for event in iter_rollout_events(
            path,
            source_role=source_role,
            project_turns=selected_turns,
            agent_ids=agent_id_set,
            default_stage=default_stage,
            agent_stages=stage_map,
            turn_stages=turn_stage_map,
            is_main=is_main,
        ):
            if event.thread_id in agent_id_set:
                supplied_agent_ids.add(event.thread_id)
            existing = deduped.get(event.dedupe_key)
            if existing is None or (
                existing.source_role != "agent" and event.source_role == "agent"
            ):
                deduped[event.dedupe_key] = event

    records = sorted(
        deduped.values(),
        key=lambda event: (
            event.source_session_id,
            event.source_ordinal,
            event.source_line,
            event.thread_id or "",
            event.response_id or "",
        ),
    )

    issues: list[str] = []
    for agent_id in normalized_agent_ids:
        if agent_id not in supplied_agent_ids:
            issues.append(f"requested_agent_unavailable:{agent_id}")
    return records, issues


def price_spec_for(model: str) -> PriceSpec | None:
    return PRICE_BOOK.get(model)


def family_for_model(model: str) -> str:
    spec = price_spec_for(model)
    return spec.family if spec else "Unknown"


def _money(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP))


def _usage_to_json(usage: Mapping[str, int | None]) -> dict[str, int | None]:
    return {key: usage.get(key) for key in TOKEN_KEYS}


def _valid_usage(usage: Mapping[str, int | None]) -> bool:
    return all(
        isinstance(usage.get(key), int) and not isinstance(usage.get(key), bool)
        for key in TOKEN_KEYS
    )


def calculate_pricing(
    usage: Mapping[str, int | None],
    model: str,
) -> dict[str, Any]:
    """Price one response using the 97% input-cache reference assumption."""
    if not _valid_usage(usage):
        return {
            "priced": False,
            "model_family": family_for_model(model),
            "mapped_model": None,
            "reason": "malformed_usage_unpriced",
            "usage_complete": False,
            "estimated_usd": None,
            "estimated_cny_reference": None,
        }
    spec = price_spec_for(model)
    if spec is None:
        return {
            "priced": False,
            "model_family": "Unknown",
            "mapped_model": None,
            "reason": "unknown_model_unpriced",
            "usage_complete": True,
            "estimated_usd": None,
            "estimated_cny_reference": None,
        }

    input_tokens = Decimal(_as_nonnegative_int(usage.get("input_tokens")))
    output_tokens = Decimal(_as_nonnegative_int(usage.get("output_tokens")))
    assumed_cached = input_tokens * CACHE_ASSUMPTION
    assumed_uncached = input_tokens - assumed_cached
    long_context = bool(
        spec.long_context_threshold is not None
        and input_tokens > Decimal(spec.long_context_threshold)
    )
    input_multiplier = spec.long_input_multiplier if long_context else Decimal("1")
    output_multiplier = spec.long_output_multiplier if long_context else Decimal("1")

    cached_cost = (
        assumed_cached
        * spec.cached_input_usd_per_million
        * input_multiplier
        / Decimal(1_000_000)
    )
    uncached_cost = (
        assumed_uncached
        * spec.uncached_input_usd_per_million
        * input_multiplier
        / Decimal(1_000_000)
    )
    output_cost = (
        output_tokens
        * spec.output_usd_per_million
        * output_multiplier
        / Decimal(1_000_000)
    )
    total_usd = cached_cost + uncached_cost + output_cost
    return {
        "priced": True,
        "model_family": spec.family,
        "mapped_model": spec.mapped_model,
        "usage_complete": True,
        "usd_per_million": {
            "uncached_input": _money(spec.uncached_input_usd_per_million),
            "cached_input": _money(spec.cached_input_usd_per_million),
            "output": _money(spec.output_usd_per_million),
        },
        "assumed_cache_ratio": float(CACHE_ASSUMPTION),
        "assumed_cached_input_tokens": _money(assumed_cached),
        "assumed_uncached_input_tokens": _money(assumed_uncached),
        "long_context": {
            "applied": long_context,
            "threshold_input_tokens": spec.long_context_threshold,
            "input_multiplier": float(input_multiplier),
            "output_multiplier": float(output_multiplier),
        },
        "estimated_usd": {
            "cached_input": _money(cached_cost),
            "uncached_input": _money(uncached_cost),
            "output": _money(output_cost),
            "total": _money(total_usd),
        },
        "estimated_cny_reference": _money(total_usd * USD_CNY_REFERENCE),
    }


def empty_usage() -> dict[str, int]:
    return {key: 0 for key in TOKEN_KEYS}


def add_usage(target: dict[str, int], usage: Mapping[str, int | None]) -> None:
    if not _valid_usage(usage):
        return
    for key in TOKEN_KEYS:
        target[key] += _as_nonnegative_int(usage.get(key))


def build_budget(
    stage_reserved_cny: Mapping[str, Decimal],
    total_reserved_cny: Decimal,
    incomplete_reasons: Sequence[str],
    *,
    stage: str = DEFAULT_PHASE,
) -> dict[str, Any]:
    tiers: dict[str, Any] = {}
    for tier in STAGE_NAMES:
        limit_cny = STAGE_LIMITS_CNY[tier]
        tier_reserved = stage_reserved_cny.get(tier, Decimal("0"))
        tiers[tier] = {
            "limit_cny": _money(limit_cny),
            "reserved_cny": _money(tier_reserved),
            "within_limit": tier_reserved <= limit_cny,
        }
    max_limit_cny = BUDGET_LIMITS_CNY["MAX"]
    tiers["MAX"] = {
        "limit_cny": _money(max_limit_cny),
        "reserved_cny": _money(total_reserved_cny),
        "within_limit": total_reserved_cny <= max_limit_cny,
    }

    active_limit = BUDGET_LIMITS_CNY.get(stage, BUDGET_LIMITS_CNY["MAX"])
    active_reserved = stage_reserved_cny.get(stage, total_reserved_cny)
    any_stage_over = any(
        not tiers[tier]["within_limit"] for tier in STAGE_NAMES
    )
    max_over = not tiers["MAX"]["within_limit"]
    if incomplete_reasons:
        decision = "fail_closed_incomplete_accounting"
        within_budget = False
    elif any_stage_over or max_over:
        decision = "over_budget"
        within_budget = False
    else:
        decision = "within_budget"
        within_budget = True
    return {
        "basis": "known-priced reference USD converted at reserve FX",
        "reference_fx_usd_cny": float(USD_CNY_REFERENCE),
        "reserve_fx_usd_cny": float(USD_CNY_RESERVE),
        "safety_multiplier": float(SAFETY_MULTIPLIER),
        "stage": stage,
        "active_limit_cny": _money(active_limit),
        "active_reserved_cny": _money(active_reserved),
        "active_stage_within_limit": active_reserved <= active_limit,
        "reserved_cny": _money(total_reserved_cny),
        "all_stage_limits_within": not any_stage_over,
        "max_limit_within": not max_over,
        "unknown_pricing_present": any(
            reason.startswith("unknown_pricing") for reason in incomplete_reasons
        ),
        "incomplete_accounting": bool(incomplete_reasons),
        "incomplete_reasons": list(incomplete_reasons),
        "within_budget": within_budget,
        "decision": decision,
        "tiers": tiers,
    }


def build_report(
    session_root: Path,
    *,
    main_session: str = DEFAULT_MAIN_SESSION,
    project_turn: str | None = DEFAULT_PROJECT_TURN,
    project_turns: Sequence[str] = (),
    agent_ids: Sequence[str] = (),
    phase: str = DEFAULT_PHASE,
    agent_stages: Mapping[str, str] | None = None,
    turn_stages: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    normalized_phase = normalize_stage(phase)
    normalized_stages = {
        agent_id: normalize_stage(stage)
        for agent_id, stage in (agent_stages or {}).items()
    }
    normalized_turn_stages = {
        turn_id: normalize_stage(stage)
        for turn_id, stage in (turn_stages or {}).items()
    }
    selected_turns = normalize_project_turns(project_turn, project_turns)
    events, selection_issues = collect_events(
        session_root,
        main_session=main_session,
        project_turns=selected_turns,
        agent_ids=agent_ids,
        phase=normalized_phase,
        agent_stages=normalized_stages,
        turn_stages=normalized_turn_stages,
    )

    families: dict[str, dict[str, Any]] = {
        "GPT": {
            "record_count": 0,
            "known_record_count": 0,
            "unknown_record_count": 0,
            "actual_usage": empty_usage(),
            "estimated_usd": Decimal("0"),
            "estimated_usd_json": 0.0,
            "models": {},
            "responses": [],
        },
        "DeepSeek": {
            "record_count": 0,
            "known_record_count": 0,
            "unknown_record_count": 0,
            "actual_usage": empty_usage(),
            "estimated_usd": Decimal("0"),
            "estimated_usd_json": 0.0,
            "models": {},
            "responses": [],
        },
        "Claude": {
            "record_count": 0,
            "known_record_count": 0,
            "unknown_record_count": 0,
            "actual_usage": empty_usage(),
            "estimated_usd": Decimal("0"),
            "estimated_usd_json": 0.0,
            "models": {},
            "responses": [],
        },
        "Unknown": {
            "record_count": 0,
            "known_record_count": 0,
            "unknown_record_count": 0,
            "actual_usage": empty_usage(),
            "estimated_usd": Decimal("0"),
            "estimated_usd_json": 0.0,
            "models": {},
            "responses": [],
        },
    }
    all_usage = empty_usage()
    known_total_usd = Decimal("0")
    unknown_models: set[str] = set()
    malformed_usage_count = 0
    stage_usage: dict[str, dict[str, int]] = {
        stage: empty_usage() for stage in STAGE_NAMES
    }
    stage_known_usd: dict[str, Decimal] = {
        stage: Decimal("0") for stage in STAGE_NAMES
    }

    for event in events:
        pricing = (
            calculate_pricing(event.usage, event.model)
            if not event.usage_issues
            else {
                "priced": False,
                "model_family": family_for_model(event.model),
                "mapped_model": None,
                "reason": "malformed_usage_unpriced",
                "usage_complete": False,
                "estimated_usd": None,
                "estimated_cny_reference": None,
            }
        )
        family = pricing["model_family"]
        bucket = families[family]
        bucket["record_count"] += 1
        add_usage(bucket["actual_usage"], event.usage)
        add_usage(all_usage, event.usage)
        if event.stage not in stage_usage:
            stage_usage[event.stage] = empty_usage()
        add_usage(stage_usage[event.stage], event.usage)
        bucket["models"][event.model] = bucket["models"].get(event.model, 0) + 1
        if event.usage_issues:
            malformed_usage_count += 1

        response = {
            "model": event.model,
            "model_family": family,
            "thread_id": event.thread_id,
            "turn_id": event.turn_id,
            "response_id": event.response_id,
            "source_session_id": event.source_session_id,
            "source_role": event.source_role,
            "inclusion": event.inclusion,
            "stage": event.stage,
            "source_ordinal": event.source_ordinal,
            "actual_usage": _usage_to_json(event.usage),
            "usage_complete": not event.usage_issues,
            "usage_issues": list(event.usage_issues),
            "pricing": pricing,
        }
        bucket["responses"].append(response)

        if pricing["priced"]:
            amount = Decimal(str(pricing["estimated_usd"]["total"]))
            bucket["known_record_count"] += 1
            bucket["estimated_usd"] += amount
            known_total_usd += amount
            stage_known_usd[event.stage] = (
                stage_known_usd.get(event.stage, Decimal("0")) + amount
            )
        else:
            bucket["unknown_record_count"] += 1
            if pricing["reason"] == "unknown_model_unpriced":
                unknown_models.add(event.model)

    for family_name, bucket in families.items():
        bucket["actual_usage"] = _usage_to_json(bucket["actual_usage"])
        priced_total = bucket.pop("estimated_usd")
        bucket["estimated_usd_json"] = (
            None if family_name == "Unknown" else _money(priced_total)
        )
        bucket["models"] = dict(sorted(bucket["models"].items()))

    incomplete_reasons = list(selection_issues)
    if unknown_models:
        incomplete_reasons.append("unknown_pricing")
    if malformed_usage_count:
        incomplete_reasons.append("malformed_usage")
    status = "partial" if incomplete_reasons else "complete"
    unknown_count = sum(bucket["unknown_record_count"] for bucket in families.values())
    total_estimated_usd = None if unknown_count else _money(known_total_usd)
    total_estimated_cny = (
        None if unknown_count else _money(known_total_usd * USD_CNY_REFERENCE)
    )
    selected_agent_ids = sorted({value for value in agent_ids if value})
    warnings = [
        "The final main-response usage may not be finalized; rerun after completion.",
        "Reference estimates are not actual intranet bills.",
        "Complete accounting describes the observed snapshot, not future charges.",
        (
            "Stage attribution is exact only for turn overrides; agent-stage and "
            "default phase mappings are approximate/shared and conservatively charged."
        ),
    ]
    warnings.extend(f"Requested source is unavailable: {issue.split(':', 1)[1]}" for issue in selection_issues)
    if unknown_models:
        warnings.append(
            "One or more models are unpriced; known-cost totals exclude them."
        )
    if malformed_usage_count:
        warnings.append(
            "Malformed usage was retained as null counters and excluded from cost."
        )
    if incomplete_reasons:
        warnings.append("Accounting is partial; spending gates fail closed.")

    stages: dict[str, Any] = {}
    for stage in STAGE_NAMES:
        stage_events = [event for event in events if event.stage == stage]
        stage_usd = stage_known_usd.get(stage, Decimal("0"))
        stage_reserved = stage_usd * USD_CNY_RESERVE * SAFETY_MULTIPLIER
        stages[stage] = {
            "record_count": len(stage_events),
            "actual_usage": _usage_to_json(stage_usage.get(stage, empty_usage())),
            "known_estimated_usd": _money(stage_usd),
            "reserved_cny": _money(stage_reserved),
            "limit_cny": _money(STAGE_LIMITS_CNY[stage]),
            "within_limit": stage_reserved <= STAGE_LIMITS_CNY[stage],
        }

    total_reserved_cny = known_total_usd * USD_CNY_RESERVE * SAFETY_MULTIPLIER
    stage_reserved_cny = {
        stage: value * USD_CNY_RESERVE * SAFETY_MULTIPLIER
        for stage, value in stage_known_usd.items()
    }
    budget = build_budget(
        stage_reserved_cny,
        total_reserved_cny,
        incomplete_reasons,
        stage=normalized_phase,
    )

    source_ordinals: dict[str, int] = {}
    for event in events:
        source_ordinals[event.source_session_id] = max(
            source_ordinals.get(event.source_session_id, 0),
            event.source_ordinal,
        )
    observed_timestamps = [
        event.observed_timestamp
        for event in events
        if event.observed_timestamp is not None
    ]
    snapshot = {
        "max_observed_usage_timestamp": (
            max(observed_timestamps) if observed_timestamps else None
        ),
        "source_max_ordinals": dict(sorted(source_ordinals.items())),
        "usage_record_count": len(events),
        "note": (
            "Observed usage snapshot only; status complete does not mean the "
            "session has no future charges."
        ),
    }

    return {
        "schema_version": SCHEMA_VERSION + 1,
        "reference_date": REFERENCE_DATE,
        "status": status,
        "phase": normalized_phase,
        "selection": {
            "main_session": main_session,
            "project_turn": selected_turns[0],
            "project_turns": selected_turns,
            "agent_ids": selected_agent_ids,
            "agent_stages": dict(sorted(normalized_stages.items())),
            "turn_stages": dict(sorted(normalized_turn_stages.items())),
            "phase": normalized_phase,
            "main_scope": "project_turn_only",
            "agent_scope": "full",
        },
        "selection_rule": (
            "Include token_usage_record.payload.usage from the main session only "
            "for selected project-turn records; include selected child sessions/threads "
            "in full. Repeated project turns are aggregated idempotently."
        ),
        "attribution_rule": (
            "Attribute usage to the nearest preceding turn_context.payload.model; "
            "missing model metadata becomes unknown."
        ),
        "dedupe_rule": (
            "Deduplicate by thread_id + response_id; if either ID is missing, use "
            "a stable source-session and ordinal fallback so distinct calls remain "
            "distinct."
        ),
        "stage_attribution": {
            "precedence": "turn_stage > agent_stage > phase",
            "agent_stage_scope": "whole_child_history_approximate",
            "main_default": normalized_phase,
            "main_default_is_conservative": True,
            "reused_agents_may_span_stages": True,
            "exact_attribution_claimed": False,
            "note": (
                "Agent-stage mapping assigns a reused child's full history to one "
                "stage; treat it as approximate/shared. The default P0 charge is "
                "conservative for main turns spanning P0 architecture and P1 work."
            ),
        },
        "assumptions": {
            "input_cache_ratio_for_cost": float(CACHE_ASSUMPTION),
            "recorded_cache_is_preserved_separately": True,
            "recorded_cache_is_not_used_for_cost": True,
            "reasoning_is_subset_of_output": True,
            "reasoning_not_added_to_output": True,
            "cache_write_is_reported_separately": True,
            "cache_write_not_added_to_cost": True,
            "cumulative_usage_fields_ignored": [
                "turn_token_usage",
                "thread_token_usage",
                "total_tokens",
            ],
            "reference_estimates_not_actual_intranet_bills": True,
            "malformed_usage_fails_closed": True,
            "unavailable_requested_source_fails_closed": True,
        },
        "pricing_sources": list(PRICING_SOURCES),
        "totals": {
            "record_count": len(events),
            "known_record_count": sum(
                bucket["known_record_count"] for bucket in families.values()
            ),
            "unknown_record_count": sum(
                bucket["unknown_record_count"] for bucket in families.values()
            ),
            "malformed_usage_record_count": malformed_usage_count,
            "actual_usage": _usage_to_json(all_usage),
            "estimated_usd": total_estimated_usd,
            "estimated_cny_reference": total_estimated_cny,
            "known_estimated_usd": _money(known_total_usd),
            "known_estimated_cny_reference": _money(
                known_total_usd * USD_CNY_REFERENCE
            ),
            "unknown_models": sorted(unknown_models),
            "incomplete_reasons": incomplete_reasons,
        },
        "budget": budget,
        "stages": stages,
        "snapshot": snapshot,
        "families": families,
        "warnings": warnings,
    }


def write_report(report: Mapping[str, Any], output_dir: Path) -> Path:
    """Atomically regenerate the deterministic JSON artifact."""
    destination = output_dir.expanduser() / OUTPUT_FILENAME
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(report, indent=2, sort_keys=True, ensure_ascii=True) + "\n"
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=destination.parent,
            prefix=f".{OUTPUT_FILENAME}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_name = handle.name
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, destination)
    finally:
        if temporary_name and os.path.exists(temporary_name):
            os.unlink(temporary_name)
    return destination


def _safe_console_summary(report: Mapping[str, Any], destination: Path) -> dict[str, Any]:
    return {
        "artifact": destination.name,
        "status": report["status"],
        "record_count": report["totals"]["record_count"],
        "estimated_usd": report["totals"]["estimated_usd"],
        "known_estimated_usd": report["totals"]["known_estimated_usd"],
        "unknown_record_count": report["totals"]["unknown_record_count"],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build an allowlisted Codex token-cost ledger from rollout JSONL."
    )
    parser.add_argument("--session-root", default=DEFAULT_SESSION_ROOT)
    parser.add_argument("--main-session", default=DEFAULT_MAIN_SESSION)
    parser.add_argument(
        "--project-turn",
        action="append",
        default=[],
        help="Project turn to aggregate; repeatable. Defaults to the current turn.",
    )
    parser.add_argument(
        "--project-turns",
        action="append",
        default=[],
        help="Additional project turn to aggregate; repeatable.",
    )
    parser.add_argument(
        "--agent-id",
        action="append",
        default=[],
        help="Child session/thread ID to include in full; repeatable.",
    )
    parser.add_argument("--phase", default=DEFAULT_PHASE)
    parser.add_argument(
        "--agent-stage",
        action="append",
        default=[],
        help="Associate a child agent with a stage as ID=P0..P5 or ID=Reserve.",
    )
    parser.add_argument(
        "--turn-stage",
        action="append",
        default=[],
        help="Override one turn's stage as TURN_ID=P0..P5 or TURN_ID=Reserve.",
    )
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--check-budget",
        action="store_true",
        help="Fail closed for incomplete accounting or an exceeded stage gate.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        agent_stages = parse_agent_stages(args.agent_stage)
        turn_stages = parse_turn_stages(args.turn_stage)
        requested_turns = normalize_project_turns(
            None,
            [*args.project_turn, *args.project_turns],
        )
        report = build_report(
            Path(args.session_root),
            main_session=args.main_session,
            project_turn=None,
            project_turns=requested_turns,
            agent_ids=args.agent_id,
            phase=args.phase,
            agent_stages=agent_stages,
            turn_stages=turn_stages,
        )
        destination = write_report(report, Path(args.output))
    except (FileNotFoundError, OSError, UnicodeError, ValueError):
        print(
            json.dumps(
                {
                    "status": "error",
                    "error": "rollout read failed; input paths or schema unavailable",
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2

    print(
        json.dumps(
            _safe_console_summary(report, destination),
            sort_keys=True,
            ensure_ascii=True,
        )
    )
    if args.check_budget:
        if report["status"] == "partial":
            return 2
        if not report["budget"]["within_budget"]:
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
