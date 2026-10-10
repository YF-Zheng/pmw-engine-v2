from __future__ import annotations

from copy import deepcopy
import math
import unittest

from experiments.generative_mechanics.next_tracks_v06.canonical import canonical_json
from experiments.generative_mechanics.next_tracks_v06.validator import MechanismValidationError, validate_catalog, validate_mechanism, validate_mechanism_batch
from experiments.generative_mechanics.next_tracks_v06.tests.helpers import VALID_OPERATORS, catalog, mechanism, raw_catalog


class CatalogValidationTests(unittest.TestCase):
    def test_all_catalogs_load(self):
        for name in ("thermal_fluid", "electric_network", "mechanical_structural"):
            self.assertTrue(catalog(name).objects)

    def test_all_six_object_kinds_exist(self):
        kinds = {item.kind for item in catalog().objects}
        self.assertEqual(kinds, {"field", "stock", "process", "relation", "discrete", "derived"})

    def test_catalog_canonical_roundtrip(self):
        raw = raw_catalog()
        self.assertEqual(canonical_json(raw), canonical_json(deepcopy(raw)))


def _catalog_mutation_test(name, mutate, code):
    def test(self):
        raw = raw_catalog()
        mutate(raw)
        with self.assertRaises(MechanismValidationError) as caught:
            validate_catalog(raw)
        self.assertEqual(caught.exception.issues[0].code, code)
    test.__name__ = name
    return test


CATALOG_CASES = {
    "unknown_top": (lambda x: x.update(extra=True), "UNKNOWN_FIELD"),
    "bad_protocol": (lambda x: x.update(protocol="bad"), "SCHEMA_TYPE"),
    "bool_limit": (lambda x: x["limits"].update(max_operators=True), "SCHEMA_TYPE"),
    "zero_limit": (lambda x: x["limits"].update(max_instances=0), "OUT_OF_RANGE"),
    "duplicate_object": (lambda x: x["objects"].append(deepcopy(x["objects"][0])), "DUPLICATE_ID"),
    "duplicate_capability": (lambda x: x["capabilities"].append(deepcopy(x["capabilities"][0])), "DUPLICATE_ID"),
    "duplicate_slot": (lambda x: x["effect_slots"].append(deepcopy(x["effect_slots"][0])), "DUPLICATE_ID"),
    "unknown_cap_target": (lambda x: x["capabilities"][0].update(targets=["missing"]), "UNKNOWN_OBJECT"),
    "unknown_slot_target": (lambda x: x["effect_slots"][0].update(target="missing"), "UNKNOWN_OBJECT"),
    "bad_field_domain": (lambda x: x["objects"][0].update(domain={"min": 1.0, "max": 0.0}), "OUT_OF_RANGE"),
    "derived_writable": (lambda x: x["objects"][-1].update(writable=True), "DERIVED_READ_ONLY"),
    "bad_relation_endpoint": (lambda x: x["objects"][4].update(source_objects=["missing"]), "UNKNOWN_OBJECT"),
    "unknown_object_field": (lambda x: x["objects"][0].update(secret=True), "UNKNOWN_FIELD"),
    "unknown_state_ref_field": (lambda x: x["objects"][0]["state_ref"].update(secret=True), "UNKNOWN_FIELD"),
    "nonfinite_initial": (lambda x: x["objects"][0].update(initial=math.inf), "NON_FINITE"),
}
for _name, (_mutate, _code) in CATALOG_CASES.items():
    setattr(CatalogValidationTests, f"test_reject_{_name}", _catalog_mutation_test(_name, _mutate, _code))


