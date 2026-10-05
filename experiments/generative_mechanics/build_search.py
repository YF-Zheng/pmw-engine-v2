"""Deterministic exhaustive build search for the bounded 10/6 lab space."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Callable, Iterable

from .spec import SkillSpec

MAX_BACKPACK = 10
MAX_AUGMENTED_BACKPACK = 11
MAX_ACTIVE = 6
MAX_SLOT_COST = 6


class BuildSearchError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class BuildScore:
    skills: tuple[str, ...]
    value: float


@dataclass(frozen=True, slots=True)
class SearchResult:
    best: BuildScore
    evaluations: int
    legal_builds: int


@dataclass(frozen=True, slots=True)
class PersonalizedDelta:
    before: BuildScore
    after: BuildScore
    delta: float


def _catalog(
    skills: Iterable[SkillSpec], *, max_backpack: int = MAX_BACKPACK,
) -> dict[str, SkillSpec]:
    result: dict[str, SkillSpec] = {}
    for spec in skills:
        if spec.id in result:
            raise BuildSearchError(f"duplicate backpack skill {spec.id!r}")
        result[spec.id] = spec
    if len(result) > max_backpack:
        raise BuildSearchError(f"backpack exceeds {max_backpack} skills")
    return result


def legal_builds(
    skills: Iterable[SkillSpec], *, max_backpack: int = MAX_BACKPACK,
) -> tuple[tuple[str, ...], ...]:
    catalog = _catalog(skills, max_backpack=max_backpack)
    ids = tuple(sorted(catalog))
    builds: list[tuple[str, ...]] = [()]
    for size in range(1, min(MAX_ACTIVE, len(ids)) + 1):
        for selected in combinations(ids, size):
            if sum(catalog[skill_id].slot_cost for skill_id in selected) <= MAX_SLOT_COST:
                builds.append(selected)
    return tuple(builds)


def search_best(
    skills: Iterable[SkillSpec], value_fn: Callable[[tuple[str, ...]], float],
    *, max_backpack: int = MAX_BACKPACK,
) -> SearchResult:
    builds = legal_builds(skills, max_backpack=max_backpack)
    scored = [BuildScore(build, float(value_fn(build))) for build in builds]
    best = min(scored, key=lambda item: (-item.value, item.skills))
    return SearchResult(best=best, evaluations=len(scored), legal_builds=len(builds))


def pairwise_synergy(skills: Iterable[SkillSpec], value_fn: Callable[[tuple[str, ...]], float]) -> dict[str, float]:
    catalog = _catalog(skills)
    empty = float(value_fn(()))
    singles = {skill_id: float(value_fn((skill_id,))) for skill_id in sorted(catalog)}
    return {
        f"{left}+{right}": float(value_fn((left, right))) - singles[left] - singles[right] + empty
        for left, right in combinations(sorted(catalog), 2)
        if catalog[left].slot_cost + catalog[right].slot_cost <= MAX_SLOT_COST
    }


def personalized_delta(
    existing: Iterable[SkillSpec], candidate: SkillSpec,
    value_fn: Callable[[tuple[str, ...]], float],
) -> PersonalizedDelta:
    before_specs = tuple(existing)
    if candidate.id in {item.id for item in before_specs}:
        raise BuildSearchError("candidate already exists in backpack")
    before = search_best(before_specs, value_fn).best
    after = search_best(
        (*before_specs, candidate), value_fn,
        max_backpack=MAX_AUGMENTED_BACKPACK,
    ).best
    return PersonalizedDelta(before, after, after.value - before.value)
