from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pmw import Event
from pmw.validation.errors import WorldValidationError

from experiments.generative_mechanics.next_tracks_v06.gameplay_v04 import (
    time_ledger,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.action_compiler import (
    build_action_laws,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.actions import (
    ActionRequest,
    resolve_action,
    submit_timed_primary_action,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.checkpoint import (
    load_registry_checkpoint,
    save_registry_checkpoint,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.contracts import (
    GameplayContractError,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.processes import (
    PROCESS_COMPONENT,
    PROCESS_MODIFY_EVENT,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.runtime import (
    advance_world_tick,
    build_runtime,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.tests.test_sandbox_process_action import (
    NPC_ID,
    PLAYER_ID,
    _amount,
    _component,
    _profile,
    _template,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.tests.test_sandbox_process_modify_review import (
    _modify_document,
    _parse_modify,
    _setup_modifier,
    _snapshot,
)


START_SKILL_ID = "start_refining"
RATE_ONLY_ID = "rate_only_expiry"
EXPLICIT_ID = "explicit_expiry"
LIFECYCLE_FIELDS = (
    "duration_ticks",
    "remaining_ticks",
    "elapsed_ticks",
    "progress",
    "started_at",
    "hard_deadline",
    "expiry_handle",
    "last_step",
    "last_failure",
)


def _rate_only_document(*, duration: int = 1) -> dict:
    document = _modify_document(
        skill_id=RATE_ONLY_ID,
        rate=1.5,
        remaining_ticks=None,
        duration=duration,
    )
    assert "process_remaining_ticks" not in document["effects"][0]
    return document


def _full_runtime(
    *,
    actor_id: str = PLAYER_ID,
    profile_id: str = "rate_only_full",
):
    profile = replace(
        _profile(profile_id, actor_id),
        template=replace(_template(), duration_ticks=3, max_duration_ticks=3),
        rate=1.0,
    )
    runtime, compiled, start, modifiers = _setup_modifier(
        (profile,),
        time_budget=12,
        documents=(_rate_only_document(),),
    )
    runtime.session.state.entities[
        profile.outputs[0].stock.entity_id
    ].components["stock"]["amount"] = 20.0
    runtime.session.runtime.revalidate()
    return runtime, compiled, profile, start, modifiers


def _pending_runtime(
    *,
    actor_id: str = PLAYER_ID,
    profile_id: str = "rate_only_pending",
    profile=None,
):
    if profile is None:
        runtime, compiled, profile, start, modifiers = _full_runtime(
            actor_id=actor_id,
            profile_id=profile_id,
        )
    else:
        runtime, compiled, start, modifiers = _setup_modifier(
            (profile,),
            time_budget=12,
            documents=(_rate_only_document(),),
        )
        runtime.session.state.entities[
            profile.outputs[0].stock.entity_id
        ].components["stock"]["amount"] = 20.0
        runtime.session.runtime.revalidate()
    begun = submit_timed_primary_action(
        runtime.session,
        runtime.action_registry,
        ActionRequest(f"{actor_id}_start", actor_id, START_SKILL_ID),
    )
    assert begun.time.duration == 2
    assert runtime.session.state.sim_time == 2.0
    return runtime, compiled, profile, start, modifiers


def _expiry(session, component):
    matches = [
        event
        for event in session.state.scheduled_events
        if event.id == component["expiry_handle"]
    ]
    assert len(matches) == 1
    return matches[0]


def _try_pure_modify(runtime, profile, request_id: str):
    return resolve_action(
        runtime.session,
        runtime.action_registry,
        ActionRequest(request_id, profile.owner, RATE_ONLY_ID),
    )


class ProcessRateExpiryIndependentReviewTests(unittest.TestCase):
    def test_pure_rate_only_cold_catalog_lifecycle_preserves_actual_expiry(self):
        document = _rate_only_document()
        self.assertNotIn("process_remaining_ticks", document["effects"][0])
        parsed = _parse_modify(document)
        self.assertEqual(parsed.id, RATE_ONLY_ID)
        self.assertEqual(parsed.effects[0].process_rate, 1.5)
        self.assertIsNone(parsed.effects[0].process_remaining_ticks)

        runtime, _, profile, start, modifiers = _pending_runtime(
            profile_id="pure_rate_lifecycle"
        )
        self.assertEqual(start.id, START_SKILL_ID)
        self.assertEqual(len(modifiers), 1)
        self.assertEqual(modifiers[0].id, RATE_ONLY_ID)
        self.assertIsNone(modifiers[0].effects[0].process_remaining_ticks)

        before = deepcopy(_component(runtime.session, profile))
        self.assertEqual(before["state"], "running")
        self.assertEqual(before["rate"], 1.0)
        self.assertEqual(before["duration_ticks"], 3)
        self.assertEqual(before["remaining_ticks"], 3)
        self.assertEqual(before["elapsed_ticks"], 0)
        self.assertEqual(before["progress"], 0.0)
        self.assertEqual(before["hard_deadline"], 3.0)
        self.assertEqual(_expiry(runtime.session, before).time, 3.0)
        self.assertEqual(runtime.session.state.sim_time, 2.0)
        self.assertEqual(
            _amount(runtime.session, profile.inputs[0].stock.entity_id),
            10.0,
        )
        self.assertEqual(
            _amount(runtime.session, profile.outputs[0].stock.entity_id),
            20.0,
        )

        prepared = runtime.action_registry.process_controller.prepare_modify(
            runtime.session,
            profile.id,
            owner=PLAYER_ID,
            rate=1.5,
        )
        self.assertEqual(prepared["after_rate"], 1.5)
        self.assertEqual(prepared["after_duration"], 3)
        self.assertEqual(prepared["after_remaining"], 3)
        self.assertEqual(prepared["after_progress"], 0.0)
        self.assertEqual(prepared["deadline"], 3.0)
        self.assertEqual(_component(runtime.session, profile), before)

        cast = _try_pure_modify(runtime, profile, "pure_lifecycle_rate")
        self.assertEqual(cast.effect_outcomes[0]["kind"], "process_modify")
        after = deepcopy(_component(runtime.session, profile))
        self.assertEqual(after["rate"], 1.5)
        for field in LIFECYCLE_FIELDS:
            self.assertEqual(after[field], before[field], field)
        self.assertEqual(after["duration_ticks"], 3)
        self.assertEqual(after["remaining_ticks"], 3)
        self.assertEqual(_expiry(runtime.session, after).time, 3.0)

        advance_world_tick(runtime.session)
        self.assertEqual(runtime.session.state.sim_time, 3.0)
        expired = _component(runtime.session, profile)
        self.assertEqual(expired["state"], "stopped")
        self.assertEqual(expired["last_step"], 2)
        self.assertEqual(expired["remaining_ticks"], 0)
        self.assertEqual(expired["progress"], 1.0)
        self.assertIsNone(expired["expiry_handle"])
        self.assertEqual(runtime.session.state.scheduled_events, [])

    def test_pure_rate_only_formal_player_and_npc_paid_actions_are_quantitative(self):
        for actor_id, profile_id in (
            (PLAYER_ID, "pure_rate_player"),
            (NPC_ID, "pure_rate_npc"),
        ):
            with self.subTest(actor_id=actor_id):
                _, _, planned_profile, _, _ = _full_runtime(
                    actor_id=actor_id,
                    profile_id=profile_id,
                )
                runtime, _, profile, _, _ = _pending_runtime(
                    actor_id=actor_id,
                    profile_id=profile_id,
                    profile=planned_profile,
                )
                actor = runtime.session.state.entities[actor_id].components[
                    "pmw_gameplay_actor"
                ]
                budget = runtime.session.state.entities[
                    "pmw:v04:clock"
                ].components["pmw_gameplay_time_budget"]
                self.assertEqual(actor["mana"], 16.0)
                self.assertEqual(budget["remaining_ticks"], 10)
                before = deepcopy(_component(runtime.session, profile))
                self.assertEqual(before["remaining_ticks"], 3)
                self.assertEqual(before["hard_deadline"], 3.0)

                cast = resolve_action(
                    runtime.session,
                    runtime.action_registry,
                    ActionRequest(f"{actor_id}_rate", actor_id, RATE_ONLY_ID),
                )
                self.assertEqual(cast.effect_outcomes[0]["kind"], "process_modify")
                actor = runtime.session.state.entities[actor_id].components[
                    "pmw_gameplay_actor"
                ]
                budget = runtime.session.state.entities[
                    "pmw:v04:clock"
                ].components["pmw_gameplay_time_budget"]
                self.assertEqual(actor["mana"], 15.0)
                self.assertEqual(budget["remaining_ticks"], 10)
                modified = deepcopy(_component(runtime.session, profile))
                self.assertEqual(modified["rate"], 1.5)
                self.assertEqual(modified["remaining_ticks"], 3)
                self.assertEqual(modified["duration_ticks"], 3)
                self.assertEqual(_expiry(runtime.session, modified).time, 3.0)

                advance_world_tick(runtime.session)
                self.assertEqual(runtime.session.state.sim_time, 3.0)
                self.assertLessEqual(
                    runtime.session.state.sim_time,
                    before["hard_deadline"],
                )
                actor = runtime.session.state.entities[actor_id].components[
                    "pmw_gameplay_actor"
                ]
                budget = runtime.session.state.entities[
                    "pmw:v04:clock"
                ].components["pmw_gameplay_time_budget"]
                self.assertEqual(actor["mana"], 15.0)
                self.assertEqual(budget["remaining_ticks"], 10)
                self.assertEqual(
                    _component(runtime.session, profile)["state"],
                    "stopped",
                )
                self.assertEqual(
                    _amount(runtime.session, profile.inputs[0].stock.entity_id),
                    10.0,
                )
                self.assertEqual(
                    _amount(runtime.session, profile.outputs[0].stock.entity_id),
                    20.0,
                )

    def test_explicit_duration_and_invalid_schedule_rejections_are_distinct(self):
        profile = replace(
            _profile("explicit_rate_expiry", PLAYER_ID),
            template=replace(_template(), duration_ticks=3, max_duration_ticks=6),
            rate=1.0,
        )
        runtime, _, _, _ = _setup_modifier(
            (profile,),
            time_budget=12,
            documents=(
                _modify_document(
                    skill_id=EXPLICIT_ID,
                    rate=1.5,
                    remaining_ticks=2,
                    duration=1,
                ),
            ),
        )
        runtime.session.state.entities[
            profile.outputs[0].stock.entity_id
        ].components["stock"]["amount"] = 20.0
        runtime.session.runtime.revalidate()
        submit_timed_primary_action(
            runtime.session,
            runtime.action_registry,
            ActionRequest("explicit_start", PLAYER_ID, START_SKILL_ID),
        )
        rejected = _snapshot(runtime)
        with self.assertRaisesRegex(GameplayContractError, "hard deadline"):
            runtime.action_registry.process_controller.prepare_modify(
                runtime.session,
                profile.id,
                owner=PLAYER_ID,
                rate=1.5,
                remaining_ticks=5,
            )
        self.assertEqual(_snapshot(runtime), rejected)

        cast = resolve_action(
            runtime.session,
            runtime.action_registry,
            ActionRequest("explicit_rate", PLAYER_ID, EXPLICIT_ID),
        )
        self.assertEqual(cast.effect_outcomes[0]["kind"], "process_modify")
        modified = deepcopy(_component(runtime.session, profile))
        self.assertEqual(modified["rate"], 1.5)
        self.assertEqual(modified["duration_ticks"], 2)
        self.assertEqual(modified["remaining_ticks"], 2)
        self.assertEqual(modified["progress"], 0.0)
        self.assertEqual(_expiry(runtime.session, modified).time, 4.0)
        advance_world_tick(runtime.session)
        self.assertEqual(runtime.session.state.sim_time, 3.0)
        self.assertEqual(_component(runtime.session, profile)["state"], "running")
        advance_world_tick(runtime.session)
        self.assertEqual(runtime.session.state.sim_time, 4.0)
        expired = _component(runtime.session, profile)
        self.assertEqual(expired["state"], "stopped")
        self.assertEqual(expired["remaining_ticks"], 0)
        self.assertEqual(expired["progress"], 1.0)
        self.assertEqual(runtime.session.state.scheduled_events, [])

        for name, pattern in (
            ("missing", "missing"),
            ("past", "not in the future"),
            ("beyond", "schedule exceeds"),
        ):
            with self.subTest(schedule=name):
                pending, _, pending_profile, _, _ = _pending_runtime(
                    profile_id=f"invalid_{name}"
                )
                component = deepcopy(_component(pending.session, pending_profile))
                expiry = _expiry(pending.session, component)
                if name == "missing":
                    pending.session.state.scheduled_events = []
                elif name == "past":
                    pending.session.state.scheduled_events = [
                        replace(expiry, time=2.0)
                    ]
                else:
                    component["expiry_handle"] = "beyond_handle"
                    pending.session.state.entities[
                        pending_profile.process_entity_id
                    ].components[PROCESS_COMPONENT] = component
                    pending.session.state.scheduled_events = [
                        replace(expiry, id="beyond_handle", time=7.0)
                    ]
                pending.session.runtime.revalidate()
                before = _snapshot(pending)
                with self.assertRaisesRegex(GameplayContractError, pattern):
                    pending.action_registry.process_controller.prepare_modify(
                        pending.session,
                        pending_profile.id,
                        owner=PLAYER_ID,
                        rate=1.5,
                    )
                self.assertEqual(_snapshot(pending), before)

        duplicate, _, duplicate_profile, _, _ = _pending_runtime(
            profile_id="duplicate_expiry"
        )
        before = _snapshot(duplicate)
        scheduled = deepcopy(duplicate.session.state.scheduled_events[0])
        duplicate.session.state.scheduled_events.append(scheduled)
        with self.assertRaisesRegex(WorldValidationError, "duplicate id"):
            duplicate.session.runtime.revalidate()
        duplicate.session.state.scheduled_events.pop()
        self.assertEqual(_snapshot(duplicate), before)
        self.assertEqual(
            _component(duplicate.session, duplicate_profile)["state"],
            "running",
        )

    def test_cascade_late_tick_and_checkpoint_keep_rate_only_rollback_semantics(self):
        runtime, _, profile, _, _ = _pending_runtime(
            profile_id="cascade_rate_expiry"
        )
        source = runtime.session
        cascade_laws = (
            {
                "id": "pmw.v04.review.aa_rate_expiry_bridge",
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
                        "type": "pmw.v04.review.rate_expiry_committed",
                        "time": "$event.time",
                        "source": "$event.source",
                        "target": "$process.id",
                        "payload": {"after_rate": "$event.payload.after_rate"},
                    },
                }],
            },
            {
                "id": "pmw.v04.review.zz_rate_expiry_failure",
                "mode": "event",
                "priority": 100,
                "bindings": {
                    "process": {
                        "kind": "entity",
                        "requires": [PROCESS_COMPONENT],
                    }
                },
                "when": {"all": [
                    {"event.type": {"eq": "pmw.v04.review.rate_expiry_committed"}},
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
        before_cascade = _snapshot(runtime)
        with self.assertRaises(ZeroDivisionError):
            _try_pure_modify(runtime, profile, "cascade_rate")
        self.assertEqual(_snapshot(runtime), before_cascade)

        late, _, late_profile, _, _ = _pending_runtime(
            profile_id="late_rate_expiry"
        )
        original_tick = time_ledger.advance_world_tick
        calls = 0

        def fail_after_expiry_tick(working, **kwargs):
            nonlocal calls
            calls += 1
            result = original_tick(working, **kwargs)
            raise RuntimeError("review injected rate-expiry tick failure")

        before_late = _snapshot(late)
        with patch.object(
            time_ledger,
            "advance_world_tick",
            side_effect=fail_after_expiry_tick,
        ):
            with self.assertRaisesRegex(RuntimeError, "rate-expiry tick"):
                submit_timed_primary_action(
                    late.session,
                    late.action_registry,
                    ActionRequest("late_rate", PLAYER_ID, RATE_ONLY_ID),
                )
        self.assertEqual(calls, 1)
        self.assertEqual(_snapshot(late), before_late)
        self.assertEqual(_component(late.session, late_profile)["state"], "running")

        checkpoint, compiled, checkpoint_profile, _, _ = _pending_runtime(
            profile_id="checkpoint_rate_expiry"
        )
        _try_pure_modify(checkpoint, checkpoint_profile, "checkpoint_rate")
        saved = deepcopy(_component(checkpoint.session, checkpoint_profile))
        self.assertEqual(saved["rate"], 1.5)
        self.assertEqual(saved["remaining_ticks"], 3)
        self.assertEqual(_expiry(checkpoint.session, saved).time, 3.0)

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rate_expiry.json"
            save_registry_checkpoint(path, checkpoint)
            restored = load_registry_checkpoint(path, compiled)
            self.assertEqual(
                restored.session.state.to_dict(),
                checkpoint.session.state.to_dict(),
            )
            for session in (checkpoint.session, restored.session):
                advance_world_tick(session)
                expired = _component(session, checkpoint_profile)
                self.assertEqual(expired["state"], "stopped")
                self.assertEqual(expired["rate"], 1.5)
                self.assertEqual(expired["hard_deadline"], 3.0)
                self.assertEqual(session.state.scheduled_events, [])
            self.assertEqual(
                checkpoint.session.state.to_dict(),
                restored.session.state.to_dict(),
            )


if __name__ == "__main__":
    unittest.main()
