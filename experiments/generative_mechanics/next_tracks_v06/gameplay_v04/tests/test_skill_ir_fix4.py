from __future__ import annotations

import math
import unittest

from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.contracts import (
    GameplayContractError,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.skill_ir import (
    MAX_JSON_DEPTH,
    MAX_JSON_STRING,
    MAX_JSON_VALUES,
    _validate_json_shape,
    compile_skill_ir,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.tests.test_skill_ir_review import (
    _document,
    _parse,
)


def _nested_list(depth: int):
    value = None
    for _ in range(depth):
        value = [value]
    return value


def _nested_dict(depth: int):
    value = None
    for _ in range(depth):
        value = {"next": value}
    return value


def _with_payload(payload):
    raw = _document()
    raw["entries"][0]["effects"][0]["payload"] = payload
    return raw


class SkillIRFix4InputShapeTests(unittest.TestCase):
    def test_500_nested_lists_fail_closed_before_deepcopy(self):
        with self.assertRaisesRegex(GameplayContractError, r"\$"):
            _parse(_with_payload(_nested_list(500)))

    def test_2000_nested_lists_fail_closed_without_recursion_error(self):
        with self.assertRaises(GameplayContractError):
            _parse(_with_payload(_nested_list(2000)))

    def test_dict_container_depth_is_bounded(self):
        with self.assertRaisesRegex(GameplayContractError, "depth"):
            _parse(_with_payload(_nested_dict(MAX_JSON_DEPTH + 1)))

    def test_total_value_count_is_bounded(self):
        payload = [None] * (MAX_JSON_VALUES + 1)
        with self.assertRaisesRegex(GameplayContractError, "value limit"):
            _parse(_with_payload(payload))

    def test_overlong_string_and_key_are_rejected(self):
        with self.subTest(field="string"):
            with self.assertRaisesRegex(GameplayContractError, "string limit"):
                _parse(_with_payload("x" * (MAX_JSON_STRING + 1)))

        with self.subTest(field="key"):
            raw = _document()
            raw["x" * (MAX_JSON_STRING + 1)] = None
            with self.assertRaisesRegex(GameplayContractError, "string limit"):
                _parse(raw)

    def test_non_string_key_is_rejected(self):
        raw = _document()
        raw[7] = "not a JSON object key"
        with self.assertRaisesRegex(GameplayContractError, "keys must be strings"):
            _parse(raw)

    def test_set_and_arbitrary_object_values_are_rejected(self):
        for label, value in (
            ("set", {1, 2}),
            ("object", object()),
        ):
            with self.subTest(label=label):
                with self.assertRaisesRegex(
                    GameplayContractError, "unsupported JSON value type"
                ):
                    _parse(_with_payload(value))

    def test_non_finite_floats_are_rejected(self):
        for label, value in (
            ("nan", math.nan),
            ("positive infinity", math.inf),
            ("negative infinity", -math.inf),
        ):
            with self.subTest(label=label):
                with self.assertRaisesRegex(
                    GameplayContractError, "finite numeric"
                ):
                    _parse(_with_payload(value))

    def test_tuple_is_allowed_by_shape_validation(self):
        _validate_json_shape((1, ("x", None), 2.5, True))

    def test_legal_document_still_parses_and_compiles_to_identical_hashes(self):
        parsed = _parse(_document())
        compiled = compile_skill_ir(parsed)

        self.assertEqual(
            parsed.canonical_hash,
            "bc1e5676dfda8bef9d6ea7f2fcbfcfef26a2b52f445e080bcae27972456d8c7f",
        )
        self.assertEqual(compiled.canonical_hash, parsed.canonical_hash)
        self.assertEqual(
            compiled.blueprints[0].canonical_hash,
            "67f8bc9813354512b218709f7a895ae2e8088e8494d5ab9f2a97be630c3308c2",
        )


if __name__ == "__main__":
    unittest.main()
