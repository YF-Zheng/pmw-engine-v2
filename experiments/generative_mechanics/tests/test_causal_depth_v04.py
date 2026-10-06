from __future__ import annotations

import unittest
from pathlib import Path

from pmw import parse_law

from experiments.generative_mechanics.causal_depth_v04 import causal_depth_from_runs, evaluate_causal_depth
from experiments.generative_mechanics.compiler import compile_skill
from experiments.generative_mechanics.runner import RootExecution, ScenarioRun, load_skill_catalog, run_scenario
from experiments.generative_mechanics.scenario import load_scenario


ZONE = "zone:test"


def law(law_id: str, read: str, write: str):
    return parse_law({
        "id": law_id,
        "mode": "event",
        "priority": 0,
        "bindings": {"zone": {"kind": "entity", "requires": ["fields"]}},
        "when": {"all": [
            {"event.type": {"eq": "lab.step"}},
            {"ref": f"$zone.fields.{read}", "gt": 0},
        ]},
        "effects": [{"op": "delta", "target": f"$zone.fields.{write}", "value": 1}],
    })


DIRECT = law("gm.skill.candidate.activate", "gate", "a")
DIRECT_B = law("gm.skill.candidate.secondary", "gate", "b")
WORLD_A = law("gm.world.a", "a", "b")
WORLD_B = law("gm.world.b", "b", "c")
BACKGROUND = law("gm.world.background", "noise", "other")
UNRELATED = law("gm.world.unrelated", "never_connected", "other")
LAWS = (WORLD_A, WORLD_B, BACKGROUND, UNRELATED)


def root(index: int, rules: tuple, *, command: str | None = None, event_id: str | None = None, time: float | None = None):
    command = command or f"cmd.{index:03d}"
    event_id = event_id or f"step.{index:03d}"
    proposals = []
    matches = []
    deltas = []
    for serial, rule in enumerate(rules, 1):
        proposal_id = f"proposal:{event_id}:{serial:03d}"
        target = rule.effects[0]["target"].removeprefix("$zone.").replace(".", "/")
        address = f"entity:{ZONE}/{target}"
        proposals.append({
            "proposal_id": proposal_id, "law_id": rule.law_id, "op": "delta",
            "target": address, "status": "accepted", "reason": None, "value": 1,
            "cause_event_id": event_id, "source_proposal_ids": [proposal_id],
            "source_law_ids": [rule.law_id], "emitted_event_id": None,
        })
        matches.append({
            "law_id": rule.law_id, "mode": "event", "bindings": {"zone": ZONE},
            "proposal_ids": [proposal_id],
        })
        deltas.append({
            "address": address, "old": 0, "new": 1,
            "proposal_ids": [proposal_id], "law_ids": [rule.law_id],
        })
    event = {
        "id": event_id, "type": "lab.step", "time": float(index if time is None else time),
        "source": None, "target": ZONE, "payload": {},
        "provenance": {"kind": "external", "parent_event": None},
    }
    trace = {
        "root_event": event,
        "events": [{
            "event": event, "event_law_matches": matches, "state_law_matches": [],
            "commits": [{
                "microstep": 0, "phase": "event",
                "accepted_proposal_ids": [item["proposal_id"] for item in proposals],
                "rejected_proposal_ids": [], "state_deltas": deltas,
                "derived_event_ids": [], "scheduled_event_ids": [],
                "cancelled_event_ids": [], "rescheduled_events": [],
            }],
        }],
        "proposals": proposals, "conflicts": [],
    }
    return RootExecution(command, event_id, "lab.step", tuple(rule.law_id for rule in rules), trace)


def run(*roots):
    return ScenarioRun("scenario", "evaluation", "mine", (), {}, tuple(roots), {}, {})


