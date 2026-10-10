from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.actions import ActionRequest, resolve_action
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.checkpoint import (
    load_registry_checkpoint, save_registry_checkpoint,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.content_compiler import compile_content
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.contracts import GameplayContractError
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.gate3_demo import build_gate3_demo
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.loadout import change_loadout, skill_ref
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.materials import MaterialAuthority
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.registry import MechanismRegistryRuntime
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.runtime import advance_world_tick, run_phase_event


def _runtime():
    session, content, skill, _ = build_gate3_demo()
    compiled = compile_content(content)
    return MechanismRegistryRuntime.from_compiled_content(session, compiled), compiled, skill


def _version(skill, version):
    document = json.loads(skill.canonical_document_json)
    document["version"] = version
    return document


def _timed_skill():
    return {
        "protocol": "pmw-gameplay-v0.4", "kind": "skill_blueprint", "id": "slow_mist", "version": 1,
        "trigger": "on_use", "condition": None, "duration": None,
        "cost": {"duration": 1, "mana": 0},
        "scope": {"selectors": ["current_area"], "relation_types": []},
        "effects": [{"id": "slow_recovery", "kind": "modify_rate",
                     "target": {"kind": "current_area"}, "commitment": "required",
                     "field_id": "mist", "amount": -0.02, "duration": 2}],
        "budget": {"limit": 6}, "max_firings_per_root": 1,
        "material_ids": ["mist_crystal"],
    }


TIMED_AUTHORITY = MaterialAuthority(("mist_crystal",), ("modify_rate",), ("current_area",), 8.0)


class RegistryCheckpointTests(unittest.TestCase):
    def test_install_is_formal_traced_and_once_per_world_tick_boundary(self):
        runtime, _, _ = _runtime()
        change = runtime.install(_timed_skill(), TIMED_AUTHORITY)
        self.assertTrue(change.event_result.changed)
        self.assertIn("pmw.v04.registry.change", change.event_result.triggered_law_ids)
        component = runtime.session.state.entities["pmw:v04:clock"].components["pmw_gameplay_mechanism_registry"]
        self.assertEqual((component["epoch"], component["last_boundary_step"]), (1, 0))
        second = deepcopy(_timed_skill()); second["id"] = "other_mist"
        with self.assertRaisesRegex(GameplayContractError, "one registry transaction"):
            runtime.install(second, TIMED_AUTHORITY)

    def test_fractional_time_is_not_a_world_tick_boundary(self):
        runtime, _, _ = _runtime()
        runtime.session.runtime.advance_to(0.5)
        before = runtime.session.state.to_dict()
        with self.assertRaisesRegex(GameplayContractError, "complete World Tick boundary"):
            runtime.install(_timed_skill(), TIMED_AUTHORITY)
        self.assertEqual(runtime.session.state.to_dict(), before)

    def test_failed_rebuild_preflight_does_not_publish_manifest(self):
        runtime, _, _ = _runtime()
        collision = _timed_skill(); collision["id"] = "basic_attack"
        before = runtime.session.state.to_dict()
        with self.assertRaisesRegex(GameplayContractError, "duplicate action id"):
            runtime.install(collision, TIMED_AUTHORITY)
        self.assertEqual(runtime.session.state.to_dict(), before)
        self.assertNotIn(("basic_attack", 1), runtime.blueprints)

    def test_versions_are_monotonic_and_old_loadout_refs_cannot_alias_new_action(self):
        runtime, _, skill = _runtime()
        change_loadout(runtime.session, runtime.manifest, actor_id="hero_actor", operation="equip_active",
                       skill=skill_ref(skill), slot=0)
        with self.assertRaisesRegex(GameplayContractError, "removed from every loadout"):
            runtime.install(_version(skill, 2), skill.material_authority)
        change_loadout(runtime.session, runtime.manifest, actor_id="hero_actor", operation="unload_active", slot=0)
        runtime.install(_version(skill, 2), skill.material_authority)
        rows = [row for row in runtime.manifest.entries if row.skill_id == skill.id]
        self.assertEqual([(row.version, row.enabled) for row in rows], [(1, False), (2, True)])
        self.assertEqual(runtime.action_registry.actions[skill.id].version, 2)
        advance_world_tick(runtime.session)
        with self.assertRaisesRegex(GameplayContractError, "next monotonic version"):
            runtime.install(_version(skill, 4), skill.material_authority)

    def test_disable_blocks_new_use_but_retains_scheduled_expiry(self):
        runtime, _, _ = _runtime()
        runtime.install(_timed_skill(), TIMED_AUTHORITY)
        timed = runtime.blueprints[("slow_mist", 1)]
        change_loadout(runtime.session, runtime.manifest, actor_id="hero_actor", operation="equip_active",
                       skill=skill_ref(timed), slot=0)
        resolve_action(runtime.session, runtime.action_registry,
                       ActionRequest("use_slow_mist", "hero_actor", "slow_mist"))
        self.assertEqual(len(runtime.session.state.scheduled_events), 1)
        advance_world_tick(runtime.session)
        change_loadout(runtime.session, runtime.manifest, actor_id="hero_actor", operation="unload_active", slot=0)
        runtime.disable("slow_mist")
        with self.assertRaisesRegex(GameplayContractError, "unknown registered action"):
            resolve_action(runtime.session, runtime.action_registry,
                           ActionRequest("reuse_slow_mist", "hero_actor", "slow_mist"))
        dispatched = runtime.session.runtime.advance_to(2.0)
        self.assertEqual(dispatched.processed_event_ids,
                         ["pmw:v04:action-expiry:use_slow_mist:slow_recovery"])
        self.assertEqual(runtime.session.state.scheduled_events, [])
        slot = runtime.session.state.entities["mist_forest"].components["pmw_gameplay_dynamics"]["fields"]["mist"]["temporary_modifiers"]["slot_0"]
        self.assertFalse(slot["active"])

    def test_checkpoint_restores_world_registry_scheduler_and_continuation_trace(self):
        runtime, compiled, _ = _runtime()
        runtime.install(_timed_skill(), TIMED_AUTHORITY)
        timed = runtime.blueprints[("slow_mist", 1)]
        change_loadout(runtime.session, runtime.manifest, actor_id="hero_actor", operation="equip_active",
                       skill=skill_ref(timed), slot=0)
        resolve_action(runtime.session, runtime.action_registry,
                       ActionRequest("use_slow_mist", "hero_actor", "slow_mist"))
        advance_world_tick(runtime.session)
        change_loadout(runtime.session, runtime.manifest, actor_id="hero_actor", operation="unload_active", slot=0)
        runtime.disable("slow_mist")
        resolve_action(runtime.session, runtime.action_registry,
                       ActionRequest("guard_before_save", "hero_actor", "basic_guard"))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "checkpoint.json"
            digest = save_registry_checkpoint(path, runtime)
            restored = load_registry_checkpoint(path, compiled)
            self.assertEqual(len(digest), 64)
        self.assertEqual(restored.session.state.to_dict(), runtime.session.state.to_dict())
        self.assertEqual(restored.manifest, runtime.manifest)
        left_status = run_phase_event(runtime.session, "owner_turn", actor_id="hero_actor")
        right_status = run_phase_event(restored.session, "owner_turn", actor_id="hero_actor")
        self.assertEqual(left_status.trace.to_dict(), right_status.trace.to_dict())
        left = runtime.session.runtime.advance_to(2.0)
        right = restored.session.runtime.advance_to(2.0)
        self.assertEqual(left.processed_event_ids, right.processed_event_ids)
        self.assertEqual(left.dispatches[0].result.trace.to_dict(), right.dispatches[0].result.trace.to_dict())
        self.assertEqual(runtime.session.state.to_dict(), restored.session.state.to_dict())

    def test_checkpoint_hash_rejects_corruption_before_rebuild(self):
        runtime, compiled, _ = _runtime()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "checkpoint.json"
            save_registry_checkpoint(path, runtime)
            document = json.loads(path.read_text(encoding="utf-8"))
            document["world"]["time"]["sim_time"] = 99
            path.write_text(json.dumps(document), encoding="utf-8")
            with self.assertRaisesRegex(GameplayContractError, "payload hash mismatch"):
                load_registry_checkpoint(path, compiled)


if __name__ == "__main__":
    unittest.main()
