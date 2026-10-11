from __future__ import annotations

from copy import deepcopy
import unittest

from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.action_compiler import build_action_session
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.actions import (
    ActionRegistry, ActionRequest, _resolve_action, resolve_action,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.basics import basic_registry_document
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.runtime import (
    discover_profiles, migrate_gameplay_world, run_phase_event,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.tests.test_gate2_actions import make_session


def shield_registry(*, attack_base: float = 6.0, power_scale: float = 1.0) -> ActionRegistry:
    document = basic_registry_document(attack_base=attack_base, power_scale=power_scale)
    document["actions"].append({
        "id": "aegis_skill", "version": 1, "action_type": "skill", "builtin": False,
        "cost": {"duration": 1, "mana": 0.0},
        "scope": {"selectors": ["self"], "relation_types": []},
        "effects": [{
            "id": "aegis_layer", "kind": "shield", "target": {"kind": "self"},
            "commitment": "required", "amount": 100.0,
        }],
    })
    return ActionRegistry.parse(document)


class ShieldOwnershipRegressionTests(unittest.TestCase):
    def test_migration_is_exactly_idempotent_for_current_worlds(self):
        current, _ = make_session(shield_registry(), actors=1)
        before = current.state.to_dict()
        migrate_gameplay_world(current.state)
        migrate_gameplay_world(current.state)
        self.assertEqual(current.state.to_dict(), before)

    def test_legacy_checkpoint_shape_is_migrated_before_law_evaluation(self):
        registry = shield_registry()
        current, _ = make_session(registry, actors=1)
        resolve_action(current, registry, ActionRequest("old_guard", "actor_0", "basic_guard"))
        legacy_world = deepcopy(current.state)
        entity = legacy_world.entities["actor_0"]
        entity.components.pop("pmw_gameplay_shields")
        entity.components["pmw_gameplay_actor"]["shield"] = 100.0
        for row in entity.components["pmw_gameplay_statuses"]["slots"].values():
            row.pop("shield_layer_slot")

        migrated = build_action_session(legacy_world, discover_profiles(legacy_world), registry)
        migrated_entity = migrated.state.entities["actor_0"]
        self.assertEqual(migrated_entity.components["pmw_gameplay_actor"]["shield"], 100.0)
        legacy_layers = [
            row for row in migrated_entity.components["pmw_gameplay_shields"]["slots"].values()
            if row["active"]
        ]
        self.assertEqual(len(legacy_layers), 1)
        self.assertEqual(legacy_layers[0]["source_id"], "pmw.v04.shield.legacy")
        self.assertIsNone(
            migrated_entity.components["pmw_gameplay_statuses"]["slots"]["slot_0"]["shield_layer_slot"]
        )

        run_phase_event(migrated, "owner_turn", actor_id="actor_0")
        migrated_entity = migrated.state.entities["actor_0"]
        self.assertEqual(migrated_entity.components["pmw_gameplay_actor"]["shield"], 100.0)
        self.assertFalse(
            migrated_entity.components["pmw_gameplay_statuses"]["slots"]["slot_0"]["active"]
        )

    def test_guard_expiry_preserves_another_shield_source(self):
        registry = shield_registry()
        session, _ = make_session(registry, actors=1)
        resolve_action(session, registry, ActionRequest("guard_one", "actor_0", "basic_guard"))
        resolve_action(session, registry, ActionRequest("aegis_one", "actor_0", "aegis_skill"))

        actor = session.state.entities["actor_0"].components["pmw_gameplay_actor"]
        self.assertEqual(actor["shield"], 108.0)
        run_phase_event(session, "owner_turn", actor_id="actor_0")
        actor = session.state.entities["actor_0"].components["pmw_gameplay_actor"]
        self.assertEqual(actor["shield"], 100.0)

    def test_damage_consumes_layers_in_stable_creation_order(self):
        registry = shield_registry()
        session, _ = make_session(registry, actors=2)
        resolve_action(session, registry, ActionRequest("guard_one", "actor_0", "basic_guard"))
        resolve_action(session, registry, ActionRequest("aegis_one", "actor_0", "aegis_skill"))
        resolve_action(session, registry,
                       ActionRequest("attack_one", "actor_1", "basic_attack", "actor_0"))

        entity = session.state.entities["actor_0"]
        layers = entity.components["pmw_gameplay_shields"]["slots"]
        self.assertEqual(layers["slot_0"]["remaining"], 0.0)
        self.assertEqual(layers["slot_1"]["remaining"], 94.0)
        self.assertEqual(entity.components["pmw_gameplay_actor"]["shield"], 94.0)

        run_phase_event(session, "owner_turn", actor_id="actor_0")
        self.assertEqual(
            session.state.entities["actor_0"].components["pmw_gameplay_actor"]["shield"],
            94.0,
        )

    def test_same_source_refresh_is_bounded_and_reowned(self):
        registry = shield_registry()
        session, _ = make_session(registry, actors=1)
        resolve_action(session, registry, ActionRequest("guard_one", "actor_0", "basic_guard"))
        resolve_action(session, registry, ActionRequest("guard_two", "actor_0", "basic_guard"))
        entity = session.state.entities["actor_0"]
        active = [row for row in entity.components["pmw_gameplay_shields"]["slots"].values()
                  if row["active"]]
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]["remaining"], 8.0)
        self.assertEqual(active[0]["status_instance_id"], "guard_two:guard_duration")
        self.assertEqual(entity.components["pmw_gameplay_actor"]["shield"], 8.0)

        run_phase_event(session, "owner_turn", actor_id="actor_0")
        self.assertEqual(
            session.state.entities["actor_0"].components["pmw_gameplay_actor"]["shield"],
            0.0,
        )

    def test_same_source_refresh_does_not_restore_consumed_capacity(self):
        registry = shield_registry(attack_base=5.0, power_scale=0.0)
        session, _ = make_session(registry, actors=2)
        resolve_action(session, registry, ActionRequest("guard_one", "actor_0", "basic_guard"))
        _resolve_action(session, registry,
                        ActionRequest("attack_one", "actor_1", "basic_attack", "actor_0"))
        self.assertEqual(
            session.state.entities["actor_0"].components["pmw_gameplay_actor"]["shield"],
            3.0,
        )

        resolve_action(session, registry, ActionRequest("guard_two", "actor_0", "basic_guard"))
        entity = session.state.entities["actor_0"]
        self.assertEqual(entity.components["pmw_gameplay_actor"]["shield"], 3.0)
        layer = entity.components["pmw_gameplay_shields"]["slots"]["slot_0"]
        self.assertEqual(layer["remaining"], 3.0)
        self.assertEqual(layer["status_instance_id"], "guard_two:guard_duration")


if __name__ == "__main__":
    unittest.main()
