import unittest

from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.ai_demo import ai_demo_registry, ai_demo_session, run_ai_demo
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.build_analysis import BuildAnalyzer, RegistrySemanticsProvider
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.observation import ActorObservationBuilder, ObservationDisclosure
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.planner import BoundedPlanner, PlannerConfig


class BoundedPlannerTests(unittest.TestCase):
    def setUp(self):
        self.session, self.registry = ai_demo_session()
        self.observation = ActorObservationBuilder().build(
            self.session, self.registry, "ai_monster",
            ObservationDisclosure.create(hostile_actor_ids=("ai_hero",)),
        )

    def test_build_analysis_finds_field_condition_without_names(self):
        graph = BuildAnalyzer(RegistrySemanticsProvider(self.registry)).analyze(("raise_mist", "mist_burst"))
        edges = {(edge.producer_action_id, edge.consumer_action_id, edge.kind) for edge in graph.edges}
        self.assertIn(("raise_mist", "mist_burst", "enables_field_condition"), edges)
        edge = graph.edges[0]
        self.assertEqual(edge.producer_write.path, "field:mist:value")
        self.assertEqual(edge.consumer_read.path, "field:mist:value")

    def test_two_action_search_beats_myopic_and_random_paths(self):
        result = BoundedPlanner(
            self.registry, config=PlannerConfig(max_nodes=128, deadline_ms=None),
        ).choose(self.observation)
        self.assertEqual(result.selected.request.action_id, "raise_mist")
        log = result.decision_log.to_dict()
        one_step = {row["request"]["action_id"]: row["one_step_score"]["total"] for row in log["candidates"]}
        self.assertGreater(one_step["basic_attack"], one_step["raise_mist"])
        attack_paths = [row["total"] for row in log["paths"] if row["first"].startswith("basic_attack|")]
        self.assertTrue(attack_paths)
        self.assertGreater(result.score, max(attack_paths))
        self.assertGreater(result.score, sum(row["total"] for row in log["paths"]) / len(log["paths"]))
        self.assertIsNotNone(log["selected_path"]["response"])
        rows = {row["request"]["action_id"]: row for row in log["candidates"]}
        future = {
            item["name"]: item["value"]
            for item in rows["raise_mist"]["one_step_score"]["terms"]
        }
        self.assertGreater(future["future_potential"], 0.0)

    def test_node_budget_has_complete_one_step_fallback(self):
        result = BoundedPlanner(
            self.registry,
            config=PlannerConfig(max_legal_actions=5, max_nodes=5, deadline_ms=None),
        ).choose(self.observation)
        self.assertTrue(result.fallback_used)
        self.assertLessEqual(result.nodes_used, 5)
        log = result.decision_log.to_dict()
        self.assertEqual(log["cutoff_reason"], "node_budget")
        self.assertTrue(all(row["one_step_score"] is not None for row in log["candidates"]))

    def test_deadline_fallback_and_logs_are_deterministic(self):
        class Clock:
            def __init__(self): self.calls = 0
            def __call__(self):
                self.calls += 1
                return 0.0 if self.calls == 1 else 2.0
        config = PlannerConfig(deadline_ms=1)
        first = BoundedPlanner(self.registry, config=config, clock=Clock()).choose(self.observation)
        second = BoundedPlanner(self.registry, config=config, clock=Clock()).choose(self.observation)
        self.assertTrue(first.fallback_used)
        self.assertEqual(first.decision_log.document_json, second.decision_log.document_json)
        self.assertNotIn("elapsed", first.decision_log.document_json)
        self.assertNotIn("timestamp", first.decision_log.document_json)

    def test_demo_is_reproducible(self):
        self.assertEqual(run_ai_demo(), run_ai_demo())
        self.assertEqual(run_ai_demo()["selected_action"], "raise_mist")


if __name__ == "__main__":
    unittest.main()
