"""Independent closed-form model inferred from the task's published Q values."""

from __future__ import annotations


def reference_initial_q(cf: float, ci: float) -> dict[str, float]:
    return {
        "calibrate": 1.0 - ci - cf,
        "forge_water": 0.825 - cf,
        "forge_resonance": 0.825 - cf,
        "repair_water": 0.65,
        "repair_resonance": 0.35,
    }


def reference_optimum(cf: float, ci: float) -> tuple[tuple[str, ...], float]:
    values = reference_initial_q(cf, ci)
    best = max(values.values())
    return tuple(sorted(action for action, value in values.items() if abs(value - best) < 1e-12)), best
