from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from pmw import load_world, save_world

from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.action_compiler import (
    build_action_session,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.actions import (
    ActionRegistry,
    ActionRequest,
    _resolve_action,
    resolve_action,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.basics import (
    basic_registry_document,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.contracts import (
    GameplayContractError,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.runtime import (
    discover_profiles,
    migrate_gameplay_world,
    run_phase_event,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.shields import (
    validate_status_shield_ownership,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.status import (
    cancel_status,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.tests.test_gate2_actions import (
    make_session,
)


def shared_status_registry(*, duration: int = 1, stack_policy: str = "refresh",
                           persistent: bool = False,
                           attack_amount: float = 4.0) -> ActionRegistry:
    document = basic_registry_document(attack_base=attack_amount, power_scale=0.0)
    document["statuses"].append({
        "id": "shared_aegis",
        "version": 1,
        "polarity": "buff",
        "max_stacks": 1,
        "stack_policy": stack_policy,
        "duration": {"unit": "owner_turn", "amount": duration},
        "granted_traits": [],
        "on_expire_resource": {"resource": "shield", "value": 0.0},
    })
    for action_id, amount in (("aegis_a", 11.0), ("aegis_b", 17.0)):
        document["actions"].append({
            "id": action_id,
            "version": 1,
            "action_type": "skill",
            "builtin": False,
            "cost": {"duration": 1, "mana": 0.0},
            "scope": {"selectors": ["self"], "relation_types": []},
            "effects": [
                {"id": "layer", "kind": "shield", "target": {"kind": "self"},
                 "commitment": "required", "amount": amount},
                {"id": "lifetime", "kind": "apply_status", "target": {"kind": "self"},
                 "commitment": "required", "status_id": "shared_aegis"},
            ],
        })
    if persistent:
        document["actions"].append({
            "id": "persistent_aegis",
            "version": 1,
            "action_type": "skill",
            "builtin": False,
            "cost": {"duration": 1, "mana": 0.0},
            "scope": {"selectors": ["self"], "relation_types": []},
            "effects": [
                {"id": "layer", "kind": "shield", "target": {"kind": "self"},
                 "commitment": "required", "amount": 23.0},
            ],
        })
    return ActionRegistry.parse(document)


def assert_ownership(test: unittest.TestCase, session) -> None:
    entity = session.state.entities["actor_0"]
    validate_status_shield_ownership(
        entity.components["pmw_gameplay_statuses"],
        entity.components["pmw_gameplay_shields"],
    )
    active_status_ids = {
        row["instance_id"]
        for row in entity.components["pmw_gameplay_statuses"]["slots"].values()
        if row["active"]
    }
    owned_layer_ids = {
        row["status_instance_id"]
        for row in entity.components["pmw_gameplay_shields"]["slots"].values()
        if row["active"] and row["status_instance_id"] is not None
    }
    test.assertTrue(owned_layer_ids <= active_status_ids)


class CrossSourceStatusShieldTests(unittest.TestCase):
    def test_different_sources_sharing_spec_expire_without_orphan(self):
        for order in (("aegis_a", "aegis_b"), ("aegis_b", "aegis_a")):
            with self.subTest(order=order):
                registry = shared_status_registry()
                session, _ = make_session(registry, actors=1)
                for index, action_id in enumerate(order):
                    resolve_action(session, registry, ActionRequest(
                        f"cast_{index}", "actor_0", action_id
                    ))
                actor = session.state.entities["actor_0"].components["pmw_gameplay_actor"]
                self.assertEqual(actor["shield"], 28.0)
                assert_ownership(self, session)

                run_phase_event(session, "owner_turn", actor_id="actor_0")

                entity = session.state.entities["actor_0"]
                self.assertEqual(entity.components["pmw_gameplay_actor"]["shield"], 0.0)
                self.assertFalse(any(
                    row["active"]
                    for row in entity.components["pmw_gameplay_shields"]["slots"].values()
                ))
                assert_ownership(self, session)

    def test_staggered_lifecycles_expire_independently_in_both_orders(self):
        for first, second in (("aegis_a", "aegis_b"), ("aegis_b", "aegis_a")):
            with self.subTest(first=first, second=second):
                registry = shared_status_registry(duration=2)
                session, _ = make_session(registry, actors=1)
                resolve_action(session, registry, ActionRequest("first", "actor_0", first))
                run_phase_event(session, "owner_turn", actor_id="actor_0")
                resolve_action(session, registry, ActionRequest("second", "actor_0", second))
                run_phase_event(session, "owner_turn", actor_id="actor_0")
                expected = 17.0 if second == "aegis_b" else 11.0
                self.assertEqual(
                    session.state.entities["actor_0"].components["pmw_gameplay_actor"]["shield"],
                    expected,
                )
                assert_ownership(self, session)
                run_phase_event(session, "owner_turn", actor_id="actor_0")
                self.assertEqual(
                    session.state.entities["actor_0"].components["pmw_gameplay_actor"]["shield"],
                    0.0,
                )

    def test_cancel_one_source_then_expire_the_other_in_both_orders(self):
        for cancelled, survivor in (("aegis_a", "aegis_b"), ("aegis_b", "aegis_a")):
            with self.subTest(cancelled=cancelled):
                registry = shared_status_registry()
                session, _ = make_session(registry, actors=1)
                request_ids = {"aegis_a": "cast_a", "aegis_b": "cast_b"}
                for action_id in (cancelled, survivor):
                    resolve_action(session, registry, ActionRequest(
                        request_ids[action_id], "actor_0", action_id
                    ))
                cancel_status(
                    session, registry, owner_id="actor_0",
                    instance_id=f"{request_ids[cancelled]}:lifetime",
                    requester_id="actor_0",
                )
                expected = 17.0 if survivor == "aegis_b" else 11.0
                self.assertEqual(
                    session.state.entities["actor_0"].components["pmw_gameplay_actor"]["shield"],
                    expected,
                )
                assert_ownership(self, session)
                run_phase_event(session, "owner_turn", actor_id="actor_0")
                self.assertEqual(
                    session.state.entities["actor_0"].components["pmw_gameplay_actor"]["shield"],
                    0.0,
                )

    def test_replace_policy_releases_replaced_source_layer(self):
        registry = shared_status_registry(stack_policy="replace")
        session, _ = make_session(registry, actors=1)
        resolve_action(session, registry, ActionRequest("cast_a", "actor_0", "aegis_a"))
        resolve_action(session, registry, ActionRequest("cast_b", "actor_0", "aegis_b"))
        entity = session.state.entities["actor_0"]
        self.assertEqual(entity.components["pmw_gameplay_actor"]["shield"], 17.0)
        self.assertEqual(sum(
            row["active"]
            for row in entity.components["pmw_gameplay_shields"]["slots"].values()
        ), 1)
        assert_ownership(self, session)
        run_phase_event(session, "owner_turn", actor_id="actor_0")
        self.assertEqual(
            session.state.entities["actor_0"].components["pmw_gameplay_actor"]["shield"],
            0.0,
        )

    def test_reject_policy_blocks_cross_source_without_partial_layer(self):
        registry = shared_status_registry(stack_policy="reject")
        session, _ = make_session(registry, actors=1)
        resolve_action(session, registry, ActionRequest("cast_a", "actor_0", "aegis_a"))
        before = deepcopy(session.state.to_dict())
        with self.assertRaisesRegex(GameplayContractError, "status stacking rejected"):
            resolve_action(session, registry, ActionRequest("cast_b", "actor_0", "aegis_b"))
        self.assertEqual(session.state.to_dict(), before)
        assert_ownership(self, session)

    def test_same_source_refresh_reowns_without_restoring_damage(self):
        registry = shared_status_registry(duration=2)
        session, _ = make_session(registry, actors=2)
        resolve_action(session, registry, ActionRequest("cast_a1", "actor_0", "aegis_a"))
        _resolve_action(session, registry, ActionRequest(
            "hit", "actor_1", "basic_attack", "actor_0"
        ))
        self.assertEqual(
            session.state.entities["actor_0"].components["pmw_gameplay_actor"]["shield"],
            7.0,
        )
        resolve_action(session, registry, ActionRequest("cast_a2", "actor_0", "aegis_a"))
        entity = session.state.entities["actor_0"]
        self.assertEqual(entity.components["pmw_gameplay_actor"]["shield"], 7.0)
        active_layers = [
            row for row in entity.components["pmw_gameplay_shields"]["slots"].values()
            if row["active"]
        ]
        self.assertEqual(len(active_layers), 1)
        self.assertEqual(active_layers[0]["status_instance_id"], "cast_a2:lifetime")
        assert_ownership(self, session)

    def test_persistent_and_temporary_layers_do_not_share_lifecycle(self):
        registry = shared_status_registry(persistent=True)
        session, _ = make_session(registry, actors=1)
        resolve_action(session, registry, ActionRequest(
            "persistent", "actor_0", "persistent_aegis"
        ))
        resolve_action(session, registry, ActionRequest("temporary", "actor_0", "aegis_a"))
        self.assertEqual(
            session.state.entities["actor_0"].components["pmw_gameplay_actor"]["shield"],
            34.0,
        )
        run_phase_event(session, "owner_turn", actor_id="actor_0")
        entity = session.state.entities["actor_0"]
        self.assertEqual(entity.components["pmw_gameplay_actor"]["shield"], 23.0)
        persistent = [
            row for row in entity.components["pmw_gameplay_shields"]["slots"].values()
            if row["active"]
        ]
        self.assertEqual(len(persistent), 1)
        self.assertIsNone(persistent[0]["status_instance_id"])
        assert_ownership(self, session)

    def test_checkpoint_then_refresh_cancel_and_expire_preserves_ownership(self):
        registry = shared_status_registry(duration=2)
        session, _ = make_session(registry, actors=2)
        resolve_action(session, registry, ActionRequest("cast_a1", "actor_0", "aegis_a"))
        resolve_action(session, registry, ActionRequest("cast_b", "actor_0", "aegis_b"))
        _resolve_action(session, registry, ActionRequest(
            "hit", "actor_1", "basic_attack", "actor_0"
        ))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "shield.json"
            save_world(path, session.state)
            world = load_world(path)
            restored = build_action_session(world, discover_profiles(world), registry)

        resolve_action(restored, registry, ActionRequest("cast_a2", "actor_0", "aegis_a"))
        self.assertEqual(
            restored.state.entities["actor_0"].components["pmw_gameplay_actor"]["shield"],
            24.0,
        )
        cancel_status(
            restored, registry, owner_id="actor_0", instance_id="cast_b:lifetime",
            requester_id="actor_0",
        )
        self.assertEqual(
            restored.state.entities["actor_0"].components["pmw_gameplay_actor"]["shield"],
            7.0,
        )
        assert_ownership(self, restored)
        run_phase_event(restored, "owner_turn", actor_id="actor_0")
        run_phase_event(restored, "owner_turn", actor_id="actor_0")
        self.assertEqual(
            restored.state.entities["actor_0"].components["pmw_gameplay_actor"]["shield"],
            0.0,
        )
        assert_ownership(self, restored)

    def test_pre_gate52_orphan_migration_is_idempotent(self):
        registry = shared_status_registry(duration=2)
        session, _ = make_session(registry, actors=1)
        resolve_action(session, registry, ActionRequest("cast_a", "actor_0", "aegis_a"))
        resolve_action(session, registry, ActionRequest("cast_b", "actor_0", "aegis_b"))
        entity = session.state.entities["actor_0"]
        status_slots = entity.components["pmw_gameplay_statuses"]["slots"]
        status_a_slot = next(name for name, row in status_slots.items()
                             if row["instance_id"] == "cast_a:lifetime")
        status_slots[status_a_slot] = {
            "active": False, "instance_id": None, "spec_id": None,
            "spec_hash": None, "source_id": None, "owner_id": None,
            "stacks": 0, "remaining": 0, "clock_unit": None,
            "granted_traits": [], "expiry_handle": None,
            "shield_layer_slot": None,
        }
        orphaned = deepcopy(session.state)

        migrate_gameplay_world(orphaned)
        after_once = orphaned.to_dict()
        migrate_gameplay_world(orphaned)
        self.assertEqual(orphaned.to_dict(), after_once)
        migrated = orphaned.entities["actor_0"]
        self.assertEqual(migrated.components["pmw_gameplay_actor"]["shield"], 17.0)
        validate_status_shield_ownership(
            migrated.components["pmw_gameplay_statuses"],
            migrated.components["pmw_gameplay_shields"],
        )

    def test_legacy_scalar_migration_remains_idempotent_and_unowned(self):
        registry = shared_status_registry()
        session, _ = make_session(registry, actors=1)
        entity = session.state.entities["actor_0"]
        entity.components.pop("pmw_gameplay_shields")
        entity.components["pmw_gameplay_actor"]["shield"] = 9.0
        migrate_gameplay_world(session.state)
        once = session.state.to_dict()
        migrate_gameplay_world(session.state)
        self.assertEqual(session.state.to_dict(), once)
        layers = [
            row for row in entity.components["pmw_gameplay_shields"]["slots"].values()
            if row["active"]
        ]
        self.assertEqual(len(layers), 1)
        self.assertIsNone(layers[0]["status_instance_id"])

    def test_malformed_temporary_ownership_is_rejected_before_action_commit(self):
        registry = shared_status_registry()
        session, _ = make_session(registry, actors=1)
        resolve_action(session, registry, ActionRequest("cast_a", "actor_0", "aegis_a"))
        entity = session.state.entities["actor_0"]
        layer = next(
            row for row in entity.components["pmw_gameplay_shields"]["slots"].values()
            if row["active"]
        )
        layer["status_instance_id"] = "missing:status"
        before = deepcopy(session.state.to_dict())
        with self.assertRaisesRegex(GameplayContractError, "no unique status owner"):
            resolve_action(session, registry, ActionRequest("wait", "actor_0", "basic_wait"))
        self.assertEqual(session.state.to_dict(), before)

    def test_mismatched_layer_caster_is_rejected_before_action_commit(self):
        registry = shared_status_registry()
        session, _ = make_session(registry, actors=2)
        resolve_action(session, registry, ActionRequest("cast_a", "actor_0", "aegis_a"))
        entity = session.state.entities["actor_0"]
        layer = next(
            row for row in entity.components["pmw_gameplay_shields"]["slots"].values()
            if row["active"]
        )
        layer["owner_id"] = "actor_1"
        before = deepcopy(session.state.to_dict())
        with self.assertRaisesRegex(GameplayContractError, "no unique status owner"):
            resolve_action(session, registry, ActionRequest("wait", "actor_0", "basic_wait"))
        self.assertEqual(session.state.to_dict(), before)

    def test_mismatched_layer_source_lineage_is_rejected_before_action_commit(self):
        registry = shared_status_registry()
        session, _ = make_session(registry, actors=1)
        resolve_action(session, registry, ActionRequest("cast_a", "actor_0", "aegis_a"))
        entity = session.state.entities["actor_0"]
        layer = next(
            row for row in entity.components["pmw_gameplay_shields"]["slots"].values()
            if row["active"]
        )
        layer["source_id"] = "aegis_b:layer"
        before = deepcopy(session.state.to_dict())
        with self.assertRaisesRegex(GameplayContractError, "no unique status owner"):
            resolve_action(session, registry, ActionRequest("wait", "actor_0", "basic_wait"))
        self.assertEqual(session.state.to_dict(), before)


if __name__ == "__main__":
    unittest.main()
