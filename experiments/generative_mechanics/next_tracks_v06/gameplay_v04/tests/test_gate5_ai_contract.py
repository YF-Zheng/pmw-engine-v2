from __future__ import annotations

import unittest

from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.actions import ActionRequest
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.ai_demo import ai_demo_session
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.observation import ActorObservationBuilder, ObservationDisclosure
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.planner import BoundedPlanner, PlannerConfig
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.simulation import revalidate_and_execute


class ActorAndAIContractTests(unittest.TestCase):
    def test_ai_plan_beats_one_step_and_average_bounded_paths(self):
        session, registry = ai_demo_session()
        observation = ActorObservationBuilder().build(
            session, registry, "ai_monster",
            ObservationDisclosure.create(hostile_actor_ids=("ai_hero",)),
        )
        result = BoundedPlanner(
            registry, config=PlannerConfig(max_nodes=128, deadline_ms=None),
        ).choose(observation)
        document = result.decision_log.to_dict()
        one_step = max(row["one_step_score"]["total"] for row in document["candidates"])
        random_expectation = sum(row["total"] for row in document["paths"]) / len(document["paths"])
        self.assertEqual(result.selected.request.action_id, "raise_mist")
        self.assertGreater(result.score, one_step)
        self.assertGreater(result.score, random_expectation)
        self.assertLessEqual(result.nodes_used, 128)

    def test_repeated_planning_is_bounded_and_never_emits_an_illegal_request(self):
        for _ in range(12):
            session, registry = ai_demo_session()
            disclosure = ObservationDisclosure.create(hostile_actor_ids=("ai_hero",))
            observation = ActorObservationBuilder().build(session, registry, "ai_monster", disclosure)
            plan = BoundedPlanner(
                registry, config=PlannerConfig(max_nodes=64, deadline_ms=None),
            ).choose(observation)
            self.assertIsNotNone(plan.selected)
            self.assertLessEqual(plan.nodes_used, 64)
            execution = revalidate_and_execute(
                session, registry,
                ActionRequest("gate5_execute", "ai_monster", plan.selected.request.action_id,
                              plan.selected.request.target_actor_id),
                disclosure=disclosure,
            )
            self.assertTrue(execution.accepted)


if __name__ == "__main__":
    unittest.main()
