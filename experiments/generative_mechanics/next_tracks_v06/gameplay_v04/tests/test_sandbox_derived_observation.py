from __future__ import annotations

from copy import deepcopy
import json
import math
from pathlib import Path
import unittest

from pmw import Relation

from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.actions import (
    ActionRequest,
    submit_timed_primary_action,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.contracts import (
    GameplayContractError,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.derived import (
    DERIVED_COMPONENT,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.legal_actions import (
    LegalActionGenerator,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.observation import (
    ActorObservation,
    ActorObservationBuilder,
    ObservationDisclosure,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.simulation import (
    SandboxSimulator,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.tests.test_p1_scenarios import (
    AREA,
    NPC,
    OTHER_AREA,
    PLAYER,
    _actor_state,
    _budget,
    _field,
    _field_state,
    _skill,
    _skill_raw,
    _world,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.tests.test_sandbox_derived_catalog import (
    _derived_values,
    _formal_runtime,
    _weighted,
)


PROJECT_ROOT = Path(__file__).resolve().parents[5]
TEST_TMP = PROJECT_ROOT / "docs" / "agent_bootstrap" / "evidence" / "test_tmp"

# Captured from the unchanged fixture before this fix was applied.  This whole
# document digest proves the no-Derived Observation path stayed byte-identical.
LEGACY_DOCUMENT_SHA256 = (
    "766cf7daed2e0346b066081ef14630b99c26da1bf064524d9e604f893a36f722"
)
LEGACY_REVISION_TOKEN = (
    "d20da7f1a84f076eaab75b66a0c8571a83851fb68d2808f3169b224dd19b1bd6"
)


def _static_fields():
    return [
        _field("humidity", initial=0.2, target=0.2, rate=0.0),
        _field("temperature", initial=0.4, target=0.4, rate=0.0),
    ]


def _derived_skill(
    skill_id: str,
    *,
    condition=None,
    amount: float,
    duration: int = 1,
    mana: float = 3.0,
):
    return _skill(_skill_raw(
        skill_id,
        [{
            "id": f"{skill_id}_effect",
            "kind": "modify_field",
            "target": {"kind": "current_area"},
            "commitment": "required",
            "field_id": "humidity",
            "amount": amount,
        }],
        condition=condition,
        duration=duration,
        mana=mana,
        budget=6.0,
    ))


def _gated_skill():
    return _derived_skill(
        "observed_derived_gate",
        condition={"derived": {
            "subject": "current_area",
            "key": "comfort",
            "comparator": "gte",
            "value": 0.5,
        }},
        amount=0.1,
        duration=2,
        mana=4.0,
    )


def _opener_skill():
    return _derived_skill(
        "observed_derived_opener",
        amount=0.2,
        duration=1,
        mana=1.0,
    )


def _runtime(skills=()):
    return _formal_runtime(
        _world(_static_fields()),
        skills,
        derived_by_area={
            AREA: (_observation_weighted(),),
            OTHER_AREA: (_observation_weighted(),),
        },
    )


def _observation_weighted():
    return _weighted(
        terms=(("humidity", 2.0),),
        bias=0.0,
        minimum=0.0,
        maximum=2.0,
    )


class DerivedObservationSandboxTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        TEST_TMP.mkdir(parents=True, exist_ok=True)

    def test_observation_projects_only_current_area_derived_values(self):
        world = _world(
            _static_fields(),
            extra_relations=(
                Relation("adjacent:current:other", "adjacent", AREA, OTHER_AREA),
            ),
        )
        runtime, compiled = _formal_runtime(
            world,
            (),
            derived_by_area={
                AREA: (_observation_weighted(),),
                OTHER_AREA: (_observation_weighted(),),
            },
        )
        self.assertAlmostEqual(
            _derived_values(runtime)["comfort"], 0.4, delta=1e-12
        )
        observation = ActorObservationBuilder().build(
            runtime.session,
            runtime.action_registry,
            PLAYER,
            ObservationDisclosure.create(visible_relation_types=("adjacent",)),
        )
        document = observation.to_dict()
        self.assertEqual(
            document["area"],
            {"id": AREA, "fields": document["area"]["fields"], "derived": {"comfort": 0.4}},
        )
        self.assertIn(OTHER_AREA, document["scoped_objects"])
        self.assertNotIn("derived", document["scoped_objects"][OTHER_AREA])
        self.assertNotIn("spec_hash", observation.document_json)
        self.assertNotIn(DERIVED_COMPONENT, observation.document_json)
        self.assertNotIn(
            runtime.session.state.entities[AREA].components[
                DERIVED_COMPONENT
            ]["spec_hash"],
            observation.document_json,
        )
        derived_law_ids = [
            law["id"] for law in compiled.laws
            if law["id"].startswith("pmw.v04.derived.")
        ]
        self.assertTrue(derived_law_ids)
        for law_id in derived_law_ids:
            self.assertNotIn(law_id, observation.document_json)

    def test_derived_gate_false_and_true_parity_for_player_and_npc(self):
        gated = _gated_skill()
        opener = _opener_skill()

        for actor_id in (PLAYER, NPC):
            with self.subTest(actor=actor_id, state="false"):
                runtime, _ = _runtime((gated, opener))
                disclosure = ObservationDisclosure.create(
                    revealed_actions={actor_id: (gated.id,)}
                )
                observation = ActorObservationBuilder().build(
                    runtime.session,
                    runtime.action_registry,
                    actor_id,
                    disclosure,
                )
                self.assertEqual(
                    observation.to_dict()["area"]["derived"], {"comfort": 0.4}
                )
                result = SandboxSimulator(
                    runtime.action_registry
                ).simulate(
                    observation,
                    ActionRequest(
                        f"false_sandbox_{actor_id}", actor_id, gated.id
                    ),
                )
                self.assertFalse(result.legal)
                self.assertEqual(
                    result.rejection, "action condition is not satisfied"
                )
                legal = LegalActionGenerator(runtime.action_registry).generate(
                    observation, actor_id=actor_id
                )
                self.assertNotIn(
                    gated.id, {row.request.action_id for row in legal}
                )
                before = (
                    deepcopy(runtime.session.state.to_dict()),
                    _actor_state(runtime, actor_id)["mana"],
                    _budget(runtime)["spent_ticks"],
                )
                with self.assertRaisesRegex(
                    GameplayContractError,
                    "^action condition is not satisfied$",
                ):
                    submit_timed_primary_action(
                        runtime.session,
                        runtime.action_registry,
                        ActionRequest(
                            f"false_live_{actor_id}", actor_id, gated.id
                        ),
                    )
                self.assertEqual(
                    (
                        runtime.session.state.to_dict(),
                        _actor_state(runtime, actor_id)["mana"],
                        _budget(runtime)["spent_ticks"],
                    ),
                    before,
                )

            with self.subTest(actor=actor_id, state="true"):
                runtime, _ = _runtime((gated, opener))
                submit_timed_primary_action(
                    runtime.session,
                    runtime.action_registry,
                    ActionRequest("open_derived_gate", PLAYER, opener.id),
                )
                self.assertAlmostEqual(
                    _derived_values(runtime)["comfort"], 0.8, delta=1e-12
                )
                observation = ActorObservationBuilder().build(
                    runtime.session,
                    runtime.action_registry,
                    actor_id,
                    ObservationDisclosure.create(
                        revealed_actions={actor_id: (gated.id,)}
                    ),
                )
                self.assertEqual(
                    observation.to_dict()["area"]["derived"], {"comfort": 0.8}
                )
                before_mana = _actor_state(runtime, actor_id)["mana"]
                result = SandboxSimulator(
                    runtime.action_registry
                ).simulate(
                    observation,
                    ActionRequest(
                        f"true_sandbox_{actor_id}", actor_id, gated.id
                    ),
                )
                self.assertTrue(result.legal, result.rejection)
                self.assertEqual(
                    result.outcome()["cost"], {"duration": 2, "mana": 4.0}
                )
                next_document = result.next_observation.to_dict()
                self.assertEqual(
                    next_document["actors"][actor_id]["mana"],
                    before_mana - 4.0,
                )
                # The sandbox has no Derived Laws, so the projected value stays
                # at the supplied snapshot after its simulated Field write.
                self.assertEqual(
                    next_document["area"]["derived"], {"comfort": 0.8}
                )
                legal = LegalActionGenerator(runtime.action_registry).generate(
                    observation, actor_id=actor_id
                )
                self.assertIn(
                    gated.id, {row.request.action_id for row in legal}
                )

                before_spent = _budget(runtime)["spent_ticks"]
                live = submit_timed_primary_action(
                    runtime.session,
                    runtime.action_registry,
                    ActionRequest(
                        f"true_live_{actor_id}", actor_id, gated.id
                    ),
                )
                self.assertEqual(live.action.cost.mana, 4.0)
                self.assertEqual(live.time.duration, 2)
                self.assertEqual(live.time.ticks.__len__(), 2)
                self.assertEqual(
                    _actor_state(runtime, actor_id)["mana"], before_mana - 4.0
                )
                self.assertEqual(
                    _budget(runtime)["spent_ticks"], before_spent + 2
                )
                self.assertAlmostEqual(
                    _field_state(runtime)["value"], 0.5, delta=1e-12
                )

    def test_legacy_area_document_and_digest_are_byte_identical(self):
        runtime, _ = _formal_runtime(_world(_static_fields()), ())
        observation = ActorObservationBuilder().build(
            runtime.session, runtime.action_registry, PLAYER
        )
        document = observation.to_dict()
        self.assertEqual(set(document["area"]), {"id", "fields"})
        self.assertEqual(observation.canonical_sha256, LEGACY_DOCUMENT_SHA256)
        self.assertEqual(observation.revision_token, LEGACY_REVISION_TOKEN)
        self.assertEqual(
            observation.document_json,
            json.dumps(
                document,
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ),
        )

    def test_live_non_finite_derived_value_is_rejected(self):
        runtime, _ = _runtime()
        values = _derived_values(runtime)
        for label, bad_value in (
            ("nan_fixture", math.nan),
            ("positive_infinity_fixture", math.inf),
            ("negative_infinity_fixture", -math.inf),
        ):
            with self.subTest(fixture=label):
                values["comfort"] = bad_value
                with self.assertRaisesRegex(
                    GameplayContractError, "must be a finite number"
                ):
                    ActorObservationBuilder().build(
                        runtime.session, runtime.action_registry, PLAYER
                    )
        component = runtime.session.state.entities[AREA].components[
            DERIVED_COMPONENT
        ]
        component["values"] = []
        with self.assertRaisesRegex(
            GameplayContractError, "component values must be an object"
        ):
            ActorObservationBuilder().build(
                runtime.session, runtime.action_registry, PLAYER
            )

    def test_sandbox_rejects_malformed_derived_projection(self):
        runtime, _ = _runtime()
        observation = ActorObservationBuilder().build(
            runtime.session, runtime.action_registry, PLAYER
        )
        document = observation.to_dict()
        malformed_values = (
            [],
            {"comfort": True},
            {"comfort": "0.5"},
            {"": 0.5},
        )
        for index, value in enumerate(malformed_values):
            with self.subTest(case=index):
                candidate = deepcopy(document)
                candidate["area"]["derived"] = value
                projected = ActorObservation.from_document(candidate)
                with self.assertRaises(GameplayContractError):
                    SandboxSimulator(runtime.action_registry)._build(projected)

        non_finite = deepcopy(document)
        non_finite["area"]["derived"] = {"comfort": math.nan}
        raw = json.dumps(
            non_finite,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=True,
        )
        projected = ActorObservation(raw, "fixture-none-finite")
        with self.assertRaisesRegex(
            GameplayContractError, "must be a finite number"
        ):
            SandboxSimulator(runtime.action_registry)._build(projected)

        runtime, _ = _runtime((_gated_skill(),))
        observation = ActorObservationBuilder().build(
            runtime.session,
            runtime.action_registry,
            PLAYER,
            ObservationDisclosure.create(
                revealed_actions={PLAYER: ("observed_derived_gate",)}
            ),
        )
        mutated = observation.to_dict()
        mutated["area"]["derived"]["comfort"] = "changed"
        tampered = ActorObservation.from_document(mutated)
        with self.assertRaisesRegex(
            GameplayContractError, "must be a finite number"
        ):
            SandboxSimulator(runtime.action_registry).simulate(
                tampered,
                ActionRequest(
                    "tampered_derived", PLAYER, "observed_derived_gate"
                ),
            )


if __name__ == "__main__":
    unittest.main()
