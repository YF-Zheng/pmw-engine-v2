from __future__ import annotations

from copy import deepcopy
from tempfile import TemporaryDirectory
from unittest import TestCase

from pmw import Event

from examples.pmw_alpha.session import AlphaSession, AlphaSessionError
from examples.pmw_alpha.savegame import SAVE_SCHEMA
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.contracts import (
    ScopeCapability, SelectorContext,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.registry import REGISTRY_COMPONENT
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.selectors import (
    parse_selector, resolve_selector,
)


def _edges(session: AlphaSession) -> set[tuple[str, str]]:
    return {
        tuple(sorted((relation.source, relation.target)))
        for relation in session.state.relations.values()
        if relation.type == "adjacent"
    }


def _adjacent_selector(session: AlphaSession) -> tuple[str, ...]:
    capability = ScopeCapability("alpha_travel", ("adjacent_area",))
    return resolve_selector(
        session.state,
        parse_selector({"kind": "adjacent_area"}),
        SelectorContext("seventh_walker"),
        capability,
    )


class SandboxAuthorityTests(TestCase):
    def _charged_mine(self) -> AlphaSession:
        session = AlphaSession.new_game()
        session._player()["knowledge"].extend(("insight_dais", "damaged_conduit"))
        session._inventory()["thunder_crystal"] = 1.0
        session._craft("thunder_instant")
        session._equip("equip_active", "thunder_instant", 0)
        session._travel("thunder_mine")
        session._cast("thunder_instant")
        return session

    def test_public_time_tracks_completed_world_steps_not_scheduler_ticks(self) -> None:
        session = AlphaSession.new_game()
        self.assertEqual(session.public_state()["time"], 0)

        inspected = session.perform("inspect", target="survey_map")
        self.assertEqual(inspected["time"], 1)
        self.assertEqual(inspected["time"], session._time())

        session._session.runtime.schedule(Event("future-only", "ignored", time=10.0))
        scheduler_tick = session.state.tick
        traveled = session.perform("travel", target="thunder_mine")

        self.assertEqual(traveled["time"], 3)
        self.assertEqual(traveled["time"], session._time())
        self.assertEqual(session.state.tick, scheduler_tick)
        self.assertEqual(traveled["recent_events"][-1]["tick"], 3)

    def test_multi_tick_events_keep_each_completed_step_with_scheduled_roots(self) -> None:
        session = AlphaSession.new_game()
        session._session.runtime.schedule(Event("future-only", "ignored", time=10.0))
        scheduler_tick = session.state.tick

        traveled = session.perform("travel", target="moss_shallows")
        progress = [row for row in traveled["recent_events"] if row["message"].startswith("世界推进至第")]

        self.assertEqual([row["tick"] for row in progress[-2:]], [1, 2])
        self.assertEqual(traveled["recent_events"][-1]["tick"], 2)
        self.assertEqual(traveled["time"], 2)
        self.assertEqual(session.state.tick, scheduler_tick)

    def test_lift_and_bridge_edges_are_real_relations_visible_to_adjacent_selector(self) -> None:
        mine = self._charged_mine()
        mine._power_lift()
        self.assertIn(("ash_observatory", "thunder_mine"), _edges(mine))
        self.assertIn("ash_observatory", mine._neighbors("thunder_mine"))
        self.assertIn("ash_observatory", _adjacent_selector(mine))
        relation = mine.state.relations["adjacent:ash_observatory:thunder_mine"]
        self.assertEqual(relation.components["pmw_alpha_route"]["route_id"], "mine_lift")

        forest = AlphaSession.new_game()
        forest._player()["knowledge"].append("forest_heart")
        forest._inventory()["spore_bud"] = 2.0
        forest._travel("moss_shallows")
        forest._travel("frost_forest")
        forest._restore_forest()
        for _ in range(9):
            forest._spend(1, "exploration")
        self.assertIn(("ash_observatory", "frost_forest"), _edges(forest))
        self.assertIn("ash_observatory", forest._neighbors("frost_forest"))
        self.assertIn("ash_observatory", _adjacent_selector(forest))
        relation = forest.state.relations["adjacent:ash_observatory:frost_forest"]
        self.assertEqual(relation.components["pmw_alpha_route"]["route_id"], "forest_root_bridge")

    def test_flag_alone_never_authorizes_travel(self) -> None:
        session = self._charged_mine()
        session._player()["lift_powered"] = True
        self.assertNotIn("ash_observatory", session._neighbors("thunder_mine"))
        self.assertNotIn(
            "ash_observatory",
            [row.get("target") for row in session.controls() if row["action"] == "travel"],
        )
        with self.assertRaises(AlphaSessionError):
            session.perform("travel", target="ash_observatory")

        known = session._player()["lift_powered"]
        session.state.relations.pop("adjacent:ash_observatory:thunder_mine", None)
        self.assertIs(session._player()["lift_powered"], known)
        self.assertNotIn("ash_observatory", session._neighbors("thunder_mine"))

    def test_public_route_failure_preserves_state_and_registry(self) -> None:
        session = AlphaSession.new_game()
        session._player()["knowledge"].append("damaged_conduit")
        session._travel("thunder_mine")
        before_state = deepcopy(session.state.to_dict())
        before_registry = deepcopy(
            session.state.entities["pmw:v04:clock"].components[REGISTRY_COMPONENT]
        )

        with self.assertRaisesRegex(AlphaSessionError, "电荷仍不足"):
            session.perform("power_lift")

        self.assertEqual(session.state.to_dict(), before_state)
        self.assertEqual(
            session.state.entities["pmw:v04:clock"].components[REGISTRY_COMPONENT],
            before_registry,
        )

    def test_save_load_round_trips_real_unlocked_edges(self) -> None:
        self.assertEqual(SAVE_SCHEMA, "pmw-alpha-save-v0.3")
        session = self._charged_mine()
        session.perform("power_lift")
        expected = _edges(session)
        with TemporaryDirectory() as directory:
            session.save(directory)
            restored = AlphaSession.load(directory)

        self.assertEqual(_edges(restored), expected)
        self.assertIn("ash_observatory", restored._neighbors("thunder_mine"))
        self.assertIn("ash_observatory", _adjacent_selector(restored))
        self.assertTrue(restored._player()["lift_powered"])

    def test_restore_rejects_canonical_route_id_with_wrong_relation_semantics(self) -> None:
        session = self._charged_mine()
        session.perform("power_lift")
        with TemporaryDirectory() as directory:
            session.save(directory)
            baseline = AlphaSession.load(directory)
        relation_id = "adjacent:ash_observatory:thunder_mine"
        original = baseline.state.relations[relation_id]

        cases = (
            {"type": "linked"},
            {"source": "mist_camp"},
            {"target": "frost_forest"},
            {"components": {}},
            {"components": {"pmw_alpha_route": {"route_id": "forest_root_bridge", "unlocked_by": "root_bridge_formed"}}},
        )
        for change in cases:
            with self.subTest(change=change):
                restored = baseline._clone()
                relation = restored.state.relations[relation_id]
                relation.type = change.get("type", original.type)
                relation.source = change.get("source", original.source)
                relation.target = change.get("target", original.target)
                relation.components = deepcopy(change.get("components", original.components))
                with self.assertRaisesRegex(AlphaSessionError, "路线状态不完整"):
                    AlphaSession._restore(restored._registry, {})
