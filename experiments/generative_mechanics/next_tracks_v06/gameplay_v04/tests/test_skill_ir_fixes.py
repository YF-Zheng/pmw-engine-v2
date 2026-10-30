from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import hashlib
import json
import unittest

from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.basics import (
    basic_registry,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.contracts import (
    GameplayContractError,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.materials import (
    material_authority,
    parse_material,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.skill_ir import (
    compile_skill_ir,
    parse_skill_ir,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.skills import (
    parse_skill_blueprint,
)


MATERIAL_ID = "p2f_material"


def _authority():
    material = parse_material({
        "id": MATERIAL_ID,
        "tier": "rare",
        "region_rarity": "scarce",
        "traits": [{
            "id": "p2f_authority",
            "effect_kinds": ["damage", "shield"],
            "selectors": ["self", "target_actor", "current_area"],
            "budget_points": 40.0,
        }],
    })
    return material_authority((material,))


def _document(**changes):
    raw = {
        "protocol": "pmw-skill-ir-v1",
        "identity": {
            "id": "p2f_skill",
            "version": 1,
            "name": "P2.1 fix skill",
            "description": "Focused fix conformance fixture.",
        },
        "origin": {
            "source": "authored",
            "model": None,
            "context_hash": None,
            "material_ids": [MATERIAL_ID],
        },
        "capability": {"traits": ["p2f_trait"]},
        "targeting": {
            "selectors": ["self", "target_actor", "current_area"],
            "relation_types": [],
        },
        "costs": {"mana": 4.0, "duration": 1},
        "entries": [{
            "id": "active",
            "trigger": {"kind": "on_use"},
            "condition": None,
            "effects": [{
                "id": "pulse",
                "kind": "damage",
                "target": {"kind": "target_actor"},
                "commitment": "required",
                "amount": 4,
            }],
            "max_firings_per_root": 1,
        }],
        "lifecycle": {"status_duration": None},
        "limits": {"budget": 40.0},
        "display": {
            "summary": "Focused fix preview.",
            "tags": ["fix"],
        },
    }
    raw.update(changes)
    return raw


def _parse(raw, *, authority=None):
    return parse_skill_ir(
        raw,
        basic_registry().statuses,
        authority or _authority(),
    )


class SkillIRFixTests(unittest.TestCase):
    def test_non_null_status_duration_is_a_language_gap(self):
        for duration in (
            {"unit": "world_tick", "amount": 7},
            {"unit": "combat_round", "amount": 2},
            {"unit": [], "amount": 2},
        ):
            raw = _document(lifecycle={"status_duration": duration})
            with self.subTest(duration=duration):
                with self.assertRaisesRegex(
                    GameplayContractError,
                    r"^language_gap:lifecycle\.status_duration",
                ):
                    _parse(raw)

        parsed = _parse(_document())
        self.assertIsNone(parsed.status_duration)

    def test_malformed_membership_scalars_are_contract_errors(self):
        mutations = []
        raw = _document()
        raw["origin"]["source"] = []
        mutations.append(raw)

        raw = _document(lifecycle={
            "status_duration": {"unit": [], "amount": 2}
        })
        mutations.append(raw)

        raw = _document()
        raw["entries"][0]["effects"][0]["kind"] = []
        mutations.append(raw)

        raw = _document()
        raw["entries"][0]["effects"][0]["target"]["kind"] = []
        mutations.append(raw)

        raw = _document()
        raw["entries"][0]["effects"][0]["target"]["relation_type"] = []
        mutations.append(raw)

        raw = _document()
        raw["entries"][0]["trigger"]["kind"] = []
        mutations.append(raw)

        raw = _document()
        raw["entries"][0]["trigger"] = {
            "kind": "on_event",
            "event": [],
        }
        mutations.append(raw)

        raw = _document()
        raw["entries"][0]["condition"] = {frozenset(): None}
        mutations.append(raw)

        raw = _document()
        raw["targeting"]["selectors"] = [{}]
        mutations.append(raw)

        raw = _document()
        raw["display"]["tags"] = [{}]
        mutations.append(raw)

        for index, malformed in enumerate(mutations):
            with self.subTest(index=index):
                with self.assertRaises(GameplayContractError):
                    _parse(malformed)

    def test_canonical_json_prevents_hash_and_lowered_semantics_divergence(self):
        parsed = _parse(_document())
        original = compile_skill_ir(parsed)
        parsed.entries[0].effects[0]["amount"] = 999
        recompiled = compile_skill_ir(parsed)

        self.assertEqual(recompiled.canonical_hash, original.canonical_hash)
        self.assertEqual(
            recompiled.blueprints[0].canonical_hash,
            original.blueprints[0].canonical_hash,
        )
        self.assertEqual(recompiled.blueprints[0].effects[0].amount, 4.0)

        forged = replace(parsed, canonical_hash="0" * 64)
        with self.assertRaisesRegex(
            GameplayContractError, "canonical_hash"
        ):
            compile_skill_ir(forged)

    def test_input_and_canonical_length_bounds(self):
        cases = (
            (("identity", "name"), 80, 81),
            (("identity", "description"), 600, 601),
            (("origin", "model"), 128, 129),
        )
        for path, maximum, over in cases:
            raw = _document()
            section, field = path
            raw[section][field] = "x" * maximum
            _parse(raw)
            raw[section][field] = "x" * over
            with self.subTest(field=path):
                with self.assertRaisesRegex(
                    GameplayContractError, str(maximum)
                ):
                    _parse(raw)

    def test_v04_hash_parity_and_canonical_ir_hash_parity(self):
        raw = _document()
        parsed = _parse(raw)
        compiled = compile_skill_ir(parsed)
        handwritten = {
            "protocol": "pmw-gameplay-v0.4",
            "kind": "skill_blueprint",
            "id": "p2f_skill__active",
            "version": 1,
            "trigger": "on_use",
            "condition": None,
            "duration": None,
            "cost": {"duration": 1, "mana": 4.0},
            "scope": {
                "selectors": ["target_actor"],
                "relation_types": [],
            },
            "effects": [{
                "id": "pulse",
                "kind": "damage",
                "target": {"kind": "target_actor"},
                "commitment": "required",
                "amount": 4,
            }],
            "budget": {"limit": 40.0},
            "max_firings_per_root": 1,
            "material_ids": [MATERIAL_ID],
        }
        legacy = parse_skill_blueprint(
            handwritten,
            basic_registry().statuses,
            _authority(),
        )
        self.assertEqual(
            compiled.blueprints[0].canonical_hash,
            legacy.canonical_hash,
        )
        self.assertEqual(
            parsed.canonical_hash,
            hashlib.sha256(parsed.canonical_json.encode("utf-8")).hexdigest(),
        )
        self.assertEqual(
            json.dumps(
                raw,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ),
            parsed.canonical_json,
        )


if __name__ == "__main__":
    unittest.main()
