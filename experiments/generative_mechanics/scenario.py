"""Strict scenario model for the Generative Mechanics Lab benchmark."""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
import re
from typing import Any

from .spec import SkillSpec, load_skill


ROOT = Path(__file__).resolve().parent
SCENARIO_FIELDS = frozenset({
    "id", "split", "category", "environment", "build", "program",
    "horizons", "weights", "target_count",
})
SPLITS = frozenset({"calibration", "held_out"})
CATEGORIES = frozenset({
    "short_combat", "long_combat", "resource_limited", "multi_target",
    "environmental_hazard", "aftermath",
})
WEIGHT_KEYS = (
    "combat", "survival", "control", "utility", "exploration_world_impact",
)
HORIZON_KEYS = ("combat_end", "short", "medium")
ID_PATTERN = re.compile(r"[a-z][a-z0-9_]{2,63}")
MAX_STEP_REPEATS = 100
MAX_TIME = 3600.0


class ScenarioError(ValueError):
    """Raised when benchmark scenario data violates the frozen contract."""


@dataclass(frozen=True, slots=True)
class Build:
    backpack: tuple[str, ...]
    active: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Cast:
    skill: str
    target: str
    op: str = "cast"


@dataclass(frozen=True, slots=True)
class Step:
    repeats: int
    op: str = "step"


@dataclass(frozen=True, slots=True)
class Advance:
    to: float
    op: str = "advance"


ProgramInstruction = Cast | Step | Advance


@dataclass(frozen=True, slots=True)
class Scenario:
    id: str
    split: str
    category: str
    environment: str
    build: Build
    program: tuple[ProgramInstruction, ...]
    horizons: dict[str, float]
    weights: dict[str, float]
    target_count: int


def _fail(path: str, message: str) -> None:
    raise ScenarioError(f"{path}: {message}")


