"""Bounded resume probes for P2.2 lifecycle and checkpoint continuation."""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.actions import (
    ActionRequest,
    submit_timed_primary_action,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.checkpoint import (
    load_registry_checkpoint,
    save_registry_checkpoint,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.dynamics import (
    CLOCK_COMPONENT,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.loadout import (
    change_loadout,
    skill_ref,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.runtime import (
    advance_world_tick,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.time_ledger import (
    TIME_BUDGET_COMPONENT,
)

from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.tests.test_p2_reference_library_review import (
    CLOCK_ID,
    EVIDENCE_DIR,
    NPC,
    PLAYER,
    _build,
    _field,
    _library,
    _primary_effects,
    _run_skill,
    _scheduled_expiry_times,
    _world_digest,
    passive_hook_id,
)


TEST_TMP = EVIDENCE_DIR / "test_tmp"


def _next_tick_time(runtime) -> float:
    clock = runtime.session.state.entities[CLOCK_ID].components[
        CLOCK_COMPONENT
    ]
    return float(clock["next_time"])


def _time_budget(runtime) -> dict:
    return runtime.session.state.entities[CLOCK_ID].components[
        TIME_BUDGET_COMPONENT
    ]


class ReferenceLibraryResumeReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        TEST_TMP.mkdir(parents=True, exist_ok=True)
        cls.documents = _library()
        cls.by_id = {
            document["identity"]["id"]: document
            for document in cls.documents
        }

    def test_timed_effect_remains_active_until_expiry_tick_and_then_clears(self):
        for skill_id in (
            "attractor_dawn",
            "synergy_pressure",
            "synergy_tempo",
            "synergy_vital",
            "synergy_flux",
        ):
            document = self.by_id[skill_id]
            fixture, parsed, _compiled, _gate3, runtime, _content = _build(
                document, PLAYER
            )
            result = _run_skill(runtime, PLAYER, parsed)
            expiry_times = _scheduled_expiry_times(runtime)
            self.assertEqual(len(expiry_times), 1, skill_id)
            expiry = expiry_times[0]
            self.assertGreater(expiry, runtime.session.state.sim_time)

            timed_effects = [
                effect
                for effect in _primary_effects(parsed)
                if effect.get("duration") is not None
            ]
            self.assertEqual(len(timed_effects), 1, skill_id)
            effect = timed_effects[0]
            outcome = next(
                row
                for row in result.action.effect_outcomes
                if row["effect_id"] == effect["id"]
            )
            source = _field(
                runtime, outcome["target_id"], effect["field_id"]
            )["temporary_modifiers"][outcome["values"]["slot"]]
            self.assertTrue(source["active"])
            while _next_tick_time(runtime) < expiry:
                advance_world_tick(runtime.session)
            self.assertLess(runtime.session.state.sim_time, expiry)
            source = _field(
                runtime, outcome["target_id"], effect["field_id"]
            )["temporary_modifiers"][outcome["values"]["slot"]]
            self.assertTrue(source["active"])
            advance_world_tick(runtime.session)
            source = _field(
                runtime, outcome["target_id"], effect["field_id"]
            )["temporary_modifiers"][outcome["values"]["slot"]]
            self.assertFalse(source["active"])
            self.assertTrue(
                set(expiry_times).isdisjoint(_scheduled_expiry_times(runtime))
            )

    def test_checkpoint_passive_cap_continuation_matches_uninterrupted_run(self):
        for skill_id in ("counter_mend", "counter_shield", "counter_spark"):
            document = self.by_id[skill_id]
            fixture, parsed, _compiled, gate3, runtime, _content = _build(
                document, PLAYER
            )
            uninterrupted = _build(document, PLAYER)[4]

            def attack(current, suffix):
                return submit_timed_primary_action(
                    current.session,
                    current.action_registry,
                    ActionRequest(
                        f"resume_{skill_id}_{suffix}",
                        NPC,
                        "basic_attack",
                        PLAYER,
                    ),
                )

            first = attack(runtime, "first")
            first_uninterrupted = attack(uninterrupted, "first")
            self.assertEqual(
                first.action.auto_hooks,
                first_uninterrupted.action.auto_hooks,
                skill_id,
            )
            self.assertEqual(
                _world_digest(runtime),
                _world_digest(uninterrupted),
                skill_id,
            )
            with tempfile.TemporaryDirectory(dir=TEST_TMP) as directory:
                path = Path(directory) / f"{skill_id}.resume.json"
                save_registry_checkpoint(path, runtime)
                restored = load_registry_checkpoint(path, gate3)
            self.assertEqual(
                _world_digest(restored),
                _world_digest(runtime),
                skill_id,
            )
            expected = attack(uninterrupted, "second")
            resumed = attack(restored, "second")
            self.assertNotEqual(
                first.action.request.request_id,
                resumed.action.request.request_id,
                skill_id,
            )
            self.assertEqual(
                resumed.action.auto_hooks,
                expected.action.auto_hooks,
                skill_id,
            )
            self.assertEqual(
                resumed.action.effect_outcomes,
                expected.action.effect_outcomes,
                skill_id,
            )
            self.assertEqual(
                len(
                    [
                        row
                        for row in resumed.action.auto_hooks
                        if row.status == "fired"
                    ]
                ),
                1,
            )
            self.assertEqual(
                _world_digest(restored),
                _world_digest(uninterrupted),
                skill_id,
            )
            self.assertEqual(
                restored.session.state.to_dict(),
                uninterrupted.session.state.to_dict(),
                skill_id,
            )

    def test_passive_cap_dual_owner_nested_notifications_terminate_refetched(self):
        document = self.by_id["counter_spark"]
        _f, _parsed, compiled, _gate3, runtime, _content = _build(
            document, PLAYER
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
        budget_before = _time_budget(runtime)
        remaining_before = budget_before["remaining_ticks"]
        spent_before = budget_before["spent_ticks"]
        sim_time_before = runtime.session.state.sim_time

        result = submit_timed_primary_action(
            runtime.session,
            runtime.action_registry,
            ActionRequest(
                "resume_counter_spark_dual_owner",
                NPC,
                "basic_attack",
                PLAYER,
            ),
        )

        hook_id = passive_hook_id(passive)
        fired = [
            row for row in result.action.auto_hooks if row.status == "fired"
        ]
        fired_per_owner = {}
        for row in fired:
            key = (row.owner, row.hook_id)
            fired_per_owner[key] = fired_per_owner.get(key, 0) + 1
        self.assertEqual(
            set(fired_per_owner),
            {(PLAYER, hook_id), (NPC, hook_id)},
        )
        self.assertTrue(
            all(count <= passive.max_firings_per_root for count in fired_per_owner.values())
        )
        self.assertGreaterEqual(
            len(
                [
                    row
                    for row in result.action.auto_hooks
                    if row.status == "skipped"
                    and row.reason == "duplicate owner+hook source in this root"
                ]
            ),
            1,
        )

        duration = result.action.cost.duration
        self.assertEqual(len(result.time.ticks), duration)
        self.assertEqual(
            _time_budget(runtime)["remaining_ticks"],
            remaining_before - duration,
        )
        self.assertEqual(
            _time_budget(runtime)["spent_ticks"],
            spent_before + duration,
        )
        self.assertEqual(
            runtime.session.state.sim_time,
            sim_time_before + duration,
        )


if __name__ == "__main__":
    unittest.main()
