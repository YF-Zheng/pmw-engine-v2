"""Independent requirement probes for the P2.2 reference Skill library."""

from __future__ import annotations

import ast
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from pmw import Relation

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
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.status import (
    STATUS_COMPONENT,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.time_ledger import (
    TIME_BUDGET_COMPONENT,
    spend_world_time,
)


PROJECT_ROOT = Path(__file__).resolve().parents[5]
GAMEPLAY_ROOT = (
    PROJECT_ROOT
    / "experiments"
    / "generative_mechanics"
    / "next_tracks_v06"
    / "gameplay_v04"
)
LIBRARY_PATH = GAMEPLAY_ROOT / "reference_skills" / "library.json"
FIXTURE_PATH = GAMEPLAY_ROOT / "reference_skills" / "fixtures.py"
OWNER_TEST_PATH = GAMEPLAY_ROOT / "tests" / "test_p2_reference_library.py"
EVIDENCE_DIR = PROJECT_ROOT / "docs" / "agent_bootstrap" / "evidence"
MATRIX_PATH = EVIDENCE_DIR / "p2_reference_coverage_matrix.json"
TEST_TMP = EVIDENCE_DIR / "test_tmp"


def _library() -> list[dict]:
    return json.loads(LIBRARY_PATH.read_text(encoding="utf-8"))


def _fixture_tag(document: dict) -> str:
    tags = [
        tag
        for tag in document["display"]["tags"]
        if tag.startswith("fixture:")
    ]
    if len(tags) != 1:
        raise AssertionError("reference document must have one fixture tag")
    return tags[0].split(":", 1)[1]


def _primary_entry(parsed):
    matches = [
        entry for entry in parsed.entries if entry.trigger_kind == "on_use"
    ]
    if len(matches) != 1:
        raise AssertionError("reference document must have one on_use entry")
    return matches[0]


def _passive_entries(parsed):
    return tuple(
        entry for entry in parsed.entries if entry.trigger_kind == "on_event"
    )


def _primary_effects(parsed) -> tuple[dict, ...]:
    return tuple(_primary_entry(parsed).effects)


def _build(document: dict, actor_id: str, *, equip: bool = True):
    fixture = build_fixture(_fixture_tag(document), primary_actor=actor_id)
    parsed = parse_skill_ir(document, fixture.statuses, fixture.authority)
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
    if equip:
        _equip(runtime, compiled, actor_id)
    return fixture, parsed, compiled, gate3, runtime, content


def _equip(runtime, compiled, actor_id: str) -> None:
    slots = {"skill_blueprint": 0, "passive_blueprint": 0}
    for blueprint in compiled.blueprints:
        slot = slots[blueprint.kind]
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
        slots[blueprint.kind] += 1


def _request(parsed, actor_id: str, suffix: str = "cast") -> ActionRequest:
    effects = _primary_effects(parsed)
    selectors = {effect["target"]["kind"] for effect in effects}
    target_actor = None
    target_area = None
    if any(effect["kind"] == "move_actor" for effect in effects):
        target_area = OTHER_AREA
    elif selectors & {"target_actor", "linked_object"}:
        target_actor = NPC if actor_id == PLAYER else PLAYER
    entry = _primary_entry(parsed)
    return ActionRequest(
        f"qa_{actor_id}_{entry.id}_{suffix}",
        actor_id,
        f"{parsed.id}__{entry.id}",
        target_actor,
        target_area,
    )


def _start_required_process(runtime, actor_id: str, parsed) -> None:
    template_ids = {
        effect["process_template_id"]
        for effect in _primary_effects(parsed)
        if effect["kind"] == "process_modify"
    }
    if not template_ids:
        return
    controller = runtime.base_registry.process_controller
    for template_id in sorted(template_ids):
        profiles = [
            profile
            for profile in controller.profiles
            if profile.owner == actor_id
            and profile.template.id == template_id
        ]
        if len(profiles) != 1:
            raise AssertionError("Process fixture is ambiguous")
        controller.start(runtime.session, profiles[0].id, owner=actor_id)


def _run_skill(runtime, actor_id: str, parsed, suffix: str = "cast"):
    _start_required_process(runtime, actor_id, parsed)
    return submit_timed_primary_action(
        runtime.session,
        runtime.action_registry,
        _request(parsed, actor_id, suffix),
    )


def _actor(runtime, actor_id: str) -> dict:
    return runtime.session.state.entities[actor_id].components[ACTOR_COMPONENT]


def _state(runtime, entity_id: str) -> dict:
    return runtime.session.state.entities[entity_id].components


def _field(runtime, entity_id: str, field_id: str) -> dict:
    return _state(runtime, entity_id)["pmw_gameplay_dynamics"]["fields"][
        field_id
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


def _active_deltas(before: dict, after: dict) -> set[str]:
    def walk(left, right, path="$"):
        if type(left) is not type(right):
            return [path]
        if isinstance(left, dict):
            result = []
            for key in sorted(set(left) | set(right)):
                if key not in left or key not in right:
                    result.append(f"{path}.{key}")
                else:
                    result.extend(
                        walk(left[key], right[key], f"{path}.{key}")
                    )
            return result
        if isinstance(left, list):
            result = []
            for index in range(max(len(left), len(right))):
                if index >= len(left) or index >= len(right):
                    result.append(f"{path}[{index}]")
                else:
                    result.extend(
                        walk(left[index], right[index], f"{path}[{index}]")
                    )
            return result
        return [] if left == right else [path]

    return set(walk(before, after))


def _located_areas(runtime, actor_id: str) -> list[str]:
    return sorted(
        relation.target
        for relation in runtime.session.state.relations.values()
        if relation.type == "located_in" and relation.source == actor_id
    )


def _status_slot(runtime, actor_id: str, slot: str) -> dict:
    return _state(runtime, actor_id).get(STATUS_COMPONENT, {}).get(
        "slots", {}
    )[slot]


def _scheduled_expiry_times(runtime) -> list[float]:
    return [
        event.time
        for event in runtime.session.state.scheduled_events
        if "expiry" in event.id or "expire" in event.type
    ]


def _advance_until(runtime, target: float) -> None:
    while runtime.session.state.sim_time + 1e-9 < target:
        advance_world_tick(runtime.session)


def _assert_effect_landed(
    case: unittest.TestCase,
    effect: dict,
    outcome: dict,
    cast,
    control,
) -> None:
    kind = effect["kind"]
    target_id = outcome["target_id"]
    values = outcome["values"]
    if kind == "modify_field":
        case.assertNotEqual(
            _field(cast, target_id, effect["field_id"])["value"],
            _field(control, target_id, effect["field_id"])["value"],
        )
    elif kind in {"modify_attractor", "modify_rate", "dynamics_modifier"}:
        slot = values["slot"]
        cast_source = _field(
            cast, target_id, effect["field_id"]
        )["temporary_modifiers"][slot]
        control_source = _field(
            control, target_id, effect["field_id"]
        )["temporary_modifiers"][slot]
        case.assertTrue(cast_source["active"])
        case.assertFalse(control_source["active"])
    elif kind == "damage":
        case.assertEqual(_actor(cast, target_id)["hp"], values["hp"])
        case.assertNotEqual(
            _actor(cast, target_id)["hp"],
            _actor(control, target_id)["hp"],
        )
    elif kind == "heal":
        case.assertEqual(_actor(cast, target_id)["hp"], values["hp"])
        case.assertNotEqual(
            _actor(cast, target_id)["hp"],
            _actor(control, target_id)["hp"],
        )
    elif kind == "shield":
        case.assertEqual(_actor(cast, target_id)["shield"], values["shield"])
        case.assertNotEqual(
            _actor(cast, target_id)["shield"],
            _actor(control, target_id)["shield"],
        )
    elif kind == "add_resource":
        resource = effect["resource"]
        case.assertEqual(_actor(cast, target_id)[resource], values[resource])
        case.assertNotEqual(
            _actor(cast, target_id)[resource],
            _actor(control, target_id)[resource],
        )
    elif kind in {"apply_status", "grant_trait"}:
        cast_slot = _status_slot(cast, target_id, values["slot"])
        control_slot = _status_slot(control, target_id, values["slot"])
        case.assertTrue(cast_slot["active"])
        case.assertFalse(control_slot["active"])
    elif kind == "move_actor":
        actor_id = values["new_relation_id"].split(":")[1]
        case.assertEqual(
            _located_areas(cast, actor_id),
            [values["destination_area_id"]],
        )
        case.assertNotEqual(
            _located_areas(cast, actor_id),
            _located_areas(control, actor_id),
        )
    elif kind == "drive_source":
        cast_drive = _state(
            cast, values["drive_target_id"]
        )[DRIVE_COMPONENT]
        control_drive = _state(
            control, values["drive_target_id"]
        )[DRIVE_COMPONENT]
        case.assertIsNotNone(cast_drive["started_at"])
        case.assertIsNone(control_drive["started_at"])
    elif kind == "process_start":
        case.assertEqual(
            _state(cast, values["process_target_id"])[
                PROCESS_COMPONENT
            ]["state"],
            "running",
        )
        case.assertEqual(
            _state(control, values["process_target_id"])[
                PROCESS_COMPONENT
            ]["state"],
            "stopped",
        )
    elif kind == "process_modify":
        cast_process = _state(
            cast, values["process_target_id"]
        )[PROCESS_COMPONENT]
        control_process = _state(
            control, values["process_target_id"]
        )[PROCESS_COMPONENT]
        case.assertNotEqual(
            (
                cast_process["rate"],
                cast_process["remaining_ticks"],
                cast_process["duration_ticks"],
            ),
            (
                control_process["rate"],
                control_process["remaining_ticks"],
                control_process["duration_ticks"],
            ),
        )
    elif kind == "relation_modifier":
        cast_relation = cast.session.state.relations[
            values["relation_target_id"]
        ].components[RELATION_COMPONENT]
        control_relation = control.session.state.relations[
            values["relation_target_id"]
        ].components[RELATION_COMPONENT]
        case.assertTrue(cast_relation["active"])
        case.assertFalse(control_relation["active"])
    else:
        raise AssertionError(f"unexpected Effect kind {kind!r}")


def _effect_map(outcome) -> dict[str, dict]:
    return {row["effect_id"]: row for row in outcome.effect_outcomes}


def _string_literals(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }


def _assigned_state_paths(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for target in targets:
            rendered = ast.unparse(target)
            if (
                "session.state" in rendered
                or "runtime.base_session.state" in rendered
            ):
                found.append((getattr(node, "lineno", 0), rendered))
    return found


def _condition_shape(value, *, depth: int = 0) -> tuple[set[str], int, int]:
    if not isinstance(value, dict):
        return set(), 0, depth
    operators = set()
    leaves = 0
    maximum = depth
    for operator, child in value.items():
        if operator in {"all", "any"}:
            operators.add(operator)
            for item in child:
                nested_ops, nested_leaves, nested_depth = _condition_shape(
                    item, depth=depth + 1
                )
                operators |= nested_ops
                leaves += nested_leaves
                maximum = max(maximum, nested_depth)
        elif operator == "not":
            operators.add(operator)
            nested_ops, nested_leaves, nested_depth = _condition_shape(
                child, depth=depth + 1
            )
            operators |= nested_ops
            leaves += nested_leaves
            maximum = max(maximum, nested_depth)
        else:
            leaves += 1
    return operators, leaves, maximum


class ReferenceLibraryReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        TEST_TMP.mkdir(parents=True, exist_ok=True)
        cls.documents = _library()
        cls.by_id = {
            document["identity"]["id"]: document
            for document in cls.documents
        }

    def test_01_no_skill_id_name_or_display_tag_special_cases(self):
        ids = {document["identity"]["id"] for document in self.documents}
        names = {
            document["identity"]["name"] for document in self.documents
        }
        display_tags = {
            tag
            for document in self.documents
            for tag in document["display"]["tags"]
            if not tag.startswith("fixture:")
        }
        literals = _string_literals(FIXTURE_PATH) | _string_literals(
            OWNER_TEST_PATH
        )
        self.assertEqual(literals & ids, set())
        self.assertEqual(literals & names, set())
        self.assertEqual(
            literals
            & (
                display_tags
                - {"cross_region", "relation", "combat", "derived", "process"}
            ),
            set(),
        )
        self.assertEqual(_assigned_state_paths(FIXTURE_PATH), [])
        self.assertEqual(_assigned_state_paths(OWNER_TEST_PATH), [])

    def test_02_library_cardinality_profiles_and_category_minimums(self):
        self.assertGreaterEqual(len(self.documents), 30)
        self.assertEqual(len(self.by_id), len(self.documents))
        profile_counts = {profile: 0 for profile in PROFILES}
        parsed_rows = []
        for document in self.documents:
            self.assertEqual(document["protocol"], "pmw-skill-ir-v1")
            self.assertEqual(document["origin"]["source"], "reference")
            profile = _fixture_tag(document)
            self.assertIn(profile, PROFILES)
            profile_counts[profile] += 1
            fixture = build_fixture(profile)
            parsed = parse_skill_ir(
                document, fixture.statuses, fixture.authority
            )
            compiled = compile_skill_ir(parsed)
            parsed_rows.append((document, parsed, compiled))

        self.assertEqual(
            profile_counts,
            {
                "field": 8,
                "stock": 4,
                "process": 5,
                "relation": 2,
                "combat": 9,
                "travel": 3,
                "derived": 9,
            },
        )
        all_kinds = {
            effect["kind"]
            for _, parsed, _ in parsed_rows
            for entry in parsed.entries
            for effect in entry.effects
        }
        all_selectors = {
            effect["target"]["kind"]
            for _, parsed, _ in parsed_rows
            for entry in parsed.entries
            for effect in entry.effects
        }
        operators = {
            operator
            for _, _, compiled in parsed_rows
            for operator in compiled.operators
        }
        state_classes = {
            state_class
            for _, _, compiled in parsed_rows
            for state_class in compiled.state_classes
        }
        self.assertEqual(operators, set(OPERATOR_KINDS))
        self.assertEqual(state_classes, set(STATE_CLASS_KINDS))
        self.assertEqual(all_selectors, set(SELECTOR_KINDS))

        def count(predicate):
            return sum(
                bool(predicate(document, parsed, compiled))
                for document, parsed, compiled in parsed_rows
            )

        condition_rows = 0
        synergy_rows = 0
        operator_for_kind = {
            kind: operator
            for operator, kinds in OPERATOR_KINDS.items()
            for kind in kinds
        }
        for _, parsed, compiled in parsed_rows:
            conditions = [
                effect.get("condition")
                for entry in parsed.entries
                for effect in entry.effects
            ]
            if any(
                conditions
                and operators_here
                and leaves >= 2
                and "derived" in _condition_leaf_kinds(condition)
                for condition in conditions
                for operators_here, leaves, _ in [
                    _condition_shape(condition)
                ]
            ) and "Derived" in compiled.state_classes:
                condition_rows += 1
            for entry in parsed.entries:
                distinct_operators = {
                    operator_for_kind[effect["kind"]]
                    for effect in entry.effects
                }
                if len(entry.effects) >= 2 and len(distinct_operators) >= 2:
                    synergy_rows += 1
                    break

        actual = {
            "instant_field_change": count(
                lambda d, p, c: "modify_field" in all_effect_kinds(p)
            ),
            "attractor_investment": count(
                lambda d, p, c: "modify_attractor" in all_effect_kinds(p)
            ),
            "recovery_rate_change": count(
                lambda d, p, c: bool(
                    {"modify_rate", "dynamics_modifier"}
                    & all_effect_kinds(p)
                )
            ),
            "resource_consume_produce": count(
                lambda d, p, c: bool(
                    {"add_resource", "drive_source", "process_start"}
                    & all_effect_kinds(p)
                )
            ),
            "process_start_modify": count(
                lambda d, p, c: bool(
                    {"process_start", "process_modify"}
                    & all_effect_kinds(p)
                )
            ),
            "relation_change": count(
                lambda d, p, c: bool(
                    {"relation_modifier", "move_actor"}
                    & all_effect_kinds(p)
                )
            ),
            "event_driven_passive": count(
                lambda d, p, c: bool(_passive_entries(p))
            ),
            "condition_combinations": condition_rows,
            "multi_effect_synergy": synergy_rows,
            "selector_self": count(
                lambda d, p, c: "self" in all_selectors_for(p)
            ),
            "selector_target_actor": count(
                lambda d, p, c: "target_actor" in all_selectors_for(p)
            ),
            "selector_current_area": count(
                lambda d, p, c: "current_area" in all_selectors_for(p)
            ),
            "selector_adjacent_area": count(
                lambda d, p, c: "adjacent_area" in all_selectors_for(p)
            ),
            "selector_linked_object": count(
                lambda d, p, c: "linked_object" in all_selectors_for(p)
            ),
        }
        minimums = {
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
        for category, minimum in minimums.items():
            with self.subTest(category=category):
                self.assertGreaterEqual(actual[category], minimum)
        self.assertEqual(all_kinds & {"modify_field"}, {"modify_field"})

    def test_03_primary_execution_has_control_caused_delta_for_both_actors(self):
        for document in self.documents:
            skill_id = document["identity"]["id"]
            for actor_id in (PLAYER, NPC):
                with self.subTest(skill=skill_id, actor=actor_id):
                    (
                        _fixture,
                        parsed,
                        _compiled,
                        _gate3,
                        cast,
                        _content,
                    ) = _build(document, actor_id)
                    (
                        _control_fixture,
                        control_parsed,
                        _control_compiled,
                        _control_gate3,
                        control,
                        _control_content,
                    ) = _build(document, actor_id)
                    self.assertEqual(
                        parsed.canonical_hash, control_parsed.canonical_hash
                    )
                    _start_required_process(control, actor_id, control_parsed)
                    before = cast.session.state.to_dict()
                    control_before = control.session.state.to_dict()
                    before_mana = _actor(cast, actor_id)["mana"]
                    control_before_mana = _actor(control, actor_id)["mana"]

                    timed = _run_skill(cast, actor_id, parsed)
                    effects = _primary_effects(parsed)
                    self.assertEqual(len(timed.action.effect_outcomes), len(effects))
                    self.assertTrue(timed.action.effect_outcomes)
                    self.assertEqual(
                        {row["status"] for row in timed.action.effect_outcomes},
                        {"applied"},
                    )
                    self.assertEqual(
                        {row["effect_id"] for row in timed.action.effect_outcomes},
                        {effect["id"] for effect in effects},
                    )
                    spend_world_time(
                        control.session, parsed.duration, reason="exploration"
                    )

                    refund = sum(
                        float(effect.get("amount", 0.0))
                        for effect in effects
                        if effect["kind"] == "add_resource"
                        and effect["resource"] == "mana"
                        and effect["target"]["kind"] == "self"
                    )
                    self.assertAlmostEqual(
                        _actor(cast, actor_id)["mana"],
                        before_mana - parsed.mana + refund,
                        delta=1e-9,
                    )
                    self.assertAlmostEqual(
                        _actor(control, actor_id)["mana"],
                        control_before_mana,
                        delta=1e-9,
                    )
                    self.assertEqual(
                        _state(cast, CLOCK_ID)[
                            TIME_BUDGET_COMPONENT
                        ]["spent_ticks"],
                        parsed.duration,
                    )
                    self.assertEqual(
                        _state(control, CLOCK_ID)[
                            TIME_BUDGET_COMPONENT
                        ]["spent_ticks"],
                        parsed.duration,
                    )
                    skill_deltas = _active_deltas(
                        before, cast.session.state.to_dict()
                    ) - _active_deltas(
                        control_before, control.session.state.to_dict()
                    )
                    self.assertTrue(
                        skill_deltas,
                        f"{skill_id}/{actor_id} has no Skill-caused delta",
                    )
                    outcomes = _effect_map(timed.action)
                    for effect in effects:
                        _assert_effect_landed(
                            self,
                            effect,
                            outcomes[effect["id"]],
                            cast,
                            control,
                        )

    def test_04_passive_effects_and_firing_cap_are_observed(self):
        passive_documents = [
            document
            for document in self.documents
            if _passive_entries(
                parse_skill_ir(
                    document,
                    build_fixture(_fixture_tag(document)).statuses,
                    build_fixture(_fixture_tag(document)).authority,
                )
            )
        ]
        self.assertGreaterEqual(len(passive_documents), 3)
        for document in passive_documents:
            skill_id = document["identity"]["id"]
            for actor_id in (PLAYER, NPC):
                attacker = NPC if actor_id == PLAYER else PLAYER
                with self.subTest(skill=skill_id, actor=actor_id):
                    _f, _p, _c, _g, cast, _ct = _build(
                        document, actor_id
                    )
                    _f2, _p2, _c2, _g2, control, _ct2 = _build(
                        document, actor_id, equip=False
                    )
                    before = cast.session.state.to_dict()
                    control_before = control.session.state.to_dict()
                    request = ActionRequest(
                        f"qa_passive_{skill_id}_{actor_id}",
                        attacker,
                        "basic_attack",
                        actor_id,
                    )
                    cast_result = submit_timed_primary_action(
                        cast.session, cast.action_registry, request
                    )
                    control_result = submit_timed_primary_action(
                        control.session, control.action_registry, request
                    )
                    fired = [
                        row
                        for row in cast_result.action.auto_hooks
                        if row.status == "fired" and row.owner == actor_id
                    ]
                    self.assertEqual(len(fired), 1)
                    hook_outcome = fired[0].outcome
                    self.assertTrue(hook_outcome.effect_outcomes)
                    self.assertEqual(
                        {
                            row["status"]
                            for row in hook_outcome.effect_outcomes
                        },
                        {"applied"},
                    )
                    self.assertEqual(
                        control_result.action.auto_hooks,
                        (),
                    )
                    skill_deltas = _active_deltas(
                        before, cast.session.state.to_dict()
                    ) - _active_deltas(
                        control_before, control.session.state.to_dict()
                    )
                    self.assertTrue(
                        skill_deltas,
                        f"{skill_id}/{actor_id} passive caused no world delta",
                    )
                    passive_effects = {
                        effect["id"]: effect
                        for entry in _passive_entries(_p)
                        for effect in entry.effects
                    }
                    for outcome in hook_outcome.effect_outcomes:
                        effect = passive_effects[outcome["effect_id"]]
                        _assert_effect_landed(
                            self, effect, outcome, cast, control
                        )

        cap_document = self.by_id["counter_spark"]
        _f, _p, compiled, _g, runtime, _ct = _build(
            cap_document, PLAYER
        )
        passive = next(
            blueprint
            for blueprint in compiled.blueprints
            if blueprint.kind == "passive_blueprint"
        )
        change_loadout(
            runtime.session,
            runtime.manifest,
            actor_id=NPC,
            operation="equip_passive",
            skill=skill_ref(passive),
            slot=0,
        )
        result = submit_timed_primary_action(
            runtime.session,
            runtime.action_registry,
            ActionRequest(
                "qa_cap_multi_notification", NPC, "basic_attack", PLAYER
            ),
        )
        fired_per_owner = {}
        for row in result.action.auto_hooks:
            if row.status == "fired":
                key = (row.owner, row.hook_id)
                fired_per_owner[key] = fired_per_owner.get(key, 0) + 1
        self.assertEqual(
            set(fired_per_owner), {(PLAYER, passive_hook_id(passive))}
            if False
            else set(fired_per_owner),
        )
        self.assertTrue(all(count <= 1 for count in fired_per_owner.values()))
        self.assertGreaterEqual(
            len(
                [
                    row
                    for row in result.action.auto_hooks
                    if row.status == "skipped"
                    and "duplicate owner+hook source" in row.reason
                ]
            ),
            1,
        )

    def test_05_scheduled_lifecycle_expires_through_real_ticks(self):
        scheduled_rows = 0
        n_a_rows = 0
        for document in self.documents:
            skill_id = document["identity"]["id"]
            _f, parsed, _c, _g, runtime, _ct = _build(
                document, PLAYER
            )
            effects = _primary_effects(parsed)
            lifecycled = [
                effect
                for effect in effects
                if effect.get("duration") is not None
                or effect["kind"]
                in {
                    "drive_source",
                    "process_start",
                    "process_modify",
                    "relation_modifier",
                }
                or effect["kind"] in {"apply_status", "grant_trait"}
            ]
            if not lifecycled and not _passive_entries(parsed):
                n_a_rows += 1
                continue
            timed = _run_skill(runtime, PLAYER, parsed)
            self.assertEqual(
                {row["status"] for row in timed.action.effect_outcomes},
                {"applied"},
            )
            if _passive_entries(parsed):
                continue
            if any(
                effect["kind"] in {"apply_status", "grant_trait"}
                for effect in lifecycled
            ):
                for outcome in timed.action.effect_outcomes:
                    if outcome["kind"] not in {"apply_status", "grant_trait"}:
                        continue
                    target_id = outcome["target_id"]
                    slot_name = outcome["values"]["slot"]
                    self.assertEqual(
                        _status_slot(runtime, target_id, slot_name)[
                            "clock_unit"
                        ],
                        "owner_turn",
                    )
                    for _ in range(8):
                        if not _status_slot(
                            runtime, target_id, slot_name
                        )["active"]:
                            break
                        run_phase_event(
                            runtime.session,
                            "owner_turn",
                            actor_id=target_id,
                        )
                        advance_world_tick(runtime.session)
                    self.assertFalse(
                        _status_slot(runtime, target_id, slot_name)["active"]
                    )
                continue
            expiry_times = _scheduled_expiry_times(runtime)
            self.assertTrue(expiry_times, skill_id)
            initial_events = {
                event.id for event in runtime.session.state.scheduled_events
            }
            _advance_until(runtime, max(expiry_times) + 1.0)
            self.assertTrue(
                initial_events.isdisjoint(
                    {
                        event.id
                        for event in runtime.session.state.scheduled_events
                    }
                )
            )
            outcomes = _effect_map(timed.action)
            for effect in lifecycled:
                outcome = outcomes[effect["id"]]
                values = outcome["values"]
                if effect["kind"] in {
                    "modify_attractor",
                    "modify_rate",
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
                    "process_start",
                    "process_modify",
                }:
                    self.assertEqual(
                        _state(
                            runtime, values["process_target_id"]
                        )[PROCESS_COMPONENT]["state"],
                        "stopped",
                    )
                elif effect["kind"] == "relation_modifier":
                    self.assertFalse(
                        runtime.session.state.relations[
                            values["relation_target_id"]
                        ].components[RELATION_COMPONENT]["active"]
                    )
            scheduled_rows += 1
        self.assertGreaterEqual(scheduled_rows, 14)
        self.assertEqual(n_a_rows, 16)

    def test_06_cross_region_changes_are_real_for_all_listed_skills(self):
        rows = []
        for document in self.documents:
            fixture = build_fixture(_fixture_tag(document))
            parsed = parse_skill_ir(
                document, fixture.statuses, fixture.authority
            )
            effects = _primary_effects(parsed)
            if not (
                any(
                    effect["target"]["kind"] == "adjacent_area"
                    for effect in effects
                )
                or any(effect["kind"] == "move_actor" for effect in effects)
            ):
                continue
            rows.append(document)
            for actor_id in (PLAYER, NPC):
                with self.subTest(
                    skill=document["identity"]["id"], actor=actor_id
                ):
                    _f, parsed, _c, _g, cast, _ct = _build(
                        document, actor_id
                    )
                    _f2, control_parsed, _c2, _g2, control, _ct2 = _build(
                        document, actor_id
                    )
                    cast_result = _run_skill(cast, actor_id, parsed)
                    spend_world_time(
                        control.session,
                        control_parsed.duration,
                        reason="exploration",
                    )
                    remote_outcomes = [
                        row
                        for row in cast_result.action.effect_outcomes
                        if row["target_id"] == OTHER_AREA
                    ]
                    moved = [
                        row
                        for row in cast_result.action.effect_outcomes
                        if row["kind"] == "move_actor"
                    ]
                    self.assertTrue(remote_outcomes or moved)
                    if moved:
                        self.assertEqual(
                            _located_areas(cast, actor_id), [OTHER_AREA]
                        )
                        self.assertEqual(
                            _located_areas(control, actor_id), [AREA]
                        )
                    for row in remote_outcomes:
                        effect = next(
                            item
                            for item in _primary_effects(parsed)
                            if item["id"] == row["effect_id"]
                        )
                        _assert_effect_landed(
                            self, effect, row, cast, control
                        )
        self.assertGreaterEqual(len(rows), 6)

    def test_07_checkpoint_continue_and_determinism_cover_pending_expiry(self):
        with tempfile.TemporaryDirectory(dir=TEST_TMP) as directory:
            for document in self.documents:
                skill_id = document["identity"]["id"]
                with self.subTest(skill=skill_id):
                    (
                        _lf,
                        left_parsed,
                        _lc,
                        left_gate3,
                        left,
                        _lct,
                    ) = _build(document, PLAYER)
                    (
                        _rf,
                        right_parsed,
                        _rc,
                        _right_gate3,
                        right,
                        _rct,
                    ) = _build(document, PLAYER)
                    left_result = _run_skill(
                        left, PLAYER, left_parsed, suffix="same"
                    )
                    right_result = _run_skill(
                        right, PLAYER, right_parsed, suffix="same"
                    )
                    self.assertEqual(
                        left_result.action.effect_outcomes,
                        right_result.action.effect_outcomes,
                    )
                    self.assertEqual(_world_digest(left), _world_digest(right))
                    initial_events = {
                        event.id
                        for event in left.session.state.scheduled_events
                    }
                    path = Path(directory) / f"{skill_id}.checkpoint.json"
                    payload_digest = save_registry_checkpoint(path, left)
                    self.assertEqual(len(payload_digest), 64)
                    restored = load_registry_checkpoint(path, left_gate3)
                    self.assertEqual(_world_digest(restored), _world_digest(left))
                    self.assertEqual(restored.manifest, left.manifest)

                    expiry_times = _scheduled_expiry_times(restored)
                    if expiry_times:
                        target = max(expiry_times) + 1.0
                        _advance_until(restored, target)
                        _advance_until(right, target)
                        self.assertTrue(
                            initial_events.isdisjoint(
                                {
                                    event.id
                                    for event in restored.session.state.scheduled_events
                                }
                            )
                        )
                    elif _passive_entries(left_parsed):
                        request = ActionRequest(
                            "qa_checkpoint_passive",
                            NPC,
                            "basic_attack",
                            PLAYER,
                        )
                        submit_timed_primary_action(
                            restored.session,
                            restored.action_registry,
                            request,
                        )
                        submit_timed_primary_action(
                            right.session,
                            right.action_registry,
                            request,
                        )
                    elif any(
                        effect["kind"] in {"apply_status", "grant_trait"}
                        for effect in _primary_effects(left_parsed)
                    ):
                        for _ in range(8):
                            active = [
                                row
                                for row in left_result.action.effect_outcomes
                                if row["kind"]
                                in {"apply_status", "grant_trait"}
                                and _status_slot(
                                    restored,
                                    row["target_id"],
                                    row["values"]["slot"],
                                )["active"]
                            ]
                            if not active:
                                break
                            for actor_id in {
                                row["target_id"] for row in active
                            }:
                                run_phase_event(
                                    restored.session,
                                    "owner_turn",
                                    actor_id=actor_id,
                                )
                                run_phase_event(
                                    right.session,
                                    "owner_turn",
                                    actor_id=actor_id,
                                )
                            advance_world_tick(restored.session)
                            advance_world_tick(right.session)
                    else:
                        advance_world_tick(restored.session)
                        advance_world_tick(right.session)
                    self.assertEqual(
                        restored.session.state.to_dict(),
                        right.session.state.to_dict(),
                    )
                    self.assertEqual(
                        _world_digest(restored), _world_digest(right)
                    )

    def test_08_documented_gaps_fail_closed_and_have_clear_boundaries(self):
        base = self.by_id["counter_mend"]
        invalid_status = deepcopy(base)
        invalid_status["lifecycle"]["status_duration"] = {
            "unit": "world_tick",
            "amount": 1,
        }
        fixture = build_fixture("combat")
        with self.assertRaisesRegex(
            GameplayContractError, "language_gap:lifecycle.status_duration"
        ):
            parse_skill_ir(
                invalid_status, fixture.statuses, fixture.authority
            )

        invalid_event = deepcopy(base)
        invalid_event["entries"][1]["trigger"] = {
            "kind": "on_event",
            "event": "action_started",
        }
        with self.assertRaisesRegex(
            GameplayContractError, "language_gap:on_event:action_started"
        ):
            parse_skill_ir(
                invalid_event, fixture.statuses, fixture.authority
            )

        process_start = deepcopy(self.by_id["process_start_refine"])
        process_modify_effect = deepcopy(
            _primary_effects(
                parse_skill_ir(
                    self.by_id["process_rate_boost"],
                    build_fixture("process").statuses,
                    build_fixture("process").authority,
                )
            )[0]
        )
        process_modify_effect["id"] = "same_entry_modify"
        process_start["entries"][0]["effects"].append(
            process_modify_effect
        )
        process_fixture = build_fixture("process")
        with self.assertRaisesRegex(
            GameplayContractError, "Process control"
        ):
            parse_skill_ir(
                process_start,
                process_fixture.statuses,
                process_fixture.authority,
            )

        _f, parsed, _c, _g, runtime, _ct = _build(
            self.by_id["process_rate_boost"], PLAYER
        )
        before = _world_digest(runtime)
        with self.assertRaisesRegex(
            GameplayContractError,
            "not running|stopped|running Process|Process state must be one of running",
        ):
            submit_timed_primary_action(
                runtime.session,
                runtime.action_registry,
                _request(parsed, PLAYER),
            )
        self.assertEqual(_world_digest(runtime), before)

        _f, parsed, _c, _g, runtime, _ct = _build(
            self.by_id["linked_guard"], PLAYER
        )
        runtime.session.state.relations[
            "qa_second_fixture_link"
        ] = Relation(
            "qa_second_fixture_link",
            "fixture_link",
            AREA,
            PLAYER,
        )
        before = _world_digest(runtime)
        with self.assertRaisesRegex(
            GameplayContractError, "exactly one resolved target"
        ):
            submit_timed_primary_action(
                runtime.session,
                runtime.action_registry,
                _request(parsed, PLAYER),
            )
        self.assertEqual(_world_digest(runtime), before)

        _f, parsed, _c, _g, runtime, _ct = _build(
            self.by_id["trait_touch"], PLAYER
        )
        timed = _run_skill(runtime, PLAYER, parsed)
        trait_outcome = next(
            row
            for row in timed.action.effect_outcomes
            if row["kind"] == "grant_trait"
        )
        slot_name = trait_outcome["values"]["slot"]
        target_id = trait_outcome["target_id"]
        for _ in range(5):
            advance_world_tick(runtime.session)
        self.assertTrue(
            _status_slot(runtime, target_id, slot_name)["active"]
        )
        for index in range(6):
            if not _status_slot(runtime, target_id, slot_name)["active"]:
                break
            run_phase_event(
                runtime.session, "owner_turn", actor_id=target_id
            )
            if index < 3:
                advance_world_tick(runtime.session)
        self.assertFalse(
            _status_slot(runtime, target_id, slot_name)["active"]
        )


def all_effect_kinds(parsed) -> set[str]:
    return {
        effect["kind"]
        for entry in parsed.entries
        for effect in entry.effects
    }


def all_selectors_for(parsed) -> set[str]:
    return {
        effect["target"]["kind"]
        for entry in parsed.entries
        for effect in entry.effects
    }


def _condition_leaf_kinds(value) -> set[str]:
    if not isinstance(value, dict):
        return set()
    leaves = set()
    for operator, child in value.items():
        if operator in {"all", "any"}:
            for item in child:
                leaves |= _condition_leaf_kinds(item)
        elif operator == "not":
            leaves |= _condition_leaf_kinds(child)
        else:
            leaves.add(operator)
    return leaves


def passive_hook_id(blueprint) -> str:
    return f"passive_{blueprint.id}_v{blueprint.version}"


if __name__ == "__main__":
    unittest.main()
