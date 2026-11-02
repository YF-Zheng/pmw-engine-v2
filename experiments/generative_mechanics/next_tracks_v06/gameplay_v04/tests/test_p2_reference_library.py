from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.actions import (
    ACTOR_COMPONENT,
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
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.combat import (
    run_combat_round,
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
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.drives import (
    DRIVE_COMPONENT,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.loadout import (
    change_loadout,
    skill_ref,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.processes import (
    PROCESS_COMPONENT,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.reference_skills.fixtures import (
    AREA,
    CLOCK_ID,
    NPC,
    OTHER_AREA,
    PLAYER,
    PROFILES,
    build_fixture,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.relations import (
    RELATION_COMPONENT,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.registry import (
    MechanismRegistryRuntime,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.runtime import (
    advance_world_tick,
    run_phase_event,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.skill_ir import (
    OPERATOR_KINDS,
    SELECTOR_KINDS,
    STATE_CLASS_KINDS,
    compile_skill_ir,
    parse_skill_ir,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.time_ledger import (
    TIME_BUDGET_COMPONENT,
    spend_world_time,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.status import (
    STATUS_COMPONENT,
)


PROJECT_ROOT = Path(__file__).resolve().parents[5]
LIBRARY_PATH = (
    PROJECT_ROOT
    / "experiments"
    / "generative_mechanics"
    / "next_tracks_v06"
    / "gameplay_v04"
    / "reference_skills"
    / "library.json"
)
FIXTURE_PATH = (
    PROJECT_ROOT
    / "experiments"
    / "generative_mechanics"
    / "next_tracks_v06"
    / "gameplay_v04"
    / "reference_skills"
    / "fixtures.py"
)
EVIDENCE_DIR = PROJECT_ROOT / "docs" / "agent_bootstrap" / "evidence"
MATRIX_PATH = EVIDENCE_DIR / "p2_reference_coverage_matrix.json"
TEST_TMP = EVIDENCE_DIR / "test_tmp"
CATEGORY_NAMES = (
    "positive_execution",
    "illegal_permission",
    "budget_overflow",
    "lifecycle",
    "cross_region",
    "checkpoint",
    "deterministic_replay",
)
CATEGORY_MINIMUMS = {
    "instant_field_change": 3,
    "attractor_investment": 2,
    "recovery_rate_change": 3,
    "resource_consume_produce": 3,
    "process_start_modify": 3,
    "relation_change": 3,
    "event_driven_passive": 3,
    "condition_combinations": 4,
    "multi_effect_synergy": 4,
    "selector_self": 1,
    "selector_target_actor": 1,
    "selector_current_area": 1,
    "selector_adjacent_area": 1,
    "selector_linked_object": 1,
}


def _library() -> list[dict]:
    return json.loads(LIBRARY_PATH.read_text(encoding="utf-8"))


def _fixture_tag(document: dict) -> str:
    tags = [
        item for item in document["display"]["tags"]
        if item.startswith("fixture:")
    ]
    if len(tags) != 1:
        raise AssertionError("each reference Skill needs one fixture tag")
    return tags[0].split(":", 1)[1]


def _parse(document: dict, fixture):
    return parse_skill_ir(document, fixture.statuses, fixture.authority)


def _request(skill, actor_id: str, request_suffix: str = "cast") -> ActionRequest:
    effects = tuple(
        effect
        for entry in skill.entries
        for effect in entry.effects
    )
    selectors = {
        effect["target"]["kind"]
        for effect in effects
    }
    target_actor = None
    target_area = None
    if any(item["kind"] == "move_actor" for item in effects):
        target_area = OTHER_AREA
    elif {"target_actor", "linked_object"} & selectors:
        target_actor = NPC if actor_id == PLAYER else PLAYER
    action_id = next(
        entry.id for entry in skill.entries
        if entry.trigger_kind == "on_use"
    )
    return ActionRequest(
        f"p22_{actor_id}_{skill.id}_{request_suffix}",
        actor_id,
        f"{skill.id}__{action_id}",
        target_actor,
        target_area,
    )


def _start_required_process(runtime, actor_id: str, skill) -> None:
    template_ids = {
        effect["process_template_id"]
        for entry in skill.entries
        for effect in entry.effects
        if effect["kind"] == "process_modify"
    }
    if not template_ids:
        return
    controller = runtime.base_registry.process_controller
    for template_id in sorted(template_ids):
        matches = [
            item for item in controller.profiles
            if item.owner == actor_id and item.template.id == template_id
        ]
        if len(matches) != 1:
            raise AssertionError("expected exactly one local Process profile")
        controller.start(runtime.session, matches[0].id, owner=actor_id)


def _build(document: dict, actor_id: str):
    fixture = build_fixture(_fixture_tag(document), primary_actor=actor_id)
    parsed = _parse(document, fixture)
    compiled = compile_skill_ir(parsed)
    base = ActionRegistry(
        basic_registry().actions.values(),
        basic_registry().statuses.values(),
        process_controller=fixture.process_controller,
        drive_controller=fixture.drive_controller,
        relation_controller=fixture.relation_controller,
    )
    content = make_content(
        base,
        skills=compiled.blueprints,
        material_ids=(fixture.material_id,),
        derived_by_area=fixture.derived_by_area,
    )
    initialized = initialize_content_world(fixture.world, content)
    gate3 = compile_content(content)
    session = build_content_session(initialized, gate3)
    runtime = MechanismRegistryRuntime.from_compiled_content(session, gate3)
    for slot, blueprint in enumerate(compiled.blueprints):
        change_loadout(
            runtime.session,
            runtime.manifest,
            actor_id=actor_id,
            operation=(
                "equip_active"
                if blueprint.kind == "skill_blueprint"
                else "equip_passive"
            ),
            skill=skill_ref(blueprint),
            slot=slot,
        )
    return fixture, parsed, compiled, gate3, runtime, content


def _mana(runtime, actor_id: str) -> float:
    return runtime.session.state.entities[actor_id].components[
        ACTOR_COMPONENT
    ]["mana"]


def _budget(runtime) -> dict:
    return runtime.session.state.entities[CLOCK_ID].components[
        TIME_BUDGET_COMPONENT
    ]


def _digest(value) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _world_digest(runtime) -> str:
    return _digest(runtime.session.state.to_dict())


def _state(runtime, entity_id: str) -> dict:
    return runtime.session.state.entities[entity_id].components


def _actor_state(runtime, actor_id: str) -> dict:
    return _state(runtime, actor_id)[ACTOR_COMPONENT]


def _field(runtime, area_id: str, field_id: str) -> dict:
    return _state(runtime, area_id)["pmw_gameplay_dynamics"]["fields"][field_id]


def _relation(runtime, relation_id: str) -> dict:
    return runtime.session.state.relations[relation_id].components[
        "pmw_gameplay_link"
    ]


def _active_deltas(before: dict, after: dict) -> list[str]:
    def walk(left, right, path="$"):
        if type(left) is not type(right):
            return [path]
        if isinstance(left, dict):
            deltas = []
            for key in sorted(set(left) | set(right)):
                if key not in left or key not in right:
                    deltas.append(f"{path}.{key}")
                else:
                    deltas.extend(walk(left[key], right[key], f"{path}.{key}"))
            return deltas
        if isinstance(left, list):
            deltas = []
            for index in range(max(len(left), len(right))):
                if index >= len(left) or index >= len(right):
                    deltas.append(f"{path}[{index}]")
                else:
                    deltas.extend(walk(
                        left[index], right[index], f"{path}[{index}]"
                    ))
            return deltas
        return [] if left == right else [path]

    return walk(before, after)


def _located_areas(runtime, actor_id: str) -> list[str]:
    return sorted(
        relation.target
        for relation in runtime.session.state.relations.values()
        if relation.type == "located_in" and relation.source == actor_id
    )


def _effect_by_id(parsed, effect_id: str) -> dict:
    matches = [
        effect
        for entry in parsed.entries
        for effect in entry.effects
        if effect["id"] == effect_id
    ]
    if len(matches) != 1:
        raise AssertionError(f"expected one parsed Effect {effect_id!r}")
    return matches[0]


def _status_slot(runtime, actor_id: str, slot: str) -> dict | None:
    value = _status_slots(runtime, actor_id).get(slot)
    return value if isinstance(value, dict) else None


def _scheduled_ids(runtime) -> set[str]:
    return {event.id for event in runtime.session.state.scheduled_events}


def _effect_targets(parsed) -> list[str]:
    return sorted({
        effect["target"]["kind"]
        for entry in parsed.entries
        if entry.trigger_kind == "on_use"
        for effect in entry.effects
    })


def _expect_applied(testcase, outcome) -> None:
    testcase.assertTrue(outcome.effect_outcomes)
    for row in outcome.effect_outcomes:
        testcase.assertEqual(row["status"], "applied")


def _assert_effect_landed(
    testcase,
    effect: dict,
    outcome: dict,
    cast_runtime,
    control_runtime,
) -> None:
    kind = effect["kind"]
    target_id = outcome["target_id"]
    values = outcome["values"]
    if kind == "modify_field":
        cast_field = _field(cast_runtime, target_id, effect["field_id"])
        control_field = _field(control_runtime, target_id, effect["field_id"])
        testcase.assertNotEqual(cast_field["value"], control_field["value"])
    elif kind in {"modify_attractor", "modify_rate", "dynamics_modifier"}:
        slot = values["slot"]
        cast_source = _field(
            cast_runtime, target_id, effect["field_id"]
        )["temporary_modifiers"][slot]
        control_source = _field(
            control_runtime, target_id, effect["field_id"]
        )["temporary_modifiers"][slot]
        testcase.assertTrue(cast_source["active"])
        testcase.assertFalse(control_source["active"])
    elif kind == "damage":
        testcase.assertEqual(
            _actor_state(cast_runtime, target_id)["hp"],
            values["hp"],
        )
        testcase.assertNotEqual(
            _actor_state(cast_runtime, target_id)["hp"],
            _actor_state(control_runtime, target_id)["hp"],
        )
    elif kind == "heal":
        testcase.assertEqual(
            _actor_state(cast_runtime, target_id)["hp"],
            values["hp"],
        )
        testcase.assertNotEqual(
            _actor_state(cast_runtime, target_id)["hp"],
            _actor_state(control_runtime, target_id)["hp"],
        )
    elif kind == "shield":
        testcase.assertEqual(
            _actor_state(cast_runtime, target_id)["shield"],
            values["shield"],
        )
        testcase.assertNotEqual(
            _actor_state(cast_runtime, target_id)["shield"],
            _actor_state(control_runtime, target_id)["shield"],
        )
    elif kind == "add_resource":
        resource = effect["resource"]
        testcase.assertEqual(
            _actor_state(cast_runtime, target_id)[resource],
            values[resource],
        )
        testcase.assertNotEqual(
            _actor_state(cast_runtime, target_id)[resource],
            _actor_state(control_runtime, target_id)[resource],
        )
    elif kind in {"apply_status", "grant_trait"}:
        cast_slot = _status_slot(cast_runtime, target_id, values["slot"])
        control_slot = _status_slot(control_runtime, target_id, values["slot"])
        testcase.assertIsNotNone(cast_slot)
        testcase.assertIsNotNone(control_slot)
        testcase.assertTrue(cast_slot["active"])
        testcase.assertFalse(control_slot["active"])
    elif kind == "move_actor":
        testcase.assertEqual(
            _located_areas(cast_runtime, values["new_relation_id"].split(":")[1]),
            [values["destination_area_id"]],
        )
        actor_id = values["new_relation_id"].split(":")[1]
        testcase.assertNotEqual(
            _located_areas(cast_runtime, actor_id),
            _located_areas(control_runtime, actor_id),
        )
    elif kind == "drive_source":
        component = _state(cast_runtime, values["drive_target_id"])[
            DRIVE_COMPONENT
        ]
        control_component = _state(control_runtime, values["drive_target_id"])[
            DRIVE_COMPONENT
        ]
        testcase.assertIsNotNone(component["started_at"])
        testcase.assertIsNone(control_component["started_at"])
    elif kind == "process_start":
        component = _state(cast_runtime, values["process_target_id"])[
            PROCESS_COMPONENT
        ]
        control_component = _state(control_runtime, values["process_target_id"])[
            PROCESS_COMPONENT
        ]
        testcase.assertEqual(component["state"], "running")
        testcase.assertEqual(control_component["state"], "stopped")
    elif kind == "process_modify":
        component = _state(cast_runtime, values["process_target_id"])[
            PROCESS_COMPONENT
        ]
        control_component = _state(control_runtime, values["process_target_id"])[
            PROCESS_COMPONENT
        ]
        testcase.assertNotEqual(
            (
                component["rate"],
                component["remaining_ticks"],
                component["duration_ticks"],
            ),
            (
                control_component["rate"],
                control_component["remaining_ticks"],
                control_component["duration_ticks"],
            ),
        )
    elif kind == "relation_modifier":
        cast_component = _relation(
            cast_runtime, values["relation_target_id"]
        )
        control_component = _relation(
            control_runtime, values["relation_target_id"]
        )
        testcase.assertTrue(cast_component["active"])
        testcase.assertFalse(control_component["active"])
    else:
        raise AssertionError(f"unhandled Effect kind {kind!r}")


def _continue_runtime(runtime, actor_id: str, parsed) -> None:
    if _is_passive(parsed):
        opponent = NPC if actor_id == PLAYER else PLAYER
        submit_timed_primary_action(
            runtime.session,
            runtime.action_registry,
            ActionRequest(f"p22_continue_{actor_id}", opponent, "basic_attack", actor_id),
        )
    else:
        advance_world_tick(runtime.session)


def _run_skill(runtime, actor_id: str, parsed, gate3, *, suffix: str = "cast"):
    _start_required_process(runtime, actor_id, parsed)
    return submit_timed_primary_action(
        runtime.session,
        runtime.action_registry,
        _request(parsed, actor_id, suffix),
    )


def _run_without_skill(runtime, duration: int) -> None:
    spend_world_time(runtime.session, duration, reason="exploration")


def _coverage_row(document: dict, parsed, compiled) -> dict:
    return {
        "fixture_profile": _fixture_tag(document),
        "operators": sorted(compiled.operators),
        "state_classes": sorted(compiled.state_classes),
        "selectors": sorted(_used_selectors(parsed)),
        "effect_kinds": sorted(_used_effect_kinds(parsed)),
        "trigger_kinds": sorted({
            entry.trigger_kind for entry in parsed.entries
        }),
        "categories": {},
    }


def _category_tags(document: dict) -> set[str]:
    return set(document["display"]["tags"])


def _effects(compiled) -> list:
    return [
        effect
        for blueprint in compiled.blueprints
        for effect in blueprint.effects
    ]


def _used_effect_kinds(parsed) -> set[str]:
    return {
        effect["kind"]
        for entry in parsed.entries
        for effect in entry.effects
    }


def _used_budget(parsed) -> float:
    return float(sum(
        blueprint.budget_used
        for blueprint in compile_skill_ir(parsed).blueprints
    ))


def _condition_operators(value) -> set[str]:
    if value is None or not isinstance(value, dict):
        return set()
    operators = set()
    for operator, child in value.items():
        if operator in {"all", "any"} and isinstance(child, list):
            operators.add(operator)
            for item in child:
                operators |= _condition_operators(item)
        elif operator == "not":
            operators.add(operator)
            operators |= _condition_operators(child)
        elif operator in {
            "derived", "resource", "field", "status", "trait",
        }:
            operators.add(f"leaf:{operator}")
    return operators


def _used_selectors(parsed) -> set[str]:
    return {
        effect["target"]["kind"]
        for entry in parsed.entries
        for effect in entry.effects
    }


def _has_duration(parsed) -> bool:
    return any(
        effect.get("duration") is not None
        for entry in parsed.entries
        for effect in entry.effects
    )


def _is_passive(parsed) -> bool:
    return any(entry.trigger_kind == "on_event" for entry in parsed.entries)


def _scheduled_expiry(runtime) -> float | None:
    times = [
        event.time for event in runtime.session.state.scheduled_events
        if "expiry" in event.id or "expire" in event.type
    ]
    return min(times) if times else None


def _advance_to(runtime, target: float) -> None:
    while runtime.session.state.sim_time + 1e-9 < target:
        advance_world_tick(runtime.session)


def _status_slots(runtime, actor_id: str) -> dict:
    return _state(runtime, actor_id).get(STATUS_COMPONENT, {}).get(
        "slots", {}
    )


def _cross_region(document: dict, parsed) -> bool:
    selectors = _used_selectors(parsed)
    return (
        "adjacent_area" in selectors
        or _fixture_tag(document) == "travel"
        or "off_area" in _category_tags(document)
    )


class ReferenceLibraryContractTests(unittest.TestCase):
    def test_library_is_versioned_reference_content_with_closed_fixture_tags(self):
        documents = _library()
        self.assertGreaterEqual(len(documents), 30)
        self.assertEqual(len({item["identity"]["id"] for item in documents}), len(documents))
        for document in documents:
            with self.subTest(skill=document["identity"]["id"]):
                self.assertEqual(document["protocol"], "pmw-skill-ir-v1")
                self.assertEqual(document["origin"]["source"], "reference")
                self.assertIn(_fixture_tag(document), PROFILES)
                with self.assertRaisesRegex(GameplayContractError, "fixture profile"):
                    build_fixture("unknown_profile")

    def test_fixture_source_contains_no_library_skill_ids(self):
        source = FIXTURE_PATH.read_text(encoding="utf-8")
        skill_ids = [item["identity"]["id"] for item in _library()]
        leaked = [skill_id for skill_id in skill_ids if skill_id in source]
        self.assertEqual(leaked, [])

    def test_category_minimums_and_mechanical_coverage(self):
        documents = _library()
        compiled_rows = []
        for document in documents:
            profile = _fixture_tag(document)
            parsed = _parse(document, build_fixture(profile))
            compiled = compile_skill_ir(parsed)
            compiled_rows.append((document, parsed, compiled))

        operators = {
            operator for _, _, compiled in compiled_rows
            for operator in compiled.operators
        }
        state_classes = {
            state_class for _, _, compiled in compiled_rows
            for state_class in compiled.state_classes
        }
        selectors = {
            selector for _, parsed, _ in compiled_rows
            for selector in _used_selectors(parsed)
        }
        self.assertEqual(operators, set(OPERATOR_KINDS))
        self.assertEqual(state_classes, set(STATE_CLASS_KINDS))
        self.assertEqual(selectors, set(SELECTOR_KINDS))

        def count(predicate) -> int:
            return sum(bool(predicate(document, parsed, compiled))
                       for document, parsed, compiled in compiled_rows)

        def has_kind(document, parsed, compiled, kind):
            return kind in _used_effect_kinds(parsed)

        def has_condition_combo(document, parsed, compiled):
            return any(
                {"all", "any", "not"}
                & _condition_operators(effect.get("condition"))
                and {
                    item for item in _condition_operators(
                        effect.get("condition")
                    )
                    if item.startswith("leaf:")
                }
                for entry in parsed.entries
                for effect in entry.effects
            ) and "Derived" in compiled.state_classes

        def has_synergy(document, parsed, compiled):
            return (
                any(len(entry.effects) >= 2 for entry in parsed.entries)
                and len(compiled.operators) >= 2
            )
        minimums = {
            "instant_field_change": (
                count(lambda d, p, c: has_kind(d, p, c, "modify_field")),
                3,
            ),
            "attractor_investment": (
                count(lambda d, p, c: has_kind(d, p, c, "modify_attractor")),
                2,
            ),
            "recovery_rate_change": (
                count(lambda d, p, c: (
                    has_kind(d, p, c, "modify_rate")
                    or has_kind(d, p, c, "dynamics_modifier")
                )),
                3,
            ),
            "resource_consume_produce": (
                count(lambda d, p, c: (
                    has_kind(d, p, c, "add_resource")
                    or has_kind(d, p, c, "process_start")
                    or has_kind(d, p, c, "drive_source")
                )),
                3,
            ),
            "process_start_modify": (
                count(lambda d, p, c: (
                    has_kind(d, p, c, "process_start")
                    or has_kind(d, p, c, "process_modify")
                )),
                3,
            ),
            "relation_change": (
                count(lambda d, p, c: (
                    has_kind(d, p, c, "relation_modifier")
                    or has_kind(d, p, c, "move_actor")
                )),
                3,
            ),
            "event_driven_passive": (
                count(lambda d, p, c: any(
                    entry.trigger_kind == "on_event"
                    for entry in parsed.entries
                )),
                3,
            ),
            "condition_combinations": (
                count(has_condition_combo), 4,
            ),
            "multi_effect_synergy": (
                count(has_synergy), 4,
            ),
            "selector_self": (
                count(lambda d, p, c: "self" in _used_selectors(p)),
                1,
            ),
            "selector_target_actor": (
                count(lambda d, p, c: "target_actor" in _used_selectors(p)),
                1,
            ),
            "selector_current_area": (
                count(lambda d, p, c: "current_area" in _used_selectors(p)),
                1,
            ),
            "selector_adjacent_area": (
                count(lambda d, p, c: "adjacent_area" in _used_selectors(p)),
                1,
            ),
            "selector_linked_object": (
                count(lambda d, p, c: "linked_object" in _used_selectors(p)),
                1,
            ),
        }
        EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
        for key, (actual, minimum) in minimums.items():
            with self.subTest(category=key):
                self.assertGreaterEqual(actual, minimum)
        self.assertGreaterEqual(
            count(lambda d, p, c: _cross_region(d, p)),
            6,
        )


class ReferenceLibraryExecutionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        TEST_TMP.mkdir(parents=True, exist_ok=True)
        EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
        cls.documents = _library()
        cls.matrix = {}

    @classmethod
    def tearDownClass(cls):
        operators = sorted({
            item
            for row in cls.matrix.values()
            for item in row["operators"]
        })
        state_classes = sorted({
            item
            for row in cls.matrix.values()
            for item in row["state_classes"]
        })
        selectors = sorted({
            item
            for row in cls.matrix.values()
            for item in row["selectors"]
        })
        category_totals = {
            category: {
                status: sum(
                    row["categories"].get(category, {}).get("status") == status
                    for row in cls.matrix.values()
                )
                for status in ("pass", "n/a", "fail")
            }
            for category in CATEGORY_NAMES
        }
        MATRIX_PATH.write_text(
            json.dumps(
                {
                    "protocol": "pmw-p2-reference-coverage-v1",
                    "skill_count": len(cls.documents),
                    "summary": {
                        "operators": operators,
                        "state_classes": state_classes,
                        "selectors": selectors,
                        "category_totals": category_totals,
                    },
                    "skills": cls.matrix,
                },
                indent=2,
                sort_keys=True,
                ensure_ascii=True,
            ) + "\n",
            encoding="utf-8",
        )

    def _record(self, skill_id: str, category: str, status: str, reason=None):
        if skill_id not in self.matrix:
            document = next(
                item for item in self.documents
                if item["identity"]["id"] == skill_id
            )
            parsed = _parse(document, build_fixture(_fixture_tag(document)))
            compiled = compile_skill_ir(parsed)
            self.matrix[skill_id] = _coverage_row(
                document, parsed, compiled
            )
        row = self.matrix[skill_id]
        row["categories"][category] = {
            "status": status,
            "reason": reason,
        }

    def test_01_each_reference_skill_has_illegal_permission_rejections(self):
        for document in self.documents:
            skill_id = document["identity"]["id"]
            with self.subTest(skill=skill_id):
                fixture = build_fixture(_fixture_tag(document))
                parsed = _parse(document, fixture)

                used_kinds = sorted(_used_effect_kinds(parsed))
                removed_kind = used_kinds[0]
                original = fixture.authority
                bad_authority = type(original)(
                    original.material_ids,
                    tuple(
                        item for item in original.effect_kinds
                        if item != removed_kind
                    ),
                    original.selectors,
                    original.budget_points,
                )
                with self.assertRaisesRegex(
                    GameplayContractError, "effect authorization"
                ):
                    parse_skill_ir(document, fixture.statuses, bad_authority)

                used_selectors = sorted(_used_selectors(parsed))
                removed_selector = used_selectors[0]
                bad_scope = type(original)(
                    original.material_ids,
                    original.effect_kinds,
                    tuple(
                        item for item in original.selectors
                        if item != removed_selector
                    ),
                    original.budget_points,
                )
                with self.assertRaisesRegex(
                    GameplayContractError, "scope authorization"
                ):
                    parse_skill_ir(document, fixture.statuses, bad_scope)

                self._record(skill_id, "illegal_permission", "pass")

    def test_02_each_reference_skill_rejects_budget_overflow(self):
        for document in self.documents:
            skill_id = document["identity"]["id"]
            with self.subTest(skill=skill_id):
                fixture = build_fixture(_fixture_tag(document))
                parsed = _parse(document, fixture)
                compiled = compile_skill_ir(parsed)
                used_budget = sum(
                    item.budget_used for item in compiled.blueprints
                )
                overflow = deepcopy(document)
                overflow["limits"]["budget"] = used_budget - 0.01
                with self.assertRaisesRegex(GameplayContractError, "budget"):
                    parse_skill_ir(
                        overflow, fixture.statuses, fixture.authority
                    )
                self._record(skill_id, "budget_overflow", "pass")

    def test_03_each_reference_skill_executes_for_player_and_npc(self):
        for document in self.documents:
            skill_id = document["identity"]["id"]
            fixture_tag = _fixture_tag(document)
            for actor_id in (PLAYER, NPC):
                with self.subTest(skill=skill_id, actor=actor_id):
                    fixture, parsed, compiled, gate3, cast, cast_content = _build(
                        document, actor_id
                    )
                    (
                        control_fixture,
                        control_parsed,
                        control_compiled,
                        _,
                        control,
                        control_content,
                    ) = _build(document, actor_id)
                    self.assertEqual(
                        parsed.canonical_hash,
                        control_parsed.canonical_hash,
                    )
                    self.assertEqual(
                        compiled.canonical_hash,
                        control_compiled.canonical_hash,
                    )
                    self.assertEqual(
                        _fixture_tag(document), control_fixture.profile
                    )

                    _start_required_process(control, actor_id, control_parsed)
                    before_cast = cast.session.state.to_dict()
                    before_mana = _mana(cast, actor_id)
                    before_spent = _budget(cast)["spent_ticks"]
                    timed = _run_skill(cast, actor_id, parsed, gate3)
                    after_cast = cast.session.state.to_dict()
                    _expect_applied(self, timed.action)

                    _run_without_skill(control, parsed.duration)
                    after_control = control.session.state.to_dict()

                    expected_mana = before_mana - parsed.mana + sum(
                        float(effect.get("amount", 0.0))
                        for entry in parsed.entries
                        if entry.trigger_kind == "on_use"
                        for effect in entry.effects
                        if effect["kind"] == "add_resource"
                        and effect["resource"] == "mana"
                        and effect["target"]["kind"] == "self"
                    )
                    self.assertAlmostEqual(
                        _mana(cast, actor_id), expected_mana, delta=1e-9
                    )
                    self.assertEqual(
                        _budget(cast)["spent_ticks"],
                        before_spent + parsed.duration,
                    )
                    self.assertEqual(timed.action.cost.duration, parsed.duration)
                    self.assertEqual(timed.time.duration, parsed.duration)
                    self.assertEqual(
                        _budget(control)["spent_ticks"],
                        before_spent + parsed.duration,
                    )
                    self.assertEqual(
                        _mana(control, actor_id), before_mana
                    )

                    cast_deltas = set(_active_deltas(before_cast, after_cast))
                    control_deltas = set(_active_deltas(before_cast, after_control))
                    skill_deltas = cast_deltas - control_deltas
                    self.assertTrue(
                        skill_deltas,
                        f"no Skill-caused world delta for {skill_id}/{actor_id}",
                    )
                    for outcome in timed.action.effect_outcomes:
                        effect = _effect_by_id(
                            parsed, outcome["effect_id"]
                        )
                        _assert_effect_landed(
                            self, effect, outcome, cast, control
                        )
            self._record(skill_id, "positive_execution", "pass")

    def test_04_each_reference_skill_has_observed_or_explicit_lifecycle(self):
        lifecycle_kinds = {
            "drive_source", "process_start", "process_modify",
            "relation_modifier", "apply_status", "grant_trait",
        }
        for document in self.documents:
            skill_id = document["identity"]["id"]
            with self.subTest(skill=skill_id):
                fixture, parsed, compiled, gate3, runtime, content = _build(
                    document, PLAYER
                )
                active_effects = [
                    effect
                    for entry in parsed.entries
                    if entry.trigger_kind == "on_use"
                    for effect in entry.effects
                ]
                passive_entries = [
                    entry
                    for entry in parsed.entries
                    if entry.trigger_kind == "on_event"
                ]
                applicable = (
                    any(
                        effect.get("duration") is not None
                        or effect["kind"] in lifecycle_kinds
                        for effect in active_effects
                    )
                    or bool(passive_entries)
                )
                if not applicable:
                    self._record(
                        skill_id,
                        "lifecycle",
                        "n/a",
                        "Active Effects are instantaneous; no per-Effect "
                        "duration, expiry, Process/Drive/Relation state, or "
                        "passive firing cap exists. The action Tick is "
                        "covered by positive execution.",
                    )
                    continue

                timed = _run_skill(runtime, PLAYER, parsed, gate3)
                _expect_applied(self, timed.action)
                outcome_by_id = {
                    row["effect_id"]: row
                    for row in timed.action.effect_outcomes
                }
                if passive_entries:
                    attacker = NPC
                    attack = submit_timed_primary_action(
                        runtime.session,
                        runtime.action_registry,
                        ActionRequest(
                            f"p22_lifecycle_{skill_id}_attack",
                            attacker,
                            "basic_attack",
                            PLAYER,
                        ),
                    )
                    fired = [
                        row for row in attack.action.auto_hooks
                        if row.status == "fired"
                    ]
                    cap = min(
                        entry.max_firings_per_root
                        for entry in passive_entries
                    )
                    self.assertGreaterEqual(len(fired), 1)
                    self.assertLessEqual(len(fired), cap)
                    for entry in passive_entries:
                        self.assertLessEqual(
                            sum(
                                row.hook_id.startswith(
                                    f"passive_{skill_id}_v"
                                )
                                for row in fired
                            ),
                            entry.max_firings_per_root,
                        )
                    self._record(skill_id, "lifecycle", "pass")
                    continue

                status_outcomes = [
                    row for row in timed.action.effect_outcomes
                    if row["kind"] in {"apply_status", "grant_trait"}
                ]
                if status_outcomes:
                    for outcome in status_outcomes:
                        target_id = outcome["target_id"]
                        slot_name = outcome["values"]["slot"]
                        slot = _status_slot(runtime, target_id, slot_name)
                        self.assertIsNotNone(slot)
                        self.assertTrue(slot["active"])
                        self.assertEqual(slot["clock_unit"], "owner_turn")
                        for _ in range(16):
                            slot = _status_slot(runtime, target_id, slot_name)
                            if not slot["active"]:
                                break
                            run_phase_event(
                                runtime.session,
                                "owner_turn",
                                actor_id=target_id,
                            )
                            if _status_slot(
                                runtime, target_id, slot_name
                            )["active"]:
                                advance_world_tick(runtime.session)
                        slot = _status_slot(runtime, target_id, slot_name)
                        self.assertFalse(slot["active"])
                    self._record(skill_id, "lifecycle", "pass")
                    continue

                scheduled = set(_scheduled_ids(runtime))
                expiry = _scheduled_expiry(runtime)
                self.assertIsNotNone(expiry)
                self.assertTrue(scheduled)
                _advance_to(runtime, expiry)
                self.assertTrue(scheduled.isdisjoint(_scheduled_ids(runtime)))
                for effect in active_effects:
                    if effect.get("duration") is None:
                        continue
                    outcome = outcome_by_id[effect["id"]]
                    values = outcome["values"]
                    if effect["kind"] in {
                        "modify_attractor", "modify_rate",
                        "dynamics_modifier",
                    }:
                        source = _field(
                            runtime,
                            outcome["target_id"],
                            effect["field_id"],
                        )["temporary_modifiers"][values["slot"]]
                        self.assertFalse(source["active"])
                    elif effect["kind"] == "drive_source":
                        component = _state(
                            runtime, values["drive_target_id"]
                        )[DRIVE_COMPONENT]
                        self.assertIsNone(component["started_at"])
                        self.assertEqual(component["rate"], 0.0)
                    elif effect["kind"] in {
                        "process_start", "process_modify",
                    }:
                        component = _state(
                            runtime, values["process_target_id"]
                        )[PROCESS_COMPONENT]
                        self.assertEqual(component["state"], "stopped")
                    elif effect["kind"] == "relation_modifier":
                        component = _relation(
                            runtime, values["relation_target_id"]
                        )
                        self.assertFalse(component["active"])
                self._record(skill_id, "lifecycle", "pass")

    def test_05_each_reference_skill_records_cross_region_coverage(self):
        cross_region_count = 0
        for document in self.documents:
            skill_id = document["identity"]["id"]
            with self.subTest(skill=skill_id):
                fixture, parsed, compiled, gate3, runtime, content = _build(
                    document, PLAYER
                )
                if not _cross_region(document, parsed):
                    self._record(
                        skill_id,
                        "cross_region",
                        "n/a",
                        "No adjacent_area selector or move_actor Effect; "
                        "the Skill operates only on self, target_actor, "
                        "current_area, or linked_object.",
                    )
                    continue
                cast = _run_skill(runtime, PLAYER, parsed, gate3)
                adjacent_outcomes = [
                    row for row in cast.action.effect_outcomes
                    if row["target_id"] == OTHER_AREA
                ]
                moved = [
                    row for row in cast.action.effect_outcomes
                    if row["kind"] == "move_actor"
                ]
                self.assertTrue(
                    adjacent_outcomes or moved,
                    f"cross-region Skill {skill_id} produced no remote delta",
                )
                if moved:
                    self.assertEqual(_located_areas(runtime, PLAYER), [OTHER_AREA])
                cross_region_count += 1
                self._record(skill_id, "cross_region", "pass")
        self.assertGreaterEqual(cross_region_count, 6)

    def test_06_each_reference_skill_checkpoints_and_replays(self):
        for document in self.documents:
            skill_id = document["identity"]["id"]
            with self.subTest(skill=skill_id):
                (
                    left_fixture,
                    left_parsed,
                    left_compiled,
                    left_gate3,
                    left,
                    left_content,
                ) = _build(document, PLAYER)
                (
                    right_fixture,
                    right_parsed,
                    right_compiled,
                    right_gate3,
                    right,
                    right_content,
                ) = _build(document, PLAYER)
                self.assertEqual(left_content.skills, right_content.skills)
                self.assertEqual(
                    left_content.action_registry.actions,
                    right_content.action_registry.actions,
                )
                self.assertEqual(
                    left_fixture.profile, right_fixture.profile
                )
                self.assertEqual(
                    left_compiled.canonical_hash,
                    right_compiled.canonical_hash,
                )
                left_timed = _run_skill(
                    left, PLAYER, left_parsed, left_gate3, suffix="checkpoint_a"
                )
                right_timed = _run_skill(
                    right, PLAYER, right_parsed, right_gate3, suffix="checkpoint_a"
                )
                self.assertEqual(
                    left_timed.action.effect_outcomes,
                    right_timed.action.effect_outcomes,
                )
                self.assertEqual(_world_digest(left), _world_digest(right))

                with tempfile.TemporaryDirectory(dir=TEST_TMP) as directory:
                    path = Path(directory) / f"{skill_id}_checkpoint.json"
                    payload_digest = save_registry_checkpoint(path, left)
                    self.assertEqual(len(payload_digest), 64)
                    restored = load_registry_checkpoint(path, left_gate3)
                self.assertEqual(_world_digest(restored), _world_digest(left))
                self.assertEqual(restored.manifest, left.manifest)

                _continue_runtime(restored, PLAYER, left_parsed)
                _continue_runtime(right, PLAYER, right_parsed)
                self.assertEqual(
                    _world_digest(restored), _world_digest(right)
                )
                self.assertEqual(
                    restored.session.state.to_dict(),
                    right.session.state.to_dict(),
                )
                self._record(skill_id, "checkpoint", "pass")
                self._record(skill_id, "deterministic_replay", "pass")

    def test_zz_matrix_and_mechanical_coverage_are_complete(self):
        for document in self.documents:
            skill_id = document["identity"]["id"]
            with self.subTest(skill=skill_id):
                row = self.matrix.get(skill_id)
                self.assertIsNotNone(row)
                self.assertEqual(set(row), {
                    "fixture_profile",
                    "operators",
                    "state_classes",
                    "selectors",
                    "effect_kinds",
                    "trigger_kinds",
                    "categories",
                })
                self.assertEqual(
                    set(row["categories"]), set(CATEGORY_NAMES)
                )
                for category in CATEGORY_NAMES:
                    entry = row["categories"][category]
                    self.assertIn(entry["status"], {"pass", "n/a"})
                    if entry["status"] == "n/a":
                        self.assertTrue(entry["reason"])
                    else:
                        self.assertIsNone(entry["reason"])
        self.assertEqual(
            {
                operator
                for row in self.matrix.values()
                for operator in row["operators"]
            },
            set(OPERATOR_KINDS),
        )
        self.assertEqual(
            {
                state_class
                for row in self.matrix.values()
                for state_class in row["state_classes"]
            },
            set(STATE_CLASS_KINDS),
        )
        self.assertEqual(
            {
                selector
                for row in self.matrix.values()
                for selector in row["selectors"]
            },
            set(SELECTOR_KINDS),
        )


if __name__ == "__main__":
    unittest.main()
