from __future__ import annotations

import unittest

from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.contracts import GameplayContractError
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.gate3_demo import build_gate3_demo, run_gate3_demo
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.loadout import change_loadout, skill_ref


class LoadoutIntegrationTests(unittest.TestCase):
    def test_active_move_is_reversible(self):
        session, content, skill, _ = build_gate3_demo(); ref = skill_ref(skill)
        change_loadout(session, content.manifest, actor_id="hero_actor", operation="equip_active", skill=ref, slot=0)
        change_loadout(session, content.manifest, actor_id="hero_actor", operation="move_active", slot=0, other_slot=2)
        change_loadout(session, content.manifest, actor_id="hero_actor", operation="unstow_active", slot=4, other_slot=2)
        actor = session.state.entities["hero_actor"].components["pmw_gameplay_actor"]
        self.assertIsNone(actor["active_stowed"][2]); self.assertEqual(actor["active_equipped"][4]["id"], skill.id)

    def test_empty_move_fails_without_mutation(self):
        session, content, _, _ = build_gate3_demo(); before = session.state.to_dict()
        with self.assertRaises(GameplayContractError):
            change_loadout(session, content.manifest, actor_id="hero_actor", operation="move_active", slot=0, other_slot=0)
        self.assertEqual(session.state.to_dict(), before)

    def test_loadout_locked_in_combat(self):
        session, content, skill, _ = build_gate3_demo()
        session.state.entities["hero_actor"].components["pmw_gameplay_actor"]["in_combat"] = True
        with self.assertRaises(GameplayContractError):
            change_loadout(session, content.manifest, actor_id="hero_actor", operation="equip_active", skill=skill_ref(skill), slot=0)

    def test_demo_has_trace_and_no_scheduler_leak(self):
        result = run_gate3_demo()
        self.assertTrue(result["trace_present"]); self.assertEqual(result["scheduled_events"], 0)


if __name__ == "__main__": unittest.main()
