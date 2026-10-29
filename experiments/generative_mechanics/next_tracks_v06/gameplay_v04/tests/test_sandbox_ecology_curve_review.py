from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.basics import (
    basic_registry,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.blueprints import (
    instantiate_area,
    parse_area_blueprint,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.content_compiler import (
    build_content_session,
    compile_content,
    initialize_content_world,
    make_content,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.contracts import (
    DynamicsSource,
    GameplayContractError,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.dynamics import (
    build_dynamics_laws,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.ecology import (
    parse_ecology_spec,
    sample_ecology,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.registry import (
    MechanismRegistryRuntime,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.runtime import (
    advance_world_tick,
    apply_source,
    build_runtime,
    clock_entity,
    discover_profiles,
    load_checkpoint,
    save_checkpoint,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.transactions import (
    stage_gameplay_session,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.worlds import (
    build_gameplay_world,
)


FIELD = "temperature"


def _field(
    *,
    initial: float = 0.5,
    target: float,
    rate: float,
    curve: str,
) -> dict:
    return {
        "id": FIELD,
        "domain": {"min": 0.0, "max": 1.0},
        "initial": initial,
        "target": target,
        "rate": rate,
        "curve": curve,
        "max_persistent_patches": 4,
        "max_temporary_modifiers": 4,
    }


def _area(area_id: str, field: dict) -> object:
    return instantiate_area(
        parse_area_blueprint({
            "protocol": "pmw-gameplay-v0.4",
            "kind": "area_blueprint",
            "id": f"{area_id}_blueprint",
            "fields": [field],
        }),
        area_id,
    )


def _ecology(
    ecology_id: str,
    *,
    initial: dict,
    target: dict,
    comparator: str,
    threshold: float,
) -> object:
    raw = {
        "protocol": "pmw-gameplay-v0.4",
        "id": ecology_id,
        "label": ecology_id,
        "initial_regime": "alpha",
        "sample_count": 2,
        "regimes": [
            {
                "id": "alpha",
                "label": "Alpha",
                "clue": "initial",
                "baselines": [{"field_id": FIELD, **initial}],
            },
            {
                "id": "beta",
                "label": "Beta",
                "clue": "changed",
                "baselines": [{"field_id": FIELD, **target}],
            },
        ],
        "transitions": [{
            "id": "advance",
            "from": "alpha",
            "to": "beta",
            "condition": {
                "field_id": FIELD,
                "comparator": comparator,
                "threshold": threshold,
            },
            "window_ticks": 1,
            "clue": "advance",
        }],
    }
    return sample_ecology(parse_ecology_spec(raw), 17)


def _content(areas: dict[str, tuple[dict, object]]):
    entities = [
        _area(area_id, field)
        for area_id, (field, _) in sorted(areas.items())
    ]
    world = build_gameplay_world(
        "ecology_curve_review",
        areas=[*entities, clock_entity()],
    )
    content = make_content(
        basic_registry(),
        ecology_by_area={
            area_id: plan for area_id, (_, plan) in areas.items()
        },
    )
    initialized = initialize_content_world(world, content)
    return build_content_session(initialized, compile_content(content))


def _field_state(session, area_id: str) -> dict:
    return session.state.entities[area_id].components[
        "pmw_gameplay_dynamics"
    ]["fields"][FIELD]


def _regime(session, area_id: str) -> str:
    return session.state.entities[area_id].components[
        "pmw_gameplay_ecology"
    ]["current"]


class EcologyTransitionReadStateReview(unittest.TestCase):
    def test_two_areas_commit_on_pre_dynamics_values_then_use_live_curves(self):
        session = _content({
            "curve_linear_area": (
                _field(target=1.0, rate=0.5, curve="linear"),
                _ecology(
                    "linear_ecology",
                    initial={"target": 1.0, "rate": 0.5, "curve": "linear"},
                    target={"target": 0.0, "rate": 1.0, "curve": "distance_squared"},
                    comparator="lte",
                    threshold=0.5,
                ),
            ),
            "curve_squared_area": (
                _field(target=0.0, rate=1.0, curve="distance_squared"),
                _ecology(
                    "squared_ecology",
                    initial={"target": 0.0, "rate": 1.0, "curve": "distance_squared"},
                    target={"target": 1.0, "rate": 0.5, "curve": "linear"},
                    comparator="gte",
                    threshold=0.5,
                ),
            ),
        })

        advance_world_tick(session)
        linear = _field_state(session, "curve_linear_area")
        squared = _field_state(session, "curve_squared_area")

        # Both thresholds are true for the root read-state value 0.5 but false
        # for the values those dynamics formulas publish in the same tick.
        self.assertEqual(_regime(session, "curve_linear_area"), "beta")
        self.assertEqual(_regime(session, "curve_squared_area"), "beta")
        self.assertEqual(linear["baseline"]["curve"], "distance_squared")
        self.assertEqual(squared["baseline"]["curve"], "linear")
        self.assertEqual(linear["diagnostics"]["effective_curve"], "linear")
        self.assertEqual(squared["diagnostics"]["effective_curve"], "distance_squared")
        self.assertAlmostEqual(linear["value"], 0.75, delta=1e-12)
        self.assertAlmostEqual(squared["value"], 0.25, delta=1e-12)

        advance_world_tick(session)
        linear = _field_state(session, "curve_linear_area")
        squared = _field_state(session, "curve_squared_area")
        self.assertEqual(linear["diagnostics"]["effective_curve"], "distance_squared")
        self.assertEqual(squared["diagnostics"]["effective_curve"], "linear")
        self.assertAlmostEqual(linear["value"], 0.1875, delta=1e-12)
        self.assertAlmostEqual(squared["value"], 0.625, delta=1e-12)

    def test_live_target_and_rate_combine_with_source_contributions(self):
        session = _content({
            "source_area": (
                _field(target=1.0, rate=0.5, curve="linear"),
                _ecology(
                    "source_ecology",
                    initial={"target": 1.0, "rate": 0.5, "curve": "linear"},
                    target={"target": 0.2, "rate": 0.4, "curve": "distance_squared"},
                    comparator="lte",
                    threshold=0.5,
                ),
            ),
        })
        advance_world_tick(session)
        apply_source(
            session,
            entity_id="source_area",
            field_id=FIELD,
            layer="persistent",
            source=DynamicsSource(
                "review_target",
                "review_oracle",
                target=0.8,
                target_weight=3.0,
            ),
        )
        apply_source(
            session,
            entity_id="source_area",
            field_id=FIELD,
            layer="persistent",
            source=DynamicsSource(
                "review_rate",
                "review_oracle",
                rate_add=0.3,
                rate_multiplier=0.5,
            ),
        )

        advance_world_tick(session)
        field = _field_state(session, "source_area")
        expected_target = (0.2 + 3.0 * 0.8) / 4.0
        expected_rate = (0.4 + 0.3) * 0.5
        expected_value = 0.75 + expected_rate * (
            expected_target - 0.75
        ) * abs(expected_target - 0.75)
        self.assertEqual(field["diagnostics"]["effective_curve"], "distance_squared")
        self.assertAlmostEqual(field["diagnostics"]["effective_target"], expected_target, delta=1e-12)
        self.assertAlmostEqual(field["diagnostics"]["effective_rate"], expected_rate, delta=1e-12)
        self.assertAlmostEqual(field["value"], expected_value, delta=1e-12)

    def test_override_expiry_precedes_dynamics_and_then_uses_live_baseline(self):
        session = _content({
            "expiry_area": (
                _field(target=1.0, rate=0.5, curve="linear"),
                _ecology(
                    "expiry_ecology",
                    initial={"target": 1.0, "rate": 0.5, "curve": "linear"},
                    target={"target": 0.0, "rate": 1.0, "curve": "linear"},
                    comparator="lte",
                    threshold=0.5,
                ),
            ),
        })
        apply_source(
            session,
            entity_id="expiry_area",
            field_id=FIELD,
            layer="temporary",
            source=DynamicsSource(
                "review_freeze",
                "review_oracle",
                curve="none",
                curve_priority=7,
                duration_ticks=2,
            ),
        )

        advance_world_tick(session)
        frozen = _field_state(session, "expiry_area")
        self.assertEqual(_regime(session, "expiry_area"), "beta")
        self.assertEqual(frozen["baseline"]["curve"], "linear")
        self.assertEqual(frozen["diagnostics"]["effective_curve"], "none")
        self.assertEqual(frozen["diagnostics"]["effective_rate"], 0.0)
        self.assertAlmostEqual(frozen["value"], 0.5, delta=1e-12)

        advance_world_tick(session)
        thawed = _field_state(session, "expiry_area")
        self.assertEqual(thawed["diagnostics"]["effective_curve"], "linear")
        self.assertEqual(thawed["diagnostics"]["effective_target"], 0.0)
        self.assertAlmostEqual(thawed["diagnostics"]["effective_rate"], 1.0, delta=1e-12)
        self.assertAlmostEqual(thawed["value"], 0.0, delta=1e-12)
        self.assertEqual(session.state.scheduled_events, [])

    def test_curve_transition_and_override_expiry_oracle(self):
        session = _content({
            "curve_expiry_area": (
                _field(target=1.0, rate=0.5, curve="linear"),
                _ecology(
                    "curve_expiry_ecology",
                    initial={"target": 1.0, "rate": 0.5, "curve": "linear"},
                    target={"target": 0.0, "rate": 1.0, "curve": "distance_squared"},
                    comparator="lte",
                    threshold=0.5,
                ),
            ),
        })
        apply_source(
            session,
            entity_id="curve_expiry_area",
            field_id=FIELD,
            layer="temporary",
            source=DynamicsSource(
                "review_curved_freeze",
                "review_oracle",
                curve="none",
                curve_priority=7,
                duration_ticks=2,
            ),
        )

        advance_world_tick(session)
        first = _field_state(session, "curve_expiry_area")
        self.assertEqual(_regime(session, "curve_expiry_area"), "beta")
        self.assertEqual(first["baseline"]["curve"], "distance_squared")
        # T1 root read-state: old linear formula with no override is skipped
        # because the override is active; transition publishes the new values.
        self.assertEqual(first["diagnostics"]["effective_curve"], "none")
        self.assertAlmostEqual(first["value"], 0.5, delta=1e-12)

        advance_world_tick(session)
        second = _field_state(session, "curve_expiry_area")
        # Expiry occurs before T2. The new squared baseline then applies to
        # x=0.5, target=0, rate=1: x' = 0.5 + 1 * (-0.5) * 0.5 = 0.25.
        self.assertEqual(second["diagnostics"]["effective_curve"], "distance_squared")
        self.assertAlmostEqual(second["value"], 0.25, delta=1e-12)

    def test_staged_rebuilt_and_loaded_continuations_match(self):
        session = _content({
            "replay_area": (
                _field(target=1.0, rate=0.5, curve="linear"),
                _ecology(
                    "replay_ecology",
                    initial={"target": 1.0, "rate": 0.5, "curve": "linear"},
                    target={"target": 0.0, "rate": 1.0, "curve": "distance_squared"},
                    comparator="lte",
                    threshold=0.5,
                ),
            ),
        })
        advance_world_tick(session)
        self.assertEqual(_field_state(session, "replay_area")["baseline"]["curve"], "distance_squared")

        # stage_gameplay_session retains the construction-time profile tuple,
        # while registry/Alpha rebuilds rediscover profiles from published state.
        staged = stage_gameplay_session(session)
        rebuilt = build_runtime(
            deepcopy(session.state),
            discover_profiles(session.state),
        )
        compiled = compile_content(
            make_content(
                basic_registry(),
                ecology_by_area={
                    "replay_area": _ecology(
                        "replay_ecology",
                        initial={"target": 1.0, "rate": 0.5, "curve": "linear"},
                        target={
                            "target": 0.0,
                            "rate": 1.0,
                            "curve": "distance_squared",
                        },
                        comparator="lte",
                        threshold=0.5,
                    ),
                },
            )
        )
        registry = MechanismRegistryRuntime.from_compiled_content(
            build_content_session(deepcopy(session.state), compiled),
            compiled,
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "replay.json"
            save_checkpoint(path, session)
            loaded = load_checkpoint(path)

        candidates = (session, staged, rebuilt, registry.session, loaded)
        for candidate in candidates:
            advance_world_tick(candidate)
        expected = session.state.to_dict()
        for candidate in candidates[1:]:
            self.assertEqual(candidate.state.to_dict(), expected)
        registry._rebuild()
        advance_world_tick(registry.session)
        advance_world_tick(session)
        self.assertEqual(registry.session.state.to_dict(), session.state.to_dict())
        field = _field_state(session, "replay_area")
        self.assertEqual(field["diagnostics"]["effective_curve"], "distance_squared")
        expected = 0.1875 + 1.0 * (-0.1875) * 0.1875
        self.assertAlmostEqual(field["value"], expected, delta=1e-12)

    def test_canonical_law_catalog_and_applied_ids_survive_profile_rebuild(self):
        session = _content({
            "identity_area": (
                _field(target=1.0, rate=0.5, curve="linear"),
                _ecology(
                    "identity_ecology",
                    initial={"target": 1.0, "rate": 0.5, "curve": "linear"},
                    target={"target": 0.0, "rate": 1.0, "curve": "distance_squared"},
                    comparator="lte",
                    threshold=0.5,
                ),
            ),
        })
        advance_world_tick(session)
        self.assertEqual(
            _field_state(session, "identity_area")["baseline"]["curve"],
            "distance_squared",
        )

        staged = stage_gameplay_session(session)
        rebuilt = build_runtime(
            deepcopy(session.state),
            discover_profiles(session.state),
        )
        old_ids = tuple(
            law["id"]
            for law in build_dynamics_laws(staged.profiles)
            if law["id"].startswith("pmw.v04.dynamics.200.")
        )
        current_ids = tuple(
            law["id"]
            for law in build_dynamics_laws(rebuilt.profiles)
            if law["id"].startswith("pmw.v04.dynamics.200.")
        )
        self.assertEqual(old_ids, current_ids)
        self.assertIn(
            "pmw.v04.dynamics.200.identity_area.temperature.base_distance_squared.up",
            current_ids,
        )
        self.assertIn(
            "pmw.v04.dynamics.200.identity_area.temperature.base.all",
            current_ids,
        )

        left = advance_world_tick(staged)
        right = advance_world_tick(rebuilt)
        dynamics = "pmw.v04.dynamics.200.identity_area.temperature."
        left_ids = tuple(
            law_id for law_id in left.event_result.triggered_law_ids
            if law_id.startswith(dynamics)
        )
        right_ids = tuple(
            law_id for law_id in right.event_result.triggered_law_ids
            if law_id.startswith(dynamics)
        )
        self.assertEqual(left_ids, right_ids)
        self.assertIn(
            "pmw.v04.dynamics.200.identity_area.temperature.base_distance_squared.down",
            right_ids,
        )
        self.assertEqual(staged.state.to_dict(), rebuilt.state.to_dict())
        self.assertEqual(
            left.event_result.trace.to_dict(),
            right.event_result.trace.to_dict(),
        )


class EcologyBaselineConfigurationReview(unittest.TestCase):
    def test_none_baseline_with_linear_override_expires_back_to_none(self):
        area = _area("override_area", _field(target=1.0, rate=0.0, curve="none"))
        session = build_runtime(build_gameplay_world(
            "override_none",
            areas=[area, clock_entity()],
        ))
        apply_source(
            session,
            entity_id="override_area",
            field_id=FIELD,
            layer="temporary",
            source=DynamicsSource(
                "review_recover",
                "review_oracle",
                rate_add=0.2,
                curve="linear",
                curve_priority=1,
                duration_ticks=2,
            ),
        )

        advance_world_tick(session)
        recovering = _field_state(session, "override_area")
        self.assertEqual(recovering["diagnostics"]["effective_curve"], "linear")
        self.assertAlmostEqual(recovering["diagnostics"]["effective_rate"], 0.2, delta=1e-12)
        self.assertAlmostEqual(recovering["value"], 0.6, delta=1e-12)
        advance_world_tick(session)
        frozen = _field_state(session, "override_area")
        self.assertEqual(frozen["diagnostics"]["effective_curve"], "none")
        self.assertEqual(frozen["diagnostics"]["effective_rate"], 0.0)
        self.assertAlmostEqual(frozen["value"], 0.6, delta=1e-12)

    def test_invalid_reachable_baselines_fail_before_session_construction(self):
        cases = (
            ("linear_rate", "linear", 1.01, 0.2),
            ("squared_rate", "distance_squared", 1.01, 0.2),
            ("target_domain", "linear", 0.5, 1.01),
        )
        for name, curve, rate, target in cases:
            with self.subTest(case=name):
                plan = _ecology(
                    f"invalid_{name}",
                    initial={"target": 0.5, "rate": 0.0, "curve": "linear"},
                    target={"target": target, "rate": rate, "curve": curve},
                    comparator="lte",
                    threshold=0.5,
                )
                world = build_gameplay_world(
                    "invalid_ecology",
                    areas=[
                        _area("invalid_area", _field(target=0.5, rate=0.0, curve="linear")),
                        clock_entity(),
                    ],
                )
                content = make_content(
                    basic_registry(),
                    ecology_by_area={"invalid_area": plan},
                )
                with self.assertRaises(GameplayContractError):
                    initialize_content_world(world, content)

    def test_unknown_and_nonzero_none_baselines_are_rejected(self):
        for curve, rate in (("quadratic", 0.5), ("none", 0.5)):
            with self.subTest(curve=curve, rate=rate):
                with self.assertRaises(GameplayContractError):
                    _ecology(
                        f"invalid_{curve}",
                        initial={"target": 0.5, "rate": 0.0, "curve": "linear"},
                        target={"target": 0.2, "rate": rate, "curve": curve},
                        comparator="lte",
                        threshold=0.5,
                    )


if __name__ == "__main__":
    unittest.main()
