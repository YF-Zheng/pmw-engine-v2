from __future__ import annotations

from copy import deepcopy
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
    Gate3Content,
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
    DerivedSpec,
    build_derived_laws,
    canonical_spec_hash,
    parse_derived_spec,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.loadout import (
    change_loadout,
    skill_ref,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.registry import (
    MechanismRegistryRuntime,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.skills import (
    registry_manifest,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.runtime import (
    advance_world_tick,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.time_ledger import (
    TIME_BUDGET_COMPONENT,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.tests.test_p1_scenarios import (
    AREA,
    CLOCK_ID,
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


def _weighted(
    derived_id: str = "comfort",
    *,
    terms=(("humidity", 2.0), ("temperature", -0.5)),
    bias=0.1,
    minimum=0.0,
    maximum=2.0,
) -> DerivedSpec:
    return parse_derived_spec({
        "id": derived_id,
        "kind": "weighted_sum",
        "terms": [list(item) for item in terms],
        "bias": bias,
        "minimum": minimum,
        "maximum": maximum,
    })


def _threshold(
    derived_id: str = "humid",
    *,
    field_id="humidity",
    comparator="gte",
    value=0.5,
) -> DerivedSpec:
    return parse_derived_spec({
        "id": derived_id,
        "kind": "threshold",
        "field_id": field_id,
        "comparator": comparator,
        "value": value,
    })


def _formal_runtime(
    world,
    skills: tuple,
    *,
    derived_by_area=None,
):
    base = ActionRegistry(
        basic_registry().actions.values(),
        basic_registry().statuses.values(),
    )
    content = make_content(
        base,
        skills=skills,
        material_ids=(MATERIAL_ID,),
        derived_by_area=derived_by_area,
    )
    initialized = initialize_content_world(world, content)
    compiled = compile_content(content)
    session = build_content_session(initialized, compiled)
    runtime = MechanismRegistryRuntime.from_compiled_content(session, compiled)
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
    return runtime, compiled


def _derived_values(runtime, area_id=AREA):
    return runtime.session.state.entities[area_id].components[
        DERIVED_COMPONENT
    ]["values"]


def _trace_deltas(outcome):
    return [
        delta
        for event in outcome.event_result.trace.events
        for commit in event.commits
        for delta in commit.state_deltas
    ]


def _derived_commits(outcome):
    rows = []
    for event in outcome.event_result.trace.events:
        for commit in event.commits:
            derived = [
                delta for delta in commit.state_deltas
                if str(delta.address) == (
                    f"entity:{AREA}/{DERIVED_COMPONENT}/values/comfort"
                )
            ]
            if derived:
                rows.append((commit, derived[0]))
    return rows


def _trace_matches(outcome):
    return [
        match
        for event in outcome.event_result.trace.events
        for match in event.state_law_matches
    ]


def _humidity_world(*, initial=0.2, target=0.8, rate=0.2):
    return _world([
        _field("humidity", initial=initial, target=target, rate=rate),
        _field("temperature", initial=0.4, target=0.4, rate=0.0),
    ])


def _static_humidity_world(*, initial=0.2):
    return _world([
        _field("humidity", initial=initial, target=initial, rate=0.0),
        _field("temperature", initial=0.4, target=0.4, rate=0.0),
    ])


def _condition_skill(*, derived_id="comfort", threshold=0.5):
    return _skill(_skill_raw(
        "derived_gated_soak",
        [{
            "id": "soak",
            "kind": "modify_field",
            "target": {"kind": "current_area"},
            "commitment": "required",
            "field_id": "humidity",
            "amount": 0.2,
        }],
        condition={"derived": {
            "subject": "current_area",
            "key": derived_id,
            "comparator": "gte",
            "value": threshold,
        }},
        duration=2,
        mana=4.0,
        budget=5.0,
    ))


def _digest(value):
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()).hexdigest()


class DerivedCatalogAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        TEST_TMP.mkdir(parents=True, exist_ok=True)

    def test_paid_modify_field_updates_derived_immediately_and_follows_native_ticks(self):
        skill = _skill(_skill_raw(
            "derived_humidify",
            [{
                "id": "humidify",
                "kind": "modify_field",
                "target": {"kind": "current_area"},
                "commitment": "required",
                "field_id": "humidity",
                "amount": 0.2,
            }],
            duration=1,
            mana=3.0,
            budget=4.0,
        ))
        runtime, _ = _formal_runtime(
            _humidity_world(),
            (skill,),
            derived_by_area={AREA: (_weighted(),), OTHER_AREA: (_weighted(),)},
        )
        self.assertAlmostEqual(_derived_values(runtime)["comfort"], 0.3, delta=1e-12)
        result = submit_timed_primary_action(
            runtime.session,
            runtime.action_registry,
            ActionRequest("derived_paid", PLAYER, skill.id),
        )
        self.assertEqual(_actor_state(runtime, PLAYER)["mana"], 27.0)
        self.assertEqual(_budget(runtime)["spent_ticks"], 1)
        # The paid duration already ran one native Tick.
        self.assertAlmostEqual(_field_state(runtime)["value"], 0.48, delta=1e-12)
        self.assertAlmostEqual(_derived_values(runtime)["comfort"], 0.86, delta=1e-12)
        derived_commits = _derived_commits(result.action)
        self.assertEqual(len(derived_commits), 1)
        commit, persisted_delta = derived_commits[0]
        self.assertEqual(commit.phase, "state:1")
        self.assertAlmostEqual(persisted_delta.old_value, 0.3, delta=1e-12)
        self.assertAlmostEqual(persisted_delta.new_value, 0.7, delta=1e-12)
        derived_match_ids = {
            match.law_id
            for event in result.action.event_result.trace.events
            for match in event.state_law_matches
            if match.law_id.startswith(f"pmw.v04.derived.{AREA}.comfort")
        }
        self.assertEqual(
            derived_match_ids,
            {f"pmw.v04.derived.{AREA}.comfort.weighted_sum"},
        )
        self.assertTrue(all(
            law_id in persisted_delta.law_ids for law_id in derived_match_ids
        ))
        field_deltas = [
            delta for delta in _trace_deltas(result.action)
            if str(delta.address) == f"entity:{AREA}/pmw_gameplay_dynamics/fields/humidity/value"
        ]
        self.assertEqual(len(field_deltas), 1)
        self.assertAlmostEqual(field_deltas[0].old_value, 0.2, delta=1e-12)
        self.assertAlmostEqual(field_deltas[0].new_value, 0.4, delta=1e-12)
        # The next explicit public Tick starts from the 0.48 state and moves
        # by its native recurrence; the later cases use their own explicit
        # Tick sequence.
        field_value = 0.48
        for _ in range(3):
            advance_world_tick(runtime.session)
            field_value += 0.2 * (0.8 - field_value)
            self.assertAlmostEqual(
                _field_state(runtime)["value"], field_value, delta=1e-12
            )
            self.assertAlmostEqual(
                _derived_values(runtime)["comfort"],
                0.1 + 2.0 * field_value - 0.2,
                delta=1e-12,
            )

    def test_same_parsed_skill_derived_gate_player_npc_atomic_false_then_true(self):
        skill = _condition_skill()
        runtime, _ = _formal_runtime(
            _static_humidity_world(),
            (skill,),
            derived_by_area={AREA: (_weighted(),), OTHER_AREA: (_weighted(),)},
        )
        for actor_id in (PLAYER, NPC):
            self.assertEqual(
                runtime.action_registry.actions[skill.id].canonical_hash,
                skill.action.canonical_hash,
            )
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
                    ActionRequest(f"derived_false_{actor_id}", actor_id, skill.id),
                )
            self.assertEqual(
                (
                    runtime.session.state.to_dict(),
                    _actor_state(runtime, actor_id)["mana"],
                    _budget(runtime)["spent_ticks"],
                ),
                before,
            )
        # A real paid action raises comfort 0.3 -> 0.7, then the same parsed
        # gated Skill becomes available to both controllers.
        opener = _skill(_skill_raw(
            "derived_open_gate",
            [{
                "id": "open_gate",
                "kind": "modify_field",
                "target": {"kind": "current_area"},
                "commitment": "required",
                "field_id": "humidity",
                "amount": 0.2,
            }],
            duration=1,
            mana=3.0,
            budget=4.0,
        ))
        runtime, _ = _formal_runtime(
            _static_humidity_world(),
            (skill, opener),
            derived_by_area={AREA: (_weighted(),), OTHER_AREA: (_weighted(),)},
        )
        submit_timed_primary_action(
            runtime.session,
            runtime.action_registry,
            ActionRequest("derived_gate_opener", PLAYER, opener.id),
        )
        self.assertAlmostEqual(_derived_values(runtime)["comfort"], 0.7, delta=1e-12)
        for actor_id in (PLAYER, NPC):
            before_mana = _actor_state(runtime, actor_id)["mana"]
            before_spent = _budget(runtime)["spent_ticks"]
            paid = submit_timed_primary_action(
                runtime.session,
                runtime.action_registry,
                ActionRequest(f"derived_true_{actor_id}", actor_id, skill.id),
            )
            self.assertEqual(paid.action.definition.canonical_hash, skill.action.canonical_hash)
            self.assertEqual(paid.action.cost.mana, 4.0)
            self.assertEqual(paid.time.duration, 2)
            self.assertEqual(_actor_state(runtime, actor_id)["mana"], before_mana - 4.0)
            self.assertEqual(_budget(runtime)["spent_ticks"], before_spent + 2)

    def test_threshold_flips_zero_one_zero_across_real_field_crossing(self):
        skill = _skill(_skill_raw(
            "derived_cross_threshold",
            [{
                "id": "cross",
                "kind": "modify_field",
                "target": {"kind": "current_area"},
                "commitment": "required",
                "field_id": "humidity",
                "amount": 0.2,
            }],
            duration=1,
            mana=2.0,
            budget=3.0,
        ))
        runtime, _ = _formal_runtime(
            _world([
                _field("humidity", initial=0.4, target=0.2, rate=0.2),
            ]),
            (skill,),
            derived_by_area={
                AREA: (_threshold(),),
                OTHER_AREA: (_threshold(),),
            },
        )
        self.assertEqual(_derived_values(runtime)["humid"], 0.0)
        submit_timed_primary_action(
            runtime.session,
            runtime.action_registry,
            ActionRequest("derived_threshold_up", PLAYER, skill.id),
        )
        # Paid duration=1 advances one native Tick after the modify_field.
        self.assertAlmostEqual(_field_state(runtime)["value"], 0.52, delta=1e-12)
        self.assertEqual(_derived_values(runtime)["humid"], 1.0)
        advance_world_tick(runtime.session)
        self.assertAlmostEqual(_field_state(runtime)["value"], 0.456, delta=1e-12)
        self.assertEqual(_derived_values(runtime)["humid"], 0.0)
        advance_world_tick(runtime.session)
        self.assertAlmostEqual(_field_state(runtime)["value"], 0.4048, delta=1e-12)
        self.assertEqual(_derived_values(runtime)["humid"], 0.0)

    def test_two_areas_have_independent_specs_and_values(self):
        runtime, _ = _formal_runtime(
            _world([
                _field("humidity", initial=0.2, target=0.2, rate=0.0),
                _field("temperature", initial=0.4, target=0.4, rate=0.0),
            ]),
            (),
            derived_by_area={
                AREA: (_weighted(),),
                OTHER_AREA: (_weighted(
                    "dryness",
                    terms=(("humidity", -2.0),),
                    bias=1.0,
                    minimum=0.0,
                    maximum=2.0,
                ),),
            },
        )
        self.assertAlmostEqual(_derived_values(runtime, AREA)["comfort"], 0.3, delta=1e-12)
        self.assertAlmostEqual(
            _derived_values(runtime, OTHER_AREA)["dryness"], 0.6, delta=1e-12
        )
        area = runtime.session.state.entities[AREA]
        self.assertEqual(
            set(area.components[DERIVED_COMPONENT]["values"]), {"comfort"}
        )
        other = runtime.session.state.entities[OTHER_AREA]
        self.assertEqual(
            set(other.components[DERIVED_COMPONENT]["values"]), {"dryness"}
        )
        self.assertNotEqual(
            area.components[DERIVED_COMPONENT]["spec_hash"],
            other.components[DERIVED_COMPONENT]["spec_hash"],
        )

    def test_trace_shows_state_law_and_no_python_mutation_after_initialization(self):
        skill = _skill(_skill_raw(
            "derived_trace",
            [{
                "id": "trace_humidity",
                "kind": "modify_field",
                "target": {"kind": "current_area"},
                "commitment": "required",
                "field_id": "humidity",
                "amount": 0.2,
            }],
            duration=1,
            mana=1.0,
            budget=2.0,
        ))
        runtime, compiled = _formal_runtime(
            _static_humidity_world(),
            (skill,),
            derived_by_area={AREA: (_weighted(),), OTHER_AREA: (_weighted(),)},
        )
        component = runtime.session.state.entities[AREA].components[
            DERIVED_COMPONENT
        ]
        self.assertEqual(set(component), {"values", "spec_hash"})
        self.assertEqual(
            component["spec_hash"],
            canonical_spec_hash((_weighted(),)),
        )
        result = submit_timed_primary_action(
            runtime.session,
            runtime.action_registry,
            ActionRequest("derived_trace_action", PLAYER, skill.id),
        )
        matches = _trace_matches(result.action)
        derived_matches = [
            match for match in matches
            if match.law_id.startswith(f"pmw.v04.derived.{AREA}.comfort")
        ]
        self.assertTrue(derived_matches)
        self.assertTrue(all(match.mode == "state" for match in derived_matches))
        derived_laws = {
            law["id"] for law in compiled.laws
            if law.get("mode") == "state"
            and law["id"].startswith("pmw.v04.derived.")
        }
        self.assertEqual(
            derived_laws,
            {f"pmw.v04.derived.{AREA}.comfort.weighted_sum",
             f"pmw.v04.derived.{OTHER_AREA}.comfort.weighted_sum"},
        )

    def test_strict_parse_rejections_unknown_field_duplicates_and_limits(self):
        valid = {
            "id": "comfort",
            "kind": "weighted_sum",
            "terms": [["humidity", 2.0]],
            "bias": 0.1,
            "minimum": 0.0,
            "maximum": 2.0,
        }
        cases = (
            valid | {"extra": 1},
            {key: value for key, value in valid.items() if key != "bias"},
            valid | {"id": "Upper"},
            valid | {"id": "x"},
            valid | {"terms": []},
            valid | {"terms": [["humidity", 8.01]]},
            valid | {"terms": [["humidity", True]]},
            valid | {"bias": math.nan},
            valid | {"minimum": 2.0, "maximum": 2.0},
            {"id": "bad", "kind": "weighted_sum", "terms": [["humidity", 1.0], ["humidity", 2.0]], "bias": 0.0, "minimum": 0.0, "maximum": 1.0},
            {"id": "bad", "kind": "threshold", "field_id": "humidity", "comparator": "eq", "value": 0.5},
        )
        for index, raw in enumerate(cases):
            with self.subTest(index=index):
                with self.assertRaises(GameplayContractError):
                    parse_derived_spec(raw)
        specs = tuple(
            _weighted(f"derived_{index}", terms=(("humidity", 1.0),))
            for index in range(8)
        )
        with self.assertRaises(GameplayContractError):
            build_derived_laws({AREA: (*specs, _weighted("derived_extra", terms=(("humidity", 1.0),)))})
        with self.assertRaises(GameplayContractError):
            build_derived_laws({AREA: (_weighted("duplicate"), _weighted("duplicate"))})
        malformed_trusted = (
            DerivedSpec("bad", "weighted_sum", terms=(), bias=0.0, minimum=0.0, maximum=1.0),
            DerivedSpec("bad", "weighted_sum", terms=(("humidity", 9.0),), bias=0.0, minimum=0.0, maximum=1.0),
            DerivedSpec("bad", "weighted_sum", terms=(("humidity", 1.0),), bias=0.0, minimum=1.0, maximum=0.0),
            DerivedSpec("bad", "threshold", field_id="humidity", comparator="eq", value=0.5),
            DerivedSpec("bad", "threshold", field_id="humidity", comparator="gte", value=math.inf),
        )
        for spec in malformed_trusted:
            with self.subTest(spec=spec):
                with self.assertRaises(GameplayContractError):
                    build_derived_laws({AREA: (spec,)})
        runtime = _formal_runtime(_humidity_world(), ())[0]
        initial = deepcopy(runtime.session.state)
        before = deepcopy(runtime.session.state.to_dict())
        with self.assertRaisesRegex(GameplayContractError, "unavailable Field"):
            content = make_content(
                ActionRegistry(
                    basic_registry().actions.values(),
                    basic_registry().statuses.values(),
                ),
                material_ids=(MATERIAL_ID,),
                derived_by_area={AREA: (_weighted(terms=(("missing", 1.0),)),)},
            )
            initialize_content_world(
                initial,
                content,
            )
        self.assertEqual(runtime.session.state.to_dict(), before)

    def test_only_derived_laws_write_component_and_legacy_is_byte_identical(self):
        skill = _skill(_skill_raw(
            "derived_static_scan",
            [{
                "id": "scan_write",
                "kind": "modify_field",
                "target": {"kind": "current_area"},
                "commitment": "required",
                "field_id": "humidity",
                "amount": 0.2,
            }],
            duration=1,
            mana=1.0,
            budget=2.0,
        ))
        base = ActionRegistry(
            basic_registry().actions.values(),
            basic_registry().statuses.values(),
        )
        legacy_content = make_content(base, skills=(skill,), material_ids=(MATERIAL_ID,))
        derived_content = make_content(
            base,
            skills=(skill,),
            material_ids=(MATERIAL_ID,),
            derived_by_area={AREA: (_weighted(),)},
        )
        legacy_compiled = compile_content(legacy_content)
        derived_compiled = compile_content(derived_content)
        self.assertEqual(
            legacy_compiled.laws,
            tuple(law for law in derived_compiled.laws
                  if not law["id"].startswith("pmw.v04.derived.")),
        )
        self.assertEqual(
            legacy_content.action_registry.actions[skill.id].canonical_hash,
            derived_content.action_registry.actions[skill.id].canonical_hash,
        )
        self.assertEqual(
            legacy_content.skills[0].canonical_hash,
            derived_content.skills[0].canonical_hash,
        )
        self.assertEqual(
            _digest(legacy_compiled.laws),
            _digest(tuple(
                law for law in derived_compiled.laws
                if not law["id"].startswith("pmw.v04.derived.")
            )),
        )
        for law in derived_compiled.laws:
            effects = json.dumps(law["effects"], sort_keys=True)
            if DERIVED_COMPONENT in effects:
                self.assertTrue(law["id"].startswith("pmw.v04.derived."))
                self.assertEqual(law["mode"], "state")
        self.assertFalse(any(
            DERIVED_COMPONENT in json.dumps(law["effects"], sort_keys=True)
            and not law["id"].startswith("pmw.v04.derived.")
            for law in derived_compiled.laws
        ))

    def test_checkpoint_round_trip_preserves_derived_without_catalog_rebuild(self):
        skill = _skill(_skill_raw(
            "derived_checkpoint",
            [{
                "id": "checkpoint_humidity",
                "kind": "modify_field",
                "target": {"kind": "current_area"},
                "commitment": "required",
                "field_id": "humidity",
                "amount": 0.2,
            }],
            duration=1,
            mana=1.0,
            budget=2.0,
        ))
        runtime, compiled = _formal_runtime(
            _static_humidity_world(),
            (skill,),
            derived_by_area={AREA: (_weighted(),), OTHER_AREA: (_weighted(),)},
        )
        submit_timed_primary_action(
            runtime.session,
            runtime.action_registry,
            ActionRequest("derived_checkpoint_action", PLAYER, skill.id),
        )
        before = deepcopy(runtime.session.state.to_dict())
        with tempfile.TemporaryDirectory(dir=TEST_TMP) as directory:
            path = Path(directory) / "derived_checkpoint.json"
            save_registry_checkpoint(path, runtime)
            restored = load_registry_checkpoint(path, compiled)
        self.assertEqual(restored.session.state.to_dict(), before)
        self.assertAlmostEqual(
            restored.session.state.entities[AREA].components[
                DERIVED_COMPONENT
            ]["values"]["comfort"],
            0.7,
            delta=1e-12,
        )
        submit_timed_primary_action(
            restored.session,
            restored.action_registry,
            ActionRequest("derived_checkpoint_continue", NPC, skill.id),
        )
        self.assertAlmostEqual(
            restored.session.state.entities[AREA].components[
                DERIVED_COMPONENT
            ]["values"]["comfort"],
            1.1,
            delta=1e-12,
        )
        self.assertEqual(
            restored.session.state.entities[CLOCK_ID].components[
                "pmw_gameplay_clock"
            ]["last_completed_step"],
            2,
        )

    def test_many_ticks_reach_fixed_point_without_settle_limit(self):
        runtime, _ = _formal_runtime(
            _world([
                _field("humidity", initial=0.2, target=0.8, rate=0.2),
                _field("temperature", initial=0.4, target=0.4, rate=0.0),
            ]),
            (),
            derived_by_area={
                AREA: (_weighted(), _threshold()),
                OTHER_AREA: (_weighted(),),
            },
        )
        expected = 0.2
        for tick in range(30):
            advance_world_tick(runtime.session)
            expected = expected + 0.2 * (0.8 - expected)
            expected_comfort = max(
                0.0, min(2.0, 0.1 + 2.0 * expected - 0.5 * 0.4)
            )
            self.assertAlmostEqual(
                _derived_values(runtime)["comfort"],
                expected_comfort,
                delta=1e-12,
            )
            self.assertEqual(
                _derived_values(runtime)["humid"],
                1.0 if expected >= 0.5 else 0.0,
            )
        self.assertEqual(
            runtime.session.state.entities[CLOCK_ID].components[
                "pmw_gameplay_clock"
            ]["last_completed_step"],
            30,
        )
        self.assertTrue(runtime.session.runtime.state_closure_known)

    def test_condition_leaf_is_scoped_and_existing_leaves_are_unchanged(self):
        spec = parse_condition({"derived": {
            "subject": "current_area",
            "key": "comfort",
            "comparator": "gte",
            "value": 0.5,
        }})
        self.assertTrue(evaluate_condition(spec, {
            "current_area": {"derived": {"comfort": 0.7}},
        }))
        self.assertFalse(evaluate_condition(spec, {
            "current_area": {"derived": {}},
        }))
        self.assertFalse(evaluate_condition(spec, {
            "current_area": {"derived": {"comfort": True}},
        }))
        with self.assertRaises(GameplayContractError):
            parse_condition({"derived": {
                "subject": "self",
                "key": "comfort",
                "comparator": "gte",
                "value": 0.5,
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
                "key": "comfort",
                "comparator": "eq",
                "value": 0.5,
                "extra": 1,
            }})
        legacy = parse_condition({"field": {
            "subject": "current_area",
            "key": "humidity",
            "comparator": "gte",
            "value": 0.5,
        }})
        self.assertTrue(evaluate_condition(legacy, {
            "current_area": {"fields": {"humidity": {"value": 0.5}}},
        }))

    def test_positional_gate3_content_remains_compatible(self):
        from types import MappingProxyType
        registry = ActionRegistry(
            basic_registry().actions.values(),
            basic_registry().statuses.values(),
        )
        content = Gate3Content(
            registry,
            (),
            registry_manifest(()),
            MappingProxyType({}),
            MappingProxyType({}),
            MappingProxyType({}),
            MappingProxyType({}),
            (),
        )
        self.assertEqual(content.derived_by_area, {})
        self.assertEqual(compile_content(content).laws, compile_content(
            make_content(registry, material_ids=())
        ).laws)


if __name__ == "__main__":
    unittest.main()
