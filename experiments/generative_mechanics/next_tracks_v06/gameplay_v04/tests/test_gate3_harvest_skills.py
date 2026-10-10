from __future__ import annotations

import unittest

from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.contracts import GameplayContractError
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.gate3_demo import build_gate3_demo, run_gate3_demo
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.harvest import HarvestRequest, resolve_harvest
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.materials import material_authority, parse_material


class HarvestSkillTests(unittest.TestCase):
    def test_lucky_changes_time_and_yield_not_consumption(self):
        result = run_gate3_demo()["harvest"]
        self.assertEqual((result["first_duration"], result["first_yield"], result["first_consumption"]), (1, 2.0, .2))

    def test_compound_skill_uses_shared_budget(self):
        _, _, skill, _ = build_gate3_demo()
        self.assertEqual(skill.budget_used, 4.25)
        self.assertLessEqual(skill.budget_used, skill.budget_limit)

    def test_material_tier_and_region_rarity_are_independent(self):
        material = parse_material({"id": "ore", "tier": "legendary", "region_rarity": "abundant",
            "traits": [{"id": "heat", "effect_kinds": ["damage"], "selectors": ["target_actor"], "budget_points": 3}]})
        self.assertEqual((material.tier, material.region_rarity), ("legendary", "abundant"))
        self.assertEqual(material_authority((material,)).budget_points, 3)

    def test_unauthorized_lucky_harvest_is_atomic(self):
        session, content, _, spec = build_gate3_demo()
        before = session.state.to_dict()
        with self.assertRaises(GameplayContractError):
            resolve_harvest(session, content.action_registry, spec, HarvestRequest("bad_luck", "hero_actor", spec.id, True))
        self.assertEqual(session.state.to_dict(), before)


if __name__ == "__main__": unittest.main()
