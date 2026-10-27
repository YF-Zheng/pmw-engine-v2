from __future__ import annotations

import unittest

from examples.pmw_alpha.skills import recipe_materials, skill_catalogue


class AlphaSkillCatalogueTests(unittest.TestCase):
    def test_four_cores_by_three_glyphs_are_mechanically_distinct(self) -> None:
        skills = skill_catalogue()
        self.assertEqual(len(skills), 12)
        self.assertEqual({row.core for row in skills}, {"tide", "thunder", "spore", "ash"})
        self.assertEqual({row.glyph for row in skills}, {"instant", "sustain", "echo"})
        self.assertEqual(len({row.effect for row in skills}), 12)

    def test_every_template_has_bounded_recipe_and_declared_uses(self) -> None:
        for skill in skill_catalogue():
            self.assertEqual(sum(recipe_materials(skill).values()), 2)
            self.assertTrue(skill.exploration_use)
            self.assertTrue(skill.combat_use)
