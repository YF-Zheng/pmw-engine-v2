from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.action_compiler import build_action_laws
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.actions import (
    ActionRegistry,
    ActionRequest,
    resolve_action,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.basics import basic_registry_document
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.checkpoint import (
    load_registry_checkpoint,
    save_registry_checkpoint,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.combat import run_combat_round
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.content_compiler import compile_content
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.contracts import GameplayContractError
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.gate3_demo import build_gate3_demo
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.loadout import change_loadout, skill_ref
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.registry import MechanismRegistryRuntime
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.runtime import build_runtime, discover_profiles
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.tests.test_gate2_actions import make_session
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.time_ledger import (
    TIME_BUDGET_COMPONENT,
    build_time_budget_laws,
    initialize_time_budget,
)


def _timed_demo(total_ticks: int = 1):
    session, content, skill, _ = build_gate3_demo(time_budget_ticks=total_ticks)
    return session, content, skill


def _timed_basic(total_ticks: int, actors: int):
    original, registry = make_session(actors=actors)
    world = initialize_time_budget(original.state, total_ticks)
    laws = (*build_action_laws(registry), *build_time_budget_laws())
    return build_runtime(world, discover_profiles(world), laws), registry


class CombatTimeAuthorityTests(unittest.TestCase):
    def test_finite_budget_allows_one_round_then_rejects_atomically(self):
        session, content, _ = _timed_demo(1)
        run_combat_round(
            session, content.action_registry, round_index=1,
            actor_order=("hero_actor", "plain_actor"), requests={},
        )
        budget = session.state.entities["pmw:v04:clock"].components[TIME_BUDGET_COMPONENT]
        self.assertEqual((budget["spent_ticks"], budget["remaining_ticks"]), (1, 0))
        self.assertEqual(session.state.sim_time, 1.0)

        before = deepcopy(session.state.to_dict())
        with self.assertRaisesRegex(GameplayContractError, "budget"):
            run_combat_round(
                session, content.action_registry, round_index=2,
                actor_order=("hero_actor", "plain_actor"),
                requests={"hero_actor": ActionRequest(
                    "second_round_wait", "hero_actor", "basic_wait"
                )},
            )
        self.assertEqual(session.state.to_dict(), before)

    def test_unbudgeted_fixture_mode_must_be_explicit(self):
        session, registry = make_session(actors=1)
        before = deepcopy(session.state.to_dict())
        with self.assertRaisesRegex(GameplayContractError, "time budget"):
            run_combat_round(
                session, registry, round_index=1,
                actor_order=("actor_0",), requests={},
            )
        self.assertEqual(session.state.to_dict(), before)

        result = run_combat_round(
            session, registry, round_index=1,
            actor_order=("actor_0",), requests={},
            time_policy="unbudgeted_fixture",
        )
        self.assertEqual(result.world_tick_result.step, 1)

    def test_actor_count_still_costs_exactly_one_tick(self):
        session, registry = _timed_basic(2, 4)
        run_combat_round(
            session, registry, round_index=1,
            actor_order=tuple(f"actor_{index}" for index in range(4)), requests={},
        )
        budget = session.state.entities["pmw:v04:clock"].components[TIME_BUDGET_COMPONENT]
        self.assertEqual((budget["spent_ticks"], budget["remaining_ticks"]), (1, 1))

    def test_guard_owner_turn_and_world_tick_share_the_time_lifecycle(self):
        session, registry = _timed_basic(2, 1)
        first = run_combat_round(
            session, registry, round_index=1, actor_order=("actor_0",),
            requests={"actor_0": ActionRequest(
                "timed_guard", "actor_0", "basic_guard"
            )},
        )
        self.assertEqual(first.world_tick_result.step, 1)
        run_combat_round(
            session, registry, round_index=2, actor_order=("actor_0",),
            requests={"actor_0": ActionRequest(
                "timed_wait", "actor_0", "basic_wait"
            )},
        )
        budget = session.state.entities["pmw:v04:clock"].components[TIME_BUDGET_COMPONENT]
        slots = session.state.entities["actor_0"].components["pmw_gameplay_statuses"]["slots"]
        self.assertEqual((budget["spent_ticks"], budget["remaining_ticks"]), (2, 0))
        self.assertFalse(any(row["active"] and row["spec_id"] == "basic_guarding"
                             for row in slots.values()))

    def test_checkpoint_restores_combat_budget_without_tick_drift(self):
        session, content, _, _ = build_gate3_demo(time_budget_ticks=2)
        compiled = compile_content(content)
        runtime = MechanismRegistryRuntime.from_compiled_content(session, compiled)
        run_combat_round(
            runtime.session, runtime.action_registry, round_index=1,
            actor_order=("hero_actor", "plain_actor"), requests={},
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "combat_checkpoint.json"
            save_registry_checkpoint(path, runtime)
            restored = load_registry_checkpoint(path, compiled)
        for candidate in (runtime, restored):
            run_combat_round(
                candidate.session, candidate.action_registry, round_index=2,
                actor_order=("hero_actor", "plain_actor"), requests={},
            )
        self.assertEqual(runtime.session.state.to_dict(), restored.session.state.to_dict())
        budget = restored.session.state.entities["pmw:v04:clock"].components[TIME_BUDGET_COMPONENT]
        self.assertEqual((budget["spent_ticks"], budget["remaining_ticks"]), (2, 0))
        self.assertEqual(restored.session.state.sim_time, 2.0)


class CombatActionAuthorityTests(unittest.TestCase):
    def test_public_resolve_action_cannot_bypass_equipment_authority(self):
        session, content, skill, _ = build_gate3_demo()
        before = deepcopy(session.state.to_dict())
        with self.assertRaisesRegex(GameplayContractError, "equipped"):
            resolve_action(
                session, content.action_registry,
                ActionRequest("direct_bypass", "hero_actor", skill.id, "plain_actor"),
            )
        self.assertEqual(session.state.to_dict(), before)

    def test_builtin_flag_cannot_forge_a_privileged_basic_action(self):
        document = basic_registry_document()
        document["actions"][0]["effects"][0]["amount"] = 999
        forged = ActionRegistry.parse(document)
        session, _ = make_session(forged)
        before = deepcopy(session.state.to_dict())
        with self.assertRaisesRegex(GameplayContractError, "identity"):
            resolve_action(
                session, forged,
                ActionRequest("forged_basic", "actor_0", "basic_attack", "actor_1"),
            )
        self.assertEqual(session.state.to_dict(), before)

    def test_public_resolver_has_no_forgeable_hook_mode(self):
        session, content, skill, _ = build_gate3_demo()
        before = deepcopy(session.state.to_dict())
        with self.assertRaises(TypeError):
            resolve_action(
                session, content.action_registry,
                ActionRequest("fake_hook", "hero_actor", skill.id, "plain_actor"),
                execution_kind="hook", hook_context={"fake": True},
            )
        self.assertEqual(session.state.to_dict(), before)

    def test_unequipped_skill_rejected_before_owner_turn(self):
        session, content, skill, _ = build_gate3_demo()
        resolve_action(
            session, content.action_registry,
            ActionRequest("guard_before_illegal", "hero_actor", "basic_guard"),
        )
        before = deepcopy(session.state.to_dict())
        with self.assertRaisesRegex(GameplayContractError, "equipped"):
            run_combat_round(
                session, content.action_registry, round_index=1,
                actor_order=("hero_actor", "plain_actor"),
                requests={"hero_actor": ActionRequest(
                    "illegal_mist", "hero_actor", skill.id, "plain_actor"
                )},
            )
        self.assertEqual(session.state.to_dict(), before)

    def test_equipped_skill_succeeds_but_stowed_or_other_owner_does_not(self):
        session, content, skill, _ = build_gate3_demo()
        ref = skill_ref(skill)
        change_loadout(
            session, content.manifest, actor_id="hero_actor",
            operation="equip_active", skill=ref, slot=0,
        )
        result = run_combat_round(
            session, content.action_registry, round_index=1,
            actor_order=("hero_actor", "plain_actor"),
            requests={"hero_actor": ActionRequest(
                "legal_mist", "hero_actor", skill.id, "plain_actor"
            )},
        )
        self.assertEqual([row.definition.id for row in result.outcomes], [skill.id])

        stowed, content, skill, _ = build_gate3_demo()
        change_loadout(
            stowed, content.manifest, actor_id="hero_actor",
            operation="stow_active", skill=skill_ref(skill), slot=0,
        )
        before = deepcopy(stowed.state.to_dict())
        with self.assertRaisesRegex(GameplayContractError, "equipped"):
            run_combat_round(
                stowed, content.action_registry, round_index=1,
                actor_order=("hero_actor", "plain_actor"),
                requests={"hero_actor": ActionRequest(
                    "stowed_mist", "hero_actor", skill.id, "plain_actor"
                )},
            )
        self.assertEqual(stowed.state.to_dict(), before)

        other, content, skill, _ = build_gate3_demo()
        change_loadout(
            other, content.manifest, actor_id="plain_actor",
            operation="equip_active", skill=skill_ref(skill), slot=0,
        )
        before = deepcopy(other.state.to_dict())
        with self.assertRaisesRegex(GameplayContractError, "equipped"):
            run_combat_round(
                other, content.action_registry, round_index=1,
                actor_order=("hero_actor", "plain_actor"),
                requests={"hero_actor": ActionRequest(
                    "borrowed_mist", "hero_actor", skill.id, "plain_actor"
                )},
            )
        self.assertEqual(other.state.to_dict(), before)

    def test_forged_version_or_hash_is_rejected(self):
        for field, value in (("version", 999), ("canonical_hash", "0" * 64)):
            with self.subTest(field=field):
                session, content, skill, _ = build_gate3_demo()
                forged = skill_ref(skill).to_dict()
                forged[field] = value
                session.state.entities["hero_actor"].components[
                    "pmw_gameplay_actor"
                ]["active_equipped"][0] = forged
                before = deepcopy(session.state.to_dict())
                with self.assertRaisesRegex(GameplayContractError, "equipped"):
                    run_combat_round(
                        session, content.action_registry, round_index=1,
                        actor_order=("hero_actor", "plain_actor"),
                        requests={"hero_actor": ActionRequest(
                            f"forged_{field}", "hero_actor", skill.id, "plain_actor"
                        )},
                    )
                self.assertEqual(session.state.to_dict(), before)

    def test_disabled_skill_is_rejected_even_with_stale_registry_object(self):
        session, content, skill, _ = build_gate3_demo()
        compiled = compile_content(content)
        runtime = MechanismRegistryRuntime.from_compiled_content(session, compiled)
        change_loadout(
            runtime.session, runtime.manifest, actor_id="hero_actor",
            operation="equip_active", skill=skill_ref(skill), slot=0,
        )
        change_loadout(
            runtime.session, runtime.manifest, actor_id="hero_actor",
            operation="unload_active", slot=0,
        )
        runtime.disable(skill.id)
        runtime.session.state.entities["hero_actor"].components[
            "pmw_gameplay_actor"
        ]["active_equipped"][0] = skill_ref(skill).to_dict()
        before = deepcopy(runtime.session.state.to_dict())
        with self.assertRaisesRegex(GameplayContractError, "enabled"):
            run_combat_round(
                runtime.session, content.action_registry, round_index=1,
                actor_order=("hero_actor", "plain_actor"),
                requests={"hero_actor": ActionRequest(
                    "disabled_mist", "hero_actor", skill.id, "plain_actor"
                )},
            )
        self.assertEqual(runtime.session.state.to_dict(), before)

    def test_three_basic_actions_need_no_slots(self):
        cases = (
            ("basic_attack", "actor_1"),
            ("basic_guard", None),
            ("basic_wait", None),
        )
        for action_id, target_id in cases:
            with self.subTest(action_id=action_id):
                session, registry = make_session()
                result = run_combat_round(
                    session, registry, round_index=1,
                    actor_order=("actor_0", "actor_1"),
                    requests={"actor_0": ActionRequest(
                        f"use_{action_id}", "actor_0", action_id, target_id
                    )}, time_policy="unbudgeted_fixture",
                )
                self.assertEqual(result.outcomes[0].definition.id, action_id)


if __name__ == "__main__":
    unittest.main()
