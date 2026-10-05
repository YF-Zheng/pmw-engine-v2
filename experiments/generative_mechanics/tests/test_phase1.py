from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from pmw import Engine, Entity, Event, load_laws, load_world, parse_law

from experiments.generative_mechanics.compiler import canonical_json, compile_skill
from experiments.generative_mechanics.execution import ExperimentExecutionError, activation_event, validate_activation_payload
from experiments.generative_mechanics.smoke import ROOT, default_smoke, run_cross_environment
from experiments.generative_mechanics.spec import SkillSpecError, load_skill, validate_skill
from experiments.generative_mechanics.substrate import CHANNELS


def valid_raw() -> dict:
    return {
        "id": "test_skill", "name": "Test Skill", "target_scope": "zone",
        "effects": [{"field": "electric_field", "delta": 0.5}],
        "duration": 0.0, "periodic": None, "trigger_conditions": [],
        "resource_cost": 10.0, "charges": 2, "slot_cost": 1,
    }


class ValidatorTests(unittest.TestCase):
    def test_valid_minimal(self):
        self.assertEqual(validate_skill(valid_raw()).id, "test_skill")

    def test_load_skill(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "skill.json"
            path.write_text(json.dumps(valid_raw()), encoding="utf-8")
            self.assertEqual(load_skill(path).name, "Test Skill")

    def test_all_seed_skills_validate(self):
        paths = [p for p in (ROOT / "skills").glob("*.json") if p.name != "manifest.json"]
        self.assertEqual(len(paths), 36)
        self.assertEqual(len({load_skill(path).id for path in paths}), 36)

    def test_all_channels_can_be_perturbed(self):
        seen = {effect.field for path in (ROOT / "skills").glob("*.json") if path.name != "manifest.json" for effect in load_skill(path).effects}
        self.assertEqual(seen, set(CHANNELS))

    def test_manifest_covers_nine_categories(self):
        raw = json.loads((ROOT / "skills" / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual({item["category"] for item in raw["skills"]}, {"Starter", "Setup", "Payoff", "Converter", "Amplifier", "Control", "Utility", "Engine", "Consumable"})


INVALID_CASES = {
    "unknown_top_level": lambda x: x.update({"damage": 99}),
    "missing_top_level": lambda x: x.pop("duration"),
    "bad_id_upper": lambda x: x.update(id="Bad"),
    "reserved_gm_namespace": lambda x: x.update(id="gm_injected"),
    "reserved_pmw_namespace": lambda x: x.update(id="pmw_injected"),
    "empty_name": lambda x: x.update(name=" "),
    "entity_target": lambda x: x.update(target_scope="entity"),
    "empty_effects": lambda x: x.update(effects=[]),
    "effect_outcome_injection": lambda x: x.update(effects=[{"field": "electric_field", "delta": .2, "outcome": "win"}]),
    "effect_pmw_injection": lambda x: x.update(effects=[{"op": "delete_entity", "field": "wetness", "delta": .2}]),
    "hidden_effect": lambda x: x.update(effects=[{"field": "secret", "delta": .2}]),
    "infinite_delta": lambda x: x.update(effects=[{"field": "wetness", "delta": float("inf")}]),
    "large_delta": lambda x: x.update(effects=[{"field": "wetness", "delta": 1.01}]),
    "duplicate_effect": lambda x: x.update(effects=[{"field": "wetness", "delta": .1}, {"field": "wetness", "delta": .2}]),
    "unbounded_duration": lambda x: x.update(duration=301),
    "negative_duration": lambda x: x.update(duration=-1),
    "zero_period": lambda x: x.update(periodic={"interval": 0, "repeats": 2}),
    "unbounded_repeats": lambda x: x.update(periodic={"interval": 1, "repeats": 13}),
    "duration_with_periodic": lambda x: x.update(duration=5, periodic={"interval": 1, "repeats": 2}),
    "hidden_read": lambda x: x.update(trigger_conditions=[{"field": "secret", "op": "eq", "value": 1}]),
    "bad_comparator": lambda x: x.update(trigger_conditions=[{"field": "wetness", "op": "exec", "value": 1}]),
    "negative_cost": lambda x: x.update(resource_cost=-1),
    "zero_charges": lambda x: x.update(charges=0),
    "bad_slot_cost": lambda x: x.update(slot_cost=3),
}


def _invalid_test(mutator):
    def test(self):
        raw = valid_raw()
        mutator(raw)
        with self.assertRaises(SkillSpecError):
            validate_skill(raw)
    return test


for _name, _mutator in INVALID_CASES.items():
    setattr(ValidatorTests, f"test_reject_{_name}", _invalid_test(_mutator))


class CompilerTests(unittest.TestCase):
    def test_canonical_output_is_byte_stable(self):
        spec = validate_skill(valid_raw())
        self.assertEqual(canonical_json(compile_skill(spec)), canonical_json(compile_skill(spec)))

    def test_compiled_laws_pass_parse_law(self):
        for raw in compile_skill(validate_skill(valid_raw()))["laws"]:
            parse_law(raw)

    def test_compiled_document_passes_load_laws(self):
        document = compile_skill(validate_skill(valid_raw()))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "compiled.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            self.assertEqual(len(load_laws(path)), 1)

    def test_namespace_and_activation_event(self):
        laws = compile_skill(validate_skill(valid_raw()))["laws"]
        self.assertTrue(all(law["id"].startswith("gm.skill.test_skill.") for law in laws))
        self.assertEqual(laws[0]["when"]["all"][0], {"event.type": {"eq": "lab.skill.activate"}})

    def test_immediate_targets_are_bounded(self):
        effects = compile_skill(validate_skill(valid_raw()))["laws"][0]["effects"]
        targets = {effect.get("target") for effect in effects if "target" in effect}
        self.assertEqual(targets, {"$zone.fields.electric_field", "$actor.resource.energy", "$skill.skill.charges"})

    def test_duration_has_inverse_expiry(self):
        raw = valid_raw(); raw["duration"] = 5
        laws = compile_skill(validate_skill(raw))["laws"]
        self.assertEqual(len(laws), 2)
        self.assertEqual(laws[1]["effects"], [{"op": "delta", "target": "$zone.fields.electric_field", "value": -0.5}])
        self.assertEqual(laws[0]["effects"][-1]["event"]["id"], "$event.payload.expiry_event_id")

    def test_periodic_is_finite_and_handles_stable(self):
        raw = valid_raw(); raw["periodic"] = {"interval": 2, "repeats": 3}
        laws = compile_skill(validate_skill(raw))["laws"]
        self.assertEqual(len(laws), 4)
        handles = [item["event"]["id"] for item in laws[0]["effects"] if item["op"] == "schedule_event"]
        self.assertEqual(handles, ["$event.payload.pulse_01_event_id", "$event.payload.pulse_02_event_id", "$event.payload.pulse_03_event_id"])

    def test_resource_and_charges_are_consumed(self):
        spec = validate_skill(valid_raw())
        world = load_world(ROOT / "environments" / "mine.json")
        world.entities["skill:equipped"].components["skill"].update(spec_id=spec.id, charges=spec.charges)
        zone = world.entities["zone:mine"]
        engine = Engine([parse_law(raw) for raw in compile_skill(spec)["laws"]])
        engine.run_event(world, activation_event(spec, activation_id="activate", skill_instance_id="skill:equipped", actor_id="actor:researcher", zone_id="zone:mine", time=0))
        self.assertEqual(world.entities["actor:researcher"].components["resource"]["energy"], 90)
        self.assertEqual(world.entities["skill:equipped"].components["skill"]["charges"], 1)
        self.assertAlmostEqual(world.entities["zone:mine"].components["fields"]["electric_field"], .55)

    def test_trigger_condition_blocks_activation(self):
        raw = valid_raw(); raw["trigger_conditions"] = [{"field": "wetness", "op": "gt", "value": .8}]
        spec = validate_skill(raw)
        world = load_world(ROOT / "environments" / "mine.json")
        world.entities["skill:equipped"].components["skill"].update(spec_id=spec.id, charges=spec.charges)
        Engine([parse_law(item) for item in compile_skill(spec)["laws"]]).run_event(world, activation_event(spec, activation_id="a", skill_instance_id="skill:equipped", actor_id="actor:researcher", zone_id="zone:mine", time=0))
        self.assertEqual(world.entities["actor:researcher"].components["resource"]["energy"], 100)

    def test_duration_executes_and_restores_field(self):
        raw = valid_raw(); raw["duration"] = 5
        spec = validate_skill(raw)
        world = load_world(ROOT / "environments" / "mine.json")
        world.entities["skill:equipped"].components["skill"].update(spec_id=spec.id, charges=spec.charges)
        runtime = Engine([parse_law(item) for item in compile_skill(spec)["laws"]]).attach(world)
        runtime.run_event(activation_event(spec, activation_id="a", skill_instance_id="skill:equipped", actor_id="actor:researcher", zone_id="zone:mine", time=0))
        self.assertAlmostEqual(runtime.state.entities["zone:mine"].components["fields"]["electric_field"], .55)
        self.assertEqual([event.id for event in runtime.state.scheduled_events], ["gm.handle.a.expiry_event_id"])
        runtime.advance_to(5)
        self.assertAlmostEqual(runtime.state.entities["zone:mine"].components["fields"]["electric_field"], .05)

    def test_periodic_executes_exact_finite_pulse_count(self):
        raw = valid_raw(); raw["periodic"] = {"interval": 2, "repeats": 3}
        spec = validate_skill(raw)
        world = load_world(ROOT / "environments" / "mine.json")
        world.entities["skill:equipped"].components["skill"].update(spec_id=spec.id, charges=spec.charges)
        runtime = Engine([parse_law(item) for item in compile_skill(spec)["laws"]]).attach(world)
        runtime.run_event(activation_event(spec, activation_id="a", skill_instance_id="skill:equipped", actor_id="actor:researcher", zone_id="zone:mine", time=0))
        self.assertEqual(len(runtime.state.scheduled_events), 3)
        runtime.advance_to(6)
        self.assertEqual(runtime.state.scheduled_events, [])
        self.assertAlmostEqual(runtime.state.entities["zone:mine"].components["fields"]["electric_field"], 2.05)

    def test_activation_routes_only_selected_compiled_skill(self):
        first = validate_skill(valid_raw())
        second_raw = valid_raw(); second_raw.update(id="second_skill", effects=[{"field": "wetness", "delta": .4}])
        second = validate_skill(second_raw)
        world = load_world(ROOT / "environments" / "mine.json")
        world.entities.pop("skill:equipped")
        world.entities["skill:first"] = Entity("skill:first", components={"skill": {"spec_id": first.id, "owner": "actor:researcher", "charges": 2}})
        world.entities["skill:second"] = Entity("skill:second", components={"skill": {"spec_id": second.id, "owner": "actor:researcher", "charges": 2}})
        laws = [parse_law(item) for spec in (first, second) for item in compile_skill(spec)["laws"]]
        Engine(laws).run_event(world, activation_event(first, activation_id="only-first", skill_instance_id="skill:first", actor_id="actor:researcher", zone_id="zone:mine", time=0))
        fields = world.entities["zone:mine"].components["fields"]
        self.assertAlmostEqual(fields["electric_field"], .55)
        self.assertAlmostEqual(fields["wetness"], .20)
        self.assertEqual(world.entities["skill:first"].components["skill"]["charges"], 1)
        self.assertEqual(world.entities["skill:second"].components["skill"]["charges"], 2)

    def test_overlapping_duration_casts_use_distinct_explicit_handles(self):
        raw = valid_raw(); raw["duration"] = 5
        spec = validate_skill(raw)
        world = load_world(ROOT / "environments" / "mine.json")
        world.entities["skill:equipped"].components["skill"].update(spec_id=spec.id, charges=spec.charges)
        runtime = Engine([parse_law(item) for item in compile_skill(spec)["laws"]]).attach(world)
        for activation_id in ("cast-one", "cast-two"):
            runtime.run_event(activation_event(spec, activation_id=activation_id, skill_instance_id="skill:equipped", actor_id="actor:researcher", zone_id="zone:mine", time=0))
        self.assertEqual({event.id for event in runtime.state.scheduled_events}, {"gm.handle.cast-one.expiry_event_id", "gm.handle.cast-two.expiry_event_id"})
        self.assertAlmostEqual(runtime.state.entities["zone:mine"].components["fields"]["electric_field"], 1.05)
        runtime.advance_to(5)
        self.assertAlmostEqual(runtime.state.entities["zone:mine"].components["fields"]["electric_field"], .05)

    def test_missing_handle_payload_is_clear_experiment_error(self):
        raw = valid_raw(); raw["duration"] = 5
        with self.assertRaisesRegex(ExperimentExecutionError, "expiry_event_id"):
            validate_activation_payload(validate_skill(raw), {"skill_id": "test_skill", "skill_instance_id": "skill:x"})

    def test_overlapping_periodic_casts_use_distinct_handle_sets(self):
        raw = valid_raw(); raw["periodic"] = {"interval": 2, "repeats": 2}
        spec = validate_skill(raw)
        world = load_world(ROOT / "environments" / "mine.json")
        world.entities["skill:equipped"].components["skill"].update(spec_id=spec.id, charges=spec.charges)
        runtime = Engine([parse_law(item) for item in compile_skill(spec)["laws"]]).attach(world)
        for activation_id in ("pulse-one", "pulse-two"):
            runtime.run_event(activation_event(spec, activation_id=activation_id, skill_instance_id="skill:equipped", actor_id="actor:researcher", zone_id="zone:mine", time=0))
        self.assertEqual(len({event.id for event in runtime.state.scheduled_events}), 4)
        runtime.advance_to(4)
        self.assertEqual(runtime.state.scheduled_events, [])
        self.assertAlmostEqual(runtime.state.entities["zone:mine"].components["fields"]["electric_field"], 3.05)


class SubstrateTests(unittest.TestCase):
    def test_exactly_eight_frozen_channels(self):
        self.assertEqual(len(CHANNELS), 8)

    def test_four_worlds_load(self):
        worlds = [load_world(path) for path in sorted((ROOT / "environments").glob("*.json"))]
        self.assertEqual(len(worlds), 4)
        self.assertTrue(all(len(world.entities) == 3 for world in worlds))

    def test_worlds_share_component_contract(self):
        for path in (ROOT / "environments").glob("*.json"):
            world = load_world(path); zone = next(item for item in world.entities.values() if "zone" in item.components)
            self.assertEqual(set(zone.components["fields"]), set(CHANNELS))
            self.assertIn("resource", world.entities["actor:researcher"].components)
            self.assertIn("skill", world.entities["skill:equipped"].components)

    def test_24_generic_laws_load(self):
        laws = load_laws(ROOT / "substrate" / "world_laws.json")
        self.assertEqual(len(laws), 24)
        self.assertTrue(all(law.law_id.startswith("gm.world.") for law in laws))

    def test_world_laws_are_skill_independent(self):
        text = (ROOT / "substrate" / "world_laws.json").read_text(encoding="utf-8")
        self.assertNotIn("gm.skill.", text)
        self.assertNotIn("lab.skill.activate", text)

    def test_non_idempotent_world_processes_are_step_driven(self):
        laws = load_laws(ROOT / "substrate" / "world_laws.json")
        self.assertTrue(all(law.mode == "event" and "lab.step" in json.dumps(law.when) for law in laws))

    def test_wet_electric_discharge(self):
        world = load_world(ROOT / "environments" / "wetland.json")
        world.entities["zone:wetland"].components["fields"]["electric_field"] = .8
        Engine(load_laws(ROOT / "substrate" / "world_laws.json")).run_event(world, Event("step", "lab.step"))
        self.assertEqual(world.entities["zone:wetland"].components["outcome"]["discharges"], 1)

    def test_electric_iron_charges_ore(self):
        world = load_world(ROOT / "environments" / "mine.json")
        world.entities["zone:mine"].components["fields"]["electric_field"] = .8
        Engine(load_laws(ROOT / "substrate" / "world_laws.json")).run_event(world, Event("step", "lab.step"))
        self.assertGreater(world.entities["zone:mine"].components["outcome"]["charged_ore"], 0)

    def test_same_skill_has_different_environmental_consequences(self):
        result = default_smoke()["environments"]
        signatures = {(data["outcome"]["discharges"], data["outcome"]["charged_ore"], data["process"]["alert"]) for data in result.values()}
        self.assertGreaterEqual(len(signatures), 3)

    def test_smoke_is_deterministic(self):
        self.assertEqual(canonical_json(default_smoke()), canonical_json(default_smoke()))


if __name__ == "__main__":
    unittest.main()
