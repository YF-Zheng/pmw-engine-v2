from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.actions import ActionRequest
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.checkpoint import (
    load_registry_checkpoint,
    save_registry_checkpoint,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.combat import run_combat_round
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.content_compiler import compile_content
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.contracts import GameplayContractError
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.gate3_demo import build_gate3_demo
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.harvest import (
    HarvestRequest,
    resolve_harvest,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.loadout import (
    change_loadout,
    skill_ref,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.registry import (
    MechanismRegistryRuntime,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.time_ledger import (
    TIME_BUDGET_COMPONENT,
)


class Gate51IntegratedTransactionScenario(unittest.TestCase):
    def test_combat_harvest_exhaustion_and_checkpoint_share_one_authority(self):
        session, content, skill, harvest = build_gate3_demo(time_budget_ticks=3)
        compiled = compile_content(content)
        runtime = MechanismRegistryRuntime.from_compiled_content(session, compiled)
        change_loadout(
            runtime.session,
            runtime.manifest,
            actor_id="hero_actor",
            operation="equip_active",
            skill=skill_ref(skill),
            slot=0,
        )

        first = run_combat_round(
            runtime.session,
            runtime.action_registry,
            round_index=1,
            actor_order=("hero_actor", "plain_actor"),
            requests={
                "hero_actor": ActionRequest(
                    "gate51_cast", "hero_actor", skill.id, "plain_actor"
                ),
                "plain_actor": ActionRequest(
                    "gate51_guard", "plain_actor", "basic_guard"
                ),
            },
        )
        self.assertEqual(first.time_spend_result.duration, 1)
        plain = runtime.session.state.entities["plain_actor"]
        self.assertTrue(any(
            row["active"] and row["spec_id"] == "basic_guarding"
            for row in plain.components["pmw_gameplay_statuses"]["slots"].values()
        ))

        second = run_combat_round(
            runtime.session,
            runtime.action_registry,
            round_index=2,
            actor_order=("hero_actor", "plain_actor"),
            requests={
                "hero_actor": ActionRequest(
                    "gate51_hero_wait", "hero_actor", "basic_wait"
                ),
                "plain_actor": ActionRequest(
                    "gate51_plain_wait", "plain_actor", "basic_wait"
                ),
            },
        )
        self.assertEqual(second.world_tick_result.step, 2)
        plain = runtime.session.state.entities["plain_actor"]
        self.assertFalse(any(
            row["active"] and row["spec_id"] == "basic_guarding"
            for row in plain.components["pmw_gameplay_statuses"]["slots"].values()
        ))

        gathered = resolve_harvest(
            runtime.session,
            runtime.action_registry,
            harvest,
            HarvestRequest(
                "gate51_final_harvest", "hero_actor", harvest.id, True
            ),
            permissions=("lucky_harvest",),
        )
        self.assertEqual((gathered.duration, len(gathered.time_result.ticks)), (1, 1))
        budget = runtime.session.state.entities["pmw:v04:clock"].components[
            TIME_BUDGET_COMPONENT
        ]
        self.assertEqual((budget["spent_ticks"], budget["remaining_ticks"]), (3, 0))

        exhausted = deepcopy(runtime.session.state.to_dict())
        with self.assertRaises(GameplayContractError):
            run_combat_round(
                runtime.session,
                runtime.action_registry,
                round_index=3,
                actor_order=("hero_actor", "plain_actor"),
                requests={
                    "hero_actor": ActionRequest(
                        "gate51_after_exhaustion", "hero_actor", "basic_wait"
                    )
                },
            )
        self.assertEqual(runtime.session.state.to_dict(), exhausted)

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "gate51-checkpoint.json"
            save_registry_checkpoint(path, runtime)
            restored = load_registry_checkpoint(path, compiled)
        self.assertEqual(restored.session.state.to_dict(), runtime.session.state.to_dict())
        restored_budget = restored.session.state.entities[
            "pmw:v04:clock"
        ].components[TIME_BUDGET_COMPONENT]
        self.assertEqual(
            (restored_budget["spent_ticks"], restored_budget["remaining_ticks"]),
            (3, 0),
        )


if __name__ == "__main__":
    unittest.main()
