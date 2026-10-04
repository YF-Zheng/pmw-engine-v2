import math
from typing import Any

from .errors import PMWValidationError
from .world import validate_state_value


class EventValidationError(PMWValidationError):
    pass


def validate_event(raw: Any, document: str = "event") -> None:
    if not isinstance(raw, dict): raise EventValidationError(f"document={document} path=$ event must be object")
    if not isinstance(raw.get("id"), str) or not raw["id"]: raise EventValidationError(f"document={document} path=id must be non-empty string")
    _event_fields(raw, document, allow_id=True, allow_provenance=True)


def validate_derived_event(raw: Any, document: str) -> None:
    if not isinstance(raw, dict): raise EventValidationError(f"document={document} derived event must be object")
    _event_fields(raw, document, allow_id=True, allow_provenance=True)


def _event_fields(raw: dict[str, Any], document: str, allow_id: bool, allow_provenance: bool) -> None:
    if not isinstance(raw.get("type"), str) or not raw["type"]: raise EventValidationError(f"document={document} path=type must be non-empty string")
    if "time" in raw and (not isinstance(raw["time"], (int, float)) or isinstance(raw["time"], bool) or not math.isfinite(raw["time"])): raise EventValidationError(f"document={document} path=time must be finite number")
    for key in ("source", "target"):
        if key in raw and raw[key] is not None and not isinstance(raw[key], str): raise EventValidationError(f"document={document} path={key} must be string|null")
    if "payload" in raw:
        if not isinstance(raw["payload"], dict): raise EventValidationError(f"document={document} path=payload must be object")
        try: validate_state_value(raw["payload"], "payload")
        except Exception as exc: raise EventValidationError(f"document={document} path=payload invalid JSON value") from exc
    if "provenance" in raw:
        provenance = raw["provenance"]
        if not isinstance(provenance, dict) or provenance.get("kind") not in {"external", "derived", "scheduled"} or provenance.get("parent_event") is not None and not isinstance(provenance.get("parent_event"), str): raise EventValidationError(f"document={document} path=provenance invalid")
