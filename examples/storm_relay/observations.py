"""Public, browser-safe projections for the Storm Relay demo.

The authoritative session may keep PMW ``WorldState`` objects, traces, and a
mechanism registry.  None of those are browser protocol objects.  This module
is deliberately an allow-list boundary between that trusted state and the UI.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


PUBLIC_TOP_LEVEL = (
    "outcome",
    "time",
    "current_area",
    "player",
    "areas",
    "inventory",
    "discoveries",
    "recipes",
    "registered_skills",
    "equipped_skills",
    "combat",
    "recent_events",
    "feedback",
    "legal_actions",
)

# Trace objects and registries occasionally contain a ``to_dict`` method.  A
# recursive conversion here would accidentally turn that implementation detail
# into a browser API, so public values are data-only and shallowly structured.
_SCALAR = (str, int, float, bool, type(None))


def _json_data(value: Any, *, depth: int = 0) -> Any:
    """Return JSON-safe plain data, rejecting object graphs at the boundary."""

    if isinstance(value, _SCALAR):
        return value
    if depth >= 8:
        return "[truncated]"
    if isinstance(value, Mapping):
        return {
            str(key): _json_data(item, depth=depth + 1)
            for key, item in value.items()
            if isinstance(key, (str, int, float, bool))
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_json_data(item, depth=depth + 1) for item in value]
    return "[private]"


def summarize_event(event: Mapping[str, Any]) -> dict[str, Any]:
    """Return a compact source-labelled event suitable for the event feed."""

    allowed = ("id", "type", "message", "source", "target", "area", "tick", "kind")
    summary = {key: _json_data(event[key]) for key in allowed if key in event}
    # The UI requires an explicit source label even for system events.
    summary["source"] = str(summary.get("source") or "system")
    return summary


def project_public_state(state: Mapping[str, Any]) -> dict[str, Any]:
    """Build the stable JSON state document consumed by the local browser UI.

    ``state`` must already be a session's public snapshot.  Unknown fields are
    intentionally discarded; in particular this prevents raw WorldState,
    causal traces, private controller state, and registry internals escaping as
    new session implementations evolve.
    """

    if not isinstance(state, Mapping):
        raise TypeError("Storm Relay public state must be a mapping")

    result: dict[str, Any] = {}
    for field in PUBLIC_TOP_LEVEL:
        value = state.get(field)
        if field == "recent_events":
            if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
                result[field] = []
            else:
                result[field] = [
                    summarize_event(item)
                    for item in value
                    if isinstance(item, Mapping)
                ]
        elif field == "legal_actions":
            if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
                result[field] = []
            else:
                result[field] = [
                    _json_data(item)
                    for item in value
                    if isinstance(item, Mapping)
                ]
        elif field in ("areas", "inventory", "discoveries", "recipes", "registered_skills", "equipped_skills", "feedback"):
            result[field] = _json_data(value) if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)) else []
        elif field in ("time", "player", "combat"):
            result[field] = _json_data(value) if isinstance(value, Mapping) else {}
        else:
            result[field] = _json_data(value)
    return result


def session_view(session: Any) -> dict[str, Any]:
    """Read and project a session snapshot without exposing session internals."""

    return project_public_state(session.public_state())
