from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import unittest

from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.basics import (
    basic_registry,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.conditions import (
    ConditionLimits,
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
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.tests.test_skill_ir_review import (
    DEFAULT_SELECTORS,
    MATERIAL_ID,
    _document,
    _effect,
    _entry,
)


def _authority(
    *kinds: str,
    selectors: tuple[str, ...] = DEFAULT_SELECTORS,
):
    material = parse_material({
        "id": MATERIAL_ID,
        "tier": "rare",
        "region_rarity": "scarce",
        "traits": [{
            "id": "p2f3_authority",
            "effect_kinds": list(kinds),
            "selectors": list(selectors),
            "budget_points": 40.0,
        }],
    })
    return material_authority((material,))


def _parse(raw, *, authority=None, condition_limits=None):
    return parse_skill_ir(
        raw,
        basic_registry().statuses,
        authority or _authority("damage", "shield"),
        condition_limits=condition_limits,
    )


def _replace_canonical(ir, document):
    canonical_json = json.dumps(
        document,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    object.__setattr__(ir, "canonical_json", canonical_json)
    object.__setattr__(
        ir,
        "canonical_hash",
        hashlib.sha256(canonical_json.encode("utf-8")).hexdigest(),
    )
    return ir


class SkillIRFix3ReparseTests(unittest.TestCase):
    def test_reviewer_empty_entries_reproduction_is_rejected(self):
        ir = _parse(_document())
        document = deepcopy(_document())
        document["entries"] = []
        _replace_canonical(ir, document)

        with self.assertRaisesRegex(GameplayContractError, "1\\.\\.4"):
            compile_skill_ir(ir)

    def test_self_consistent_invalid_documents_are_rejected(self):
        cases = []

        document = _document(entries=[
            _entry("active"),
            _entry("active", on_use=False),
        ])
        cases.append(("duplicate entry IDs", document))

        document = _document(entries=[
            _entry("one"),
            _entry("two"),
        ])
        cases.append(("two on_use entries", document))

        document = _document(selectors=("self",))
        cases.append(("target outside selectors", document))

        document = _document(
            selectors=("self", "target_actor", "linked_object"),
            relation_types=(),
            entries=[_entry(effects=[
                _effect(target="linked_object"),
            ])],
        )
        cases.append(("linked_object without relation types", document))

        document = _document(
            entries=[
                _entry(
                    "active",
                    effects=[_effect("strike", amount=2)],
                ),
                _entry(
                    "reaction",
                    on_use=False,
                    effects=[_effect("counter", amount=2)],
                ),
            ],
            budget=3.0,
        )
        cases.append(("shared budget overflow", document))

        document = _document()
        document["origin"]["source"] = "untrusted"
        cases.append(("invalid origin source", document))

        for label, document in cases:
            with self.subTest(label=label):
                authority = _authority(
                    "damage",
                    "shield",
                    selectors=(
                        *DEFAULT_SELECTORS,
                        "linked_object",
                    ),
                )
                ir = _parse(_document(), authority=authority)
                _replace_canonical(ir, document)
                with self.assertRaises(GameplayContractError):
                    compile_skill_ir(ir)

    def test_over_bound_text_in_self_consistent_document_is_rejected(self):
        boundaries = (
            (("identity", "name"), 81),
            (("identity", "description"), 601),
            (("origin", "model"), 129),
            (("display", "summary"), 241),
        )
        for path, length in boundaries:
            with self.subTest(path=path):
                document = _document()
                section, field = path
                document[section][field] = "x" * length
                ir = _replace_canonical(_parse(_document()), document)
                with self.assertRaises(GameplayContractError):
                    compile_skill_ir(ir)

    def test_forged_condition_nodes_are_recomputed_from_fresh_parse(self):
        ir = _parse(_document())
        expected = ir.condition_nodes
        object.__setattr__(ir, "condition_nodes", 999)

        compiled = compile_skill_ir(ir)

        self.assertEqual(compiled.ir.condition_nodes, expected)
        self.assertEqual(compiled.preview["condition_nodes"], expected)
        self.assertNotEqual(compiled.preview["condition_nodes"], 999)

    def test_compile_type_and_json_boundaries_are_contract_errors(self):
        with self.assertRaises(GameplayContractError):
            compile_skill_ir(object())

        ir = _parse(_document())
        object.__setattr__(ir, "authority", object())
        with self.assertRaises(GameplayContractError):
            compile_skill_ir(ir)

        ir = _parse(_document())
        object.__setattr__(ir, "condition_limits", object())
        with self.assertRaises(GameplayContractError):
            compile_skill_ir(ir)

        ir = _parse(_document())
        object.__setattr__(ir, "statuses", ())
        with self.assertRaises(GameplayContractError):
            compile_skill_ir(ir)

        ir = _parse(_document())
        object.__setattr__(ir, "canonical_json", {})
        with self.assertRaises(GameplayContractError):
            compile_skill_ir(ir)

        ir = _parse(_document())
        object.__setattr__(ir, "canonical_json", "{")
        object.__setattr__(
            ir,
            "canonical_hash",
            hashlib.sha256(b"{").hexdigest(),
        )
        with self.assertRaises(GameplayContractError):
            compile_skill_ir(ir)

    def test_valid_document_returns_fresh_ir_and_identical_hashes(self):
        parsed = _parse(_document())
        compiled = compile_skill_ir(parsed)

        self.assertEqual(compiled.ir.canonical_json, parsed.canonical_json)
        self.assertEqual(compiled.ir.canonical_hash, parsed.canonical_hash)
        self.assertEqual(compiled.canonical_hash, parsed.canonical_hash)
        self.assertEqual(
            compiled.blueprints[0].canonical_hash,
            "67f8bc9813354512b218709f7a895ae2e8088e8494d5ab9f2a97be630c3308c2",
        )
        self.assertEqual(
            compiled.canonical_hash,
            hashlib.sha256(parsed.canonical_json.encode("utf-8")).hexdigest(),
        )
        self.assertEqual(
            compiled.metadata_by_ir_hash[compiled.canonical_hash],
            compiled.metadata,
        )

    def test_parse_records_the_trusted_condition_limits(self):
        limits = ConditionLimits(max_nodes=63, max_depth=15, max_children=15)
        parsed = _parse(_document(), condition_limits=limits)
        self.assertIs(parsed.condition_limits, limits)

    def test_compile_reuses_the_recorded_condition_limits(self):
        recorded = ConditionLimits(max_nodes=53)
        parsed = _parse(_document(), condition_limits=recorded)
        document = _document(entries=[_entry(
            effects=[_effect(condition={
                "all": [{"all": [None] * 16} for _ in range(3)] + [None],
            })],
        )])
        _replace_canonical(parsed, document)

        self.assertEqual(
            parse_skill_ir(
                document,
                basic_registry().statuses,
                _authority("damage", "shield"),
            ).condition_nodes,
            54,
        )
        with self.assertRaisesRegex(GameplayContractError, "max_nodes 53"):
            compile_skill_ir(parsed)


if __name__ == "__main__":
    unittest.main()
