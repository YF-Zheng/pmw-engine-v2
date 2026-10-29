from __future__ import annotations

import tempfile
from pathlib import Path
import unittest

from pmw import Event

from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.blueprints import (
    instantiate_area,
    parse_area_blueprint,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.contracts import (
    DynamicsSource,
    FieldDefinition,
    FieldProfile,
    GameplayContractError,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.dynamics import (
    build_dynamics_laws,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.runtime import (
    advance_world_tick,
    apply_source,
    build_runtime,
    clock_entity,
    load_checkpoint,
    save_checkpoint,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.worlds import (
    build_gameplay_world,
)


AREA_ID = "eco_area"
FIELD_ID = "temperature"
ECOLOGY_ENTER_EVENT = "pmw.test.ecology.enter"


def _area(curve: str = "linear", rate: float = 0.2):
    return instantiate_area(
        parse_area_blueprint({
            "protocol": "pmw-gameplay-v0.4",
            "kind": "area_blueprint",
            "id": AREA_ID,
            "fields": [{
                "id": FIELD_ID,
                "domain": {"min": 0.0, "max": 1.0},
                "initial": 0.8,
                "target": 0.2,
                "rate": rate,
                "curve": curve,
                "max_persistent_patches": 2,
                "max_temporary_modifiers": 2,
            }],
        }),
        AREA_ID,
    )


def _session(curve: str = "linear", rate: float = 0.2):
    return build_runtime(build_gameplay_world(
        "ecology_curve_world",
        areas=[_area(curve, rate), clock_entity()],
    ), extra_laws=(_ecology_law(),))


def _field(session):
    return session.state.entities[AREA_ID].components[
        "pmw_gameplay_dynamics"
    ]["fields"][FIELD_ID]


def _ecology_law():
    baseline = "$area.pmw_gameplay_dynamics.fields.temperature.baseline"
    return {
        "id": "pmw.test.ecology.enter",
        "mode": "event",
        "priority": 100,
        "bindings": {
            "area": {
                "kind": "entity",
                "requires": [
                    "pmw_gameplay_area",
                    "pmw_gameplay_dynamics",
                ],
            },
        },
        "when": {"all": [
            {"event.type": {"eq": ECOLOGY_ENTER_EVENT}},
            {"ref": "$area.id", "eq": AREA_ID},
        ]},
        "effects": [
            {"op": "set", "target": f"{baseline}.curve", "value": "$event.payload.curve"},
            {"op": "set", "target": f"{baseline}.target", "value": "$event.payload.target"},
            {"op": "set", "target": f"{baseline}.rate", "value": "$event.payload.rate"},
        ],
    }


def _two_area_ecology_law():
    baseline = "$area.pmw_gameplay_dynamics.fields.temperature.baseline"
    return {
        "id": "pmw.test.ecology.enter.area",
        "mode": "event",
        "priority": 100,
        "bindings": {
            "area": {
                "kind": "entity",
                "requires": [
                    "pmw_gameplay_area",
                    "pmw_gameplay_dynamics",
                ],
            },
        },
        "when": {"all": [
            {"event.type": {"eq": ECOLOGY_ENTER_EVENT}},
            {"ref": "$area.id", "eq": "$event.target"},
        ]},
        "effects": [
            {"op": "set", "target": f"{baseline}.curve", "value": "$event.payload.curve"},
            {"op": "set", "target": f"{baseline}.target", "value": "$event.payload.target"},
            {"op": "set", "target": f"{baseline}.rate", "value": "$event.payload.rate"},
        ],
    }


def _publish_baseline(session, *, curve, target=0.2, rate=0.2):
    result = session.runtime.run_event(Event(
        id=f"ecology:{session.state.tick}:{curve}",
        type=ECOLOGY_ENTER_EVENT,
        time=session.state.sim_time,
        source="ecology",
        target=AREA_ID,
        payload={"curve": curve, "target": target, "rate": rate},
    ))
    if not result.changed:
        raise AssertionError("ecology baseline event did not match")


class LiveBaselineCurveTests(unittest.TestCase):
    def test_all_base_curve_transitions_use_next_tick_formula(self):
        cases = (
            ("linear", 0.2, "distance_squared", 0.5),
            ("linear", 0.2, "none", 0.0),
            ("distance_squared", 0.5, "linear", 0.2),
            ("distance_squared", 0.5, "none", 0.0),
            ("none", 0.0, "linear", 0.2),
            ("none", 0.0, "distance_squared", 0.5),
        )
        for old_curve, old_rate, new_curve, new_rate in cases:
            with self.subTest(old=old_curve, new=new_curve):
                session = _session(old_curve, old_rate)
                advance_world_tick(session)
                self.assertEqual(_field(session)["diagnostics"]["effective_curve"], old_curve)
                _publish_baseline(session, curve=new_curve, rate=new_rate)
                advance_world_tick(session)
                self.assertEqual(_field(session)["diagnostics"]["effective_curve"], new_curve)
                before = _field(session)["value"]
                advance_world_tick(session)
                difference = 0.2 - before
                expected = (
                    before
                    if new_curve == "none"
                    else before + new_rate * difference
                    if new_curve == "linear"
                    else before + new_rate * difference * abs(difference)
                )
                self.assertAlmostEqual(_field(session)["value"], expected)

    def test_published_transition_keeps_old_formula_then_uses_new_formula(self):
        session = _session("linear", 0.2)
        advance_world_tick(session)
        self.assertAlmostEqual(_field(session)["value"], 0.68)
        self.assertEqual(_field(session)["diagnostics"]["effective_curve"], "linear")
        _publish_baseline(session, curve="none", rate=0.0)
        advance_world_tick(session)
        self.assertEqual(_field(session)["diagnostics"]["effective_curve"], "none")

    def test_live_target_and_rate_changes_are_used_without_rebuild(self):
        session = _session("linear", 0.2)
        advance_world_tick(session)
        _publish_baseline(session, curve="linear", target=0.6, rate=0.5)
        advance_world_tick(session)
        self.assertAlmostEqual(_field(session)["diagnostics"]["effective_target"], 0.6)
        self.assertAlmostEqual(_field(session)["diagnostics"]["effective_rate"], 0.5)
        self.assertAlmostEqual(_field(session)["diagnostics"]["unclamped"], 0.64)

    def test_override_priority_and_expiry_survive_baseline_curve_changes(self):
        session = _session("linear", 0.2)
        advance_world_tick(session)
        _publish_baseline(session, curve="none", rate=0.0)
        apply_source(
            session,
            entity_id=AREA_ID,
            field_id=FIELD_ID,
            layer="temporary",
            source=DynamicsSource(
                "recover", "status", rate_add=0.2, curve="linear",
                curve_priority=2, duration_ticks=3,
            ),
        )
        advance_world_tick(session)
        self.assertEqual(_field(session)["diagnostics"]["effective_curve"], "linear")
        self.assertAlmostEqual(_field(session)["value"], 0.584)
        advance_world_tick(session)
        self.assertEqual(_field(session)["diagnostics"]["effective_curve"], "linear")
        self.assertAlmostEqual(_field(session)["value"], 0.5072)
        advance_world_tick(session)
        self.assertEqual(_field(session)["diagnostics"]["effective_curve"], "none")
        frozen = _field(session)["value"]
        advance_world_tick(session)
        self.assertAlmostEqual(_field(session)["value"], frozen)

    def test_curve_override_wins_and_expiry_restores_live_baseline(self):
        session = _session("linear", 0.2)
        apply_source(
            session,
            entity_id=AREA_ID,
            field_id=FIELD_ID,
            layer="temporary",
            source=DynamicsSource(
                "freeze", "status", curve="none",
                curve_priority=1, duration_ticks=2,
            ),
        )
        advance_world_tick(session)
        self.assertAlmostEqual(_field(session)["value"], 0.8)
        self.assertEqual(_field(session)["diagnostics"]["effective_curve"], "none")
        _publish_baseline(session, curve="distance_squared", rate=0.5)
        advance_world_tick(session)
        self.assertEqual(_field(session)["diagnostics"]["effective_curve"], "distance_squared")
        advance_world_tick(session)
        self.assertEqual(_field(session)["diagnostics"]["effective_curve"], "distance_squared")

    def test_two_areas_with_different_live_baselines_do_not_cross_contaminate(self):
        left = instantiate_area(parse_area_blueprint({
            "protocol": "pmw-gameplay-v0.4",
            "kind": "area_blueprint",
            "id": "left",
            "fields": [{
                "id": FIELD_ID,
                "domain": {"min": 0.0, "max": 1.0},
                "initial": 0.8, "target": 0.2,
                "rate": 0.2, "curve": "linear",
                "max_persistent_patches": 1,
                "max_temporary_modifiers": 1,
            }],
        }), "left")
        right = instantiate_area(parse_area_blueprint({
            "protocol": "pmw-gameplay-v0.4",
            "kind": "area_blueprint",
            "id": "right",
            "fields": [{
                "id": FIELD_ID,
                "domain": {"min": 0.0, "max": 1.0},
                "initial": 0.8, "target": 0.2,
                "rate": 0.2, "curve": "linear",
                "max_persistent_patches": 1,
                "max_temporary_modifiers": 1,
            }],
        }), "right")
        session = build_runtime(build_gameplay_world(
            "two_areas", areas=[left, right, clock_entity()],
        ), extra_laws=(_two_area_ecology_law(),))
        published = session.runtime.run_event(Event(
            id="ecology:right:entry",
            type=ECOLOGY_ENTER_EVENT,
            time=session.state.sim_time,
            source="ecology",
            target="right",
            payload={"curve": "none", "target": 0.2, "rate": 0.0},
        ))
        self.assertTrue(published.changed)
        advance_world_tick(session)
        original = session.state.entities["left"].components[
            "pmw_gameplay_dynamics"
        ]["fields"][FIELD_ID]["value"]
        self.assertAlmostEqual(
            session.state.entities["right"].components[
                "pmw_gameplay_dynamics"
            ]["fields"][FIELD_ID]["value"],
            0.8,
        )
        advance_world_tick(session)
        self.assertAlmostEqual(
            session.state.entities["left"].components[
                "pmw_gameplay_dynamics"
            ]["fields"][FIELD_ID]["value"],
            original + 0.2 * (0.2 - original),
        )
        self.assertAlmostEqual(
            session.state.entities["right"].components[
                "pmw_gameplay_dynamics"
            ]["fields"][FIELD_ID]["value"],
            0.8,
        )

    def test_rebuild_from_live_baseline_continues_same_behavior(self):
        session = _session("linear", 0.2)
        advance_world_tick(session)
        _publish_baseline(session, curve="none", rate=0.0)
        advance_world_tick(session)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ecology_curve.json"
            save_checkpoint(path, session)
            rebuilt = load_checkpoint(path)
            for _ in range(3):
                advance_world_tick(session)
                advance_world_tick(rebuilt)
            self.assertEqual(rebuilt.state.to_dict(), session.state.to_dict())
            self.assertEqual(_field(session)["diagnostics"]["effective_curve"], "none")
            self.assertEqual(_field(rebuilt)["diagnostics"]["effective_curve"], "none")

    def test_rebuild_law_ids_are_independent_of_initial_curve(self):
        left = build_dynamics_laws((_session("linear").profiles[0],))
        right = build_dynamics_laws((_session("none", 0.0).profiles[0],))
        self.assertEqual(
            {law["id"] for law in left},
            {law["id"] for law in right},
        )

    def test_trusted_lowering_rejects_invalid_initial_curve_rate(self):
        bad = FieldDefinition(
            FIELD_ID, 0.0, 1.0, 0.8, 0.2, 0.2, "none", 1, 1,
        )
        with self.assertRaisesRegex(GameplayContractError, "none requires"):
            build_dynamics_laws((FieldProfile(AREA_ID, bad),))


if __name__ == "__main__":
    unittest.main()
