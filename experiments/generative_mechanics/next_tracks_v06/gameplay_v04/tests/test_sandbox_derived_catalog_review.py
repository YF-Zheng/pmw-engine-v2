from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import hashlib
import json
import math
from pathlib import Path
import tempfile
import unittest

from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.actions import (
    ActionRegistry,
    ActionRequest,
    submit_timed_primary_action,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.basics import (
    basic_registry,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.checkpoint import (
    load_registry_checkpoint,
    save_registry_checkpoint,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.conditions import (
    evaluate_condition,
    parse_condition,
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
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.derived import (
    DERIVED_COMPONENT,
    compute_derived_value,
    parse_derived_spec,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.legal_actions import (
    LegalActionGenerator,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.loadout import (
    change_loadout,
    skill_ref,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.observation import (
    ActorObservation,
    ActorObservationBuilder,
    ObservationDisclosure,
    canonical_json,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.registry import (
    MechanismRegistryRuntime,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.runtime import (
    advance_world_tick,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.simulation import (
    SandboxSimulator,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.tests.test_p1_scenarios import (
    AREA,
    MATERIAL_ID,
    NPC,
    OTHER_AREA,
    PLAYER,
    _actor_state,
    _budget,
    _field,
    _field_state,
    _skill,
    _skill_raw,
    _world,
)


PROJECT_ROOT = Path(__file__).resolve().parents[5]
TEST_TMP = PROJECT_ROOT / "docs" / "agent_bootstrap" / "evidence" / "test_tmp"
# Captured from the unchanged no-Derived fixture before the observation fix.
LEGACY_OBSERVATION_SHA256 = (
    "766cf7daed2e0346b066081ef14630b99c26da1bf064524d9e604f893a36f722"
)
LEGACY_OBSERVATION_REVISION = (
    "d20da7f1a84f076eaab75b66a0c8571a83851fb68d2808f3169b224dd19b1bd6"
)


def _weighted(
    derived_id: str = "comfort_index",
    *,
    terms=(("humidity", 3.5), ("temperature", -2.25)),
    bias: float = 0.75,
    minimum: float = -0.5,
    maximum: float = 1.25,
):
    return parse_derived_spec({
        "id": derived_id,
        "kind": "weighted_sum",
        "terms": [list(item) for item in terms],
        "bias": bias,
        "minimum": minimum,
        "maximum": maximum,
    })


def _threshold(
    derived_id: str,
    comparator: str,
    *,
    field_id: str = "humidity",
    value: float = 0.5,
):
    return parse_derived_spec({
        "id": derived_id,
        "kind": "threshold",
        "field_id": field_id,
        "comparator": comparator,
        "value": value,
    })


def _modify_skill(
    skill_id: str,
    *,
    amount: float = 0.2,
    condition=None,
    duration: int = 1,
    mana: float = 4.0,
    budget: float = 10.0,
):
    return _skill(_skill_raw(
        skill_id,
        [{
            "id": "change_humidity",
            "kind": "modify_field",
            "target": {"kind": "current_area"},
            "commitment": "required",
            "field_id": "humidity",
            "amount": amount,
        }],
        condition=condition,
        duration=duration,
        mana=mana,
        budget=budget,
    ))


def _base_registry():
    base = basic_registry()
    return ActionRegistry(base.actions.values(), base.statuses.values())


def _equip(runtime, skills):
    for actor_id in (PLAYER, NPC):
        for slot, skill in enumerate(skills):
            change_loadout(
                runtime.session,
                runtime.manifest,
                actor_id=actor_id,
                operation=(
                    "equip_active"
                    if skill.kind == "skill_blueprint"
                    else "equip_passive"
                ),
                skill=skill_ref(skill),
                slot=slot,
            )


def _formal_runtime(world, skills=(), *, derived_by_area=None):
    content = make_content(
        _base_registry(),
        skills=tuple(skills),
        material_ids=(MATERIAL_ID,),
        derived_by_area=derived_by_area,
    )
    initialized = initialize_content_world(world, content)
    compiled = compile_content(content)
    session = build_content_session(initialized, compiled)
    runtime = MechanismRegistryRuntime.from_compiled_content(session, compiled)
    _equip(runtime, skills)
    return runtime, compiled


def _derived_values(runtime, area_id=AREA):
    return runtime.session.state.entities[area_id].components[
        DERIVED_COMPONENT
    ]["values"]


def _static_fields(*, humidity=0.2, temperature=0.4):
    return _world([
        _field(
            "humidity", initial=humidity, target=humidity, rate=0.0
        ),
        _field(
            "temperature", initial=temperature, target=temperature, rate=0.0
        ),
    ])


def _law_bytes(laws):
    return json.dumps(
        laws, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _digest(value):
    return hashlib.sha256(_law_bytes(value)).hexdigest()


def _derived_match_ids(result):
    return {
        match.law_id
        for trace_event in result.event_result.trace.events
        for match in trace_event.state_law_matches
        if match.law_id.startswith("pmw.v04.derived.")
    }


class SandboxDerivedCatalogReviewTests(unittest.TestCase):
    def test_weighted_sum_hand_arithmetic_hits_both_clamps_on_native_ticks(self):
        # Formula: raw = 0.75 + 3.5*humidity - 2.25*temperature,
        # then clamp to [-0.5, 1.25].  Both Fields advance only through the
        # native world-Tick dynamics Laws.
        #
        # Initial: 0.75 + 3.5(0.8) - 2.25(0.0) = 3.55 -> clamp MAX 1.25.
        # Tick 1:  0.75 + 3.5(0.5) - 2.25(0.35) = 1.7125 -> MAX 1.25.
        # Tick 2:  0.75 + 3.5(0.35) - 2.25(0.5775) = 0.675625.
        # Tick 6:  0.75 + 3.5(0.209375) - 2.25(0.924596875)
        #          = -0.59772... -> clamp MIN -0.5.
        spec = _weighted()
        runtime, _ = _formal_runtime(
            _world([
                _field("humidity", initial=0.8, target=0.2, rate=0.5),
                _field("temperature", initial=0.0, target=1.0, rate=0.35),
            ]),
            derived_by_area={AREA: (spec,)},
        )
        humidity = 0.8
        temperature = 0.0
        raw = 0.75 + 3.5 * humidity - 2.25 * temperature
        expected = max(-0.5, min(1.25, raw))
        self.assertEqual(expected, 1.25)
        self.assertAlmostEqual(_derived_values(runtime)["comfort_index"], expected, delta=1e-12)
        observed_bounds = {"maximum" if expected == 1.25 else "other"}
        for tick in range(6):
            result = advance_world_tick(runtime.session)
            humidity += 0.5 * (0.2 - humidity)
            temperature += 0.35 * (1.0 - temperature)
            raw = 0.75 + 3.5 * humidity - 2.25 * temperature
            expected = max(-0.5, min(1.25, raw))
            if expected == 1.25:
                observed_bounds.add("maximum")
            if expected == -0.5:
                observed_bounds.add("minimum")
            self.assertAlmostEqual(
                _derived_values(runtime)["comfort_index"],
                expected,
                delta=1e-12,
                msg=f"derived mismatch after native Tick {tick + 1}",
            )
            if tick >= 1:
                self.assertTrue(
                    any(
                        law_id.endswith(".weighted_sum")
                        for law_id in _derived_match_ids(result)
                    )
                )
        self.assertEqual(observed_bounds, {"maximum", "minimum"})

    def test_threshold_comparators_keep_exact_boundary_equality(self):
        specs = (
            _threshold("gt_case", "gt"),
            _threshold("gte_case", "gte"),
            _threshold("lt_case", "lt"),
            _threshold("lte_case", "lte"),
        )
        runtime, _ = _formal_runtime(
            _static_fields(humidity=0.5),
            derived_by_area={AREA: specs},
        )
        expected = {
            "gt_case": 0.0,
            "gte_case": 1.0,
            "lt_case": 0.0,
            "lte_case": 1.0,
        }
        self.assertEqual(_derived_values(runtime), expected)
        # Equality remains at the boundary after a real Tick.  gte/lte are
        # true at equality; gt/lt are false.
        advance_world_tick(runtime.session)
        self.assertEqual(_derived_values(runtime), expected)

    def test_same_parsed_skill_derived_gate_rejects_and_accepts_atomically(self):
        condition = {"derived": {
            "subject": "current_area",
            "key": "comfort_index",
            "comparator": "gte",
            "value": 0.5,
        }}
        gated = _modify_skill(
            "derived_gate", condition=condition, duration=3, mana=7.5, budget=12.0
        )
        opener = _modify_skill(
            "derived_opener", duration=1, mana=3.0, budget=5.0
        )
        spec = _weighted(
            terms=(("humidity", 2.0),),
            bias=0.0,
            minimum=0.0,
            maximum=2.0,
        )
        runtime, compiled = _formal_runtime(
            _static_fields(humidity=0.2),
            (gated, opener),
            derived_by_area={AREA: (spec,)},
        )
        self.assertEqual(gated.action.condition.kind, "derived")
        self.assertIn(gated.action.canonical_hash, {
            action.canonical_hash for action in compiled.content.action_registry.actions.values()
        })
        for actor_id in (PLAYER, NPC):
            before = (
                deepcopy(runtime.session.state.to_dict()),
                _actor_state(runtime, actor_id)["mana"],
                _budget(runtime)["spent_ticks"],
            )
            with self.assertRaisesRegex(
                GameplayContractError, "^action condition is not satisfied$"
            ):
                submit_timed_primary_action(
                    runtime.session,
                    runtime.action_registry,
                    ActionRequest(
                        f"derived_false_{actor_id}", actor_id, gated.id
                    ),
                )
            self.assertEqual(
                (
                    runtime.session.state.to_dict(),
                    _actor_state(runtime, actor_id)["mana"],
                    _budget(runtime)["spent_ticks"],
                ),
                before,
            )
            # The rejected Skill's own effect would have made the predicate
            # true, proving the gate uses the current pre-action staged state.
            self.assertAlmostEqual(_field_state(runtime)["value"], 0.2, delta=1e-12)

        before_mana = _actor_state(runtime, PLAYER)["mana"]
        before_spent = _budget(runtime)["spent_ticks"]
        opened = submit_timed_primary_action(
            runtime.session,
            runtime.action_registry,
            ActionRequest("derived_open", PLAYER, opener.id),
        )
        self.assertEqual(opened.action.cost.mana, 3.0)
        self.assertEqual(opened.time.duration, 1)
        self.assertAlmostEqual(_field_state(runtime)["value"], 0.4, delta=1e-12)
        self.assertAlmostEqual(_derived_values(runtime)["comfort_index"], 0.8, delta=1e-12)
        self.assertEqual(_actor_state(runtime, PLAYER)["mana"], before_mana - 3.0)
        self.assertEqual(_budget(runtime)["spent_ticks"], before_spent + 1)

        for actor_id in (PLAYER, NPC):
            before_mana = _actor_state(runtime, actor_id)["mana"]
            before_spent = _budget(runtime)["spent_ticks"]
            paid = submit_timed_primary_action(
                runtime.session,
                runtime.action_registry,
                ActionRequest(f"derived_true_{actor_id}", actor_id, gated.id),
            )
            self.assertEqual(paid.action.definition.canonical_hash, gated.action.canonical_hash)
            self.assertEqual(paid.action.cost.mana, 7.5)
            self.assertEqual(paid.time.duration, 3)
            self.assertEqual(_actor_state(runtime, actor_id)["mana"], before_mana - 7.5)
            self.assertEqual(_budget(runtime)["spent_ticks"], before_spent + 3)

    def test_top_level_condition_is_evaluated_before_mana_cost(self):
        condition = {"all": [
            {"derived": {
                "subject": "current_area",
                "key": "comfort_index",
                "comparator": "gte",
                "value": 0.5,
            }},
            {"resource": {
                "subject": "self",
                "key": "mana",
                "comparator": "gte",
                "value": 4.0,
            }},
        ]}
        skill = _modify_skill(
            "derived_pre_cost", condition=condition, duration=1, mana=4.0
        )
        world = _static_fields(humidity=0.4)
        # Fixture-only resource setup: leave exactly enough Mana for the cost.
        # If the condition were checked after the charge it would see 0 Mana.
        world.entities[PLAYER].components["pmw_gameplay_actor"]["mana"] = 4.0
        spec = _weighted(
            terms=(("humidity", 2.0),),
            bias=0.0,
            minimum=0.0,
            maximum=2.0,
        )
        runtime, _ = _formal_runtime(
            world,
            (skill,),
            derived_by_area={AREA: (spec,)},
        )
        before_spent = _budget(runtime)["spent_ticks"]
        paid = submit_timed_primary_action(
            runtime.session,
            runtime.action_registry,
            ActionRequest("derived_pre_cost_request", PLAYER, skill.id),
        )
        self.assertEqual(paid.action.cost.mana, 4.0)
        self.assertEqual(paid.time.duration, 1)
        self.assertEqual(_actor_state(runtime, PLAYER)["mana"], 0.0)
        self.assertEqual(_budget(runtime)["spent_ticks"], before_spent + 1)

    def test_condition_parser_is_strict_and_missing_key_is_false(self):
        with self.assertRaises(GameplayContractError):
            parse_condition({"unknown_condition_key": {}})
        for subject in ("self", "target_actor"):
            with self.subTest(subject=subject):
                with self.assertRaises(GameplayContractError):
                    parse_condition({"derived": {
                        "subject": subject,
                        "key": "comfort_index",
                        "comparator": "gte",
                        "value": 0.5,
                    }})
        for bad_value in (True, math.nan, math.inf, -math.inf):
            with self.subTest(value=bad_value):
                with self.assertRaises(GameplayContractError):
                    parse_condition({"derived": {
                        "subject": "current_area",
                        "key": "comfort_index",
                        "comparator": "gte",
                        "value": bad_value,
                    }})
        with self.assertRaises(GameplayContractError):
            parse_condition({"derived": {
                "subject": "current_area",
                "key": "comfort_index",
                "comparator": "gte",
                "value": 0.5,
                "extra": 1,
            }})
        with self.assertRaises(GameplayContractError):
            parse_condition({"derived": {
                "subject": "current_area",
                "key": "",
                "comparator": "gte",
                "value": 0.5,
            }})
        with self.assertRaises(GameplayContractError):
            parse_condition({"derived": {
                "subject": "current_area",
                "key": "comfort_index",
                "comparator": "approximately",
                "value": 0.5,
            }})

        missing = parse_condition({"derived": {
            "subject": "current_area",
            "key": "not_in_catalog",
            "comparator": "gte",
            "value": 0.5,
        }})
        self.assertFalse(evaluate_condition(
            missing, {"current_area": {"derived": {"comfort_index": 0.9}}}
        ))
        self.assertFalse(evaluate_condition(missing, {"current_area": {}}))

    def test_mutation_checks_for_missing_law_wrong_inverse_and_dropped_clamp(self):
        # (a) Deliberate in-test mutant: remove Derived Laws from the compiled
        # artifact.  The formal action still changes the Field, but the derived
        # component remains at its initialization value.
        skill = _modify_skill("derived_mutation_skill", duration=1, mana=1.0)
        spec = _weighted(
            terms=(("humidity", 2.0),),
            bias=0.0,
            minimum=0.0,
            maximum=2.0,
        )
        world = _static_fields(humidity=0.2)
        content = make_content(
            _base_registry(),
            skills=(skill,),
            material_ids=(MATERIAL_ID,),
            derived_by_area={AREA: (spec,)},
        )
        compiled = compile_content(content)
        without_derived = replace(
            compiled,
            laws=tuple(
                law for law in compiled.laws
                if not law["id"].startswith("pmw.v04.derived.")
            ),
        )
        initialized = initialize_content_world(world, content)
        mutant_session = build_content_session(initialized, without_derived)
        mutant = MechanismRegistryRuntime.from_compiled_content(
            mutant_session, without_derived
        )
        _equip(mutant, (skill,))
        submit_timed_primary_action(
            mutant.session,
            mutant.action_registry,
            ActionRequest("derived_mutation_request", PLAYER, skill.id),
        )
        self.assertAlmostEqual(_field_state(mutant)["value"], 0.4, delta=1e-12)
        self.assertAlmostEqual(_derived_values(mutant)["comfort_index"], 0.4, delta=1e-12)
        # The correct post-action value is 0.8; the mutant's stale 0.4 proves
        # the normal assertion would fail if the Law were omitted.
        self.assertNotAlmostEqual(0.8, _derived_values(mutant)["comfort_index"], places=12)

        # (b) Exact inverse mapping required by the two guarded threshold Laws.
        threshold_specs = (
            _threshold("gt_case", "gt"),
            _threshold("gte_case", "gte"),
            _threshold("lt_case", "lt"),
            _threshold("lte_case", "lte"),
        )
        _, threshold_compiled = _formal_runtime(
            _static_fields(humidity=0.5),
            derived_by_area={AREA: threshold_specs},
        )
        actual = {}
        for law in threshold_compiled.laws:
            if not law["id"].startswith("pmw.v04.derived."):
                continue
            if not law["id"].endswith(".threshold.false"):
                continue
            spec_id = law["id"].split(".")[-3]
            comparison = next(
                condition for condition in law["when"]["all"]
                if isinstance(condition, dict)
                and condition.get("ref", "").endswith(".humidity.value")
            )
            actual[spec_id] = next(
                key for key in (
                    "gt", "gte", "lt", "lte"
                ) if key in comparison
            )
        wrong_inverse = {
            "gt_case": "gte",
            "gte_case": "gt",
            "lt_case": "lte",
            "lte_case": "lt",
        }
        self.assertEqual(actual, {
            "gt_case": "lte",
            "gte_case": "lt",
            "lt_case": "gte",
            "lte_case": "gt",
        })
        self.assertNotEqual(actual, wrong_inverse)

        # (c) Same formula with an effectively unbounded range exposes the raw
        # totals that the bounded spec must clamp.
        tight = _weighted("tight_value", minimum=-0.5, maximum=1.25)
        loose = _weighted(
            "loose_value", minimum=-1000.0, maximum=1000.0
        )
        clamp_runtime, _ = _formal_runtime(
            _world([
                _field("humidity", initial=0.8, target=0.2, rate=0.5),
                _field("temperature", initial=0.0, target=1.0, rate=0.35),
            ]),
            derived_by_area={
                AREA: (tight,),
                OTHER_AREA: (loose,),
            },
        )
        self.assertEqual(_derived_values(clamp_runtime, AREA)["tight_value"], 1.25)
        self.assertAlmostEqual(
            _derived_values(clamp_runtime, OTHER_AREA)["loose_value"],
            3.55,
            delta=1e-12,
        )
        for _ in range(6):
            advance_world_tick(clamp_runtime.session)
        self.assertEqual(_derived_values(clamp_runtime, AREA)["tight_value"], -0.5)
        self.assertLess(
            _derived_values(clamp_runtime, OTHER_AREA)["loose_value"], -0.5
        )

        # The production helper agrees independently of the runtime path.
        self.assertEqual(
            compute_derived_value(tight, {
                "humidity": {"value": 0.209375},
                "temperature": {"value": 0.924596875},
            }),
            -0.5,
        )

    def test_checkpoint_preserves_derived_values_and_native_updates(self):
        spec = _weighted(
            terms=(("humidity", 2.0),),
            bias=0.0,
            minimum=0.0,
            maximum=2.0,
        )
        runtime, compiled = _formal_runtime(
            _world([
                _field("humidity", initial=0.2, target=0.8, rate=0.5),
            ]),
            derived_by_area={AREA: (spec,)},
        )
        advance_world_tick(runtime.session)
        self.assertAlmostEqual(_field_state(runtime)["value"], 0.5, delta=1e-12)
        before = deepcopy(runtime.session.state.to_dict())
        self.assertAlmostEqual(_derived_values(runtime)["comfort_index"], 1.0, delta=1e-12)
        with tempfile.TemporaryDirectory(dir=TEST_TMP) as directory:
            path = Path(directory) / "c5_derived_review_checkpoint.json"
            save_registry_checkpoint(path, runtime)
            restored = load_registry_checkpoint(path, compiled)
        self.assertEqual(restored.session.state.to_dict(), before)
        self.assertAlmostEqual(
            restored.session.state.entities[AREA].components[
                DERIVED_COMPONENT
            ]["values"]["comfort_index"],
            1.0,
            delta=1e-12,
        )
        result = advance_world_tick(restored.session)
        self.assertAlmostEqual(
            _field_state(restored)["value"], 0.65, delta=1e-12
        )
        self.assertAlmostEqual(
            restored.session.state.entities[AREA].components[
                DERIVED_COMPONENT
            ]["values"]["comfort_index"],
            1.3,
            delta=1e-12,
        )
        self.assertTrue(any(
            law_id.endswith(".weighted_sum")
            for law_id in _derived_match_ids(result)
        ))

    def test_legacy_content_without_derived_is_byte_identical(self):
        skill = _modify_skill("legacy_hash_skill", duration=1, mana=1.0)
        omitted = make_content(
            _base_registry(),
            skills=(skill,),
            material_ids=(MATERIAL_ID,),
        )
        explicit_none = make_content(
            _base_registry(),
            skills=(skill,),
            material_ids=(MATERIAL_ID,),
            derived_by_area=None,
        )
        omitted_compiled = compile_content(omitted)
        explicit_compiled = compile_content(explicit_none)
        self.assertFalse(any(
            law["id"].startswith("pmw.v04.derived.")
            for law in omitted_compiled.laws
        ))
        self.assertEqual(
            _law_bytes(omitted_compiled.laws),
            _law_bytes(explicit_compiled.laws),
        )
        self.assertEqual(_digest(omitted_compiled.laws), _digest(explicit_compiled.laws))
        self.assertEqual(
            omitted.action_registry.actions[skill.id].canonical_hash,
            explicit_none.action_registry.actions[skill.id].canonical_hash,
        )
        self.assertEqual(
            omitted.skills[0].canonical_hash,
            explicit_none.skills[0].canonical_hash,
        )

    def test_only_derived_state_laws_write_the_component(self):
        skill = _modify_skill("derived_static_scan_skill")
        spec = _weighted(
            terms=(("humidity", 2.0),),
            bias=0.0,
            minimum=0.0,
            maximum=2.0,
        )
        _, compiled = _formal_runtime(
            _static_fields(humidity=0.2),
            (skill,),
            derived_by_area={AREA: (spec,)},
        )
        writers = [
            law for law in compiled.laws
            if DERIVED_COMPONENT in json.dumps(
                law["effects"], sort_keys=True
            )
        ]
        self.assertTrue(writers)
        self.assertTrue(all(
            law["id"].startswith("pmw.v04.derived.")
            and law["mode"] == "state"
            for law in writers
        ))

    def test_observation_projects_derived_and_sandbox_matches_live(self):
        condition = {"derived": {
            "subject": "current_area",
            "key": "comfort_index",
            "comparator": "gte",
            "value": 0.5,
        }}
        gated = _modify_skill("observed_derived_gate", condition=condition)
        opener = _modify_skill(
            "observed_derived_opener", duration=1, mana=1.0
        )
        spec = _weighted(
            terms=(("humidity", 2.0),),
            bias=0.0,
            minimum=0.0,
            maximum=2.0,
        )
        for actor_id in (PLAYER, NPC):
            with self.subTest(actor=actor_id, state="false"):
                runtime, compiled = _formal_runtime(
                    _static_fields(humidity=0.2),
                    (gated, opener),
                    derived_by_area={AREA: (spec,)},
                )
                disclosure = ObservationDisclosure.create(
                    revealed_actions={actor_id: (gated.id,)}
                )
                observation = ActorObservationBuilder().build(
                    runtime.session,
                    runtime.action_registry,
                    actor_id,
                    disclosure,
                )
                document = observation.to_dict()
                self.assertEqual(
                    document["area"]["derived"],
                    {"comfort_index": 0.4},
                )
                self.assertEqual(
                    set(document["area"]), {"id", "fields", "derived"}
                )
                self.assertNotIn("spec_hash", observation.document_json)
                self.assertNotIn(DERIVED_COMPONENT, observation.document_json)
                for law in compiled.laws:
                    if law["id"].startswith("pmw.v04.derived."):
                        self.assertNotIn(law["id"], observation.document_json)

                before = (
                    deepcopy(runtime.session.state.to_dict()),
                    _actor_state(runtime, actor_id)["mana"],
                    _budget(runtime)["spent_ticks"],
                )
                with self.assertRaisesRegex(
                    GameplayContractError,
                    "^action condition is not satisfied$",
                ):
                    submit_timed_primary_action(
                        runtime.session,
                        runtime.action_registry,
                        ActionRequest(
                            f"observed_derived_false_live_{actor_id}",
                            actor_id,
                            gated.id,
                        ),
                    )
                self.assertEqual(
                    (
                        runtime.session.state.to_dict(),
                        _actor_state(runtime, actor_id)["mana"],
                        _budget(runtime)["spent_ticks"],
                    ),
                    before,
                )
                simulation = SandboxSimulator(
                    runtime.action_registry
                ).simulate(
                    observation,
                    ActionRequest(
                        f"observed_derived_false_sandbox_{actor_id}",
                        actor_id,
                        gated.id,
                    ),
                )
                self.assertFalse(simulation.legal)
                self.assertEqual(
                    simulation.rejection,
                    "action condition is not satisfied",
                )
                legal = LegalActionGenerator(
                    runtime.action_registry
                ).generate(observation, actor_id=actor_id)
                self.assertNotIn(
                    gated.id, {row.request.action_id for row in legal}
                )

            with self.subTest(actor=actor_id, state="true"):
                runtime, _ = _formal_runtime(
                    _static_fields(humidity=0.2),
                    (gated, opener),
                    derived_by_area={AREA: (spec,)},
                )
                submit_timed_primary_action(
                    runtime.session,
                    runtime.action_registry,
                    ActionRequest(
                        f"observed_derived_open_{actor_id}",
                        PLAYER,
                        opener.id,
                    ),
                )
                self.assertGreaterEqual(
                    _derived_values(runtime)["comfort_index"], 0.5
                )
                observation = ActorObservationBuilder().build(
                    runtime.session,
                    runtime.action_registry,
                    actor_id,
                    ObservationDisclosure.create(
                        revealed_actions={actor_id: (gated.id,)}
                    ),
                )
                self.assertGreaterEqual(
                    observation.to_dict()["area"]["derived"]["comfort_index"],
                    0.5,
                )
                simulation = SandboxSimulator(
                    runtime.action_registry
                ).simulate(
                    observation,
                    ActionRequest(
                        f"observed_derived_true_sandbox_{actor_id}",
                        actor_id,
                        gated.id,
                    ),
                )
                self.assertTrue(simulation.legal, simulation.rejection)
                self.assertEqual(
                    simulation.outcome()["cost"],
                    {"duration": 1, "mana": 4.0},
                )
                legal = LegalActionGenerator(
                    runtime.action_registry
                ).generate(observation, actor_id=actor_id)
                self.assertIn(
                    gated.id, {row.request.action_id for row in legal}
                )
                before_mana = _actor_state(runtime, actor_id)["mana"]
                before_spent = _budget(runtime)["spent_ticks"]
                live = submit_timed_primary_action(
                    runtime.session,
                    runtime.action_registry,
                    ActionRequest(
                        f"observed_derived_true_live_{actor_id}",
                        actor_id,
                        gated.id,
                    ),
                )
                self.assertEqual(live.action.cost.mana, 4.0)
                self.assertEqual(live.time.duration, 1)
                self.assertEqual(
                    _actor_state(runtime, actor_id)["mana"],
                    before_mana - 4.0,
                )
                self.assertEqual(
                    _budget(runtime)["spent_ticks"],
                    before_spent + 1,
                )

        legacy_runtime, _ = _formal_runtime(
            _static_fields(humidity=0.2),
            (),
        )
        legacy_observation = ActorObservationBuilder().build(
            legacy_runtime.session,
            legacy_runtime.action_registry,
            PLAYER,
        )
        legacy_document = legacy_observation.to_dict()
        self.assertEqual(set(legacy_document["area"]), {"id", "fields"})
        self.assertEqual(
            legacy_observation.document_json,
            canonical_json(legacy_document),
        )
        self.assertEqual(
            legacy_observation.canonical_sha256,
            LEGACY_OBSERVATION_SHA256,
        )
        self.assertEqual(
            legacy_observation.revision_token,
            LEGACY_OBSERVATION_REVISION,
        )
        self.assertNotIn("derived", legacy_observation.document_json)

        derived_runtime, _ = _formal_runtime(
            _static_fields(humidity=0.2),
            (),
            derived_by_area={AREA: (spec,)},
        )
        for bad_value in (math.nan, math.inf, -math.inf):
            with self.subTest(non_finite=bad_value):
                _derived_values(derived_runtime)["comfort_index"] = bad_value
                with self.assertRaisesRegex(
                    GameplayContractError, "must be a finite number"
                ):
                    ActorObservationBuilder().build(
                        derived_runtime.session,
                        derived_runtime.action_registry,
                        PLAYER,
                    )

        valid_observation = ActorObservationBuilder().build(
            legacy_runtime.session,
            legacy_runtime.action_registry,
            PLAYER,
        )
        tampered_document = valid_observation.to_dict()
        tampered_document["area"]["derived"] = {
            "comfort_index": math.nan
        }
        tampered_raw = json.dumps(
            tampered_document,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=True,
        )
        tampered = ActorObservation(tampered_raw, "fixture-review")
        with self.assertRaisesRegex(
            GameplayContractError, "must be a finite number"
        ):
            SandboxSimulator(legacy_runtime.action_registry)._build(tampered)


if __name__ == "__main__":
    unittest.main()
