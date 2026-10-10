"""Stable player-facing source explanations backed by PMW traces."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from .contracts import GameplayContractError


@dataclass(frozen=True, slots=True)
class ExplanationSource:
    kind: str
    public_id: str
    label: str
    contribution: str


def explain_result(result: Any, *, event: str, sources: Iterable[ExplanationSource],
                   values: Mapping[str, Any] | None = None) -> dict[str, Any]:
    rows = tuple(sources)
    allowed = {"skill", "passive", "trait", "status", "weather", "ecology", "area_law", "material"}
    if any(item.kind not in allowed or not item.public_id or not item.label or not item.contribution for item in rows):
        raise GameplayContractError("explanation source is invalid")
    trace = result.trace.semantic_projection()
    return {
        "event": event,
        "sources": [
            {"kind": item.kind, "id": item.public_id, "label": item.label, "contribution": item.contribution}
            for item in rows
        ],
        "values": dict(values or {}),
        "causal_trace": trace,
    }
