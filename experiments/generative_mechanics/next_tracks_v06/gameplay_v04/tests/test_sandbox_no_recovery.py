from __future__ import annotations

import math
import random
from pathlib import Path
import tempfile
import unittest

from pmw import Event

from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.blueprints import (
    instantiate_actor,
    instantiate_area,
    parse_actor_blueprint,
    parse_area_blueprint,
    parse_field_definition,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.contracts import (
    DynamicsSource,
    FieldDefinition,
    GameplayContractError,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.dynamics import evaluate_field
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.runtime import (
    advance_world_tick,
    apply_source,
    build_runtime,
    clock_entity,
    load_checkpoint,
    save_checkpoint,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.worlds import build_gameplay_world


def field_raw(curve="none", rate=0.0, *, field_id="temperature", initial=0.8, target=0.2):
    return {
        "id": field_id,
        "domain": {"min": 0.0, "max": 1.0},
        "initial": initial,
        "target": target,
        "rate": rate,
        "curve": curve,
        "max_persistent_patches": 2,
        "max_temporary_modifiers": 2,
    }


def area_raw(curve="none", rate=0.0):
    return {
        "protocol": "pmw-gameplay-v0.4",
        "kind": "area_blueprint",
        "id": "no_recovery_area",
        "fields": [field_raw(curve, rate)],
        "ecology_state": "stock",
    }


def actor_raw(curve="none", rate=0.0):
    return {
        "protocol": "pmw-gameplay-v0.4",
        "kind": "actor_blueprint",
        "id": "mana_actor",
        "hp": {"max": 70, "initial": 70},
        "mana": {
            "max": 100,
            "initial": 70,
            "dynamics": field_raw(curve, rate, field_id="mana", initial=70, target=80),
        },
        "attributes": {"power": 8, "control": 7, "resilience": 8, "agility": 7},
        "traits": ["reservoir"],
    }


def build_area_session(curve="none", rate=0.0, *, extra_laws=()):
    area = instantiate_area(parse_area_blueprint(area_raw(curve, rate)), "no_recovery_area")
    world = build_gameplay_world("no_recovery", areas=[area, clock_entity()])
    return build_runtime(world, extra_laws=extra_laws)


def field_state(session, entity_id="no_recovery_area", field_id="temperature"):
    return session.state.entities[entity_id].components["pmw_gameplay_dynamics"]["fields"][field_id]


def reference_next(definition, value, persistent=(), temporary=()):
    sources = tuple(persistent) + tuple(temporary)
    overrides = [item for item in sources if item.curve is not None]
    curve = max(overrides, key=lambda item: item.curve_priority).curve if overrides else definition.curve

    numerator = definition.target
    denominator = 1.0
    for item in sources:
        if item.target is not None:
            numerator += item.target_weight * item.target
            denominator += item.target_weight
    target = numerator / denominator

    rate = definition.rate + sum(item.rate_add for item in sources)
    for item in sources:
        rate *= item.rate_multiplier
    if curve == "none":
        rate = 0.0
    elif curve == "linear":
        rate = min(1.0, max(0.0, rate))
    elif curve == "distance_squared":
        rate = min(1.0 / definition.width, max(0.0, rate))
    else:
        raise AssertionError("test reference received an unknown curve")

    if curve == "none":
        return value, target, curve, rate
    difference = target - value
    delta = rate * difference if curve == "linear" else rate * difference * abs(difference)
    bounded = min(definition.maximum, max(definition.minimum, value + delta))
    return bounded, target, curve, rate


class NoRecoveryContractTests(unittest.TestCase):
    def test_none_accepts_zero_rate_and_has_zero_stability_limit(self):
        definition = parse_field_definition(field_raw())
        self.assertEqual(definition.curve, "none")
        self.assertEqual(definition.rate, 0.0)
        self.assertEqual(definition.stable_rate_limit, 0.0)

    def test_none_rejects_positive_nonfinite_and_bool_rates(self):
        for bad_rate in (0.01, True, math.nan, math.inf, -math.inf):
            with self.subTest(rate=bad_rate):
                with self.assertRaises(GameplayContractError):
                    parse_field_definition(field_raw(rate=bad_rate))

    def test_none_rejects_nonfinite_rates_in_existing_state_profiles(self):
        definition = parse_field_definition(field_raw())
        for bad_rate in (0.01, True, math.nan, math.inf):
            with self.subTest(rate=bad_rate):
                malformed = FieldDefinition(
                    definition.id, definition.minimum, definition.maximum,
                    definition.initial, definition.target, bad_rate, "none",
                )
                with self.assertRaises(GameplayContractError):
                    evaluate_field(malformed, definition.initial)

    def test_none_formula_is_independent_of_target_and_rate_sources(self):
        definition = parse_field_definition(field_raw())
        sources = (
            DynamicsSource(
                "held_target", "external_rule", target=0.0,
                target_weight=9.0, rate_add=0.8, rate_multiplier=3.0,
            ),
        )
        result = evaluate_field(definition, 0.8, persistent=sources)
        self.assertEqual(result.value, 0.8)
        self.assertEqual(result.effective_curve, "none")
        self.assertEqual(result.effective_rate, 0.0)
        self.assertLess(result.effective_target, 0.2)

    def test_numeric_reference_parity_for_all_three_curves(self):
        rng = random.Random(2801)
        for index in range(300):
            curve = ("linear", "distance_squared", "none")[index % 3]
            low = rng.uniform(-5.0, 0.0)
            width = rng.uniform(0.25, 5.0)
            high = low + width
            value = rng.uniform(low, high)
            target = rng.uniform(low, high)
            rate_limit = {"linear": 1.0, "distance_squared": 1.0 / width, "none": 0.0}[curve]
            rate = rng.uniform(0.0, rate_limit)
            definition = FieldDefinition("oracle", low, high, value, target, rate, curve, 1, 1)
            expected, expected_target, expected_curve, expected_rate = reference_next(
                definition, value,
            )
            result = evaluate_field(definition, value)
            self.assertAlmostEqual(result.value, expected, delta=1e-12)
            self.assertAlmostEqual(result.effective_target, expected_target, delta=1e-12)
            self.assertAlmostEqual(result.effective_rate, expected_rate, delta=1e-12)
            self.assertEqual(result.effective_curve, expected_curve)


class EngineNoRecoveryTests(unittest.TestCase):
    def test_formal_engine_three_curve_parity(self):
        cases = (
            ("linear", 0.2, 0.68),
            ("distance_squared", 0.5, 0.62),
            ("none", 0.0, 0.8),
        )
        for curve, rate, expected in cases:
            with self.subTest(curve=curve):
                game = build_area_session(curve, rate)
                result = advance_world_tick(game)
                state = field_state(game)
                self.assertAlmostEqual(state["value"], expected, delta=1e-12)
                self.assertEqual(state["diagnostics"]["effective_curve"], curve)
                self.assertAlmostEqual(
                    state["diagnostics"]["effective_rate"],
                    0.0 if curve == "none" else rate,
                    delta=1e-12,
                )
                self.assertTrue(any(
                    law_id.startswith("pmw.v04.dynamics.200.no_recovery_area.temperature.")
                    for law_id in result.event_result.triggered_law_ids
                ))

    def test_none_engine_parity_with_independent_target_and_rate_reference(self):
        game = build_area_session("none")
        source = DynamicsSource(
            "held_rule", "world_rule", target=0.0,
            target_weight=4.0, rate_add=0.7, rate_multiplier=2.0,
        )
        apply_source(
            game, entity_id="no_recovery_area", field_id="temperature",
            layer="persistent", source=source,
        )
        definition = parse_area_blueprint(area_raw()).fields[0]
        expected, expected_target, expected_curve, expected_rate = reference_next(
            definition, 0.8, persistent=(source,),
        )
        advance_world_tick(game)
        state = field_state(game)
        self.assertAlmostEqual(state["value"], expected, delta=1e-12)
        self.assertAlmostEqual(state["diagnostics"]["effective_target"], expected_target, delta=1e-12)
        self.assertAlmostEqual(state["diagnostics"]["effective_rate"], expected_rate, delta=1e-12)
        self.assertEqual(state["diagnostics"]["effective_curve"], expected_curve)

    def test_none_holds_across_ticks_with_target_and_rate_modifiers(self):
        game = build_area_session("none")
        apply_source(
            game, entity_id="no_recovery_area", field_id="temperature",
            layer="persistent",
            source=DynamicsSource("target_shift", "ecology", target=0.0, target_weight=6.0),
        )
        apply_source(
            game, entity_id="no_recovery_area", field_id="temperature",
            layer="temporary",
            source=DynamicsSource(
                "rate_boost", "weather", rate_add=0.9,
                rate_multiplier=4.0, duration_ticks=3,
            ),
        )
        for step in range(1, 5):
            advance_world_tick(game)
            state = field_state(game)
            self.assertEqual(state["value"], 0.8, msg=f"step={step}")
            self.assertEqual(state["diagnostics"]["effective_curve"], "none")
            self.assertEqual(state["diagnostics"]["effective_rate"], 0.0)

    def test_external_pmw_rule_impulse_survives_none_ticks(self):
        impulse_law = {
            "id": "pmw.test.none.impulse",
            "mode": "event",
            "priority": 100,
            "bindings": {
                "subject": {"kind": "entity", "requires": ["pmw_gameplay_dynamics"]},
            },
            "when": {"all": [
                {"event.type": {"eq": "pmw.test.none.impulse"}},
                {"ref": "$subject.id", "eq": "no_recovery_area"},
            ]},
            "effects": [{
                "op": "delta",
                "target": "$subject.pmw_gameplay_dynamics.fields.temperature.value",
                "value": 0.1,
            }],
        }
        game = build_area_session("none", extra_laws=(impulse_law,))
        result = game.runtime.run_event(Event(
            "impulse_1", "pmw.test.none.impulse", time=game.state.sim_time,
            target="no_recovery_area",
        ))
        self.assertIn("pmw.test.none.impulse", result.triggered_law_ids)
        self.assertAlmostEqual(field_state(game)["value"], 0.9, delta=1e-12)
        advance_world_tick(game)
        advance_world_tick(game)
        self.assertAlmostEqual(field_state(game)["value"], 0.9, delta=1e-12)
        self.assertEqual(field_state(game)["diagnostics"]["effective_rate"], 0.0)

    def test_override_into_none_zeroes_rate_and_expiry_restores_linear(self):
        game = build_area_session("linear", 0.2)
        override = DynamicsSource(
            "freeze", "status", rate_add=0.5, curve="none",
            curve_priority=2, duration_ticks=2,
        )
        apply_source(
            game, entity_id="no_recovery_area", field_id="temperature",
            layer="temporary", source=override,
        )
        advance_world_tick(game)
        frozen = field_state(game)
        self.assertEqual(frozen["value"], 0.8)
        self.assertEqual(frozen["diagnostics"]["effective_curve"], "none")
        self.assertEqual(frozen["diagnostics"]["effective_rate"], 0.0)
        advance_world_tick(game)
        restored = field_state(game)
        self.assertAlmostEqual(restored["value"], 0.68, delta=1e-12)
        self.assertEqual(restored["diagnostics"]["effective_curve"], "linear")
        self.assertAlmostEqual(restored["diagnostics"]["effective_rate"], 0.2, delta=1e-12)

    def test_override_out_of_none_uses_modifier_rate_then_returns_to_none(self):
        game = build_area_session("none")
        override = DynamicsSource(
            "recover", "status", rate_add=0.2, curve="linear",
            curve_priority=1, duration_ticks=2,
        )
        apply_source(
            game, entity_id="no_recovery_area", field_id="temperature",
            layer="temporary", source=override,
        )
        advance_world_tick(game)
        recovering = field_state(game)
        self.assertAlmostEqual(recovering["value"], 0.68, delta=1e-12)
        self.assertEqual(recovering["diagnostics"]["effective_curve"], "linear")
        self.assertAlmostEqual(recovering["diagnostics"]["effective_rate"], 0.2, delta=1e-12)
        advance_world_tick(game)
        frozen = field_state(game)
        self.assertAlmostEqual(frozen["value"], 0.68, delta=1e-12)
        self.assertEqual(frozen["diagnostics"]["effective_curve"], "none")
        self.assertEqual(frozen["diagnostics"]["effective_rate"], 0.0)

    def test_priority_conflict_with_none_override_fails_closed(self):
        game = build_area_session("linear", 0.2)
        apply_source(
            game, entity_id="no_recovery_area", field_id="temperature",
            layer="persistent",
            source=DynamicsSource("curve_a", "owner_a", curve="distance_squared", curve_priority=3),
        )
        with self.assertRaises(GameplayContractError):
            apply_source(
                game, entity_id="no_recovery_area", field_id="temperature",
                layer="temporary",
                source=DynamicsSource(
                    "curve_b", "owner_b", curve="none",
                    curve_priority=3, duration_ticks=1,
                ),
            )

    def test_save_load_none_replay_is_deterministic(self):
        game = build_area_session("none")
        apply_source(
            game, entity_id="no_recovery_area", field_id="temperature",
            layer="persistent",
            source=DynamicsSource("held_target", "world", target=0.0, target_weight=3.0),
        )
        advance_world_tick(game)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "none_replay.json"
            save_checkpoint(path, game)
            loaded = load_checkpoint(path)
            for _ in range(4):
                advance_world_tick(game)
                advance_world_tick(loaded)
            self.assertEqual(game.state.to_dict(), loaded.state.to_dict())
            self.assertEqual(field_state(game)["value"], 0.8)

    def test_actor_mana_none_law_writes_value_and_mirror(self):
        actor = instantiate_actor(parse_actor_blueprint(actor_raw()), "mana_holder", controller="human")
        game = build_runtime(build_gameplay_world(
            "mana_none", areas=[clock_entity()], actors=[actor],
        ))
        first = advance_world_tick(game)
        advance_world_tick(game)
        entity = game.state.entities["mana_holder"]
        dynamics = field_state(game, "mana_holder", "mana")
        mana = entity.components["pmw_gameplay_actor"]["mana"]
        self.assertEqual(dynamics["value"], 70.0)
        self.assertEqual(mana, dynamics["value"])
        self.assertEqual(dynamics["diagnostics"]["effective_curve"], "none")
        self.assertEqual(dynamics["diagnostics"]["effective_rate"], 0.0)
        self.assertTrue(any(
            law_id.startswith("pmw.v04.dynamics.200.mana_holder.mana.")
            for law_id in first.event_result.triggered_law_ids
        ))


if __name__ == "__main__":
    unittest.main()