def _strict_object(value: Any, path: str, fields: set[str] | frozenset[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail(path, "must be an object")
    unknown = set(value) - fields
    missing = fields - set(value)
    if unknown or missing:
        _fail(path, f"strict fields required; unknown={sorted(unknown)} missing={sorted(missing)}")
    return value


def _finite(value: Any, path: str, *, low: float = 0.0, high: float = MAX_TIME) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        _fail(path, "must be a finite number")
    result = float(value)
    if not low <= result <= high:
        _fail(path, f"must be in [{low}, {high}]")
    return result


def _skill_catalog(skills_dir: Path) -> dict[str, SkillSpec]:
    catalog: dict[str, SkillSpec] = {}
    for path in sorted(skills_dir.glob("*.json")):
        if path.name == "manifest.json":
            continue
        skill = load_skill(path)
        if skill.id in catalog:
            _fail("build", f"duplicate SkillSpec id in catalog: {skill.id}")
        catalog[skill.id] = skill
    return catalog


def _skill_ids(value: Any, path: str, *, length: int, catalog: dict[str, SkillSpec]) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) != length:
        _fail(path, f"must contain exactly {length} skill ids")
    if any(not isinstance(item, str) for item in value):
        _fail(path, "skill ids must be strings")
    result = tuple(value)
    if len(set(result)) != len(result):
        _fail(path, "skill ids must be unique")
    unknown = sorted(set(result) - set(catalog))
    if unknown:
        _fail(path, f"unknown skill ids: {unknown}")
    return result


def validate_scenario(
    raw: Any,
    *,
    environments_dir: str | Path | None = None,
    skills_dir: str | Path | None = None,
) -> Scenario:
    """Validate untrusted scenario JSON and resolve all repository references."""
    data = _strict_object(raw, "$", SCENARIO_FIELDS)
    scenario_id = data["id"]
    if not isinstance(scenario_id, str) or not ID_PATTERN.fullmatch(scenario_id):
        _fail("id", "must match [a-z][a-z0-9_]{2,63}")
    split = data["split"]
    if split not in SPLITS:
        _fail("split", f"must be one of {sorted(SPLITS)}")
    if not scenario_id.startswith(f"{split}_"):
        _fail("id", "must start with its split name")
    category = data["category"]
    if category not in CATEGORIES:
        _fail("category", f"must be one of {sorted(CATEGORIES)}")
    target_count = data["target_count"]
    if isinstance(target_count, bool) or not isinstance(target_count, int) or not 1 <= target_count <= 4:
        _fail("target_count", "must be an integer in [1, 4]")
    if (category == "multi_target") != (target_count > 1):
        _fail("target_count", "must exceed one exactly for multi_target scenarios")

    environment = data["environment"]
    if not isinstance(environment, str) or not ID_PATTERN.fullmatch(environment):
        _fail("environment", "must be a canonical environment id")
    env_dir = Path(environments_dir) if environments_dir is not None else ROOT / "environments"
    if not (env_dir / f"{environment}.json").is_file():
        _fail("environment", f"unknown environment: {environment}")

    skill_dir = Path(skills_dir) if skills_dir is not None else ROOT / "skills"
    catalog = _skill_catalog(skill_dir)
    build_raw = _strict_object(data["build"], "build", frozenset({"backpack", "active"}))
    backpack = _skill_ids(build_raw["backpack"], "build.backpack", length=10, catalog=catalog)
    active = _skill_ids(build_raw["active"], "build.active", length=6, catalog=catalog)
    if not set(active) <= set(backpack):
        _fail("build.active", "must be a subset of backpack")
    active_slots = sum(catalog[skill_id].slot_cost for skill_id in active)
    if active_slots > 6:
        _fail("build.active", f"uses {active_slots} slots; capacity is 6")
    build = Build(backpack, active)

    if not isinstance(data["program"], list) or not data["program"]:
        _fail("program", "must be a non-empty instruction list")
    program: list[ProgramInstruction] = []
    last_advance = -1.0
    for index, item in enumerate(data["program"]):
        path = f"program[{index}]"
        if not isinstance(item, dict) or "op" not in item:
            _fail(path, "must be an instruction object with op")
        op = item["op"]
        if op == "cast":
            cast = _strict_object(item, path, frozenset({"op", "skill", "target"}))
            if cast["skill"] != "each_active" and cast["skill"] not in active:
                _fail(f"{path}.skill", "must be each_active or an active skill")
            if cast["target"] != "zone":
                _fail(f"{path}.target", "only public zone target is supported")
            program.append(Cast(cast["skill"], cast["target"]))
        elif op == "step":
            step = _strict_object(item, path, frozenset({"op", "repeats"}))
            repeats = step["repeats"]
            if isinstance(repeats, bool) or not isinstance(repeats, int) or not 1 <= repeats <= MAX_STEP_REPEATS:
                _fail(f"{path}.repeats", f"must be an integer in [1, {MAX_STEP_REPEATS}]")
            program.append(Step(repeats))
        elif op == "advance":
            advance = _strict_object(item, path, frozenset({"op", "to"}))
            to = _finite(advance["to"], f"{path}.to")
            if to <= last_advance:
                _fail(f"{path}.to", "advance times must be strictly increasing")
            last_advance = to
            program.append(Advance(to))
        else:
            _fail(f"{path}.op", "must be cast, step, or advance")

    horizons_raw = _strict_object(data["horizons"], "horizons", frozenset(HORIZON_KEYS))
    horizons = {key: _finite(horizons_raw[key], f"horizons.{key}") for key in HORIZON_KEYS}
    if not horizons["combat_end"] <= horizons["short"] <= horizons["medium"]:
        _fail("horizons", "must satisfy combat_end <= short <= medium")
    if last_advance > horizons["combat_end"]:
        _fail("program", "advance cannot exceed combat_end; later times are observation horizons")

    weights_raw = _strict_object(data["weights"], "weights", frozenset(WEIGHT_KEYS))
    weights = {key: _finite(weights_raw[key], f"weights.{key}", high=1.0) for key in WEIGHT_KEYS}
    if not math.isclose(sum(weights.values()), 1.0, abs_tol=1e-9):
        _fail("weights", "must sum to 1.0")
    return Scenario(scenario_id, split, category, environment, build, tuple(program), horizons, weights, target_count)


def load_scenario(path: str | Path) -> Scenario:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ScenarioError(f"{path}: cannot load scenario: {exc}") from exc
    return validate_scenario(raw)
