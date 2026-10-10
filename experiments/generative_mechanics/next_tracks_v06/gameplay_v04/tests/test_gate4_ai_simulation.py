from copy import deepcopy
import unittest

from pmw import Relation

from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.actions import ActionRegistry, ActionRequest
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.ai_demo import ai_demo_registry, ai_demo_session
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.basics import basic_registry_document
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.observation import ActorObservationBuilder, ObservationDisclosure
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.simulation import SandboxSimulator, revalidate_and_execute


class RealSandboxTests(unittest.TestCase):
    def setUp(self):
        self.session, self.registry = ai_demo_session()
        self.disclosure = ObservationDisclosure.create(hostile_actor_ids=("ai_hero",))
        self.observation = ActorObservationBuilder().build(
            self.session, self.registry, "ai_monster", self.disclosure,
        )
        self.simulator = SandboxSimulator(self.registry)

    def test_attack_guard_and_wait_use_production_resolver(self):
        attack = self.simulator.simulate(
            self.observation, ActionRequest("ai_attack", "ai_monster", "basic_attack", "ai_hero")
        )
        self.assertTrue(attack.legal)
        self.assertEqual(attack.next_observation.to_dict()["actors"]["ai_hero"]["hp"], 44.0)
        self.assertTrue(attack.trace()["events"])

        guard = self.simulator.simulate(
            self.observation, ActionRequest("ai_guard", "ai_monster", "basic_guard")
        )
        guarded = guard.next_observation.to_dict()["actors"]["ai_monster"]
        self.assertEqual(guarded["shield"], 2.0)
        self.assertEqual(guarded["statuses"][0]["spec_id"], "basic_guarding")

        wait = self.simulator.simulate(
            self.observation, ActionRequest("ai_wait", "ai_monster", "basic_wait")
        )
        self.assertEqual(wait.next_observation.to_dict()["actors"]["ai_monster"]["mana"], 14.0)
        self.assertEqual(self.session.state.entities["ai_hero"].components["pmw_gameplay_actor"]["hp"], 50.0)

    def test_simple_skill_changes_projected_area_through_pmw(self):
        result = self.simulator.simulate(
            self.observation, ActionRequest("ai_mist", "ai_monster", "raise_mist")
        )
        self.assertTrue(result.legal)
        self.assertEqual(result.next_observation.to_dict()["area"]["fields"]["mist"]["value"], 0.8)
        self.assertEqual(self.observation.to_dict()["area"]["fields"]["mist"]["value"], 0.0)

    def test_explicitly_visible_adjacent_scope_is_reconstructed(self):
        document = basic_registry_document()
        document["actions"].append({
            "id": "cool_annex", "version": 1, "action_type": "skill", "builtin": False,
            "cost": {"duration": 1, "mana": 0},
            "scope": {"selectors": ["adjacent_area"], "relation_types": []},
            "effects": [{"id": "cool", "kind": "modify_field", "target": {"kind": "adjacent_area"},
                         "commitment": "required", "field_id": "mist", "amount": 0.5}],
        })
        registry = ActionRegistry.parse(document)
        annex = deepcopy(self.session.state.entities["ai_arena"]); annex.id = "ai_annex"
        self.session.state.entities[annex.id] = annex
        self.session.state.relations["adjacent:ai_annex:ai_arena"] = Relation(
            "adjacent:ai_annex:ai_arena", "adjacent", "ai_annex", "ai_arena"
        )
        self.session.state.entities["ai_monster"].components["pmw_gameplay_actor"]["active_equipped"][0] = "cool_annex"
        observation = ActorObservationBuilder().build(
            self.session, registry, "ai_monster",
            ObservationDisclosure.create(visible_relation_types=("adjacent",)),
        )
        self.assertIn("ai_annex", observation.to_dict()["scoped_objects"])
        result = SandboxSimulator(registry).simulate(
            observation, ActionRequest("ai_annex_cast", "ai_monster", "cool_annex")
        )
        self.assertTrue(result.legal)

    def test_newest_state_revalidation_rejects_without_partial_commit(self):
        document = deepcopy(__import__(
            "experiments.generative_mechanics.next_tracks_v06.gameplay_v04.basics",
            fromlist=["basic_registry_document"],
        ).basic_registry_document())
        costly = deepcopy(document["actions"][0])
        costly["id"] = "costly_hit"; costly["builtin"] = False; costly["cost"]["mana"] = 5
        document["actions"].append(costly)
        registry = ActionRegistry.parse(document)
        session, _ = ai_demo_session()
        session.state.entities["ai_monster"].components["pmw_gameplay_actor"]["active_equipped"][0] = "costly_hit"
        session.state.entities["ai_monster"].components["pmw_gameplay_actor"]["mana"] = 0.0
        before = session.state.to_dict()
        result = revalidate_and_execute(
            session, registry, ActionRequest("ai_stale", "ai_monster", "costly_hit", "ai_hero")
        )
        self.assertFalse(result.accepted)
        self.assertIn("no longer legal", result.rejection)
        self.assertEqual(session.state.to_dict(), before)

    def test_live_revalidation_rejects_unequipped_trusted_skill(self):
        before = self.session.state.to_dict()
        result = revalidate_and_execute(
            self.session, self.registry,
            ActionRequest("ai_unequipped", "ai_hero", "mist_burst", "ai_monster"),
        )
        self.assertFalse(result.accepted)
        self.assertEqual(self.session.state.to_dict(), before)


if __name__ == "__main__":
    unittest.main()