class MechanismValidationTests(unittest.TestCase):
    def assert_code(self, raw, code):
        with self.assertRaises(MechanismValidationError) as caught:
            validate_mechanism(raw, catalog())
        self.assertEqual(caught.exception.issues[0].code, code)

    def test_seven_valid_operator_variants(self):
        for kind, item in VALID_OPERATORS.items():
            with self.subTest(kind=kind):
                ir = validate_mechanism(mechanism([item]), catalog())
                self.assertEqual(ir.operators[0].kind, kind)

    def test_key_order_does_not_change_ir_hash(self):
        raw = mechanism()
        reversed_raw = dict(reversed(list(raw.items())))
        self.assertEqual(validate_mechanism(raw, catalog()).canonical_spec_sha256, validate_mechanism(reversed_raw, catalog()).canonical_spec_sha256)

    def test_slot_allocation_is_stable(self):
        first = deepcopy(VALID_OPERATORS["attractor_modifier"])
        second = deepcopy(first); second["id"] = "operator_02"
        ir = validate_mechanism(mechanism([second, first]), catalog())
        self.assertEqual([item.slot_id for item in ir.reservations], ["temp_attractor_0", "temp_attractor_1"])

    def test_max_instances_get_distinct_slots(self):
        ir = validate_mechanism(mechanism([VALID_OPERATORS["attractor_modifier"]], max_instances=2), catalog())
        self.assertEqual(len({item.slot_id for item in ir.reservations}), 2)

    def test_batch_allocates_distinct_slots_across_artifacts(self):
        one = mechanism([VALID_OPERATORS["attractor_modifier"]], artifact_id="artifact_one")
        two = mechanism([VALID_OPERATORS["attractor_modifier"]], artifact_id="artifact_two")
        batch = validate_mechanism_batch([two, one], catalog())
        self.assertEqual({item.artifact_id for item in batch}, {"artifact_one", "artifact_two"})
        self.assertEqual(len({item.reservations[0].slot_id for item in batch}), 2)

    def test_batch_slot_exhaustion_is_explicit(self):
        rows = [mechanism([VALID_OPERATORS["attractor_modifier"]], artifact_id=f"artifact_{index}") for index in range(3)]
        with self.assertRaises(MechanismValidationError) as caught:
            validate_mechanism_batch(rows, catalog())
        self.assertEqual(caught.exception.issues[0].code, "SLOT_EXHAUSTED")

    def test_batch_duplicate_artifact_rejected(self):
        raw = mechanism([VALID_OPERATORS["attractor_modifier"]], artifact_id="same_artifact")
        with self.assertRaises(MechanismValidationError) as caught:
            validate_mechanism_batch([raw, deepcopy(raw)], catalog())
        self.assertEqual(caught.exception.issues[0].code, "DUPLICATE_ID")

    def test_multiple_stock_flow_writers_rejected(self):
        first = deepcopy(VALID_OPERATORS["drive"])
        first.update(id="flow_one", target={"object":"reserve_coolant"}, parameters={"mode":"stock_sink","rate":0.1})
        second = deepcopy(first); second["id"] = "flow_two"
        with self.assertRaises(MechanismValidationError) as caught:
            validate_mechanism(mechanism([first, second], anchor="reserve_coolant"), catalog())
        self.assertEqual(caught.exception.issues[0].code, "OPERATOR_CONFLICT")

    def test_stock_flow_rejects_multiple_instances(self):
        flow = deepcopy(VALID_OPERATORS["drive"])
        flow.update(target={"object":"reserve_coolant"}, parameters={"mode":"stock_sink","rate":0.1})
        with self.assertRaises(MechanismValidationError) as caught:
            validate_mechanism(mechanism([flow], anchor="reserve_coolant", max_instances=2), catalog())
        self.assertEqual(caught.exception.issues[0].code, "OPERATOR_CONFLICT")

    def test_negative_field_drive_is_valid(self):
        drive = deepcopy(VALID_OPERATORS["drive"]); drive["parameters"]["rate"] = -0.05
        ir = validate_mechanism(mechanism([drive]), catalog())
        self.assertEqual(ir.operators[0].parameters["rate"], -0.05)

    def test_world_process_requires_privilege(self):
        raw_catalog_value = raw_catalog()
        cap = next(item for item in raw_catalog_value["capabilities"] if item["id"] == "pump_start")
        cap["privileges"].remove("modify_world_owned_process")
        restricted = validate_catalog(raw_catalog_value)
        with self.assertRaises(MechanismValidationError) as caught:
            validate_mechanism(mechanism([VALID_OPERATORS["process_start"]], anchor="coolant_pump"), restricted)
        self.assertEqual(caught.exception.issues[0].code, "OWNERSHIP_DENIED")

    def test_relation_action_must_be_granted(self):
        raw_catalog_value = raw_catalog()
        cap = next(item for item in raw_catalog_value["capabilities"] if item["id"] == "link_modify")
        cap["actions"] = ["create"]
        restricted = validate_catalog(raw_catalog_value)
        with self.assertRaises(MechanismValidationError) as caught:
            validate_mechanism(mechanism([VALID_OPERATORS["relation_modifier"]], anchor="thermal_link"), restricted)
        self.assertEqual(caught.exception.issues[0].code, "CAPABILITY_TARGET_DENIED")

    def test_duplicate_impulse_target_rejected(self):
        first = deepcopy(VALID_OPERATORS["impulse"])
        second = deepcopy(first); second["id"] = "second_impulse"
        with self.assertRaises(MechanismValidationError) as caught:
            validate_mechanism(mechanism([first, second]), catalog())
        self.assertEqual(caught.exception.issues[0].code, "OPERATOR_CONFLICT")

    def test_catalog_rejects_slot_storage_alias(self):
        raw = raw_catalog()
        raw["effect_slots"][1]["storage_ref"] = deepcopy(raw["effect_slots"][0]["storage_ref"])
        with self.assertRaises(MechanismValidationError) as caught:
            validate_catalog(raw)
        self.assertEqual(caught.exception.issues[0].code, "SLOT_OWNER_CONFLICT")

    def test_catalog_rejects_slot_runtime_object_mismatch(self):
        raw = raw_catalog(); raw["effect_slots"][0]["storage_ref"]["object_id"] = "other"
        with self.assertRaises(MechanismValidationError) as caught:
            validate_catalog(raw)
        self.assertEqual(caught.exception.issues[0].code, "SLOT_OWNER_CONFLICT")

    def test_catalog_rejects_field_slot_kind_mismatch(self):
        raw = raw_catalog(); raw["effect_slots"][0]["slot_kind"] = "drive"
        with self.assertRaises(MechanismValidationError) as caught:
            validate_catalog(raw)
        self.assertEqual(caught.exception.issues[0].code, "SLOT_OWNER_CONFLICT")

    def test_catalog_rejects_generated_flow_on_process_stock(self):
        raw = raw_catalog()
        drive = next(item for item in raw["capabilities"] if item["id"] == "temperature_drive")
        drive["targets"].append("coolant_stock")
        with self.assertRaises(MechanismValidationError) as caught:
            validate_catalog(raw)
        self.assertEqual(caught.exception.issues[0].code, "CONSERVATION_REQUIRED")

    def test_derived_is_read_only(self):
        raw = mechanism(); raw["operators"][0]["target"]["object"] = "reactor_operational"
        self.assert_code(raw, "DERIVED_READ_ONLY")


