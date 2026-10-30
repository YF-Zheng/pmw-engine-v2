"""Main (architecture) complementary probe for C5.2 Derived catalog.

Hand-computed expectations, formal chain only. Not independent QA.
Run from repo root with PYTHONPATH=src.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.actions import (  # noqa: E402
    ActionRequest, submit_timed_primary_action,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.contracts import (  # noqa: E402
    GameplayContractError,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.derived import (  # noqa: E402
    parse_derived_spec,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.runtime import (  # noqa: E402
    advance_world_tick,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.tests.test_p1_scenarios import (  # noqa: E402
    AREA, NPC, OTHER_AREA, PLAYER, _actor_state, _budget, _field, _skill, _skill_raw, _world,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.tests.test_sandbox_derived_catalog import (  # noqa: E402
    _formal_runtime, _derived_values,
)

SOURCES = [
    "experiments/generative_mechanics/next_tracks_v06/gameplay_v04/derived.py",
    "experiments/generative_mechanics/next_tracks_v06/gameplay_v04/content_compiler.py",
    "experiments/generative_mechanics/next_tracks_v06/gameplay_v04/conditions.py",
    "experiments/generative_mechanics/next_tracks_v06/gameplay_v04/actions.py",
]


def close(a, b):
    return abs(a - b) <= 1e-12


def main():
    checks = []

    def check(name, ok, **values):
        checks.append({"check": name, "ok": bool(ok), **values})

    # heat = clamp(-0.3 + 1.5*temperature + 0.5*wind, 0, 1); hot = temperature > 0.6
    heat = parse_derived_spec({"id": "heat", "kind": "weighted_sum",
                               "terms": [["temperature", 1.5], ["wind", 0.5]],
                               "bias": -0.3, "minimum": 0.0, "maximum": 1.0})
    hot = parse_derived_spec({"id": "hot", "kind": "threshold", "field_id": "temperature",
                              "comparator": "gt", "value": 0.6})
    warm = _skill(_skill_raw("probe_warm", [{
        "id": "warm", "kind": "modify_field", "target": {"kind": "current_area"},
        "commitment": "required", "field_id": "temperature", "amount": 0.25}],
        duration=1, mana=2.0, budget=3.0))
    blaze = _skill(_skill_raw("probe_blaze", [{
        "id": "blaze", "kind": "modify_field", "target": {"kind": "current_area"},
        "commitment": "required", "field_id": "wind", "amount": 0.1}],
        condition={"all": [
            {"derived": {"subject": "current_area", "key": "hot", "comparator": "eq", "value": 1.0}},
            {"derived": {"subject": "current_area", "key": "heat", "comparator": "gte", "value": 0.6}},
        ]},
        duration=1, mana=5.0, budget=6.0))
    world = _world([
        _field("temperature", initial=0.4, target=0.4, rate=0.0),
        _field("wind", initial=0.2, target=0.2, rate=0.0),
    ])
    runtime, _ = _formal_runtime(world, (warm, blaze),
                                 derived_by_area={AREA: (heat, hot), OTHER_AREA: (hot,)})
    v = _derived_values(runtime)
    # heat = -0.3 + 0.6 + 0.1 = 0.4 ; hot = 0
    check("initial_heat", close(v["heat"], 0.4), actual=v["heat"], expected=0.4)
    check("initial_hot", v["hot"] == 0.0, actual=v["hot"])

    for actor in (NPC, PLAYER):
        before = (runtime.session.state.to_dict(), _actor_state(runtime, actor)["mana"],
                  _budget(runtime)["spent_ticks"])
        try:
            submit_timed_primary_action(runtime.session, runtime.action_registry,
                                        ActionRequest(f"probe_blaze_false_{actor}", actor, blaze.id))
            rejected = False
        except GameplayContractError as exc:
            rejected = str(exc) == "action condition is not satisfied"
        after = (runtime.session.state.to_dict(), _actor_state(runtime, actor)["mana"],
                 _budget(runtime)["spent_ticks"])
        check(f"blaze_rejected_atomic_{actor}", rejected and after == before)

    # NPC warms: temperature 0.4 -> 0.65 (rate 0 keeps it); heat = -0.3+0.975+0.1 = 0.775; hot = 1
    submit_timed_primary_action(runtime.session, runtime.action_registry,
                                ActionRequest("probe_warm_npc", NPC, warm.id))
    v = _derived_values(runtime)
    check("after_warm_heat", close(v["heat"], 0.775), actual=v["heat"], expected=0.775)
    check("after_warm_hot", v["hot"] == 1.0, actual=v["hot"])
    check("other_area_independent", _derived_values(runtime, OTHER_AREA)["hot"] == 0.0)

    for actor in (PLAYER, NPC):
        mana0 = _actor_state(runtime, actor)["mana"]
        spent0 = _budget(runtime)["spent_ticks"]
        submit_timed_primary_action(runtime.session, runtime.action_registry,
                                    ActionRequest(f"probe_blaze_true_{actor}", actor, blaze.id))
        check(f"blaze_paid_{actor}",
              _actor_state(runtime, actor)["mana"] == mana0 - 5.0
              and _budget(runtime)["spent_ticks"] == spent0 + 1)
    # wind 0.2 -> 0.3 -> 0.4 ; heat = -0.3 + 0.975 + 0.2 = 0.875
    v = _derived_values(runtime)
    check("after_two_blaze_heat", close(v["heat"], 0.875), actual=v["heat"], expected=0.875)
    # warm twice more: temperature 0.65 -> 0.9 -> 1.0 (domain clamp); raw heat >= 1.15 -> clamp 1.0
    for i in range(2):
        submit_timed_primary_action(runtime.session, runtime.action_registry,
                                    ActionRequest(f"probe_warm_more_{i}", PLAYER, warm.id))
    v = _derived_values(runtime)
    check("heat_clamped_max", v["heat"] == 1.0, actual=v["heat"])
    for _ in range(3):
        advance_world_tick(runtime.session)
    check("stable_under_ticks", _derived_values(runtime)["heat"] == 1.0)

    hashes = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in SOURCES}
    result = {"probe": "c5_derived_main_probe", "author": "Main (not independent QA)",
              "all_ok": all(c["ok"] for c in checks), "checks": checks, "source_sha256": hashes}
    out = ROOT / "docs/agent_bootstrap/evidence/c5_derived_main_probe.json"
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"all_ok": result["all_ok"], "n": len(checks),
                      "failed": [c for c in checks if not c["ok"]]}, indent=1))


if __name__ == "__main__":
    main()