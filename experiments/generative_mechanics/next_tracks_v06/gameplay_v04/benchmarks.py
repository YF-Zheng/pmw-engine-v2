"""Reproducible Gate 1 locality benchmark and demonstration."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import time

from pmw import Entity, Event
from pmw.matching import MatchStats, match_law

from .blueprints import (
    instantiate_actor, instantiate_area, parse_actor_blueprint,
    parse_area_blueprint,
)
from .contracts import DynamicsSource
from .dynamics import WORLD_TICK_EVENT
from .runtime import advance_world_tick, apply_source, build_runtime, clock_entity
from .worlds import build_gameplay_world


def _area_raw(slot_count: int = 8) -> dict:
    return {
        "protocol": "pmw-gameplay-v0.4", "kind": "area_blueprint",
        "id": "benchmark_area", "fields": [{
            "id": "mana_density", "domain": {"min": 0.0, "max": 1.0},
            "initial": 0.8, "target": 0.2, "rate": 0.2, "curve": "linear",
            "max_persistent_patches": slot_count,
            "max_temporary_modifiers": slot_count,
        }],
    }


def locality_row(unrelated: int, *, active_sources: int = 0) -> dict:
    area = instantiate_area(parse_area_blueprint(_area_raw()), "benchmark_area_one")
    entities = {area.id: area, "pmw:v04:clock": clock_entity()}
    for index in range(unrelated):
        entities[f"irrelevant_{index:06d}"] = Entity(
            f"irrelevant_{index:06d}", "irrelevant",
            components={"pmw_gameplay_skill_definition": {"index": index}},
        )
    world = build_gameplay_world("gate1_locality", areas=entities.values())
    started = time.perf_counter(); session = build_runtime(world); cold = time.perf_counter() - started
    for index in range(active_sources):
        layer = "persistent" if index < 8 else "temporary"
        source = DynamicsSource(
            f"source_{index:02d}", f"owner_{index:02d}", rate_add=0.001,
            duration_ticks=10 if layer == "temporary" else None,
        )
        apply_source(session, entity_id=area.id, field_id="mana_density", layer=layer, source=source)
    event = Event(
        id="pmw:v04:benchmark:tick", type=WORLD_TICK_EVENT, time=1.0,
        source="pmw:v04:clock", payload={"step": 1},
    )
    counters = MatchStats()
    for law in session.runtime.engine.event_laws:
        local = MatchStats()
        match_law(law, session.state, event, plan=session.runtime.engine.match_plans[law.law_id], stats=local)
        for name in (
            "candidate_rows_examined", "partial_bindings_created", "complete_bindings",
            "matches_returned", "index_builds", "early_predicate_evaluations",
            "early_predicate_prunes", "exact_constraint_lookups",
        ):
            setattr(counters, name, getattr(counters, name) + getattr(local, name))
    started = time.perf_counter(); advance_world_tick(session); warm = time.perf_counter() - started
    return {
        "unrelated_entities": unrelated, "active_sources": active_sources,
        "candidate_rows": counters.candidate_rows_examined,
        "partial_bindings": counters.partial_bindings_created,
        "complete_bindings": counters.complete_bindings,
        "matches": counters.matches_returned,
        "index_builds": counters.index_builds,
        "exact_constraint_lookups": counters.exact_constraint_lookups,
        "state_full_scans": session.stats.state_full_scans,
        "cold_seconds": cold, "warm_tick_seconds": warm,
    }


def run_locality(sizes=(1_000, 10_000, 100_000)) -> list[dict]:
    return [locality_row(size) for size in sizes]


def _actor_raw(slot_count: int = 2) -> dict:
    return {
        "protocol": "pmw-gameplay-v0.4", "kind": "actor_blueprint",
        "id": "benchmark_actor", "hp": {"max": 100, "initial": 100},
        "mana": {"max": 100, "initial": 30, "dynamics": {
            "target": 60, "rate": 0.1, "curve": "linear",
            "max_persistent_patches": slot_count,
            "max_temporary_modifiers": slot_count,
        }},
        "attributes": {"power": 5, "control": 5, "resilience": 5, "agility": 5},
        "traits": [],
    }


def active_world_row(active_areas: int, active_actors: int, *, modifiers_per_field: int = 2) -> dict:
    """Measure scaling with real active Field instances, not unrelated rows."""
    if active_areas < 1 or active_actors < 0 or modifiers_per_field not in {0, 1, 2}:
        raise ValueError("invalid active-world benchmark dimensions")
    area_blueprint = parse_area_blueprint(_area_raw(slot_count=2))
    actor_blueprint = parse_actor_blueprint(_actor_raw(slot_count=2))
    areas = [clock_entity(), *[
        instantiate_area(area_blueprint, f"active_area_{index:04d}")
        for index in range(active_areas)
    ]]
    actors = [
        instantiate_actor(actor_blueprint, f"active_actor_{index:04d}", controller="ai")
        for index in range(active_actors)
    ]
    placements = [
        (actor.id, f"active_area_{index % active_areas:04d}")
        for index, actor in enumerate(actors)
    ]
    world = build_gameplay_world(
        "gate1_active_scale", areas=areas, actors=actors, placements=placements,
    )
    started = time.perf_counter(); session = build_runtime(world); cold = time.perf_counter() - started
    for profile in session.profiles:
        for index in range(modifiers_per_field):
            apply_source(
                session,
                entity_id=profile.entity_id,
                field_id=profile.field.id,
                layer="persistent",
                source=DynamicsSource(
                    f"scale_patch_{index}", f"benchmark_owner_{index}",
                    rate_add=0.005,
                ),
            )
    started = time.perf_counter(); result = advance_world_tick(session); warm = time.perf_counter() - started
    return {
        "active_areas": active_areas,
        "active_actors": active_actors,
        "active_fields": len(session.profiles),
        "active_modifiers": len(session.profiles) * modifiers_per_field,
        "triggered_laws": len(result.event_result.triggered_law_ids),
        "state_full_scans": session.stats.state_full_scans,
        "cold_seconds": cold,
        "warm_tick_seconds": warm,
    }


def run_active_scale(sizes=((4, 4), (16, 16), (32, 32))) -> list[dict]:
    return [active_world_row(areas, actors) for areas, actors in sizes]


def run_gate1_demo() -> dict:
    blueprint = parse_area_blueprint(_area_raw(slot_count=4))
    west = instantiate_area(blueprint, "demo_west")
    east = instantiate_area(blueprint, "demo_east")
    world = build_gameplay_world(
        "gate1_demo", areas=[clock_entity(), west, east],
        adjacencies=[("demo_west", "demo_east")],
    )
    session = build_runtime(world)
    apply_source(
        session, entity_id="demo_west", field_id="mana_density", layer="persistent",
        source=DynamicsSource(
            "cold_regime", "demo_ecology", target=0.0, target_weight=3.0,
            curve="distance_squared", curve_priority=10,
        ),
    )
    trajectory = []
    for step in range(5):
        trajectory.append({
            "step": step,
            "west": session.state.entities["demo_west"].components["pmw_gameplay_dynamics"]["fields"]["mana_density"]["value"],
            "east": session.state.entities["demo_east"].components["pmw_gameplay_dynamics"]["fields"]["mana_density"]["value"],
        })
        if step < 4:
            advance_world_tick(session)
    return {
        "demo_id": "gate1_two_area_dynamics",
        "trajectory": trajectory,
        "final_world": session.state.to_dict(),
        "claim": "adjacency alone does not diffuse Fields",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--skip-locality", action="store_true")
    args = parser.parse_args()
    result = {
        "demo": run_gate1_demo(),
        "locality": [] if args.skip_locality else run_locality(),
        "active_source_scale": locality_row(1_000, active_sources=16) if not args.skip_locality else {},
        "active_world_scale": run_active_scale() if not args.skip_locality else [],
    }
    text = json.dumps(result, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