class CausalDepthV04Tests(unittest.TestCase):
    def evaluate(self, with_roots, without_roots=(), *, ablations=None, candidate_laws=(DIRECT,)):
        return causal_depth_from_runs(
            run(*with_roots), run(*without_roots), "candidate",
            world_laws=LAWS, candidate_laws=candidate_laws,
            world_law_ablations=ablations,
        )

    def test_direct_candidate_effect_has_zero_downstream_depth(self):
        result = self.evaluate((root(0, (DIRECT,)),))
        self.assertTrue(result.available)
        self.assertTrue(result.candidate_activated)
        self.assertEqual(result.depth, 0)
        self.assertEqual(result.longest_path, ())
        self.assertEqual([node.kind for node in result.nodes], ["candidate_direct"])

    def test_unactivated_candidate_is_unavailable_not_depth_zero(self):
        result = self.evaluate(())
        self.assertFalse(result.available)
        self.assertFalse(result.candidate_activated)
        self.assertIsNone(result.depth)
        self.assertIn("did not activate", result.reason)

    def test_one_additional_world_consequence_has_depth_one(self):
        result = self.evaluate((root(0, (DIRECT,)), root(1, (WORLD_A,))))
        self.assertEqual(result.depth, 1)
        self.assertEqual(result.longest_path_law_ids, ("gm.world.a",))
        self.assertEqual(len(result.edges), 1)
        self.assertEqual(result.edges[0].addresses, (f"entity:{ZONE}/fields/a",))

    def test_multilevel_chain_counts_distinct_world_laws(self):
        result = self.evaluate(
            (root(0, (DIRECT,)), root(1, (WORLD_A,)), root(2, (WORLD_B,))),
            ablations={"gm.world.a": run(root(0, (DIRECT,)))},
        )
        self.assertEqual(result.depth, 2)
        self.assertEqual(result.longest_path_law_ids, ("gm.world.a", "gm.world.b"))
        self.assertEqual(len(result.longest_path), 3)  # candidate root plus two world occurrences
        world_edge = next(edge for edge in result.edges if edge.attribution == "world_law_ablation")
        self.assertEqual(world_edge.ablation, {
            "excluded": "gm.world.a",
            "target_occurrences_present": 1,
            "target_occurrences_ablated": 0,
        })

    def test_parallel_candidate_consequences_do_not_form_false_chain(self):
        present = (
            root(0, (DIRECT, DIRECT_B)),
            root(1, (WORLD_A,)),
            root(2, (WORLD_B,)),
        )
        # B survives removal of A because the candidate independently supplied b.
        without_a = run(root(0, (DIRECT, DIRECT_B)), root(2, (WORLD_B,)))
        result = self.evaluate(
            present, ablations={"gm.world.a": without_a},
            candidate_laws=(DIRECT, DIRECT_B),
        )
        self.assertEqual(result.depth, 1)
        self.assertFalse(any(
            edge.attribution == "world_law_ablation" and edge.ablation["excluded"] == "gm.world.a"
            for edge in result.edges
        ))

    def test_repeated_execution_does_not_create_structural_depth(self):
        result = self.evaluate((
            root(0, (DIRECT,)), root(1, (WORLD_A,)), root(2, (WORLD_A,)),
        ))
        self.assertEqual(result.depth, 1)
        self.assertEqual(set(result.longest_path_law_ids), {"gm.world.a"})

    def test_unrelated_background_laws_do_not_pollute_depth(self):
        common = root(1, (BACKGROUND,), command="shared", event_id="background")
        result = self.evaluate(
            (root(0, (DIRECT,)), common, root(2, (WORLD_A, UNRELATED))),
            (common,),
        )
        self.assertEqual(result.depth, 1)
        retained = {node.law_id for node in result.nodes}
        self.assertNotIn("gm.world.background", retained)
        self.assertNotIn("gm.world.unrelated", retained)

    def test_elapsed_time_and_empty_steps_do_not_inflate_depth(self):
        result = self.evaluate((
            root(0, (DIRECT,), time=0), root(1, (), time=10), root(2, (), time=10_000),
        ))
        self.assertEqual(result.depth, 0)

    def test_mismatched_pair_is_unavailable_not_zero(self):
        other = ScenarioRun("other", "evaluation", "mine", (), {}, (), {}, {})
        result = causal_depth_from_runs(run(), other, "candidate", world_laws=LAWS, candidate_laws=(DIRECT,))
        self.assertFalse(result.available)
        self.assertIsNone(result.depth)
        self.assertIn("same scenario", result.reason)

    def test_evidence_is_deterministic(self):
        roots = (root(0, (DIRECT,)), root(1, (WORLD_A,)), root(2, (WORLD_B,)))
        ablations = {"gm.world.a": run(root(0, (DIRECT,)))}
        left = self.evaluate(roots, ablations=ablations)
        right = self.evaluate(roots, ablations=ablations)
        self.assertEqual(left.to_dict(), right.to_dict())

    def test_real_runner_ablation_removes_law_and_emits_edge_evidence(self):
        base = Path(__file__).resolve().parents[1]
        scenario = load_scenario(base / "scenarios" / "evaluation" / "environmental_hazard.json")
        catalog = load_skill_catalog()
        ablated = run_scenario(
            scenario, ("static_grave",), catalog=catalog,
            excluded_world_law_ids=("gm.world.13.iron_charges",),
        )
        self.assertFalse(any(
            law_id == "gm.world.13.iron_charges"
            for execution in ablated.roots for law_id in execution.triggered_law_ids
        ))
        result = evaluate_causal_depth(
            scenario, "static_grave", catalog=catalog, compile_mechanic=compile_skill,
        )
        self.assertTrue(result.available)
        self.assertEqual(result.depth, 2)
        self.assertTrue(any(edge.attribution == "world_law_ablation" for edge in result.edges))


if __name__ == "__main__":
    unittest.main()
