"""Stable gameplay-facing explanations backed by PMW causal traces."""

from __future__ import annotations

from .actions import ActionOutcome


def explain_action(outcome: ActionOutcome) -> dict:
    trace = outcome.event_result.trace.semantic_projection()
    return {
        "request_id": outcome.request.request_id,
        "action_id": outcome.definition.id,
        "action_version": outcome.definition.version,
        "cost": {"duration": outcome.cost.duration, "mana": outcome.cost.mana},
        "effects": [dict(item) for item in outcome.effect_outcomes],
        "causal_trace": trace,
    }
