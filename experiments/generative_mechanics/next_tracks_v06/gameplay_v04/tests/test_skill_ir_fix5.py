from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.basics import (
    basic_registry,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.checkpoint import (
    load_registry_checkpoint,
    save_registry_checkpoint,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.conditions import (
    ConditionLimits,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.content_compiler import (
    build_content_session,
    compile_content,
    initialize_content_world,
    make_content,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.contracts import (
    GameplayContractError,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.materials import (
    material_authority,
    parse_material,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.registry import (
    MechanismRegistryRuntime,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.skill_ir import (
    MAX_JSON_SAFE_INT,
    compile_skill_ir,
    parse_skill_ir,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.tests.test_skill_ir import (
    _document,
    _world,
)


MATERIAL_ID = "p2_fix5_material"
DEFAULT_LIMITS = ConditionLimits()


def _authority(*kinds: str, budget: float = 40.0):
    material = parse_material({
        "id": MATERIAL_ID,
        "tier": "rare",
        "region_rarity": "scarce",
        "traits": [{
            "id": "p2_fix5_authority",
            "effect_kinds": list(kinds),
            "selectors": ["self", "target_actor", "current_area"],
            "budget_points": budget,
        }],
    })
    return material_authority((material,))


def _registry_authority(*kinds: str, budget: float = 2**53):
    material = parse_material({
        "id": MATERIAL_ID,
        "tier": "rare",
        "region_rarity": "scarce",
        "traits": [{
            "id": "p2_fix5_field_authority",
            "effect_kinds": list(kinds),
            "selectors": ["self", "target_actor", "current_area"],
            "budget_points": budget,
        }],
    })
    return material_authority((material,))


def _parse(raw, *, limits=None, authority=None):
    return parse_skill_ir(
        raw,
        basic_registry().statuses,
        authority or _authority("damage"),
        condition_limits=limits,
    )


def _document_for_authority(
    *,
    entries=None,
    mana: float = 4.0,
    budget: float = 40.0,
    material_id: str = MATERIAL_ID,
):
    raw = _document(entries=entries, mana=mana, budget=budget)
    raw["origin"]["material_ids"] = [material_id]
    return raw


def _not_chain(wrappers: int, terminal=None):
    value = terminal
    for _ in range(wrappers):
        value = {"not": value}
    return value


def _forged_limits(ir, **changes):
    return replace(ir, condition_limits=replace(ir.condition_limits, **changes))


class SkillIRFix5ConditionLimitTests(unittest.TestCase):
    def test_looser_limit_in_each_field_is_rejected_at_parse(self):
        for field in ("max_depth", "max_nodes", "max_children"):
            with self.subTest(field=field):
                limits = replace(
                    DEFAULT_LIMITS,
                    **{field: getattr(DEFAULT_LIMITS, field) + 1},
                )
                with self.assertRaisesRegex(
                    GameplayContractError, "tighten-only"
                ):
                    _parse(
                        _document_for_authority(),
                        limits=limits,
                    )

    def test_looser_limit_in_each_field_is_rejected_through_compile(self):
        parsed = _parse(_document_for_authority())
        for field in ("max_depth", "max_nodes", "max_children"):
            with self.subTest(field=field):
                forged = _forged_limits(
                    parsed,
                    **{field: getattr(DEFAULT_LIMITS, field) + 1},
                )
                with self.assertRaisesRegex(
                    GameplayContractError, "tighten-only"
                ):
                    compile_skill_ir(forged)

    def test_limits_equal_to_defaults_reach_all_three_boundaries(self):
        cases = (
            (
                "max_depth",
                _not_chain(DEFAULT_LIMITS.max_depth - 1),
                DEFAULT_LIMITS.max_depth + 1,
            ),
            (
                "max_children",
                {"all": [None] * DEFAULT_LIMITS.max_children},
                DEFAULT_LIMITS.max_children + 2,
            ),
            (
                "max_nodes",
                {"all": [
                    {"all": [None] * DEFAULT_LIMITS.max_children},
                    {"all": [None] * DEFAULT_LIMITS.max_children},
                    {"all": [None] * DEFAULT_LIMITS.max_children},
                    {"all": [None] * (DEFAULT_LIMITS.max_children - 6)},
                ]},
                DEFAULT_LIMITS.max_nodes,
            ),
        )
        for label, condition, expected_nodes in cases:
            with self.subTest(label=label):
                raw = _document_for_authority()
                raw["entries"][0]["condition"] = condition
                parsed = _parse(deepcopy(raw), limits=DEFAULT_LIMITS)
                self.assertEqual(parsed.condition_nodes, expected_nodes)
                compiled = compile_skill_ir(parsed)
                self.assertEqual(compiled.canonical_hash, parsed.canonical_hash)

    def test_default_boundary_blueprint_installs_and_round_trips_checkpoint(self):
        raw = _document_for_authority(
            entries=[{
                "id": "bounded",
                "trigger": {"kind": "on_use"},
                "condition": None,
                "effects": [{
                    "id": "pulse",
                    "kind": "modify_field",
                    "target": {"kind": "current_area"},
                    "commitment": "required",
                    "field_id": "heat",
                    "amount": 0,
                    "condition": _not_chain(DEFAULT_LIMITS.max_depth - 1),
                }],
                "max_firings_per_root": 1,
            }],
            budget=2**53,
        )
        parsed = _parse(
            raw,
            limits=DEFAULT_LIMITS,
            authority=_registry_authority("modify_field"),
        )
        compiled_skill = compile_skill_ir(parsed)
        blueprint = compiled_skill.blueprints[0]

        content = make_content(
            basic_registry(),
            skills=(blueprint,),
            material_ids=(MATERIAL_ID,),
        )
        initialized = initialize_content_world(_world(), content)
        compiled_content = compile_content(content)
        session = build_content_session(initialized, compiled_content)
        runtime = MechanismRegistryRuntime.from_compiled_content(
            session, compiled_content
        )
        self.assertEqual(
            runtime.blueprints[(blueprint.id, blueprint.version)],
            blueprint,
        )
        self.assertEqual(runtime.manifest.entries[0].canonical_hash,
                         blueprint.canonical_hash)

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fix5.json"
            save_registry_checkpoint(path, runtime)
            restored = load_registry_checkpoint(path, compiled_content)

        self.assertEqual(restored.manifest, runtime.manifest)
        self.assertEqual(
            restored.blueprints[(blueprint.id, blueprint.version)],
            blueprint,
        )
        self.assertEqual(
            restored.session.state.to_dict(),
            runtime.session.state.to_dict(),
        )


class SkillIRFix5IntegerTests(unittest.TestCase):
    def _assert_rejected_in_location(self, location):
        raw = _document_for_authority()
        if location == "mana":
            for value in (MAX_JSON_SAFE_INT + 1, 10**400):
                with self.subTest(location=location, value=value):
                    candidate = deepcopy(raw)
                    candidate["costs"]["mana"] = value
                    with self.assertRaisesRegex(
                        GameplayContractError, "safe integer"
                    ):
                        _parse(candidate)
            return
        if location == "amount":
            for value in (MAX_JSON_SAFE_INT + 1, 10**400):
                with self.subTest(location=location, value=value):
                    candidate = deepcopy(raw)
                    candidate["entries"][0]["effects"][0]["amount"] = value
                    with self.assertRaisesRegex(
                        GameplayContractError, "safe integer"
                    ):
                        _parse(candidate)
            return
        for value in (MAX_JSON_SAFE_INT + 1, 10**400):
            with self.subTest(location=location, value=value):
                candidate = deepcopy(raw)
                candidate["entries"][0]["condition"] = {
                    "resource": {
                        "subject": "self",
                        "key": "mana",
                        "comparator": "gte",
                        "value": value,
                    }
                }
                with self.assertRaisesRegex(
                    GameplayContractError, "safe integer"
                ):
                    _parse(candidate)

    def test_unsafe_values_are_contract_errors_in_all_numeric_paths(self):
        for location in ("mana", "amount", "condition"):
            self._assert_rejected_in_location(location)

    def test_safe_integer_ceiling_is_accepted_where_numeric(self):
        amount = self._parse_amount(MAX_JSON_SAFE_INT)
        self.assertEqual(amount, MAX_JSON_SAFE_INT)

        mana_raw = _document_for_authority(mana=MAX_JSON_SAFE_INT)
        mana_parsed = _parse(mana_raw)
        self.assertEqual(mana_parsed.mana, float(MAX_JSON_SAFE_INT))
        compile_skill_ir(mana_parsed)

        condition_raw = _document_for_authority()
        condition_raw["entries"][0]["condition"] = {
            "resource": {
                "subject": "self",
                "key": "mana",
                "comparator": "gte",
                "value": MAX_JSON_SAFE_INT,
            }
        }
        condition_parsed = _parse(condition_raw)
        compile_skill_ir(condition_parsed)

    def _parse_amount(self, value):
        raw = _document_for_authority(budget=2**53)
        raw["entries"][0]["effects"][0]["amount"] = value
        parsed = _parse(raw, authority=_registry_authority("damage", budget=2**53))
        compile_skill_ir(parsed)
        return parsed.entries[0].effects[0]["amount"]


if __name__ == "__main__":
    unittest.main()
