from __future__ import annotations

from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pmw import Entity, Event, Relation

from experiments.generative_mechanics.next_tracks_v06.gameplay_v04 import (
    time_ledger,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.action_compiler import (
    build_action_laws,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.actions import (
    ActionRegistry,
    ActionRequest,
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
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.build_analysis import (
    RegistrySemanticsProvider,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.checkpoint import (
    load_registry_checkpoint,
    save_registry_checkpoint,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.content_compiler import (
    CompiledGate3Content,
    build_content_session,
    compile_content,
    initialize_content_world,
    make_content,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.contracts import (
    GameplayContractError,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.effects import (
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
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.observation import (
    ActorObservationBuilder,
    ObservationDisclosure,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.registry import (
    MechanismRegistryRuntime,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.relations import (
    RELATION_COMPONENT,
    RELATION_EXPIRE_EVENT,
    RELATION_MODIFY_EVENT,
    RelationController,
    RelationLimits,
    RelationProfile,
    build_relation_laws,
    instantiate_relation,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.runtime import (
    advance_world_tick,
    build_runtime,
    clock_entity,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.simulation import (
    SandboxSimulator,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.skills import (
    parse_skill_blueprint,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.time_ledger import (
    initialize_time_budget,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.worlds import (
    build_gameplay_world,
)


PLAYER = "player_actor"
NPC = "npc_actor"
AREA = "workshop_area"
REMOTE_AREA = "remote_area"
SOURCE = "power_source"
TARGET = "power_sink"
REMOTE_SOURCE = "remote_source"
RELATION_ID = "supply_link"
PROFILE_ID = "supply_control"
SOURCE_MARKER = "pmw_gameplay_power_source"
TARGET_MARKER = "pmw_gameplay_power_sink"
SKILL_ID = "cut_power_supply"
MATERIAL_ID = "relation_crystal"
AVAILABILITY = "pmw_gameplay_relation_owner_availability"


def _actor(actor_id: str, *, controller: str):
    blueprint = parse_actor_blueprint({
        "protocol": "pmw-gameplay-v0.4",
        "kind": "actor_blueprint",
        "id": f"{actor_id}_blueprint",
        "hp": {"max": 50.0, "initial": 50.0},
        "mana": {"max": 30.0, "initial": 20.0, "dynamics": None},
        "attributes": {
            "power": 4.0,
            "control": 4.0,
            "resilience": 4.0,
            "agility": 4.0,
        },
        "traits": [],
    })
    return instantiate_actor(blueprint, actor_id, controller=controller)


def _area(area_id: str):
    blueprint = parse_area_blueprint({
        "protocol": "pmw-gameplay-v0.4",
        "kind": "area_blueprint",
        "id": f"{area_id}_blueprint",
        "fields": [{
            "id": "heat",
            "domain": {"min": 0.0, "max": 10.0},
            "initial": 1.0,
            "target": 1.0,
            "rate": 0.0,
            "curve": "none",
            "max_persistent_patches": 1,
            "max_temporary_modifiers": 1,
        }],
    })
    return instantiate_area(blueprint, area_id)


def _marked_entity(entity_id: str, marker: str):
    return Entity(entity_id, "relation_endpoint", components={marker: {}})


def _profile(
    profile_id: str = PROFILE_ID,
    *,
    owner: str = PLAYER,
    relation_id: str = RELATION_ID,
    relation_type: str = "supplies_power",
    source_id: str = SOURCE,
    target_id: str = TARGET,
    area_id: str = AREA,
    max_duration: int = 8,
) -> RelationProfile:
    return RelationProfile(
        profile_id,
        relation_id,
        relation_type,
        source_id,
        target_id,
        owner,
        area_id,
        (SOURCE_MARKER,),
        (TARGET_MARKER,),
        max_duration,
    )


def _world(*profiles: RelationProfile):
    areas = {AREA: _area(AREA), REMOTE_AREA: _area(REMOTE_AREA)}
    actors = {
        PLAYER: _actor(PLAYER, controller="human"),
        NPC: _actor(NPC, controller="ai"),
    }
    world = build_gameplay_world(
        "relation_owner_world",
        areas=areas.values(),
        actors=actors.values(),
        placements=((PLAYER, AREA), (NPC, AREA)),
    )
    world.entities.update(areas)
    world.entities.update(actors)
    world.entities[SOURCE] = _marked_entity(SOURCE, SOURCE_MARKER)
    world.entities[TARGET] = _marked_entity(TARGET, TARGET_MARKER)
    world.entities[REMOTE_SOURCE] = _marked_entity(REMOTE_SOURCE, SOURCE_MARKER)
    world.relations["located:source"] = Relation(
        "located:source", "located_in", SOURCE, AREA
    )
    world.relations["located:target"] = Relation(
        "located:target", "located_in", TARGET, AREA
    )
    world.relations["located:remote_source"] = Relation(
        "located:remote_source", "located_in", REMOTE_SOURCE, REMOTE_AREA
    )
    for profile in profiles:
        relation = instantiate_relation(profile)
        world.relations[relation.id] = relation
    world.entities["pmw:v04:clock"] = clock_entity()
    return world


def _component(session, profile: RelationProfile | None = None) -> dict:
    profile = profile or _profile()
    return session.state.relations[profile.relation_id].components[
        RELATION_COMPONENT
    ]


def _snapshot(session):
    return (
        deepcopy(session.state.to_dict()),
        session.runtime.revision,
        session.runtime.object_revision,
        deepcopy(session.runtime.stats),
        session.runtime.state_closure_known,
        tuple(
            (event.id, event.type, event.time, deepcopy(event.payload))
            for event in session.state.scheduled_events
        ),
    )


def _native_session(
    *profiles: RelationProfile,
    limits: RelationLimits | None = None,
):
    controller = RelationController(
        tuple(profiles), RelationLimits() if limits is None else limits
    )
    world = initialize_time_budget(_world(*profiles), 20)
    return (
        build_runtime(world, extra_laws=controller.laws),
        controller,
    )


def _modify(
    session,
    controller,
    profile,
    *,
    owner: str | None = None,
    enabled: bool = False,
    duration: int = 3,
):
    return controller.modify(
        session,
        profile.id,
        owner=profile.owner if owner is None else owner,
        enabled=enabled,
        duration_ticks=duration,
    )


def _material():
    return parse_material({
        "id": MATERIAL_ID,
        "tier": "rare",
        "region_rarity": "scarce",
        "traits": [{
            "id": "relation_control",
            "effect_kinds": ["relation_modifier"],
            "selectors": ["current_area"],
            "budget_points": 5.4,
        }],
    })


def _skill_document(
    *,
    skill_id: str = SKILL_ID,
    profile_id: str = PROFILE_ID,
    enabled: bool = False,
    duration: int = 4,
    fields: dict | None = None,
):
    effect = {
        "id": "control_link",
        "kind": "relation_modifier",
        "target": {"kind": "current_area"},
        "commitment": "required",
        "relation_profile_id": profile_id,
        "relation_enabled": enabled,
        "duration": duration,
    }
    if fields is not None:
        effect.update(fields)
    return {
        "protocol": "pmw-gameplay-v0.4",
        "kind": "skill_blueprint",
        "id": skill_id,
        "version": 1,
        "trigger": "on_use",
        "condition": None,
        "duration": None,
        "cost": {"duration": 1, "mana": 1.0},
        "scope": {
            "selectors": ["current_area"],
            "relation_types": ["supplies_power"],
        },
        "effects": [effect],
        "budget": {"limit": 5.4},
        "max_firings_per_root": 1,
        "material_ids": [MATERIAL_ID],
    }


def _skill(document: dict | None = None):
    return parse_skill_blueprint(
        document or _skill_document(),
        basic_registry().statuses,
        material_authority((_material(),)),
    )


def _runtime(
    profiles: tuple[RelationProfile, ...],
    skills,
    *,
    extra_laws=(),
):
    controller = RelationController(profiles)
    base = ActionRegistry(
        basic_registry().actions.values(),
        basic_registry().statuses.values(),
        relation_controller=controller,
    )
    content = make_content(
        base,
        skills=tuple(skills),
        material_ids=(MATERIAL_ID,),
    )
    world = initialize_time_budget(_world(*profiles), 20)
    world = initialize_content_world(world, content)
    compiled = compile_content(content)
    if extra_laws:
        compiled = CompiledGate3Content(
            compiled.content,
            (*compiled.laws, *(dict(law) for law in extra_laws)),
        )
    session = build_content_session(world, compiled)
    runtime = MechanismRegistryRuntime.from_compiled_content(session, compiled)
    for actor_id, skill in zip((PLAYER, NPC), skills):
        change_loadout(
            runtime.session,
            runtime.manifest,
            actor_id=actor_id,
            operation="equip_active",
            skill=skill_ref(skill),
            slot=0,
        )
    return runtime, compiled


def _same_cascade_base_change_law(profile: RelationProfile) -> dict:
    return {
        "id": "pmw.v04.owner.relation.same_cascade_base_change",
        "mode": "event",
        "priority": 100,
        "bindings": {
            "link": {
                "kind": "relation",
                "type": profile.relation_type,
                "source": "$source",
                "target": "$target",
                "requires": [RELATION_COMPONENT],
            },
            "source": {"kind": "entity", "requires": [SOURCE_MARKER]},
            "target": {"kind": "entity", "requires": [TARGET_MARKER]},
        },
        "when": {"all": [
            {"event.type": {"eq": RELATION_MODIFY_EVENT}},
            {"ref": "$link.id", "eq": profile.relation_id},
            {"ref": "$event.payload.profile_id", "eq": profile.id},
            {"ref": "$event.payload.enabled", "eq": False},
        ]},
        "effects": [{
            "op": "set",
            "target": f"$link.{RELATION_COMPONENT}.base_enabled",
            "value": False,
        }],
    }


class RelationModifierOwnerTests(unittest.TestCase):
    def test_parsed_player_npc_timed_downstream_effective_and_expiry(self):
        player = _profile()
        npc = _profile(
            "npc_supply_control",
            owner=NPC,
            relation_id="npc_supply_link",
        )
        player_skill = _skill()
        npc_skill = _skill(_skill_document(
            skill_id="cut_npc_power_supply",
            profile_id=npc.id,
        ))
        self.assertEqual(player_skill.budget_used, 5.4)
        self.assertIs(player_skill.effects[0].relation_enabled, False)
        runtime, compiled = _runtime((player, npc), (player_skill, npc_skill))

        state_law = {
            "id": "pmw.v04.owner.relation.downstream_availability",
            "mode": "state",
            "priority": 100,
            "bindings": {
                "link": {
                    "kind": "relation",
                    "type": player.relation_type,
                    "source": "$source",
                    "target": "$target",
                    "requires": [RELATION_COMPONENT],
                },
                "source": {"kind": "entity", "requires": [SOURCE_MARKER]},
                "target": {"kind": "entity", "requires": [TARGET_MARKER]},
                "area": {"kind": "entity", "requires": ["pmw_gameplay_area"]},
            },
            "when": {"all": [
                {"ref": "$link.id", "eq": player.relation_id},
                {"ref": "$source.id", "eq": SOURCE},
                {"ref": "$target.id", "eq": TARGET},
                {"ref": "$area.id", "eq": AREA},
                {
                    "ref": f"$area.{AVAILABILITY}.available",
                    "neq": f"$link.{RELATION_COMPONENT}.effective_enabled",
                },
            ]},
            "effects": [{
                "op": "set",
                "target": f"$area.{AVAILABILITY}.available",
                "value": f"$link.{RELATION_COMPONENT}.effective_enabled",
            }],
        }
        runtime.session = build_runtime(
            runtime.session.state,
            runtime.session.profiles,
            (
                *runtime.static_laws,
                *build_action_laws(runtime.action_registry),
                state_law,
            ),
        )
        runtime.session.state.entities[AREA].components[AVAILABILITY] = {
            "available": False
        }
        runtime.session.runtime.revalidate()

        player_result = submit_timed_primary_action(
            runtime.session,
            runtime.action_registry,
            ActionRequest("player_relation_cast", PLAYER, player_skill.id),
        )
        npc_result = submit_timed_primary_action(
            runtime.session,
            runtime.action_registry,
            ActionRequest("npc_relation_cast", NPC, npc_skill.id),
        )
        for expected_before, result in (
            (20, player_result),
            (19, npc_result),
        ):
            self.assertEqual(
                (
                    result.time.duration,
                    result.time.before_remaining,
                    result.time.after_remaining,
                ),
                (1, expected_before, expected_before - 1),
            )
        for actor_id in (PLAYER, NPC):
            self.assertEqual(
                runtime.session.state.entities[actor_id].components[
                    "pmw_gameplay_actor"
                ]["mana"],
                19.0,
            )
        self.assertFalse(
            runtime.session.state.entities[AREA].components[AVAILABILITY][
                "available"
            ]
        )
        for profile in (player, npc):
            component = _component(runtime.session, profile)
            self.assertTrue(component["active"])
            self.assertIs(component["enabled"], False)
            self.assertIs(component["effective_enabled"], False)
        for _ in range(4):
            advance_world_tick(runtime.session)
        for profile in (player, npc):
            component = _component(runtime.session, profile)
            self.assertFalse(component["active"])
            self.assertIs(component["effective_enabled"], True)
        self.assertTrue(
            runtime.session.state.entities[AREA].components[AVAILABILITY][
                "available"
            ]
        )

    def test_effect_scope_budget_limits_and_profile_typing_denials(self):
        valid = {
            "id": "control",
            "kind": "relation_modifier",
            "target": {"kind": "current_area"},
            "commitment": "required",
            "relation_profile_id": PROFILE_ID,
            "relation_enabled": False,
            "duration": 4,
        }
        effect = parse_effect(valid, basic_registry().statuses)
        self.assertEqual(effect.kind, "relation_modifier")
        self.assertIs(effect.relation_enabled, False)
        for mutation, pattern in (
            ({"relation_enabled": 0}, "strict boolean"),
            ({"relation_enabled": 1}, "strict boolean"),
            ({"duration": 0}, "positive integer"),
            ({"duration": True}, "positive integer"),
            ({"relation_profile_id": ""}, "relation_profile_id"),
            ({"target": {"kind": "self"}}, "current_area"),
        ):
            raw = deepcopy(valid)
            raw.update(mutation)
            with self.subTest(mutation=mutation), self.assertRaisesRegex(
                GameplayContractError, pattern
            ):
                parse_effect(raw, basic_registry().statuses)
        for injected, pattern in (
            ("source", "unknown fields"),
            ("target", "selector must be an object"),
            ("relation_type", "unknown fields"),
            ("path", "unknown fields"),
        ):
            raw = deepcopy(valid)
            raw[injected] = "candidate_value"
            with self.subTest(injected=injected), self.assertRaisesRegex(
                GameplayContractError, pattern
            ):
                parse_effect(raw, basic_registry().statuses)
        mixed_control = _skill_document()
        mixed_control["effects"].append({
            "id": "unexpected_process",
            "kind": "process_start",
            "target": {"kind": "current_area"},
            "commitment": "required",
            "process_template_id": "unexpected_process",
        })
        with self.assertRaisesRegex(GameplayContractError, "one Process/Drive"):
            _skill(mixed_control)
        with self.assertRaisesRegex(GameplayContractError, "budget"):
            document = _skill_document()
            document["budget"]["limit"] = 5.2
            _skill(document)
        with self.assertRaisesRegex(GameplayContractError, "authorization"):
            parse_skill_blueprint(
                _skill_document(),
                basic_registry().statuses,
                material_authority((
                    parse_material({
                        "id": MATERIAL_ID,
                        "tier": "rare",
                        "region_rarity": "scarce",
                        "traits": [{
                            "id": "wrong_scope",
                            "effect_kinds": ["relation_modifier"],
                            "selectors": ["self"],
                            "budget_points": 5.4,
                        }],
                    }),
                )),
            )

        profile = _profile()
        session, controller = _native_session(profile)
        session.state.relations[profile.relation_id].type = "other_type"
        session.runtime.revalidate()
        before = _snapshot(session)
        with self.assertRaisesRegex(GameplayContractError, "endpoints/type"):
            _modify(session, controller, profile)
        self.assertEqual(_snapshot(session), before)

        missing_marker_session, missing_marker_controller = _native_session(profile)
        del missing_marker_session.state.entities[SOURCE].components[SOURCE_MARKER]
        missing_marker_session.runtime.revalidate()
        before = _snapshot(missing_marker_session)
        with self.assertRaisesRegex(GameplayContractError, "source markers"):
            _modify(missing_marker_session, missing_marker_controller, profile)
        self.assertEqual(_snapshot(missing_marker_session), before)

        unknown_profile_session, unknown_profile_controller = _native_session(profile)
        before = _snapshot(unknown_profile_session)
        with self.assertRaisesRegex(GameplayContractError, "profile"):
            unknown_profile_controller.prepare_modify(
                unknown_profile_session,
                "unknown_profile",
                owner=profile.owner,
                enabled=False,
                duration_ticks=1,
            )
        self.assertEqual(_snapshot(unknown_profile_session), before)

        wrong_capability = _skill_document()
        wrong_capability["scope"]["relation_types"] = ["other_type"]
        capability_runtime, _ = _runtime((profile,), (_skill(wrong_capability),))
        before = _snapshot(capability_runtime.session)
        with self.assertRaisesRegex(GameplayContractError, "capability"):
            submit_timed_primary_action(
                capability_runtime.session,
                capability_runtime.action_registry,
                ActionRequest("wrong_capability", PLAYER, SKILL_ID),
            )
        self.assertEqual(_snapshot(capability_runtime.session), before)

        wrong_owner_session, wrong_owner_controller = _native_session(profile)
        before = _snapshot(wrong_owner_session)
        with self.assertRaisesRegex(GameplayContractError, "owner"):
            _modify(
                wrong_owner_session,
                wrong_owner_controller,
                profile,
                owner=NPC,
            )
        self.assertEqual(_snapshot(wrong_owner_session), before)

        first = _profile("first_relation_profile", relation_id="first_link")
        second = _profile("second_relation_profile", relation_id="second_link")
        limited, limited_controller = _native_session(
            first,
            second,
            limits=RelationLimits(max_instances=2, max_active=1),
        )
        _modify(limited, limited_controller, first)
        before = _snapshot(limited)
        with self.assertRaisesRegex(GameplayContractError, "max_active"):
            _modify(limited, limited_controller, second)
        self.assertEqual(_snapshot(limited), before)
        with self.assertRaisesRegex(GameplayContractError, "share a Relation slot"):
            RelationController((profile, replace(profile, id="duplicate_profile")))
        with self.assertRaises(FrozenInstanceError):
            profile.owner = NPC

        remote = _profile(
            "remote_relation_profile",
            relation_id="remote_link",
            target_id=REMOTE_SOURCE,
        )
        remote_session, remote_controller = _native_session(remote)
        before = _snapshot(remote_session)
        with self.assertRaisesRegex(
            GameplayContractError, "target markers|target is remote"
        ):
            _modify(remote_session, remote_controller, remote)
        self.assertEqual(_snapshot(remote_session), before)

    def test_formal_activation_cascade_preserves_current_base_through_owned_expiry(self):
        profile = _profile()
        skill = _skill()
        runtime, _ = _runtime(
            (profile,),
            (skill,),
            extra_laws=(_same_cascade_base_change_law(profile),),
        )
        result = submit_timed_primary_action(
            runtime.session,
            runtime.action_registry,
            ActionRequest("base_cascade_cast", PLAYER, SKILL_ID),
        )
        active = _component(runtime.session)
        self.assertTrue(active["active"])
        self.assertIs(active["enabled"], False)
        self.assertIs(active["base_enabled"], False)
        self.assertIs(active["effective_enabled"], False)
        self.assertEqual(active["expires_at"], 4.0)
        self.assertIn(
            f"pmw.v04.sandbox.relation.{profile.id}.modify.off",
            tuple(
                law.law_id
                for event in result.action.event_result.trace.events
                for law in event.event_law_matches
            ),
        )
        for _ in range(4):
            advance_world_tick(runtime.session)
        expired = _component(runtime.session)
        self.assertFalse(expired["active"])
        self.assertIs(expired["base_enabled"], False)
        self.assertIs(expired["effective_enabled"], False)
        self.assertIsNone(expired["expiry_handle"])
        self.assertEqual(runtime.session.state.scheduled_events, [])

    def test_current_base_stale_handle_and_owned_expiry_after_fixture_changes(self):
        profile = _profile()
        session, controller = _native_session(profile)
        _modify(session, controller, profile, enabled=False, duration=1)
        self.assertEqual(
            _component(session)["expires_at"],
            session.state.sim_time + 1,
        )
        first_handle = _component(session)["expiry_handle"]
        stale = next(
            event
            for event in session.state.scheduled_events
            if event.id == first_handle
        )
        session.state.relations[RELATION_ID].components[RELATION_COMPONENT][
            "base_enabled"
        ] = False
        session.runtime.revalidate()
        self.assertIs(_component(session)["effective_enabled"], False)
        advance_world_tick(session)
        expired = _component(session)
        self.assertFalse(expired["active"])
        self.assertIs(expired["base_enabled"], False)
        self.assertIs(expired["effective_enabled"], False)

        _modify(session, controller, profile, enabled=True, duration=4)
        self.assertEqual(
            _component(session)["expires_at"],
            session.state.sim_time + 4,
        )
        second_handle = _component(session)["expiry_handle"]
        self.assertNotEqual(first_handle, second_handle)
        stale_result = session.runtime.run_event(stale)
        self.assertFalse(stale_result.changed)
        current = _component(session)
        self.assertTrue(current["active"])
        self.assertEqual(current["expiry_handle"], second_handle)

        # Support fixture mutation only: Core has no remove-component Law op.
        del session.state.entities[SOURCE].components[SOURCE_MARKER]
        del session.state.relations["located:player_actor:workshop_area"]
        session.runtime.revalidate()
        for _ in range(4):
            advance_world_tick(session)
        owned = _component(session)
        self.assertFalse(owned["active"])
        self.assertEqual(owned["expiry_handle"], None)
        self.assertIs(owned["effective_enabled"], False)
        self.assertEqual(session.state.scheduled_events, [])

    def test_cascade_late_tick_checkpoint_replay_and_private_projection(self):
        profile = _profile()
        player_skill = _skill()
        runtime, compiled = _runtime((profile,), (player_skill,))
        before = _snapshot(runtime.session)
        real_tick = time_ledger.advance_world_tick

        def fail_after_tick(working, **kwargs):
            real_tick(working, **kwargs)
            raise RuntimeError("owner relation late tick")

        with patch.object(
            time_ledger, "advance_world_tick", side_effect=fail_after_tick
        ):
            with self.assertRaisesRegex(RuntimeError, "late tick"):
                submit_timed_primary_action(
                    runtime.session,
                    runtime.action_registry,
                    ActionRequest("late_relation", PLAYER, SKILL_ID),
                )
        self.assertEqual(_snapshot(runtime.session), before)

        submit_timed_primary_action(
            runtime.session,
            runtime.action_registry,
            ActionRequest("checkpoint_relation", PLAYER, SKILL_ID),
        )
        expected = _component(runtime.session)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "relation_checkpoint.json"
            save_registry_checkpoint(path, runtime)
            restored = load_registry_checkpoint(path, compiled)
            self.assertIsNotNone(restored.base_registry.relation_controller)
            self.assertEqual(
                restored.session.state.to_dict(),
                runtime.session.state.to_dict(),
            )
            advance_world_tick(runtime.session)
            advance_world_tick(restored.session)
            self.assertEqual(
                runtime.session.state.to_dict(),
                restored.session.state.to_dict(),
            )

            changed = replace(profile, max_duration_ticks=7)
            changed_content = make_content(
                ActionRegistry(
                    basic_registry().actions.values(),
                    basic_registry().statuses.values(),
                    relation_controller=RelationController((changed,)),
                ),
                skills=(player_skill,),
                material_ids=(MATERIAL_ID,),
            )
            with self.assertRaisesRegex(
                GameplayContractError, "static Law configuration"
            ):
                load_registry_checkpoint(path, compile_content(changed_content))

        semantics = RegistrySemanticsProvider(
            runtime.action_registry
        ).semantics(SKILL_ID)
        write = next(
            row for row in semantics.writes
            if row.operation == "relation_modifier"
        )
        self.assertEqual(write.path, f"relation:{PROFILE_ID}:enabled")
        self.assertNotIn(SOURCE, write.path)
        self.assertNotIn(TARGET, write.path)

        observation = ActorObservationBuilder().build(
            restored.session,
            restored.action_registry,
            PLAYER,
            ObservationDisclosure.create(
                visible_relation_types=("supplies_power",),
            ),
        )
        rendered = json.dumps(observation.to_dict(), sort_keys=True)
        self.assertNotIn(SOURCE, rendered)
        self.assertNotIn(TARGET, rendered)
        self.assertNotIn(RELATION_COMPONENT, rendered)
        simulator = SandboxSimulator(restored.action_registry)
        projected, projected_registry, _ = simulator._build(observation)
        self.assertNotIn(SKILL_ID, projected_registry.actions)
        self.assertIsNone(projected_registry.relation_controller)
        self.assertIn("basic_wait", projected_registry.actions)
        result = simulator.simulate(
            observation,
            ActionRequest("projected_relation", PLAYER, SKILL_ID),
        )
        self.assertFalse(result.legal)
        self.assertIn("unknown registered action", result.rejection)
        self.assertEqual(_component(restored.session), expected)


if __name__ == "__main__":
    unittest.main()
