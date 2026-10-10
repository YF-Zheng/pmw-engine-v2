from copy import deepcopy
import unittest

from pmw import Entity

from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.ai_demo import ai_demo_registry, ai_demo_session
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.basics import basic_registry_document
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.actions import ActionRegistry
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.observation import ActorObservationBuilder, ObservationDisclosure
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.planner import BoundedPlanner, PlannerConfig


class ActorSafeObservationTests(unittest.TestCase):
    def test_observation_is_json_owned_and_ignores_hidden_world_surfaces(self):
        left, registry = ai_demo_session()
        right, _ = ai_demo_session()
        right.state.rng_state = {"future_roll": 999999}
        right.state.entities["ai_hero"].components["secret_threshold"] = {"execute_at": 49}
        right.state.entities["hidden_vault"] = Entity(
            "hidden_vault", "hidden", components={"secret_law": {"damage": 10000}}
        )
        right.runtime.engine.laws.append(object())  # A hidden Law is never projected.
        disclosure = ObservationDisclosure.create(hostile_actor_ids=("ai_hero",))
        builder = ActorObservationBuilder()
        first = builder.build(left, registry, "ai_monster", disclosure)
        second = builder.build(right, registry, "ai_monster", disclosure)
        self.assertEqual(first.document_json, second.document_json)
        self.assertNotIn("future_roll", first.document_json)
        self.assertNotIn("secret", first.document_json)
        owned = first.to_dict(); owned["actors"]["ai_hero"]["hp"] = -100
        self.assertEqual(first.to_dict()["actors"]["ai_hero"]["hp"], 50.0)
        planner = BoundedPlanner(registry, config=PlannerConfig(deadline_ms=None))
        self.assertEqual(
            planner.choose(first).decision_log.document_json,
            planner.choose(second).decision_log.document_json,
        )

    def test_unrevealed_opponent_skill_is_not_projected(self):
        session, registry = ai_demo_session()
        session.state.entities["ai_hero"].components["pmw_gameplay_actor"]["active_equipped"][0] = "mist_burst"
        observation = ActorObservationBuilder().build(session, registry, "ai_monster")
        self.assertNotIn("mist_burst", observation.to_dict()["known_actions"]["ai_hero"])
        revealed = ActorObservationBuilder().build(
            session, registry, "ai_monster",
            ObservationDisclosure.create(revealed_actions={"ai_hero": ["mist_burst"]}),
        )
        self.assertIn("mist_burst", revealed.to_dict()["known_actions"]["ai_hero"])

    def test_gate3_skill_ref_loadout_is_understood_without_hash_exposure(self):
        session, registry = ai_demo_session()
        current = registry.actions["raise_mist"]
        session.state.entities["ai_monster"].components["pmw_gameplay_actor"]["active_equipped"][0] = {
            "id": "raise_mist", "version": current.version, "canonical_hash": current.canonical_hash,
            "kind": "skill_blueprint",
        }
        observation = ActorObservationBuilder().build(session, registry, "ai_monster")
        self.assertIn("raise_mist", observation.to_dict()["known_actions"]["ai_monster"])
        self.assertNotIn(current.canonical_hash, observation.document_json)

    def test_stale_skill_ref_cannot_alias_a_new_registry_version(self):
        session, registry = ai_demo_session()
        current = registry.actions["raise_mist"]
        session.state.entities["ai_monster"].components["pmw_gameplay_actor"]["active_equipped"][0] = {
            "id": current.id, "version": current.version + 1,
            "canonical_hash": "0" * 64, "kind": "skill_blueprint",
        }
        observation = ActorObservationBuilder().build(session, registry, "ai_monster")
        self.assertNotIn("raise_mist", observation.to_dict()["known_actions"]["ai_monster"])

    def test_hidden_skill_registry_addition_cannot_change_decision(self):
        session, registry = ai_demo_session()
        document = basic_registry_document()
        hidden = deepcopy(document["actions"][0])
        hidden["id"] = "hidden_annihilation"
        hidden["builtin"] = False
        hidden["effects"][0]["amount"] = 9999
        document["actions"].append(hidden)
        augmented = ActionRegistry.parse(document)
        # Use basic worlds so both registries expose exactly the same known set.
        basic_session, _ = ai_demo_session()
        basic_session.state.entities["ai_monster"].components["pmw_gameplay_actor"]["active_equipped"] = [None] * 6
        disclosure = ObservationDisclosure.create(hostile_actor_ids=("ai_hero",))
        obs_a = ActorObservationBuilder().build(basic_session, ActionRegistry.parse(basic_registry_document()), "ai_monster", disclosure)
        obs_b = ActorObservationBuilder().build(basic_session, augmented, "ai_monster", disclosure)
        self.assertEqual(obs_a.document_json, obs_b.document_json)
        plan_a = BoundedPlanner(ActionRegistry.parse(basic_registry_document()), config=PlannerConfig(deadline_ms=None)).choose(obs_a)
        plan_b = BoundedPlanner(augmented, config=PlannerConfig(deadline_ms=None)).choose(obs_b)
        self.assertEqual(plan_a.selected.canonical_key, plan_b.selected.canonical_key)
        self.assertEqual(plan_a.decision_log.document_json, plan_b.decision_log.document_json)


if __name__ == "__main__":
    unittest.main()
