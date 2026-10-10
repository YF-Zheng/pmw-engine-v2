from __future__ import annotations

from copy import deepcopy
import unittest

from pmw import parse_law

from experiments.generative_mechanics.next_tracks_v06.canonical import canonical_json
from experiments.generative_mechanics.next_tracks_v06.compiler import compile_mechanism, compile_mechanisms, compiled_document
from experiments.generative_mechanics.next_tracks_v06.validator import validate_mechanism
from experiments.generative_mechanics.next_tracks_v06.tests.helpers import VALID_OPERATORS, catalog, mechanism


class CompilerTests(unittest.TestCase):
    def compile(self, raw, cat=None):
        cat = cat or catalog()
        return compile_mechanism(validate_mechanism(raw, cat), cat)

    def test_all_seven_operators_lower(self):
        raw = mechanism(list(VALID_OPERATORS.values()), artifact_id="all_operators")
        compiled = self.compile(raw)
        self.assertGreaterEqual(len(compiled.law_bundle), 13)

    def test_all_laws_parse(self):
        compiled = self.compile(mechanism(list(VALID_OPERATORS.values()), artifact_id="parse_all"))
        for law in compiled.law_bundle:
            self.assertEqual(parse_law(dict(law)).law_id, law["id"])

    def test_canonical_key_order(self):
        raw = mechanism([VALID_OPERATORS["attractor_modifier"]])
        reversed_raw = dict(reversed(list(raw.items())))
        self.assertEqual(canonical_json(self.compile(raw).to_dict()), canonical_json(self.compile(reversed_raw).to_dict()))

    def test_compiled_document_is_v2(self):
        document = compiled_document(self.compile(mechanism()))
        self.assertEqual(document["schema_version"], "2.0")

    def test_law_ids_are_unique_and_sorted(self):
        compiled = self.compile(mechanism(list(VALID_OPERATORS.values()), artifact_id="unique_laws"))
        ids = [item["id"] for item in compiled.law_bundle]
        self.assertEqual(ids, sorted(set(ids)))

    def test_source_map_covers_every_law(self):
        compiled = self.compile(mechanism(list(VALID_OPERATORS.values()), artifact_id="source_map"))
        self.assertEqual(set(compiled.source_map), {item["id"] for item in compiled.law_bundle})

    def test_temporal_handles_are_unique_per_operator(self):
        compiled = self.compile(mechanism([
            VALID_OPERATORS["drive"], VALID_OPERATORS["attractor_modifier"],
        ], artifact_id="handles"))
        self.assertEqual(len(compiled.generated_temporal_handles), len(set(compiled.generated_temporal_handles)))

    def test_temporal_handles_are_unique_per_instance(self):
        compiled = self.compile(mechanism([VALID_OPERATORS["attractor_modifier"]], artifact_id="instances", max_instances=2))
        self.assertEqual(len(compiled.generated_temporal_handles), 2)
        self.assertTrue(any(".instance.0." in item for item in compiled.generated_temporal_handles))
        self.assertTrue(any(".instance.1." in item for item in compiled.generated_temporal_handles))

    def test_batch_compiler_uses_joint_slot_allocation(self):
        rows = [
            mechanism([VALID_OPERATORS["attractor_modifier"]], artifact_id="artifact_one"),
            mechanism([VALID_OPERATORS["attractor_modifier"]], artifact_id="artifact_two"),
        ]
        compiled = compile_mechanisms(rows, catalog())
        self.assertNotEqual(compiled[0].slot_allocations[0].slot_id, compiled[1].slot_allocations[0].slot_id)

    def test_created_relation_ids_are_artifact_namespaced(self):
        from experiments.generative_mechanics.next_tracks_v06.tests.helpers import operator
        create = operator("relation_modifier", "power_link_create", "power_link_template", {"action":"create"}, {"mode":"timed","steps":2}, "create_link")
        electric = catalog("electric_network")
        first, second = compile_mechanisms([
            mechanism([create], artifact_id="grid_one", anchor="bus_voltage"),
            mechanism([create], artifact_id="grid_two", anchor="bus_voltage"),
        ], electric)
        def created_id(compiled):
            return next(effect["value"]["id"] for law in compiled.law_bundle for effect in law["effects"] if effect["op"] == "create_relation")
        self.assertNotEqual(created_id(first), created_id(second))

    def test_instant_operator_has_no_handle(self):
        self.assertEqual(self.compile(mechanism()).generated_temporal_handles, ())

    def test_expiry_law_clears_own_slot(self):
        compiled = self.compile(mechanism([VALID_OPERATORS["attractor_modifier"]], artifact_id="expiry"))
        expiry = next(item for item in compiled.law_bundle if item["id"].endswith(".expire"))
        self.assertEqual(expiry["effects"][0]["value"]["weight"], 0.0)

    def test_impulse_does_not_write_dynamics_parameters(self):
        compiled = self.compile(mechanism())
        targets = [effect["target"] for effect in compiled.law_bundle[0]["effects"]]
        self.assertEqual(targets, ["$target.gm_v06_dynamics.value"])

    def test_attractor_does_not_write_current_value(self):
        compiled = self.compile(mechanism([VALID_OPERATORS["attractor_modifier"]]))
        targets = [effect.get("target", "") for law in compiled.law_bundle for effect in law["effects"]]
        self.assertNotIn("$target.gm_v06_dynamics.value", targets)

    def test_process_start_writes_real_state(self):
        compiled = self.compile(mechanism([VALID_OPERATORS["process_start"]], anchor="coolant_pump"))
        self.assertTrue(any(effect.get("target") == "$target.process.state" for law in compiled.law_bundle for effect in law["effects"]))

    def test_relation_modify_writes_parameter_slot(self):
        compiled = self.compile(mechanism([VALID_OPERATORS["relation_modifier"]], anchor="thermal_link"))
        self.assertTrue(any("modifier_slots" in effect.get("target", "") for law in compiled.law_bundle for effect in law["effects"]))

    def test_stock_transfer_has_paired_deltas(self):
        raw = deepcopy(VALID_OPERATORS["drive"])
        raw["target"] = {"object": "reserve_coolant"}
        raw["parameters"] = {"mode": "stock_transfer", "rate": 0.1, "destination": "waste_coolant"}
        compiled = self.compile(mechanism([raw], anchor="reserve_coolant", artifact_id="transfer"))
        world_step = next(item for item in compiled.law_bundle if item["id"].endswith(".world_step"))
        self.assertEqual([item["op"] for item in world_step["effects"]], ["delta", "delta"])

    def test_compilation_is_pure(self):
        raw = mechanism([VALID_OPERATORS["drive"]])
        original = deepcopy(raw)
        self.compile(raw)
        self.assertEqual(raw, original)


if __name__ == "__main__":
    unittest.main()
