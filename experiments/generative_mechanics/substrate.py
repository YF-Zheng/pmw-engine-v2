"""Frozen public substrate shared by all lab environments.

The eight fields are genuinely normalized.  ``SUBSTRATE_SYSTEM_LAWS`` is
loaded beside the 24 generic interaction laws by every experiment entry
point.  Bounds are enforced by PMW state closure (and are therefore visible
in causal traces); dissipation is an explicit event, never an implicit Python
mutation.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from pmw import parse_law

CHANNELS = (
    "temperature",
    "wetness",
    "electric_field",
    "fire_intensity",
    "sound_level",
    "ground_stability",
    "water_level",
    "visibility",
)

CHANNEL_SET = frozenset(CHANNELS)
FIELD_MIN = 0.0
FIELD_MAX = 1.0

ENVIRONMENT_VARIANTS: dict[str, dict[str, float]] = {
    "standard": {},
    "dry": {"wetness": -0.25, "water_level": -0.25},
    "saturated": {"wetness": 0.25, "water_level": 0.25},
    "charged": {"electric_field": 0.35},
    "unstable": {"ground_stability": -0.30},
    "obscured": {"visibility": -0.35, "sound_level": 0.15},
}


def _ref(channel: str) -> str:
    return f"$zone.fields.{channel}"


BOUNDS_LAW: dict[str, Any] = {
    "id": "gm.substrate.01.normalized_bounds",
    "mode": "state",
    "priority": 1000,
    "bindings": {"zone": {"kind": "entity", "requires": ["fields", "zone"]}},
    "when": {"any": [
        {"ref": _ref(channel), "lt": FIELD_MIN} for channel in CHANNELS
    ] + [
        {"ref": _ref(channel), "gt": FIELD_MAX} for channel in CHANNELS
    ]},
    "effects": [
        {"op": "set", "target": _ref(channel), "value": {"clamp": [_ref(channel), FIELD_MIN, FIELD_MAX]}}
        for channel in CHANNELS
    ],
}

# Environmental fields relax after each public step.  Temperature relaxes
# toward 0.5, stability and visibility toward 1.0, and intensities toward 0.
_DISSIPATION_TARGETS = {
    "temperature": {"add": [{"mul": [_ref("temperature"), 0.94]}, 0.03]},
    "wetness": {"mul": [_ref("wetness"), 0.96]},
    "electric_field": {"mul": [_ref("electric_field"), 0.88]},
    "fire_intensity": {"mul": [_ref("fire_intensity"), 0.90]},
    "sound_level": {"mul": [_ref("sound_level"), 0.82]},
    "ground_stability": {"add": [{"mul": [_ref("ground_stability"), 0.97]}, 0.03]},
    "water_level": {"mul": [_ref("water_level"), 0.98]},
    "visibility": {"add": [{"mul": [_ref("visibility"), 0.96]}, 0.04]},
}

DISSIPATION_LAW: dict[str, Any] = {
    "id": "gm.substrate.02.dissipation",
    "mode": "event",
    "priority": 0,
    "bindings": {"zone": {"kind": "entity", "requires": ["fields", "zone"]}},
    "when": {"event.type": {"eq": "lab.dissipate"}},
    "effects": [
        {"op": "set", "target": _ref(channel), "value": value}
        for channel, value in _DISSIPATION_TARGETS.items()
    ],
}

SUBSTRATE_SYSTEM_LAWS = (BOUNDS_LAW, DISSIPATION_LAW)


def system_laws():
    """Return fresh parsed invariant/dissipation laws."""
    return [parse_law(deepcopy(raw)) for raw in SUBSTRATE_SYSTEM_LAWS]


def validate_public_fields(values: Any, path: str = "initial_fields") -> dict[str, float]:
    """Validate a sparse override containing only normalized public fields."""
    if not isinstance(values, dict):
        raise ValueError(f"{path}: must be an object")
    unknown = set(values) - CHANNEL_SET
    if unknown:
        raise ValueError(f"{path}: unknown public fields: {sorted(unknown)}")
    result: dict[str, float] = {}
    for key, value in values.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{path}.{key}: must be a number in [0, 1]")
        number = float(value)
        if not FIELD_MIN <= number <= FIELD_MAX:
            raise ValueError(f"{path}.{key}: must be in [0, 1]")
        result[key] = number
    return result


def apply_public_initialization(world, *, variant: str = "standard", overrides: dict[str, float] | None = None) -> None:
    """Apply a named public variant and sparse public overrides before attach."""
    if variant not in ENVIRONMENT_VARIANTS:
        raise ValueError(f"unknown environment variant: {variant}")
    overrides = validate_public_fields(overrides or {})
    zones = [entity for entity in world.entities.values() if "zone" in entity.components]
    if not zones:
        raise ValueError("world has no zone for public initialization")
    for zone in zones:
        fields = zone.components["fields"]
        for channel, delta in ENVIRONMENT_VARIANTS[variant].items():
            fields[channel] = min(FIELD_MAX, max(FIELD_MIN, float(fields[channel]) + delta))
        fields.update(overrides)


def public_fields_are_bounded(state: dict[str, Any]) -> bool:
    """Check every externally serialized zone field value."""
    for entity in state.get("entities", []):
        fields = entity.get("components", {}).get("fields")
        if fields is None:
            continue
        if set(fields) != CHANNEL_SET:
            return False
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not FIELD_MIN <= float(value) <= FIELD_MAX for value in fields.values()):
            return False
    return True