def _mechanism_mutation_test(name, mutate, code):
    def test(self):
        raw = mechanism()
        mutate(raw)
        self.assert_code(raw, code)
    test.__name__ = name
    return test


MECHANISM_CASES = {
    "unknown_top": (lambda x: x.update(extra=True), "UNKNOWN_FIELD"),
    "bad_protocol": (lambda x: x.update(protocol="bad"), "SCHEMA_TYPE"),
    "reserved_id": (lambda x: x.update(id="pmw_attack"), "RESERVED_NAMESPACE"),
    "empty_name": (lambda x: x.update(name=""), "SCHEMA_TYPE"),
    "unknown_anchor": (lambda x: x["scope"].update(anchor="missing"), "UNKNOWN_OBJECT"),
    "bad_scope": (lambda x: x["scope"].update(kind="global"), "SCHEMA_TYPE"),
    "bad_policy": (lambda x: x["artifact_policy"].update(owner="model"), "OWNERSHIP_DENIED"),
    "unknown_capability": (lambda x: x.update(capability_ids=["missing"]), "UNKNOWN_CAPABILITY"),
    "bool_instances": (lambda x: x.update(max_instances=True), "SCHEMA_TYPE"),
    "too_many_instances": (lambda x: x.update(max_instances=3), "OUT_OF_RANGE"),
    "empty_operators": (lambda x: x.update(operators=[]), "SCHEMA_TYPE"),
    "unknown_operator": (lambda x: x["operators"][0].update(kind="python"), "UNKNOWN_OPERATOR"),
    "duplicate_operator": (lambda x: x["operators"].append(deepcopy(x["operators"][0])), "DUPLICATE_ID"),
    "unknown_target": (lambda x: x["operators"][0]["target"].update(object="missing"), "UNKNOWN_OBJECT"),
    "cap_not_declared": (lambda x: x.update(capability_ids=[]), "UNKNOWN_CAPABILITY"),
    "cap_kind_mismatch": (lambda x: x["operators"][0].update(capability_id="temperature_drive"), "UNKNOWN_CAPABILITY"),
    "timed_impulse": (lambda x: x["operators"][0].update(lifecycle={"mode":"timed","steps":2}), "CAPABILITY_LIFETIME_DENIED"),
    "permanent_denied": (lambda x: x["operators"][0].update(lifecycle={"mode":"permanent"}), "CAPABILITY_LIFETIME_DENIED"),
    "duration_zero": (lambda x: (x["operators"][0].update(deepcopy(VALID_OPERATORS["drive"])), x.update(capability_ids=["temperature_drive"]), x["operators"][0].update(lifecycle={"mode":"timed","steps":0})), "OUT_OF_RANGE"),
    "duration_bool": (lambda x: (x["operators"][0].update(deepcopy(VALID_OPERATORS["drive"])), x.update(capability_ids=["temperature_drive"]), x["operators"][0].update(lifecycle={"mode":"timed","steps":True})), "SCHEMA_TYPE"),
    "nan_delta": (lambda x: x["operators"][0]["parameters"].update(delta=math.nan), "NON_FINITE"),
    "inf_delta": (lambda x: x["operators"][0]["parameters"].update(delta=math.inf), "NON_FINITE"),
    "bool_delta": (lambda x: x["operators"][0]["parameters"].update(delta=True), "SCHEMA_TYPE"),
    "excess_delta": (lambda x: x["operators"][0]["parameters"].update(delta=-2.0), "OUT_OF_RANGE"),
    "unknown_parameter": (lambda x: x["operators"][0]["parameters"].update(secret=1), "UNKNOWN_FIELD"),
    "unknown_lifecycle_field": (lambda x: x["operators"][0]["lifecycle"].update(secret=1), "UNKNOWN_FIELD"),
}
for _name, (_mutate, _code) in MECHANISM_CASES.items():
    setattr(MechanismValidationTests, f"test_reject_{_name}", _mechanism_mutation_test(_name, _mutate, _code))


if __name__ == "__main__":
    unittest.main()
