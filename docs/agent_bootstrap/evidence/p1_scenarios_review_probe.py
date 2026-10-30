"""Non-collected probes for the P1 scenario conformance review.

This script is deliberately outside the collected test module. It reuses the
test fixture helpers to measure two causal controls:

1. Scenario 8 without the paid +0.5 Field effect.
2. Scenario 10 without the paid shield effect.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.actions import (
    ActionRequest,
    submit_timed_primary_action,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.ecology import (
    ECOLOGY_CHANGED_EVENT,
    ECOLOGY_COMPONENT,
    parse_ecology_spec,
    sample_ecology,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.runtime import (
    advance_world_tick,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.tests import (
    test_p1_scenarios as fixture,
)


def scenario08_without_paid_effect():
    spec = parse_ecology_spec({
        "protocol": "pmw-gameplay-v0.4",
        "id": "p1_ecology",
        "label": "P1 threshold ecology",
        "initial_regime": "dry",
        "sample_count": 2,
        "regimes": [
            {
                "id": "dry",
                "label": "Dry",
                "clue": "dry baseline",
                "baselines": [{
                    "field_id": "humidity",
                    "target": 0.1,
                    "rate": 0.2,
                    "curve": "linear",
                }],
            },
            {
                "id": "wet",
                "label": "Wet",
                "clue": "wet baseline",
                "baselines": [{
                    "field_id": "humidity",
                    "target": 0.9,
                    "rate": 0.2,
                    "curve": "linear",
                }],
            },
        ],
        "transitions": [{
            "id": "rain",
            "from": "dry",
            "to": "wet",
            "condition": {
                "field_id": "humidity",
                "comparator": "gte",
                "threshold": 0.55,
            },
            "window_ticks": 1,
            "clue": "rain threshold reached",
        }],
    })
    plan = sample_ecology(spec, 17)
    # Same payload, but amount zero: this is the no-mechanism control while
    # retaining compilation, equip, payment, and Tick execution.
    skill = fixture._skill(fixture._skill_raw(
        "p1_rain_call_noop",
        [{
            "id": "soak",
            "kind": "modify_field",
            "target": {"kind": "current_area"},
            "commitment": "required",
            "field_id": "humidity",
            "amount": 0.0,
        }],
        duration=1,
        mana=3.0,
        budget=5.0,
    ))
    runtime, _ = fixture._formal_runtime(
        fixture._world([
            fixture._field("humidity", initial=0.2, target=0.1, rate=0.2)
        ]),
        (skill,),
        ecology_by_area={fixture.AREA: plan, fixture.OTHER_AREA: plan},
    )
    result = submit_timed_primary_action(
        runtime.session,
        runtime.action_registry,
        ActionRequest("p1_scenario08_noop", fixture.PLAYER, skill.id),
    )
    tick_trace = result.time.ticks[0].event_result.trace
    changed = [
        row.event for row in tick_trace.events
        if row.event.type == ECOLOGY_CHANGED_EVENT
    ]
    ecology = runtime.session.state.entities[
        fixture.AREA
    ].components[ECOLOGY_COMPONENT]["current"]
    return {
        "changed_event_count": len(changed),
        "ecology_after_tick": ecology,
        "field_value_after_tick": fixture._field_state(runtime)["value"],
        "spent_ticks": fixture._budget(runtime)["spent_ticks"],
    }


def scenario10_without_paid_effect():
    skill = fixture._skill(fixture._skill_raw(
        "p1_self_shield_noop",
        [{
            "id": "self_shield",
            "kind": "shield",
            "target": {"kind": "self"},
            "commitment": "required",
            "amount": 0,
        }],
        duration=1,
        mana=3.0,
        budget=4.0,
    ))
    runtime, _ = fixture._formal_runtime(
        fixture._world(
            [fixture._field("heat", rate=0.0, curve="none")],
            npc_area=fixture.OTHER_AREA,
        ),
        (skill,),
    )
    states = {}
    for actor_id in (fixture.PLAYER, fixture.NPC):
        submit_timed_primary_action(
            runtime.session,
            runtime.action_registry,
            ActionRequest(
                f"p1_scenario10_noop_{actor_id}", actor_id, skill.id
            ),
        )
        actor = fixture._actor_state(runtime, actor_id)
        states[actor_id] = {
            "mana": actor["mana"],
            "shield": actor["shield"],
        }
    return {
        "actors": states,
        "spent_ticks": fixture._budget(runtime)["spent_ticks"],
    }


def main():
    result = {
        "scenario08_without_paid_effect": scenario08_without_paid_effect(),
        "scenario10_without_paid_effect": scenario10_without_paid_effect(),
    }
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    sys.exit(main())
