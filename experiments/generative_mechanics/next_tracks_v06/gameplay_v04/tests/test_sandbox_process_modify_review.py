from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pmw import Relation

from experiments.generative_mechanics.next_tracks_v06.gameplay_v04 import (
    time_ledger,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.action_compiler import (
    build_action_laws,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.actions import (
    ActionRegistry,
    ActionRequest,
    resolve_action,
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
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.loadout import (
    change_loadout,
    skill_ref,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.materials import (
    material_authority,
    parse_material,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.observation import (
    ActorObservationBuilder,
    ObservationDisclosure,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.processes import (
    PROCESS_COMPONENT,
    PROCESS_MODIFY_EVENT,
    ProcessController,
    ProcessLimits,
    instantiate_process,
    stock_entity,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.runtime import (
    advance_world_tick,
    build_runtime,
    clock_entity,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.simulation import (
    SandboxSimulator,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.skills import (
    parse_skill_blueprint,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.tests.test_sandbox_process_action import (
    AREA_ID,
    NPC_ID,
    PLAYER_ID,
    SKILL_ID,
    TEMPLATE_ID,
    _blueprint,
    _area,
    _component,
    _profile,
    _revision,
    _state,
    _template,
    _world,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.time_ledger import (
    initialize_time_budget,
)


MODIFY_SKILL_ID = "adjust_refining"
SHORTEN_SKILL_ID = "shorten_refining"
EXTEND_SKILL_ID = "extend_refining"
BEYOND_SKILL_ID = "beyond_refining"
SAME_RATE_SKILL_ID = "same_rate_refining"


def _process_material(*effect_kinds: str, budget: float = 5.0):
    return parse_material({
        "id": "process_crystal",
        "tier": "rare",
        "region_rarity": "scarce",
        "traits": [{
            "id": "process_shaping",
            "effect_kinds": list(effect_kinds),
            "selectors": ["current_area"],
            "budget_points": budget,
        }],
    })


def _modify_document(
    *,
    skill_id: str = MODIFY_SKILL_ID,
    template_id: str = TEMPLATE_ID,
    rate: float | None = 1.5,
    remaining_ticks: int | None = None,
    fields: dict | None = None,
    duration: int = 1,
    omit_process_rate: bool = False,
) -> dict:
    effect = {
        "id": "adjust",
        "kind": "process_modify",
        "target": {"kind": "current_area"},
        "commitment": "required",
        "process_template_id": template_id,
    }
    if not omit_process_rate:
        effect["process_rate"] = rate
    if remaining_ticks is not None:
        effect["process_remaining_ticks"] = remaining_ticks
    if fields is not None:
        effect.update(fields)
    return {
        "protocol": "pmw-gameplay-v0.4",
        "kind": "skill_blueprint",
        "id": skill_id,
        "version": 1,
        "trigger": "on_use",
        "condition": None,
        "duration": None,
        "cost": {"duration": duration, "mana": 1},
        "scope": {"selectors": ["current_area"], "relation_types": []},
        "effects": [effect],
        "budget": {"limit": 5},
        "max_firings_per_root": 1,
        "material_ids": ["process_crystal"],
    }


def _parse_modify(
    document: dict,
    *,
    effect_kinds: tuple[str, ...] = ("process_modify",),
    budget: float = 5.0,
):
    return parse_skill_blueprint(
        document,
        basic_registry().statuses,
        material_authority((_process_material(*effect_kinds, budget=budget),)),
    )


def _setup_modifier(
    profiles,
    *,
    time_budget: int | None = None,
    documents: tuple[dict, ...] = (),
    slots: dict[str, int] | None = None,
):
    from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.registry import (
        MechanismRegistryRuntime,
    )
    start_skill = _blueprint()
    modify_skills = tuple(
        _parse_modify(
            _modify_document(
                skill_id=skill_id,
                rate=rate,
                remaining_ticks=remaining,
                duration=duration,
            )
        )
        for skill_id, rate, remaining, duration in (
            (MODIFY_SKILL_ID, 1.5, 2, 1),
            (SHORTEN_SKILL_ID, 1.5, 2, 1),
            (EXTEND_SKILL_ID, 1.5, 4, 1),
            (BEYOND_SKILL_ID, 1.5, 5, 2),
            (SAME_RATE_SKILL_ID, 1.0, 1, 1),
        )
    )
    if documents:
        modify_skills = tuple(_parse_modify(document) for document in documents)
    skills = (start_skill, *modify_skills)
    controller = ProcessController(
        tuple(profiles),
        ProcessLimits(max_instances=8, max_active=8),
    )
    base = ActionRegistry(
        basic_registry().actions.values(),
        basic_registry().statuses.values(),
        process_controller=controller,
    )
    content = make_content(
        base,
        skills=skills,
        material_ids=("process_crystal",),
    )
    world = _world(tuple(profiles))
    world.entities["pmw:v04:clock"] = clock_entity()
    if time_budget is not None:
        world = initialize_time_budget(world, time_budget)
    world = initialize_content_world(world, content)
    compiled = compile_content(content)
    session = build_content_session(world, compiled)
    runtime = MechanismRegistryRuntime.from_compiled_content(session, compiled)
    active_slots = slots or {
        skill.id: index + 1
        for index, skill in enumerate(modify_skills)
    }
    for actor_id in (PLAYER_ID, NPC_ID):
        change_loadout(
            runtime.session,
            runtime.manifest,
            actor_id=actor_id,
            operation="equip_active",
            skill=skill_ref(start_skill),
            slot=0,
        )
        for skill in modify_skills:
            change_loadout(
                runtime.session,
                runtime.manifest,
                actor_id=actor_id,
                operation="equip_active",
                skill=skill_ref(skill),
                slot=active_slots[skill.id],
            )
    return runtime, compiled, start_skill, modify_skills


def _snapshot(runtime):
    session = runtime.session
    return {
        "state": deepcopy(_state(session)),
        "revision": deepcopy(_revision(session)),
        "scheduled": tuple(
            (event.id, event.type, event.time, deepcopy(event.payload))
            for event in session.state.scheduled_events
        ),
        "stats": deepcopy(session.runtime.stats),
        "runtime_id": id(session.runtime),
    }


def _amount(session, entity_id: str) -> float:
    return session.state.entities[entity_id].components["stock"]["amount"]


def _stock_ids(profile) -> tuple[str, ...]:
    return tuple(
        item.stock.entity_id for item in (*profile.inputs, *profile.outputs)
    )


def _relocate(session, entity_id: str, area_id: str) -> None:
    session.state.relations = {
        key: relation
        for key, relation in session.state.relations.items()
        if not (
            relation.type == "located_in"
            and relation.source == entity_id
            and relation.target == AREA_ID
        )
    }
    relation_id = f"review:located:{entity_id}:{area_id}"
    session.state.relations[relation_id] = Relation(
        relation_id, "located_in", entity_id, area_id
    )


def _add_area(session, area_id: str) -> None:
    if area_id not in session.state.entities:
        session.state.entities[area_id] = _area(area_id)


def _start_equipped(runtime, actor_id: str, request_id: str):
    return resolve_action(
        runtime.session,
        runtime.action_registry,
        ActionRequest(request_id, actor_id, SKILL_ID),
    )


def _modify(runtime, actor_id: str, request_id: str, *, timed: bool = False):
    request = ActionRequest(request_id, actor_id, MODIFY_SKILL_ID)
    if timed:
        return submit_timed_primary_action(
            runtime.session, runtime.action_registry, request
        )
    return resolve_action(runtime.session, runtime.action_registry, request)


class ProcessModificationIndependentReviewTests(unittest.TestCase):
    def test_data_skill_settles_player_and_npc_after_real_paid_ticks(self):
        template = replace(_template(), duration_ticks=6, max_duration_ticks=8)
        cases = (
            (PLAYER_ID, "player_rate_review", 0.5, 8.0, 1.0, 5.0, 2.5),
            (NPC_ID, "npc_rate_review", 0.75, 7.0, 1.5, 4.0, 3.0),
        )
        for (
            actor_id,
            profile_id,
            initial_rate,
            start_input,
            start_output,
            expected_input,
            expected_output,
        ) in cases:
            with self.subTest(actor_id=actor_id):
                profile = replace(
                    _profile(profile_id, actor_id),
                    template=template,
                    rate=initial_rate,
                )
                runtime, _, _, _ = _setup_modifier(
                    (profile,), time_budget=8
                )
                start = submit_timed_primary_action(
                    runtime.session,
                    runtime.action_registry,
                    ActionRequest(f"{actor_id}_start", actor_id, SKILL_ID),
                )
                self.assertEqual(start.time.duration, 2)
                before = _component(runtime.session, profile)
                self.assertEqual(before["rate"], initial_rate)
                self.assertEqual(before["remaining_ticks"], 1)
                self.assertEqual(
                    _amount(runtime.session, profile.inputs[0].stock.entity_id),
                    start_input,
                )
                self.assertEqual(
                    _amount(runtime.session, profile.outputs[0].stock.entity_id),
                    start_output,
                )

                modified = submit_timed_primary_action(
                    runtime.session,
                    runtime.action_registry,
                    ActionRequest(f"{actor_id}_modify", actor_id, MODIFY_SKILL_ID),
                )
                after = _component(runtime.session, profile)
                self.assertEqual(modified.time.duration, 1)
                self.assertEqual(after["rate"], 1.5)
                self.assertEqual(after["remaining_ticks"], 1)
                self.assertEqual(
                    _amount(runtime.session, profile.inputs[0].stock.entity_id),
                    expected_input,
                )
                self.assertEqual(
                    _amount(runtime.session, profile.outputs[0].stock.entity_id),
                    expected_output,
                )
                self.assertEqual(
                    runtime.session.state.entities[actor_id].components[
                        "pmw_gameplay_actor"
                    ]["mana"],
                    15.0,
                )
                budget = runtime.session.state.entities["pmw:v04:clock"].components[
                    "pmw_gameplay_time_budget"
                ]
                self.assertEqual(budget["remaining_ticks"], 5)

    def test_repeated_modification_keeps_hard_deadline_and_exact_expiry(self):
        template = replace(_template(), duration_ticks=3, max_duration_ticks=5)
        profile = replace(
            _profile("bounded_modify", PLAYER_ID),
            template=template,
            rate=0.5,
        )
        runtime, _, _, _ = _setup_modifier((profile,), time_budget=12)
        _start_equipped(runtime, PLAYER_ID, "bounded_start")
        started = _component(runtime.session, profile)
        hard_deadline = started["hard_deadline"]
        self.assertEqual(hard_deadline, 5.0)

        first = resolve_action(
            runtime.session,
            runtime.action_registry,
            ActionRequest("shorten_expiry", PLAYER_ID, SHORTEN_SKILL_ID),
        )
        self.assertEqual(first.effect_outcomes[0]["kind"], "process_modify")
        self.assertEqual(_component(runtime.session, profile)["remaining_ticks"], 2)
        self.assertEqual(
            [(event.id, event.time) for event in runtime.session.state.scheduled_events],
            [("pmw:v04:sandbox.process.expiry:bounded_modify", 2.0)],
        )
        self.assertEqual(_component(runtime.session, profile)["hard_deadline"], hard_deadline)

        advance_world_tick(runtime.session)
        self.assertEqual(_component(runtime.session, profile)["remaining_ticks"], 1)
        second = resolve_action(
            runtime.session,
            runtime.action_registry,
            ActionRequest("extend_to_deadline", PLAYER_ID, EXTEND_SKILL_ID),
        )
        self.assertEqual(second.effect_outcomes[0]["kind"], "process_modify")
        self.assertEqual(_component(runtime.session, profile)["hard_deadline"], hard_deadline)
        self.assertEqual(
            [(event.id, event.time) for event in runtime.session.state.scheduled_events],
            [("pmw:v04:sandbox.process.expiry:bounded_modify", 5.0)],
        )

        before_rejection = _snapshot(runtime)
        with self.assertRaisesRegex(GameplayContractError, "hard deadline"):
            submit_timed_primary_action(
                runtime.session,
                runtime.action_registry,
                ActionRequest(
                    "beyond_deadline",
                    PLAYER_ID,
                    BEYOND_SKILL_ID,
                ),
            )
        self.assertEqual(_snapshot(runtime), before_rejection)
        self.assertEqual(_component(runtime.session, profile)["hard_deadline"], hard_deadline)

        advance_world_tick(runtime.session)
        self.assertEqual(_component(runtime.session, profile)["remaining_ticks"], 3)
        advance_world_tick(runtime.session)
        self.assertEqual(_component(runtime.session, profile)["remaining_ticks"], 2)
        advance_world_tick(runtime.session)
        self.assertEqual(_component(runtime.session, profile)["remaining_ticks"], 1)
        advance_world_tick(runtime.session)
        expired = _component(runtime.session, profile)
        self.assertEqual(expired["state"], "stopped")
        self.assertEqual(expired["remaining_ticks"], 0)
        self.assertIsNone(expired["expiry_handle"])
        self.assertEqual(runtime.session.state.scheduled_events, [])
        self.assertEqual(expired["hard_deadline"], hard_deadline)

    def test_locality_owner_and_ambiguity_denials_are_atomic(self):
        def assert_denied(runtime, actor_id: str, request_id: str, pattern: str):
            before = _snapshot(runtime)
            with self.assertRaisesRegex(GameplayContractError, pattern):
                submit_timed_primary_action(
                    runtime.session,
                    runtime.action_registry,
                    ActionRequest(request_id, actor_id, MODIFY_SKILL_ID),
                )
            self.assertEqual(_snapshot(runtime), before)

        with self.subTest(case="remote_stock"):
            profile = _profile("remote_stock_modify", PLAYER_ID)
            runtime, _, _, _ = _setup_modifier((profile,), time_budget=6)
            _start_equipped(runtime, PLAYER_ID, "remote_stock_start")
            _add_area(runtime.session, "remote_area")
            _relocate(runtime.session, profile.inputs[0].stock.entity_id, "remote_area")
            runtime.session.runtime.revalidate()
            assert_denied(
                runtime,
                PLAYER_ID,
                "remote_stock_modify",
                "missing, ambiguous, or remote",
            )

        with self.subTest(case="owner"):
            profile = _profile("npc_only_modify", NPC_ID)
            runtime, _, _, _ = _setup_modifier((profile,), time_budget=6)
            _start_equipped(runtime, NPC_ID, "owner_npc_start")
            assert_denied(
                runtime,
                PLAYER_ID,
                "wrong_owner_modify",
                "no Process profile",
            )

        with self.subTest(case="multiple_local"):
            primary = _profile("primary_local_modify", PLAYER_ID)
            secondary = _profile("secondary_local_modify", PLAYER_ID)
            runtime, _, _, _ = _setup_modifier(
                (primary, secondary), time_budget=6
            )
            self.assertEqual(
                _component(runtime.session, primary)["state"], "stopped"
            )
            self.assertEqual(
                _component(runtime.session, secondary)["state"], "stopped"
            )
            assert_denied(
                runtime,
                PLAYER_ID,
                "ambiguous_local_modify",
                "missing, ambiguous, or remote",
            )

    def test_real_modify_cascade_and_late_tick_failures_roll_back_everything(self):
        template = replace(_template(), duration_ticks=6, max_duration_ticks=8)
        profile = _profile("cascade_modify", PLAYER_ID)
        profile = replace(profile, template=template)
        runtime, _, _, _ = _setup_modifier((profile,), time_budget=10)
        source = runtime.session
        cascade_laws = (
            {
                "id": "pmw.v04.review.aa_modify_bridge",
                "mode": "event",
                "priority": 100,
                "bindings": {
                    "process": {
                        "kind": "entity",
                        "requires": [PROCESS_COMPONENT],
                    }
                },
                "when": {"all": [
                    {"event.type": {"eq": PROCESS_MODIFY_EVENT}},
                    {"ref": "$process.id", "eq": profile.process_entity_id},
                    {"ref": f"$process.{PROCESS_COMPONENT}.state", "eq": "running"},
                ]},
                "effects": [{
                    "op": "emit_event",
                    "event": {
                        "type": "pmw.v04.review.after_modify",
                        "time": "$event.time",
                        "source": "$event.source",
                        "target": "$process.id",
                        "payload": {"after_rate": "$event.payload.after_rate"},
                    },
                }],
            },
            {
                "id": "pmw.v04.review.zz_modify_failure",
                "mode": "event",
                "priority": 100,
                "bindings": {
                    "process": {
                        "kind": "entity",
                        "requires": [PROCESS_COMPONENT],
                    }
                },
                "when": {"all": [
                    {"event.type": {"eq": "pmw.v04.review.after_modify"}},
                    {"ref": "$process.id", "eq": "$event.target"},
                ]},
                "effects": [{
                    "op": "set",
                    "target": f"$process.{PROCESS_COMPONENT}.last_failure",
                    "value": {"div": [1, 0]},
                }],
            },
        )
        runtime.session = build_runtime(
            source.state,
            source.profiles,
            (
                *runtime.static_laws,
                *build_action_laws(runtime.action_registry),
                *cascade_laws,
            ),
        )
        submit_timed_primary_action(
            runtime.session,
            runtime.action_registry,
            ActionRequest("cascade_start", PLAYER_ID, SKILL_ID),
        )
        before_cascade = _snapshot(runtime)
        with self.assertRaises(ZeroDivisionError):
            submit_timed_primary_action(
                runtime.session,
                runtime.action_registry,
                ActionRequest("cascade_modify", PLAYER_ID, MODIFY_SKILL_ID),
            )
        self.assertEqual(_snapshot(runtime), before_cascade)

        with self.subTest(case="late_tick"):
            profile = replace(_profile("late_tick_modify", PLAYER_ID), template=template)
            runtime, _, _, _ = _setup_modifier((profile,), time_budget=10)
            submit_timed_primary_action(
                runtime.session,
                runtime.action_registry,
                ActionRequest("late_tick_start", PLAYER_ID, SKILL_ID),
            )
            before_tick_failure = _snapshot(runtime)
            real_tick = time_ledger.advance_world_tick
            calls = 0

            def fail_second_tick(working, **kwargs):
                nonlocal calls
                calls += 1
                result = real_tick(working, **kwargs)
                if calls == 2:
                    raise RuntimeError("review injected late modify tick failure")
                return result

            before_tick_failure = _snapshot(runtime)
            with patch.object(
                time_ledger,
                "advance_world_tick",
                side_effect=fail_second_tick,
            ):
                with self.assertRaisesRegex(RuntimeError, "late modify tick"):
                    submit_timed_primary_action(
                        runtime.session,
                        runtime.action_registry,
                        ActionRequest(
                            "late_tick_modify",
                            PLAYER_ID,
                            BEYOND_SKILL_ID,
                        ),
                    )
            self.assertEqual(calls, 2)
            self.assertEqual(_snapshot(runtime), before_tick_failure)

        with self.subTest(case="missing_modify_law"):
            profile = replace(_profile("missing_law_modify", PLAYER_ID), template=template)
            same_rate_document = _modify_document(
                skill_id=SAME_RATE_SKILL_ID,
                rate=1.0,
                remaining_ticks=1,
            )
            runtime, _, _, _ = _setup_modifier(
                (profile,),
                time_budget=10,
                slots={
                    MODIFY_SKILL_ID: 1,
                    SAME_RATE_SKILL_ID: 2,
                },
                documents=(
                    _modify_document(rate=1.5, remaining_ticks=2),
                    same_rate_document,
                ),
            )
            _start_equipped(runtime, PLAYER_ID, "missing_law_start")
            source = runtime.session
            expected_modify_law = (
                f"pmw.v04.sandbox.process.{profile.id}.modify"
            )
            laws = tuple(
                law
                for law in (
                    *runtime.static_laws,
                    *build_action_laws(runtime.action_registry),
                )
                if law["id"] != expected_modify_law
            )
            unrelated_modify = {
                "id": "pmw.v04.review.unrelated_process_change.modify",
                "mode": "event",
                "priority": 100,
                "bindings": {
                    "process": {
                        "kind": "entity",
                        "requires": [PROCESS_COMPONENT],
                    }
                },
                "when": {"all": [
                    {"event.type": {"eq": PROCESS_MODIFY_EVENT}},
                    {"ref": "$process.id", "eq": profile.process_entity_id},
                    {"ref": "$event.payload.after_rate", "eq": 1.0},
                    {
                        "ref": "$event.payload.after_remaining",
                        "eq": f"$process.{PROCESS_COMPONENT}.remaining_ticks",
                    },
                ]},
                "effects": [{
                    "op": "set",
                    "target": f"$process.{PROCESS_COMPONENT}.last_failure",
                    "value": None,
                }],
            }
            runtime.session = build_runtime(
                source.state,
                source.profiles,
                (*laws, unrelated_modify),
            )
            before = _snapshot(runtime)
            with self.assertRaises(GameplayContractError):
                submit_timed_primary_action(
                    runtime.session,
                    runtime.action_registry,
                    ActionRequest(
                        "missing_law_modify", PLAYER_ID, SAME_RATE_SKILL_ID
                    ),
                )
            self.assertEqual(_snapshot(runtime), before)
            self.assertEqual(
                runtime.session.state.entities[PLAYER_ID].components[
                    "pmw_gameplay_actor"
                ]["mana"],
                16.0,
            )

    def test_checkpoint_continuation_and_projection_keep_private_authority_hidden(self):
        template = replace(_template(), duration_ticks=6, max_duration_ticks=8)
        saved_profile = replace(
            _profile("checkpoint_saved_modify", PLAYER_ID),
            template=template,
            rate=0.5,
        )
        future_profile = replace(
            _profile("checkpoint_future_modify", PLAYER_ID),
            template=template,
            rate=0.5,
        )
        runtime, compiled, _, _ = _setup_modifier(
            (saved_profile,), time_budget=20
        )
        submit_timed_primary_action(
            runtime.session,
            runtime.action_registry,
            ActionRequest("checkpoint_start", PLAYER_ID, SKILL_ID),
        )
        submit_timed_primary_action(
            runtime.session,
            runtime.action_registry,
            ActionRequest("checkpoint_modify", PLAYER_ID, MODIFY_SKILL_ID),
        )
        modified = _component(runtime.session, saved_profile)
        self.assertEqual(modified["rate"], 1.5)
        self.assertEqual(modified["remaining_ticks"], 1)
        expected_expiry = next(
            event
            for event in runtime.session.state.scheduled_events
            if event.id == modified["expiry_handle"]
        )
        self.assertEqual(expected_expiry.time, 4.0)

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "process_modify_checkpoint.json"
            save_registry_checkpoint(path, runtime)
            restored = load_registry_checkpoint(path, compiled)
            self.assertEqual(restored.session.state.to_dict(), runtime.session.state.to_dict())
            self.assertEqual(restored.manifest, runtime.manifest)
            self.assertIn(MODIFY_SKILL_ID, restored.action_registry.actions)

            changed_profile = _profile(
                saved_profile.id,
                PLAYER_ID,
                stock_prefix="changed_checkpoint_profile",
            )
            changed_profile = replace(
                changed_profile,
                template=template,
                rate=0.5,
            )
            changed_controller = ProcessController(
                (changed_profile,),
                ProcessLimits(max_instances=8, max_active=8),
            )
            changed_laws = (
                *(
                    law
                    for law in compiled.laws
                    if not law["id"].startswith("pmw.v04.sandbox.process.")
                ),
                *changed_controller.laws,
            )
            changed_compiled = type(compiled)(
                compiled.content,
                tuple(sorted(changed_laws, key=lambda law: law["id"])),
            )
            with self.assertRaisesRegex(
                GameplayContractError, "static Law configuration"
            ):
                load_registry_checkpoint(path, changed_compiled)

        for candidate in (runtime, restored):
            component = _component(candidate.session, saved_profile)
            self.assertEqual(component["state"], "running")
            self.assertEqual(component["remaining_ticks"], 1)
            self.assertEqual(component["hard_deadline"], 8.0)
            self.assertEqual(
                _amount(candidate.session, saved_profile.inputs[0].stock.entity_id),
                5.0,
            )
            self.assertEqual(
                _amount(candidate.session, saved_profile.outputs[0].stock.entity_id),
                2.5,
            )
            candidate.session.state.entities[future_profile.process_entity_id] = (
                instantiate_process(future_profile)
            )
            for port, ref in (*future_profile.input_ports, *future_profile.output_ports):
                candidate.session.state.entities[ref.entity_id] = stock_entity(
                    ref.entity_id,
                    amount=10.0 if port.name == "ore" else 0.0,
                    capacity=20.0,
                    unit=port.unit,
                )
            for entity_id in (
                future_profile.process_entity_id,
                *_stock_ids(future_profile),
            ):
                _relocate(candidate.session, entity_id, AREA_ID)
            prefix = "checkpoint_future_modify"
            for suffix, amount in (("_ore", 10.0), ("_ingot", 0.0)):
                entity_id = f"{prefix}{suffix}"
                candidate.session.state.entities[entity_id].components["stock"][
                    "amount"
                ] = amount
            candidate.session.runtime.revalidate()
            advance_world_tick(candidate.session)
        self.assertEqual(runtime.session.state.to_dict(), restored.session.state.to_dict())
        for candidate in (runtime, restored):
            self.assertEqual(
                _component(candidate.session, saved_profile)["state"],
                "stopped",
            )
            self.assertEqual(
                _component(candidate.session, saved_profile)["remaining_ticks"],
                0,
            )
            self.assertEqual(candidate.session.state.scheduled_events, [])
        self.assertEqual(
            _amount(runtime.session, "checkpoint_saved_modify_ingot"),
            2.5,
        )

        observation = ActorObservationBuilder().build(
            restored.session,
            restored.action_registry,
            PLAYER_ID,
            ObservationDisclosure.create(),
        )
        document = observation.to_dict()
        rendered = str(document)
        self.assertNotIn(MODIFY_SKILL_ID, document["known_actions"][PLAYER_ID])
        for profile in (saved_profile, future_profile):
            self.assertNotIn(profile.process_entity_id, rendered)
        for stock_id in (*_stock_ids(saved_profile), *_stock_ids(future_profile)):
            self.assertNotIn(stock_id, rendered)
        simulator = SandboxSimulator(restored.action_registry)
        projected, registry, _ = simulator._build(observation)
        self.assertIsNone(registry.process_controller)
        self.assertNotIn(MODIFY_SKILL_ID, registry.actions)
        for profile in (saved_profile, future_profile):
            self.assertNotIn(profile.process_entity_id, projected.state.entities)
        basic = simulator.simulate(
            observation,
            ActionRequest("projection_basic_wait", PLAYER_ID, "basic_wait"),
        )
        self.assertTrue(basic.legal, basic.rejection)

    def test_modify_effect_nulls_and_mixed_controls_are_rejected(self):
        with self.subTest(case="explicit_null_rate"):
            null_rate = _modify_document(rate=1.5, remaining_ticks=2)
            null_rate["effects"][0]["process_rate"] = None
            with self.assertRaises(GameplayContractError):
                _parse_modify(null_rate)
        with self.subTest(case="explicit_null_remaining"):
            null_remaining = _modify_document(rate=1.5)
            null_remaining["effects"][0]["process_remaining_ticks"] = None
            with self.assertRaises(GameplayContractError):
                _parse_modify(null_remaining)
        with self.subTest(case="no_fields"):
            with self.assertRaises(GameplayContractError):
                _parse_modify(_modify_document(rate=None, remaining_ticks=None))
        with self.subTest(case="mixed_start_modify"):
            mixed = json.loads(_blueprint().canonical_document_json)
            mixed_modify = _modify_document(rate=1.5, remaining_ticks=2)
            mixed["effects"].append(mixed_modify["effects"][0])
            mixed["budget"]["limit"] = 5.0
            with self.assertRaisesRegex(GameplayContractError, "at most one"):
                _parse_modify(
                    mixed,
                    effect_kinds=("process_start", "process_modify"),
                    budget=5.0,
                )


if __name__ == "__main__":
    unittest.main()
