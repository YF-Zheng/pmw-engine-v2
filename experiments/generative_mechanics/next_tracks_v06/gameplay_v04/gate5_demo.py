"""Deterministic integrated demonstration for the completed gameplay foundation."""

from __future__ import annotations

import json

from .ai_demo import run_ai_demo
from .content_compiler import build_content_session, compile_content
from .gate3_demo import build_gate3_demo, run_gate3_demo
from .harvest import HarvestRequest, resolve_harvest
from .time_ledger import TIME_BUDGET_COMPONENT, initialize_time_budget, spend_world_time


def run_gate5_demo() -> dict:
    initial, content, _, harvest = build_gate3_demo()
    world = initialize_time_budget(initial.state, 4)
    session = build_content_session(world, compile_content(content))
    gathered = resolve_harvest(
        session, content.action_registry, harvest,
        HarvestRequest("gate5_demo_harvest", "hero_actor", harvest.id, True),
        permissions=("lucky_harvest",),
    )
    harvest_time = spend_world_time(session, gathered.duration, reason="harvest")
    offline_time = spend_world_time(session, 2, reason="offline")
    budget = session.state.entities["pmw:v04:clock"].components[TIME_BUDGET_COMPONENT]
    return {
        "protocol": "pmw-gameplay-demo-v0.4",
        "content": run_gate3_demo(),
        "ai": run_ai_demo(),
        "time": {
            "harvest_duration": harvest_time.duration,
            "offline_duration": offline_time.duration,
            "world_ticks": len(harvest_time.ticks) + len(offline_time.ticks),
            "spent": budget["spent_ticks"],
            "remaining": budget["remaining_ticks"],
        },
    }


if __name__ == "__main__":
    print(json.dumps(run_gate5_demo(), ensure_ascii=True, sort_keys=True, separators=(",", ":")))
