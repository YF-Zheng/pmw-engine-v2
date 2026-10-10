from __future__ import annotations

import unittest

from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.basics import basic_registry
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.ecology import parse_ecology_spec, sample_ecology
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.gate3_demo import build_gate3_demo, run_gate3_demo
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.status import parse_status_spec
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.weather import build_weather_laws, parse_weather_spec


class WeatherEcologyTests(unittest.TestCase):
    def test_demo_weather_is_selective_and_bounded(self):
        result = run_gate3_demo()
        self.assertEqual((result["weather"]["hero_mana"], result["weather"]["plain_mana"]), (11.0, 10.0))
        self.assertEqual(result["weather"]["state"]["remaining"], 1)

    def test_status_granted_trait_compiles_runtime_slot_variants(self):
        registry = basic_registry()
        status = parse_status_spec({"id": "mist_mark", "version": 1, "polarity": "buff", "max_stacks": 1,
            "stack_policy": "refresh", "duration": {"unit": "world_tick", "amount": 2},
            "granted_traits": ["mist_attuned"]})
        weather = parse_weather_spec({"protocol": "pmw-gameplay-v0.4", "id": "mist", "label": "Mist",
            "field_id": "mist", "enter_at": .7, "exit_at": .3, "duration_ticks": 2, "source_id": "sky",
            "common_effects": [], "trait_interactions": [{"trait_id": "mist_attuned", "effect": {
                "id": "gift", "kind": "add_resource", "target": {"kind": "self"},
                "commitment": "required", "resource": "mana", "amount": 1}}]}, registry.statuses)
        laws = build_weather_laws({"area": (weather,)}, {status.id: status})
        self.assertEqual(sum("trait_status.mist_attuned.mist_mark" in law["id"] for law in laws), 8)

    def test_ecology_sampling_is_deterministic_and_reachable(self):
        session, content, _, _ = build_gate3_demo()
        plan = content.ecology_by_area["mist_forest"]
        self.assertEqual(sample_ecology(plan.spec, 17), plan)
        self.assertEqual(plan.reachable_regimes, ("thriving", "depleted"))

    def test_sustained_threshold_changes_regime_and_baseline(self):
        result = run_gate3_demo()
        self.assertEqual(result["ecology"]["current"], "depleted")
        self.assertEqual(result["ecology"]["baseline"]["target"], .2)


if __name__ == "__main__": unittest.main()
