from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from pmw import Entity, Relation

from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.actions import (
    ACTOR_COMPONENT,
    ActionRegistry,
    ActionRequest,
    _resolve_action,
    parse_action_definition,
    parse_action_request,
    submit_timed_primary_action,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.basics import (
    basic_registry,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.blueprints import (
    instantiate_actor,
    instantiate_area,
    parse_actor_blueprint,
    parse_area_blueprint,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.checkpoint import (
    load_registry_checkpoint,
    save_registry_checkpoint,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.content_compiler import (
    build_content_session,
    compile_content,
    initialize_content_world,
    make_content,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.contracts import (
    GameplayContractError,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.effects import (
    EFFECT_KINDS,
    parse_effect,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.loadout import (
    change_loadout,
    skill_ref,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.materials import (
    material_authority,
    parse_material,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.registry import (
    MechanismRegistryRuntime,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.relations import (
    RELATION_COMPONENT,
    RelationController,
    RelationProfile,
    instantiate_relation,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.runtime import (
    advance_world_tick,
    clock_entity,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.skills import (
    _effect_cost,
    parse_skill_blueprint,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.time_ledger import (
    TIME_BUDGET_COMPONENT,
    initialize_time_budget,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.worlds import (
    build_gameplay_world,
)


PROJECT_ROOT = Path(__file__).resolve().parents[5]
TEST_TMP = PROJECT_ROOT / "docs" / "agent_bootstrap" / "evidence" / "test_tmp"

PLAYER = "qa_move_player"
NPC = "qa_move_npc"
AREA_A = "qa_move_area_a"
AREA_B = "qa_move_area_b"
AREA_C = "qa_move_area_c"
CLOCK_ID = "pmw:v04:clock"
MATERIAL_ID = "qa_move_material"
MOVE_SKILL = "qa_move_step"
CONTROL_SKILL = "qa_move_link_control"
PROFILE_ID = "qa_move_link_profile"
LINK_ID = "qa_move_link"
LINK_SOURCE = "qa_move_link_source"
LINK_TARGET = "qa_move_link_target"
LINK_SOURCE_MARKER = "qa_move_link_source_marker"
LINK_TARGET_MARKER = "qa_move_link_target_marker"


def _field(*, initial=0.2, target=0.8, rate=0.2):
    return {
        "id": "humidity",
        "domain": {"min": 0.0, "max": 1.0},
        "initial": initial,
        "target": target,
        "rate": rate,
        "curve": "linear",
        "max_persistent_patches": 2,
        "max_temporary_modifiers": 2,
    }


def _area(area_id: str):
    return instantiate_area(
        parse_area_blueprint({
            "protocol": "pmw-gameplay-v0.4",
            "kind": "area_blueprint",
            "id": f"{area_id}_blueprint",
            "fields": [_field()],
        }),
        area_id,
    )


def _actor(actor_id: str, *, controller: str):
    return instantiate_actor(
        parse_actor_blueprint({
            "protocol": "pmw-gameplay-v0.4",
            "kind": "actor_blueprint",
            "id": f"{actor_id}_blueprint",
            "hp": {"max": 50, "initial": 50},
            "mana": {"max": 30, "initial": 20, "dynamics": None},
            "attributes": {
                "power": 4,
                "control": 4,
                "resilience": 4,
                "agility": 4,
            },
            "traits": [],
        }),
        actor_id,
        controller=controller,
    )


def _move_effect(effect_id: str = "travel"):
    return {
        "id": effect_id,
        "kind": "move_actor",
        "target": {"kind": "adjacent_area"},
        "commitment": "required",
    }


def _modify_field_effect(effect_id: str = "soak"):
    return {
        "id": effect_id,
        "kind": "modify_field",
        "target": {"kind": "current_area"},
        "commitment": "required",
        "field_id": "humidity",
        "amount": 0.1,
    }


def _dynamics_effect(effect_id: str = "soak_rate"):
    return {
        "id": effect_id,
        "kind": "dynamics_modifier",
        "target": {"kind": "current_area"},
        "commitment": "required",
        "field_id": "humidity",
        "rate_add": 0.2,
        "rate_multiplier": 1.0,
        "curve": "linear",
        "curve_priority": 2,
        "duration": 6,
    }


def _modifier_effect(
    effect_id: str = "disable_link",
    *,
    profile_id: str = PROFILE_ID,
    enabled: bool = False,
    duration: int = 2,
):
    return {
        "id": effect_id,
        "kind": "relation_modifier",
        "target": {"kind": "current_area"},
        "commitment": "required",
        "relation_profile_id": profile_id,
        "relation_enabled": enabled,
        "duration": duration,
    }


def _skill_document(
    skill_id: str,
    effects: list[dict],
    *,
    kind: str = "skill_blueprint",
    trigger: str = "on_use",
    mana: float = 4.0,
    budget: float = 20.0,
    selectors=None,
    relations=(),
):
    selectors = selectors or list(dict.fromkeys(
        item["target"]["kind"] for item in effects
    ))
    return {
        "protocol": "pmw-gameplay-v0.4",
        "kind": kind,
        "id": skill_id,
        "version": 1,
        "trigger": trigger,
        "condition": None,
        "duration": None,
        "cost": {
            "duration": 1,
            "mana": 0 if kind == "passive_blueprint" else mana,
        },
        "scope": {
            "selectors": selectors,
            "relation_types": list(relations),
        },
        "effects": effects,
        "budget": {"limit": budget},
        "max_firings_per_root": 1,
        "material_ids": [MATERIAL_ID],
    }


def _material(
    *,
    kinds,
    selectors,
    budget: float = 40.0,
):
    return parse_material({
        "id": MATERIAL_ID,
        "tier": "rare",
        "region_rarity": "scarce",
        "traits": [{
            "id": "qa_move_authority",
            "effect_kinds": list(kinds),
            "selectors": list(selectors),
            "budget_points": budget,
        }],
    })


def _skill(
    raw: dict,
    *,
    kinds=None,
    selectors=None,
):
    kinds = kinds or tuple(dict.fromkeys(
        item["kind"] for item in raw["effects"]
    ))
    selectors = selectors or tuple(dict.fromkeys(
        item["target"]["kind"] for item in raw["effects"]
    ))
    return parse_skill_blueprint(
        raw,
        basic_registry().statuses,
        material_authority((_material(
            kinds=kinds,
            selectors=selectors,
            budget=raw["budget"]["limit"],
        ),)),
    )


def _profile(*, owner=PLAYER):
    return RelationProfile(
        PROFILE_ID,
        LINK_ID,
        "adjacent",
        LINK_SOURCE,
        LINK_TARGET,
        owner,
        AREA_A,
        (LINK_SOURCE_MARKER,),
        (LINK_TARGET_MARKER,),
        8,
    )


def _link_world(
    *,
    profile: RelationProfile,
    base_enabled: bool = True,
    parallel_links=(),
    extra_located=(),
):
    return _world(
        links=(),
        extra_entities=(
            Entity(
                LINK_SOURCE,
                "qa_link_endpoint",
                components={LINK_SOURCE_MARKER: {}},
            ),
            Entity(
                LINK_TARGET,
                "qa_link_endpoint",
                components={LINK_TARGET_MARKER: {}},
            ),
        ),
        extra_relations=(
            Relation(
                "qa_located_link_source",
                "located_in",
                LINK_SOURCE,
                AREA_A,
            ),
            Relation(
                "qa_located_link_target",
                "located_in",
                LINK_TARGET,
                AREA_A,
            ),
            instantiate_relation(profile, base_enabled=base_enabled),
            *parallel_links,
        ),
        extra_located=extra_located,
    )


def _world(
    *,
    player_area=AREA_A,
    npc_area=AREA_A,
    links=(("qa_bare_ab", None),),
    extra_located=(),
    extra_entities=(),
    extra_relations=(),
    collision_id=None,
):
    areas = {
        AREA_A: _area(AREA_A),
        AREA_B: _area(AREA_B),
        AREA_C: _area(AREA_C),
    }
    actors = {
        PLAYER: _actor(PLAYER, controller="human"),
        NPC: _actor(NPC, controller="ai"),
    }
    world = build_gameplay_world(
        "qa_move_world",
        areas=areas.values(),
        actors=actors.values(),
        placements=((PLAYER, player_area), (NPC, npc_area)),
    )
    world.entities[CLOCK_ID] = clock_entity()
    for relation_id, enabled in links:
        components = {}
        if isinstance(enabled, dict):
            components = deepcopy(enabled)
        elif enabled is not None:
            components[RELATION_COMPONENT] = {"effective_enabled": enabled}
        world.relations[relation_id] = Relation(
            relation_id,
            "adjacent",
            AREA_A,
            AREA_B,
            components=components,
        )
    for index, row in enumerate(extra_located):
        actor_id, area_id = row
        relation_id = f"qa_extra_located_{index}"
        world.relations[relation_id] = Relation(
            relation_id, "located_in", actor_id, area_id
        )
    for entity in extra_entities:
        world.entities[entity.id] = entity
    for relation in extra_relations:
        world.relations[relation.id] = relation
    if collision_id is not None:
        world.entities[collision_id] = Entity(
            collision_id, "qa_collision", components={}
        )
    return initialize_time_budget(world, 20)


def _bare_world(*, relation_id="qa_bare_ab"):
    return _world(
        links=(),
        extra_relations=(
            Relation(relation_id, "adjacent", AREA_A, AREA_B),
        ),
    )


def _area_link_world(profile: RelationProfile, *, base_enabled=True):
    return _world(
        links=(),
        extra_relations=(
            instantiate_relation(profile, base_enabled=base_enabled),
        ),
    )


def _formal_runtime(
    skills,
    *,
    world=None,
    relation_controller=None,
    equip=(PLAYER, NPC),
):
    base = ActionRegistry(
        basic_registry().actions.values(),
        basic_registry().statuses.values(),
        relation_controller=relation_controller,
    )
    content = make_content(
        base,
        skills=tuple(skills),
        material_ids=(MATERIAL_ID,),
    )
    initialized = initialize_content_world(
        world if world is not None else _world(),
        content,
    )
    compiled = compile_content(content)
    session = build_content_session(initialized, compiled)
    runtime = MechanismRegistryRuntime.from_compiled_content(session, compiled)
    for actor_id in equip:
        for slot, skill in enumerate(skills):
            change_loadout(
                runtime.session,
                runtime.manifest,
                actor_id=actor_id,
                operation="equip_active",
                skill=skill_ref(skill),
                slot=slot,
            )
    return runtime, compiled


def _install_support_laws(runtime, compiled, laws):
    from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.content_compiler import (
        CompiledGate3Content,
    )

    isolated = CompiledGate3Content(
        compiled.content,
        (*compiled.laws, *(deepcopy(law) for law in laws)),
    )
    return MechanismRegistryRuntime.from_compiled_content(
        build_content_session(runtime.session.state, isolated),
        isolated,
    )


def _move_skill():
    return _skill(_skill_document(MOVE_SKILL, [_move_effect()]))


def _control_skill():
    return _skill(
        _skill_document(
            CONTROL_SKILL,
            [_modifier_effect()],
            mana=1.0,
            budget=8.0,
            relations=("adjacent",),
        ),
        kinds=("relation_modifier",),
        selectors=("current_area",),
    )


def _locations(runtime, actor_id: str):
    return sorted(
        (
            relation for relation in runtime.session.state.relations.values()
            if relation.type == "located_in"
            and relation.source == actor_id
        ),
        key=lambda relation: relation.id,
    )


def _budget(runtime):
    return runtime.session.state.entities[CLOCK_ID].components[
        TIME_BUDGET_COMPONENT
    ]


def _actor_state(runtime, actor_id: str):
    return runtime.session.state.entities[actor_id].components[ACTOR_COMPONENT]


def _field_state(runtime, area_id=AREA_A):
    return runtime.session.state.entities[area_id].components[
        "pmw_gameplay_dynamics"
    ]["fields"]["humidity"]


def _snapshot(runtime):
    return (
        deepcopy(runtime.session.state.to_dict()),
        runtime.session.runtime.revision,
        runtime.session.runtime.object_revision,
        deepcopy(runtime.session.runtime.stats),
        runtime.session.runtime.state_closure_known,
        deepcopy(runtime.session.state.scheduled_events),
        deepcopy(runtime.manifest.to_dict())
        if hasattr(runtime.manifest, "to_dict") else deepcopy(runtime.manifest),
    )


def _accepted(proposal):
    return getattr(proposal, "status", None) == "accepted"


def _digest(value):
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    ).hexdigest()


def _assert_rejected(testcase, runtime, request, pattern):
    before = _snapshot(runtime)
    before_budget = deepcopy(_budget(runtime))
    before_mana = _actor_state(runtime, request.actor_id)["mana"]
    before_schedule = deepcopy(runtime.session.state.scheduled_events)
    with testcase.assertRaisesRegex(GameplayContractError, pattern):
        submit_timed_primary_action(
            runtime.session,
            runtime.action_registry,
            request,
        )
    testcase.assertEqual(_snapshot(runtime), before)
    testcase.assertEqual(_budget(runtime), before_budget)
    testcase.assertEqual(
        _actor_state(runtime, request.actor_id)["mana"],
        before_mana,
    )
    testcase.assertEqual(
        runtime.session.state.scheduled_events,
        before_schedule,
    )


class MoveActorIndependentReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        TEST_TMP.mkdir(parents=True, exist_ok=True)

    def test_player_and_npc_move_with_exact_cost_and_accepted_core_lifecycle(self):
        move = _move_skill()
        runtime, _ = _formal_runtime((move,), world=_bare_world())
        self.assertEqual(runtime.blueprints[(MOVE_SKILL, 1)], move)
        self.assertEqual(EFFECT_KINDS[-1], "move_actor")
        self.assertEqual(_effect_cost(move.effects[0]), 2.0)

        for actor_id, request_id in (
            (PLAYER, "qa_player_move"),
            (NPC, "qa_npc_move"),
        ):
            with self.subTest(actor_id=actor_id):
                before_mana = _actor_state(runtime, actor_id)["mana"]
                before_spent = _budget(runtime)["spent_ticks"]
                submitted = submit_timed_primary_action(
                    runtime.session,
                    runtime.action_registry,
                    ActionRequest(request_id, actor_id, MOVE_SKILL, None, AREA_B),
                )
                self.assertEqual(submitted.action.cost.mana, 4.0)
                self.assertEqual(submitted.time.duration, 1)
                self.assertEqual(
                    _actor_state(runtime, actor_id)["mana"], before_mana - 4.0
                )
                self.assertEqual(
                    _budget(runtime)["spent_ticks"], before_spent + 1
                )
                locations = _locations(runtime, actor_id)
                self.assertEqual(len(locations), 1)
                self.assertEqual(locations[0].target, AREA_B)
                self.assertEqual(
                    locations[0].id, f"located:{actor_id}:{AREA_B}"
                )

                proposals = submitted.action.event_result.trace.proposals
                lifecycle = [
                    proposal for proposal in proposals
                    if proposal.op in {"delete_relation", "create_relation"}
                ]
                self.assertEqual(
                    sorted(proposal.op for proposal in lifecycle),
                    ["create_relation", "delete_relation"],
                )
                self.assertTrue(all(_accepted(item) for item in lifecycle))
                delete = next(
                    item for item in lifecycle if item.op == "delete_relation"
                )
                create = next(
                    item for item in lifecycle if item.op == "create_relation"
                )
                self.assertRegex(
                    delete.law_id,
                    rf"^pmw\.v04\.action\.{MOVE_SKILL}\..+\.effect\.travel\.delete$",
                )
                self.assertRegex(
                    create.law_id,
                    rf"^pmw\.v04\.action\.{MOVE_SKILL}\..+\.effect\.travel\.create$",
                )
                self.assertEqual(create.value["source"], actor_id)
                self.assertEqual(create.value["target"], AREA_B)
                self.assertEqual(create.value["type"], "located_in")

    def test_paid_profile_relation_does_not_supply_area_adjacency(self):
        """C3 marker endpoints are local objects, not the A-B joining edge."""
        profile = _profile()
        control = _control_skill()
        move = _move_skill()
        runtime, _ = _formal_runtime(
            (control, move),
            world=_link_world(profile=profile, base_enabled=True),
            relation_controller=RelationController((profile,)),
        )
        submit_timed_primary_action(
            runtime.session,
            runtime.action_registry,
            ActionRequest("qa_disable_profile_only", PLAYER, CONTROL_SKILL),
        )
        before = _snapshot(runtime)
        with self.assertRaisesRegex(
            GameplayContractError,
            "not an adjacent",
        ):
            submit_timed_primary_action(
                runtime.session,
                runtime.action_registry,
                ActionRequest("qa_profile_only_blocked", PLAYER, MOVE_SKILL, None, AREA_B),
            )
        self.assertEqual(_snapshot(runtime), before)

    def test_paid_tick_resolves_destination_with_area_scoped_law(self):
        move = _move_skill()
        runtime, compiled = _formal_runtime((move,), world=_bare_world())
        marker_id = "qa_destination_observed"
        runtime.session.state.entities[AREA_B].components["qa_destination_review"] = {
            "seen": False,
        }
        runtime.session.runtime.revalidate()
        observer = {
            "id": marker_id,
            "mode": "event",
            "priority": 100,
            "bindings": {
                "actor": {
                    "kind": "entity",
                    "requires": [ACTOR_COMPONENT],
                },
                "destination": {
                    "kind": "entity",
                    "requires": ["pmw_gameplay_area"],
                },
                "location": {
                    "kind": "relation",
                    "type": "located_in",
                    "source": "$actor",
                    "target": "$destination",
                },
            },
            "when": {"all": [
                {"event.type": {"eq": "pmw.v04.world_tick"}},
                {"ref": "$actor.id", "eq": PLAYER},
                {"ref": "$destination.id", "eq": AREA_B},
            ]},
            "effects": [{
                "op": "set",
                "target": "$destination.qa_destination_review.seen",
                "value": True,
            }],
        }
        runtime = _install_support_laws(runtime, compiled, (observer,))
        submitted = submit_timed_primary_action(
            runtime.session,
            runtime.action_registry,
            ActionRequest("qa_tick_destination", PLAYER, MOVE_SKILL, None, AREA_B),
        )
        tick = submitted.time.ticks[0]
        tick_text = json.dumps(tick.event_result.trace.to_dict(), sort_keys=True)
        self.assertIn(AREA_B, tick_text)
        self.assertIn(marker_id, tick.event_result.triggered_law_ids)
        self.assertIs(
            runtime.session.state.entities[AREA_B].components[
                "qa_destination_review"
            ]["seen"],
            True,
        )
        self.assertEqual(_locations(runtime, PLAYER)[0].target, AREA_B)
        after = advance_world_tick(runtime.session)
        self.assertEqual(_locations(runtime, PLAYER)[0].target, AREA_B)
        self.assertEqual(after.step, 2)

    def test_coeffect_and_later_origin_dynamics_use_origin(self):
        combined = _skill(
            _skill_document(
                "qa_move_and_soak",
                [_move_effect(), _modify_field_effect()],
                mana=5.0,
            )
        )
        runtime, _ = _formal_runtime((combined,), world=_bare_world())
        origin_before = _field_state(runtime, AREA_A)["value"]
        destination_before = _field_state(runtime, AREA_B)["value"]
        submitted = submit_timed_primary_action(
            runtime.session,
            runtime.action_registry,
            ActionRequest("qa_origin_coeffect", PLAYER, combined.id, None, AREA_B),
        )
        self.assertAlmostEqual(
            _field_state(runtime, AREA_A)["value"],
            (origin_before + 0.1) + 0.2 * (
                0.8 - (origin_before + 0.1)
            ),
            delta=1e-12,
        )
        # The destination's continuous Field Law runs in the same paid Tick, so
        # its observable value advances once from the untouched baseline.
        self.assertAlmostEqual(
            _field_state(runtime, AREA_B)["value"],
            destination_before + 0.2 * (0.8 - destination_before),
            delta=1e-12,
        )
        self.assertEqual(_locations(runtime, PLAYER)[0].target, AREA_B)
        self.assertEqual(submitted.time.duration, 1)

        origin_after_move = _field_state(runtime, AREA_A)["value"]
        advance_world_tick(runtime.session)
        self.assertGreater(_field_state(runtime, AREA_A)["value"], origin_after_move)

        dynamics = _skill(
            _skill_document(
                "qa_origin_pulse",
                [_dynamics_effect()],
                mana=5.0,
                budget=8.0,
            )
        )
        dynamics_runtime, _ = _formal_runtime((dynamics, combined), world=_bare_world())
        pulse = submit_timed_primary_action(
            dynamics_runtime.session,
            dynamics_runtime.action_registry,
            ActionRequest("qa_origin_pulse_cast", PLAYER, dynamics.id),
        )
        self.assertEqual(pulse.time.duration, 1)
        pulsed = _field_state(dynamics_runtime, AREA_A)["value"]
        move = submit_timed_primary_action(
            dynamics_runtime.session,
            dynamics_runtime.action_registry,
            ActionRequest("qa_move_after_pulse", PLAYER, combined.id, None, AREA_B),
        )
        self.assertEqual(move.time.duration, 1)
        self.assertEqual(_locations(dynamics_runtime, PLAYER)[0].target, AREA_B)
        moved = _field_state(dynamics_runtime, AREA_A)["value"]
        advance_world_tick(dynamics_runtime.session)
        self.assertGreater(_field_state(dynamics_runtime, AREA_A)["value"], moved)

    def test_c3_overlay_blocks_atomically_and_parallel_link_keeps_path_open(self):
        profile = _profile()
        controller = RelationController((profile,))
        control = _control_skill()
        move = _move_skill()
        parallel = Relation(
            "qa_parallel_ab",
            "adjacent",
            AREA_A,
            AREA_B,
        )
        runtime, _ = _formal_runtime(
            (control, move),
            world=_link_world(
                profile=profile,
                base_enabled=True,
                parallel_links=(parallel,),
            ),
            relation_controller=controller,
        )
        disabled = submit_timed_primary_action(
            runtime.session,
            runtime.action_registry,
            ActionRequest("qa_disable_only_link", PLAYER, CONTROL_SKILL),
        )
        self.assertEqual(disabled.time.duration, 1)
        moved = submit_timed_primary_action(
            runtime.session,
            runtime.action_registry,
            ActionRequest("qa_parallel_bare_move", PLAYER, MOVE_SKILL, None, AREA_B),
        )
        self.assertEqual(moved.time.duration, 1)
        self.assertEqual(_locations(runtime, PLAYER)[0].target, AREA_B)

        parallel_runtime, _ = _formal_runtime(
            (control, move),
            world=_link_world(
                profile=profile,
                base_enabled=True,
                parallel_links=(
                    Relation("qa_parallel_bare", "adjacent", AREA_A, AREA_B),
                    Relation(
                        "qa_parallel_enabled",
                        "adjacent",
                        AREA_A,
                        AREA_B,
                        components={
                            RELATION_COMPONENT: {"effective_enabled": True},
                        },
                    ),
                ),
            ),
            relation_controller=RelationController((profile,)),
        )
        submit_timed_primary_action(
            parallel_runtime.session,
            parallel_runtime.action_registry,
            ActionRequest("qa_disable_primary", PLAYER, CONTROL_SKILL),
        )
        moved = submit_timed_primary_action(
            parallel_runtime.session,
            parallel_runtime.action_registry,
            ActionRequest("qa_parallel_move", PLAYER, MOVE_SKILL, None, AREA_B),
        )
        self.assertEqual(moved.time.duration, 1)
        self.assertEqual(_locations(parallel_runtime, PLAYER)[0].target, AREA_B)

    def test_base_disabled_only_link_blocks_and_bare_link_opens(self):
        area_profile = RelationProfile(
            "qa_area_link_profile",
            "qa_area_link",
            "adjacent",
            AREA_A,
            AREA_B,
            PLAYER,
            AREA_A,
            ("pmw_gameplay_area",),
            ("pmw_gameplay_area",),
            8,
        )
        runtime, _ = _formal_runtime(
            (_move_skill(),),
            world=_area_link_world(area_profile, base_enabled=False),
        )
        _assert_rejected(
            self,
            runtime,
            ActionRequest("qa_base_disabled", PLAYER, MOVE_SKILL, None, AREA_B),
            "disabled",
        )
        enabled_runtime, _ = _formal_runtime(
            (_move_skill(),),
            world=_area_link_world(area_profile, base_enabled=True),
        )
        enabled = submit_timed_primary_action(
            enabled_runtime.session,
            enabled_runtime.action_registry,
            ActionRequest("qa_base_enabled", PLAYER, MOVE_SKILL, None, AREA_B),
        )
        self.assertEqual(enabled.time.duration, 1)
        self.assertEqual(_locations(enabled_runtime, PLAYER)[0].target, AREA_B)

        bare_runtime, _ = _formal_runtime(
            (_move_skill(),),
            world=_bare_world(relation_id="qa_bare_only"),
        )
        result = submit_timed_primary_action(
            bare_runtime.session,
            bare_runtime.action_registry,
            ActionRequest("qa_bare_move", PLAYER, MOVE_SKILL, None, AREA_B),
        )
        self.assertEqual(result.time.duration, 1)

    def test_atomic_rejection_matrix(self):
        move = _move_skill()
        runtime, _ = _formal_runtime((move,), world=_bare_world())
        cases = (
            (ActionRequest("qa_unknown", PLAYER, MOVE_SKILL, None, AREA_C),
             "not an adjacent"),
            (ActionRequest("qa_same", PLAYER, MOVE_SKILL, None, AREA_A),
             "not an adjacent"),
            (ActionRequest("qa_missing", PLAYER, MOVE_SKILL),
             "requires target_area_id"),
            (ActionRequest("qa_wrong_action", PLAYER, "basic_wait", None, AREA_B),
             "target_area_id"),
        )
        for request, pattern in cases:
            with self.subTest(request=request.request_id):
                _assert_rejected(self, runtime, request, pattern)

        zero, _ = _formal_runtime((move,), world=_world(extra_located=()))
        zero.session.state.relations = {
            key: relation for key, relation in zero.session.state.relations.items()
            if not (relation.type == "located_in" and relation.source == PLAYER)
        }
        zero.session.runtime.revalidate()
        _assert_rejected(
            self,
            zero,
            ActionRequest("qa_zero_locations", PLAYER, MOVE_SKILL, None, AREA_B),
            "exactly one current",
        )

        two, _ = _formal_runtime(
            (move,),
            world=_world(extra_located=((PLAYER, AREA_C),)),
        )
        _assert_rejected(
            self,
            two,
            ActionRequest("qa_two_locations", PLAYER, MOVE_SKILL, None, AREA_B),
            "exactly one current",
        )

        collision, _ = _formal_runtime(
            (move,),
            world=_world(collision_id=f"located:{PLAYER}:{AREA_B}"),
        )
        _assert_rejected(
            self,
            collision,
            ActionRequest("qa_collision", PLAYER, MOVE_SKILL, None, AREA_B),
            "collides",
        )

        for malformed in (
            {"pmw_gameplay_link": "bad"},
            {"pmw_gameplay_link": {}},
            {"pmw_gameplay_link": {"effective_enabled": 1}},
        ):
            with self.subTest(malformed=malformed):
                bad, _ = _formal_runtime(
                    (move,),
                    world=_world(
                        links=(),
                        extra_relations=(
                            Relation(
                                "qa_malformed",
                                "adjacent",
                                AREA_A,
                                AREA_B,
                                components=malformed,
                            ),
                        ),
                    ),
                )
                _assert_rejected(
                    self,
                    bad,
                    ActionRequest(
                        "qa_malformed_request", PLAYER, MOVE_SKILL, None, AREA_B
                    ),
                    "malformed",
                )

        nonarea, _ = _formal_runtime((move,), world=_bare_world())
        nonarea.session.state.entities[AREA_B].components.pop("pmw_gameplay_area")
        nonarea.session.runtime.revalidate()
        _assert_rejected(
            self,
            nonarea,
            ActionRequest("qa_nonarea", PLAYER, MOVE_SKILL, None, AREA_B),
            "not an Area|adjacent",
        )

        with self.assertRaisesRegex(GameplayContractError, "action scope"):
            _skill(
                _skill_document(
                    "qa_wrong_selector_move",
                    [_move_effect()],
                    selectors=["current_area"],
                ),
            )

    def test_hook_and_passive_paths_reject_without_mutation(self):
        move = _move_skill()
        runtime, _ = _formal_runtime((move,), world=_bare_world())
        before = _snapshot(runtime)
        with self.assertRaisesRegex(GameplayContractError, "primary"):
            _resolve_action(
                runtime.session,
                runtime.action_registry,
                ActionRequest("qa_hook_move", PLAYER, MOVE_SKILL, None, AREA_B),
                execution_kind="hook",
                hook_context={"hook_id": "qa_hook"},
            )
        self.assertEqual(_snapshot(runtime), before)

        passive_raw = _skill_document(
            "qa_passive_move",
            [_move_effect()],
            kind="passive_blueprint",
            trigger="damage_resolved",
        )
        with self.assertRaisesRegex(GameplayContractError, "active on_use"):
            _skill(passive_raw)

    def test_parse_level_forbidden_combinations_and_closed_fields(self):
        statuses = basic_registry().statuses
        move = _move_effect()
        forbidden = (
            {
                "id": "hit",
                "kind": "damage",
                "target": {"kind": "target_actor"},
                "commitment": "required",
                "amount": 1,
            },
            {
                "id": "start",
                "kind": "process_start",
                "target": {"kind": "current_area"},
                "commitment": "required",
                "process_template_id": "qa_template",
            },
            _modifier_effect(),
        )
        for extra in forbidden:
            with self.subTest(kind=extra["kind"]):
                action_raw = {
                    "id": f"qa_action_{extra['kind']}",
                    "version": 1,
                    "action_type": "skill",
                    "cost": {"duration": 1, "mana": 1},
                    "scope": {
                        "selectors": sorted({
                            "adjacent_area", extra["target"]["kind"],
                        }),
                        "relation_types": ["adjacent"],
                    },
                    "effects": [deepcopy(move), deepcopy(extra)],
                }
                with self.assertRaisesRegex(GameplayContractError, "move_actor"):
                    parse_action_definition(action_raw, statuses)
                with self.assertRaisesRegex(GameplayContractError, "move_actor"):
                    _skill(_skill_document(
                        f"qa_skill_{extra['kind']}",
                        action_raw["effects"],
                        relations=("adjacent",),
                    ))
        duplicate_action = {
            "id": "qa_duplicate_move",
            "version": 1,
            "action_type": "skill",
            "cost": {"duration": 1, "mana": 1},
            "scope": {
                "selectors": ["adjacent_area"],
                "relation_types": [],
            },
            "effects": [move, _move_effect("travel_again")],
        }
        with self.assertRaisesRegex(GameplayContractError, "one move_actor"):
            parse_action_definition(duplicate_action, statuses)
        with self.assertRaisesRegex(GameplayContractError, "one move_actor"):
            _skill(_skill_document(
                "qa_duplicate_skill",
                duplicate_action["effects"],
            ))
        for change in (
            {"extra": True},
            {"condition": None},
            {"amount": 1},
            {"target": {"kind": "current_area"}},
            {"commitment": "conditional"},
        ):
            with self.subTest(change=change):
                raw = {**move, **change}
                with self.assertRaises(GameplayContractError):
                    parse_effect(raw, statuses)

    def test_absent_target_area_payload_stays_legacy(self):
        move = _move_skill()
        runtime, _ = _formal_runtime((move,), world=_bare_world())
        submitted = submit_timed_primary_action(
            runtime.session,
            runtime.action_registry,
            ActionRequest("qa_legacy_wait", PLAYER, "basic_wait"),
        )
        payload = submitted.action.event_result.trace.root_event.payload
        self.assertNotIn("target_area_id", payload)
        self.assertEqual(
            _digest(payload),
            "5fc39b697eea0cd855ce7c6ea25b3a94cad674cc9b3b022fec72d81ef6a0eafb",
        )
        self.assertEqual(
            submitted.action.definition.canonical_hash,
            basic_registry().actions["basic_wait"].canonical_hash,
        )
        self.assertEqual(
            submitted.action.definition.canonical_hash,
            "76402836ee7b674883344f555ca8d8e0d85d5f9fb3806c4330749e562679c3ee",
        )
        parsed = parse_action_request({
            "request_id": "qa_wait_parse",
            "actor_id": PLAYER,
            "action_id": "basic_wait",
        })
        self.assertIsNone(parsed.target_area_id)

    def test_move_back_twice_and_two_actors_are_sequential_consistent(self):
        move = _move_skill()
        runtime, _ = _formal_runtime((move,), world=_bare_world())
        first = submit_timed_primary_action(
            runtime.session,
            runtime.action_registry,
            ActionRequest("qa_go_b", PLAYER, MOVE_SKILL, None, AREA_B),
        )
        second = submit_timed_primary_action(
            runtime.session,
            runtime.action_registry,
            ActionRequest("qa_back_a", PLAYER, MOVE_SKILL, None, AREA_A),
        )
        self.assertEqual(first.time.duration, 1)
        self.assertEqual(second.time.duration, 1)
        self.assertEqual(_locations(runtime, PLAYER)[0].target, AREA_A)
        self.assertEqual(_budget(runtime)["spent_ticks"], 2)
        self.assertEqual(_actor_state(runtime, PLAYER)["mana"], 12.0)

        third = submit_timed_primary_action(
            runtime.session,
            runtime.action_registry,
            ActionRequest("qa_npc_go_b", NPC, MOVE_SKILL, None, AREA_B),
        )
        self.assertEqual(third.time.duration, 1)
        self.assertEqual(_locations(runtime, NPC)[0].target, AREA_B)
        self.assertEqual(_locations(runtime, PLAYER)[0].target, AREA_A)
        self.assertEqual(_budget(runtime)["spent_ticks"], 3)

    def test_checkpoint_rebuild_preserves_moved_location_and_hashes(self):
        move = _move_skill()
        runtime, compiled = _formal_runtime((move,), world=_bare_world())
        submitted = submit_timed_primary_action(
            runtime.session,
            runtime.action_registry,
            ActionRequest("qa_checkpoint_move", PLAYER, MOVE_SKILL, None, AREA_B),
        )
        action_hash = submitted.action.definition.canonical_hash
        with tempfile.TemporaryDirectory(dir=TEST_TMP) as directory:
            path = Path(directory) / "qa_move_checkpoint.json"
            save_registry_checkpoint(path, runtime)
            restored = load_registry_checkpoint(path, compiled)
        self.assertEqual(restored.session.state.to_dict(), runtime.session.state.to_dict())
        self.assertEqual(restored.blueprints[(MOVE_SKILL, 1)].canonical_hash, move.canonical_hash)
        self.assertEqual(
            restored.action_registry.actions[MOVE_SKILL].canonical_hash,
            action_hash,
        )
        self.assertEqual(_locations(restored, PLAYER)[0].target, AREA_B)
        submit_timed_primary_action(
            restored.session,
            restored.action_registry,
            ActionRequest("qa_post_restore_move", PLAYER, MOVE_SKILL, None, AREA_A),
        )
        self.assertEqual(_locations(restored, PLAYER)[0].target, AREA_A)
if __name__ == "__main__":
    unittest.main()
