from __future__ import annotations

from copy import deepcopy
import unittest

from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.basics import (
    basic_registry,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.contracts import (
    GameplayContractError,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.effects import (
    EffectSpec,
    parse_effect,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.materials import (
    material_authority,
    parse_material,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.skills import (
    SkillBlueprint,
    parse_skill_blueprint,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.tests.test_sandbox_process_action import (
    TEMPLATE_ID,
)


MATERIAL_ID = "process_crystal"


def _effect(**fields):
    raw = {
        "id": "adjust",
        "kind": "process_modify",
        "target": {"kind": "current_area"},
        "commitment": "required",
        "process_template_id": TEMPLATE_ID,
    }
    raw.update(fields)
    return raw


def _authority(*effect_kinds: str):
    material = parse_material({
        "id": MATERIAL_ID,
        "tier": "rare",
        "region_rarity": "scarce",
        "traits": [{
            "id": "process_shaping",
            "effect_kinds": list(effect_kinds),
            "selectors": ["current_area"],
            "budget_points": 5,
        }],
    })
    return material_authority((material,))


def _blueprint(effect):
    return {
        "protocol": "pmw-gameplay-v0.4",
        "kind": "skill_blueprint",
        "id": "adjust_process",
        "version": 1,
        "trigger": "on_use",
        "condition": None,
        "duration": None,
        "cost": {"duration": 1, "mana": 0},
        "scope": {"selectors": ["current_area"], "relation_types": []},
        "effects": [effect],
        "budget": {"limit": 5},
        "max_firings_per_root": 1,
        "material_ids": [MATERIAL_ID],
    }


class ProcessModifyOptionalFieldTests(unittest.TestCase):
    def test_rate_only_remaining_only_and_both_parse_at_both_layers(self):
        cases = (
            ({"process_rate": 1.75}, 1.75, None),
            ({"process_remaining_ticks": 2}, None, 2),
            ({"process_rate": 1.75, "process_remaining_ticks": 2}, 1.75, 2),
        )
        statuses = basic_registry().statuses
        authority = _authority("process_modify")
        for optional, expected_rate, expected_remaining in cases:
            with self.subTest(optional=optional):
                raw = _effect(**optional)
                effect = parse_effect(raw, statuses)
                self.assertIsInstance(effect, EffectSpec)
                self.assertEqual(effect.process_rate, expected_rate)
                self.assertEqual(effect.process_remaining_ticks, expected_remaining)
                blueprint = parse_skill_blueprint(_blueprint(raw), statuses, authority)
                self.assertIsInstance(blueprint, SkillBlueprint)
                self.assertEqual(blueprint.effects[0], effect)

    def test_no_numeric_and_unknown_keys_remain_strict(self):
        statuses = basic_registry().statuses
        with self.assertRaisesRegex(GameplayContractError, "missing or unknown fields"):
            parse_effect(_effect(), statuses)
        with self.assertRaisesRegex(GameplayContractError, "missing or unknown fields"):
            parse_effect(_effect(process_rate=1.5, extra_field=1), statuses)

    def test_explicit_null_rejects_even_with_valid_other_numeric(self):
        statuses = basic_registry().statuses
        for raw in (
            _effect(process_rate=None, process_remaining_ticks=2),
            _effect(process_rate=1.5, process_remaining_ticks=None),
        ):
            with self.subTest(raw=raw):
                with self.assertRaises(GameplayContractError):
                    parse_effect(raw, statuses)

    def test_invalid_numeric_shapes_reject_for_either_field(self):
        statuses = basic_registry().statuses
        cases = (
            ({"process_rate": True}, "finite positive"),
            ({"process_rate": False}, "finite positive"),
            ({"process_rate": float("inf")}, "finite positive"),
            ({"process_rate": float("nan")}, "finite positive"),
            ({"process_rate": 0}, "finite positive"),
            ({"process_rate": -1}, "finite positive"),
            ({"process_rate": "1.5"}, "finite positive"),
            ({"process_rate": 1.5, "process_remaining_ticks": True}, "positive integer"),
            ({"process_remaining_ticks": 0}, "positive integer"),
            ({"process_remaining_ticks": -1}, "positive integer"),
            ({"process_remaining_ticks": 1.0}, "positive integer"),
            ({"process_remaining_ticks": "2"}, "positive integer"),
        )
        for optional, error in cases:
            with self.subTest(optional=optional):
                with self.assertRaisesRegex(GameplayContractError, error):
                    parse_effect(_effect(**optional), statuses)

    def test_start_and_other_effect_kinds_keep_strict_schemas(self):
        statuses = basic_registry().statuses
        start = {
            "id": "start",
            "kind": "process_start",
            "target": {"kind": "current_area"},
            "commitment": "required",
            "process_template_id": TEMPLATE_ID,
        }
        self.assertEqual(parse_effect(start, statuses).kind, "process_start")
        for optional in (
            {"process_rate": 1.5},
            {"process_remaining_ticks": 2},
        ):
            with self.subTest(kind="process_start", optional=optional):
                with self.assertRaisesRegex(
                    GameplayContractError, "missing or unknown fields"
                ):
                    parse_effect(deepcopy(start) | optional, statuses)

        damage = {
            "id": "strike",
            "kind": "damage",
            "target": {"kind": "target_actor"},
            "commitment": "required",
            "amount": 3,
        }
        self.assertEqual(parse_effect(damage, statuses).kind, "damage")
        with self.assertRaisesRegex(GameplayContractError, "missing or unknown fields"):
            parse_effect(damage | {"process_rate": 1.5}, statuses)


if __name__ == "__main__":
    unittest.main()
