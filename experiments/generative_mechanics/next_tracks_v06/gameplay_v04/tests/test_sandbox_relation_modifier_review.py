from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pmw import Event, Relation

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
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.contracts import (
    GameplayContractError,
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
REMOTE = "remote_area"
SOURCE = "power_source"
TARGET = "power_sink"
REMOTE_SOURCE = "remote_source"
RELATION_ID = "supply_link"
PROFILE_ID = "supply_modifier"
SOURCE_MARKER = "pmw_gameplay_power_source"
TARGET_MARKER = "pmw_gameplay_power_sink"
SKILL_ID = "cut_supply"
MATERIAL_ID = "relation_crystal"


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


def _profile_changed(profile: RelationProfile, **changes) -> RelationProfile:
    values = {
        "id": profile.id,
        "relation_id": profile.relation_id,
        "relation_type": profile.relation_type,
        "source_entity_id": profile.source_entity_id,
        "target_entity_id": profile.target_entity_id,
        "owner": profile.owner,
        "area_id": profile.area_id,
        "source_components": profile.source_components,
        "target_components": profile.target_components,
        "max_duration_ticks": profile.max_duration_ticks,
    }
    values.update(changes)
    return RelationProfile(**values)


def _world(*profiles: RelationProfile):
    areas = {AREA: _area(AREA), REMOTE: _area(REMOTE)}
    actors = {
        PLAYER: _actor(PLAYER, controller="human"),
        NPC: _actor(NPC, controller="ai"),
    }
    world = build_gameplay_world(
        "relation_review_world",
        areas=areas.values(),
        actors=actors.values(),
        placements=((PLAYER, AREA), (NPC, AREA)),
    )
    world.entities.update(areas)
    world.entities.update(actors)
    world.entities[SOURCE] = _marked_entity(SOURCE, SOURCE_MARKER)
    world.entities[TARGET] = _marked_entity(TARGET, TARGET_MARKER)
    world.entities[REMOTE_SOURCE] = _marked_entity(REMOTE_SOURCE, SOURCE_MARKER)
    # Support fixture state: opt-in World Laws expose each real link's
    # effective availability as separate Area state. This is not a generated
    # Effect, victory flag, or generic topology claim.
    world.entities[AREA].components["pmw_gameplay_relation_review"] = {
        "supply_link": {"available": True},
        "npc_supply_link": {"available": True},
    }
    world.relations["located:source"] = Relation(
        "located:source", "located_in", SOURCE, AREA
    )
    world.relations["located:target"] = Relation(
        "located:target", "located_in", TARGET, AREA
    )
    world.relations["located:remote_source"] = Relation(
        "located:remote_source", "located_in", REMOTE_SOURCE, REMOTE
    )
    for profile in profiles:
        relation = instantiate_relation(profile)
        world.relations[relation.id] = relation
    world.entities["pmw:v04:clock"] = clock_entity()
    return world


def _marked_entity(entity_id: str, marker: str):
    from pmw import Entity

    return Entity(entity_id, "review_relation_endpoint", components={marker: {}})


def _component(session, profile: RelationProfile | None = None) -> dict:
    profile = profile or _profile()
    return session.state.relations[profile.relation_id].components[RELATION_COMPONENT]


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


def _session(*profiles: RelationProfile, limits: RelationLimits | None = None):
    controller = RelationController(
        tuple(profiles), RelationLimits() if limits is None else limits
    )
    world = initialize_time_budget(_world(*profiles), 20)
    return build_runtime(world, extra_laws=controller.laws), controller


def _modify(
    session,
    controller: RelationController,
    profile: RelationProfile,
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


def _cast(runtime, request_id: str, actor_id: str, skill):
    return submit_timed_primary_action(
        runtime.session,
        runtime.action_registry,
        ActionRequest(request_id, actor_id, skill.id),
    )


def _material(
    budget: float = 6.0,
    effect_kind: str = "relation_modifier",
):
    return parse_material({
        "id": MATERIAL_ID,
        "tier": "rare",
        "region_rarity": "scarce",
        "traits": [{
            "id": "relation_control",
            "effect_kinds": [effect_kind],
            "selectors": ["current_area"],
            "budget_points": budget,
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
        "id": "change_link",
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
        "budget": {"limit": 6.0},
        "max_firings_per_root": 1,
        "material_ids": [MATERIAL_ID],
    }


def _skill(document: dict | None = None):
    return parse_skill_blueprint(
        document or _skill_document(),
        basic_registry().statuses,
        material_authority((_material(),)),
    )


def _availability_by_link_law(
    profile: RelationProfile,
    *,
    law_id: str,
) -> dict:
    """Support Law: expose one link's effective state as observable Area state."""
    return {
        "id": law_id,
        "mode": "state",
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
            "area": {"kind": "entity", "requires": ["pmw_gameplay_area"]},
        },
        "when": {"all": [
            {"ref": "$link.id", "eq": profile.relation_id},
            {"ref": "$source.id", "eq": profile.source_entity_id},
            {"ref": "$target.id", "eq": profile.target_entity_id},
            {"ref": "$area.id", "eq": profile.area_id},
            {
                "ref": (
                    "$area.pmw_gameplay_relation_review."
                    f"{profile.relation_id}.available"
                ),
                "neq": f"$link.{RELATION_COMPONENT}.effective_enabled",
            },
        ]},
        "effects": [{
            "op": "set",
            "target": (
                "$area.pmw_gameplay_relation_review."
                f"{profile.relation_id}.available"
            ),
            "value": f"$link.{RELATION_COMPONENT}.effective_enabled",
        }],
    }


def _same_cascade_base_change_law(profile: RelationProfile) -> dict:
    """Support Law: a real World Law changes CURRENT base during activation."""
    return {
        "id": "pmw.v04.review.relation.same_cascade_base_change",
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


def _available(session, profile: RelationProfile | None = None) -> bool:
    profile = profile or _profile()
    component = session.state.entities[AREA].components.get(
        "pmw_gameplay_relation_review"
    )
    if not isinstance(component, dict):
        return False
    row = component.get(profile.relation_id)
    return isinstance(row, dict) and row.get("available") is True


def _runtime(
    profiles: tuple[RelationProfile, ...],
    skills,
    *,
    extra_laws=(),
):
    controller = RelationController(profiles, RelationLimits())
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


class RelationModifierIndependentReviewTests(unittest.TestCase):
    def test_formal_player_npc_duration4_paid_ticks_and_downstream_state(self):
        player = _profile()
        npc = _profile(
            "npc_supply_modifier",
            owner=NPC,
            relation_id="npc_supply_link",
        )
        player_skill = _skill()
        npc_skill = _skill(_skill_document(
            skill_id="cut_npc_supply",
            profile_id=npc.id,
        ))
        self.assertEqual(player_skill.budget_used, 5.4)
        self.assertEqual(player_skill.effects[0].duration, 4)
        self.assertIs(player_skill.effects[0].relation_enabled, False)
        state_laws = tuple(
            _availability_by_link_law(
                profile,
                law_id=f"pmw.v04.review.relation.downstream_availability.{profile.id}",
            )
            for profile in (player, npc)
        )
        base_law = _same_cascade_base_change_law(player)
        runtime, _ = _runtime(
            (player, npc),
            (player_skill, npc_skill),
            extra_laws=(*state_laws, base_law),
        )

        player_result = _cast(runtime, "player_relation_cast", PLAYER, player_skill)
        npc_result = _cast(runtime, "npc_relation_cast", NPC, npc_skill)
        for expected_before, result in ((20, player_result), (19, npc_result)):
            self.assertEqual(
                (result.time.duration, result.time.before_remaining,
                 result.time.after_remaining),
                (1, expected_before, expected_before - 1),
            )
        budget = runtime.session.state.entities["pmw:v04:clock"].components[
            "pmw_gameplay_time_budget"
        ]
        self.assertEqual((budget["spent_ticks"], budget["remaining_ticks"]), (2, 18))
        for actor_id in (PLAYER, NPC):
            self.assertEqual(
                runtime.session.state.entities[actor_id].components[
                    "pmw_gameplay_actor"
                ]["mana"],
                19.0,
            )
        cases = (
            (player, player_result, 0.0, 4.0, False),
            (npc, npc_result, 1.0, 5.0, True),
        )
        for profile, result, started_at, expires_at, base_enabled in cases:
            component = _component(runtime.session, profile)
            self.assertTrue(component["active"])
            self.assertIs(component["enabled"], False)
            self.assertIs(component["effective_enabled"], False)
            self.assertIs(component["base_enabled"], base_enabled)
            self.assertEqual(
                (component["started_at"], component["expires_at"]),
                (started_at, expires_at),
            )
            matched = tuple(
                law.law_id
                for event in result.action.event_result.trace.events
                for law in event.event_law_matches
            )
            self.assertIn(
                f"pmw.v04.sandbox.relation.{profile.id}.modify.off", matched
            )
            self.assertNotIn(
                f"pmw.v04.sandbox.relation.{profile.id}.modify",
                matched,
            )
        for profile in (player, npc):
            self.assertIs(_available(runtime.session, profile), False)
        self.assertNotEqual(
            _component(runtime.session, player)["expiry_handle"],
            _component(runtime.session, npc)["expiry_handle"],
        )
        for tick in (*player_result.time.ticks, *npc_result.time.ticks):
            self.assertFalse(any(
                event.event.type == RELATION_EXPIRE_EVENT
                for event in tick.event_result.trace.events
            ))
        while (
            runtime.session.state.entities["pmw:v04:clock"].components[
                "pmw_gameplay_clock"
            ]["last_completed_step"]
            < 5
        ):
            advance_world_tick(runtime.session)
        for profile, expected_base, expected_effective in (
            (player, False, False),
            (npc, True, True),
        ):
            component = _component(runtime.session, profile)
            self.assertFalse(component["active"])
            self.assertIsNone(component["enabled"])
            # The activation-time World Law changed the CURRENT base to False.
            # Expiry must not restore the captured initial True value.
            self.assertIs(component["base_enabled"], expected_base)
            self.assertIs(component["effective_enabled"], expected_effective)
        self.assertIs(_available(runtime.session, player), False)
        self.assertIs(_available(runtime.session, npc), True)
        self.assertEqual(runtime.session.state.scheduled_events, [])

    def test_exact_expiry_recast_stale_handle_current_base_and_support_marker_change(self):
        profile = _profile()
        session, controller = _session(profile)
        self.assertIsInstance(session.state.relations[RELATION_ID], Relation)
        self.assertEqual(_component(session), {
            "profile_id": PROFILE_ID,
            "profile_hash": profile.profile_hash,
            "owner": PLAYER,
            "base_enabled": True,
            "effective_enabled": True,
            "active": False,
            "enabled": None,
            "started_at": None,
            "expires_at": None,
            "expiry_handle": None,
        })

        _modify(session, controller, profile, enabled=False, duration=2)
        first_handle = _component(session)["expiry_handle"]
        stale = next(
            event for event in session.state.scheduled_events
            if event.id == first_handle
        )
        self.assertEqual(
            (
                _component(session)["started_at"],
                _component(session)["expires_at"],
            ),
            (0.0, 2.0),
        )
        advance_world_tick(session)
        self.assertIs(_component(session)["effective_enabled"], False)
        advance_world_tick(session)
        expired = _component(session)
        self.assertFalse(expired["active"])
        self.assertIsNone(expired["enabled"])
        self.assertIsNone(expired["expiry_handle"])
        self.assertIs(expired["effective_enabled"], True)
        self.assertEqual(session.state.scheduled_events, [])

        _modify(session, controller, profile, enabled=False, duration=3)
        second_handle = _component(session)["expiry_handle"]
        self.assertNotEqual(first_handle, second_handle)
        self.assertFalse(session.runtime.run_event(stale).changed)
        self.assertEqual(_component(session)["expiry_handle"], second_handle)
        self.assertTrue(_component(session)["active"])

        # Support fixture mutation: generic World content changes the CURRENT
        # base and an endpoint marker after activation. This is not normal
        # Skill, movement, or generation evidence.
        _component(session)["base_enabled"] = False
        del session.state.entities[SOURCE].components[SOURCE_MARKER]
        session.runtime.revalidate()
        self.assertIs(_component(session)["effective_enabled"], False)
        before_expiry = _snapshot(session)
        with self.assertRaisesRegex(GameplayContractError, "source markers"):
            _modify(session, controller, profile, enabled=True, duration=1)
        self.assertEqual(_snapshot(session), before_expiry)
        for _ in range(3):
            advance_world_tick(session)
        # A fresh activation cannot occur while the source marker is absent.
        session.state.entities[SOURCE].components[SOURCE_MARKER] = {}
        session.runtime.revalidate()
        expired = _component(session)
        self.assertFalse(expired["active"])
        self.assertIs(expired["base_enabled"], False)
        self.assertIs(expired["effective_enabled"], False)
        self.assertNotIn(
            second_handle,
            {event.id for event in session.state.scheduled_events},
        )

        _modify(session, controller, profile, enabled=True, duration=2)
        self.assertIs(_component(session)["base_enabled"], False)
        self.assertIs(_component(session)["effective_enabled"], True)
        for _ in range(2):
            advance_world_tick(session)
        restored = _component(session)
        self.assertFalse(restored["active"])
        self.assertIs(restored["base_enabled"], False)
        self.assertIs(restored["effective_enabled"], False)

    def test_effect_schema_budget_scope_and_static_identity(self):
        valid = _skill()
        self.assertEqual(valid.effects[0].kind, "relation_modifier")
        self.assertEqual(valid.budget_used, 5.4)
        for field, value, pattern in (
            ("relation_enabled", 1, "strict boolean"),
            ("relation_enabled", 0, "strict boolean"),
            ("relation_enabled", None, "strict boolean"),
            ("relation_enabled", "false", "strict boolean"),
            ("duration", 0, "positive integer"),
            ("duration", True, "positive integer"),
            ("relation_profile_id", "", "relation_profile_id"),
        ):
            with self.subTest(field=field, value=value), self.assertRaisesRegex(
                GameplayContractError, pattern
            ):
                _skill(_skill_document(fields={field: value}))
        for field, value in (
            ("source", SOURCE),
            ("relation_type", "supplies_power"),
            ("path", "components"),
            ("relation_id", RELATION_ID),
        ):
            with self.subTest(injected=field), self.assertRaisesRegex(
                GameplayContractError, "unknown fields"
            ):
                _skill(_skill_document(fields={field: value}))
        with self.assertRaisesRegex(GameplayContractError, "current_area"):
            document = _skill_document()
            document["effects"][0]["target"] = {"kind": "self"}
            _skill(document)
        with self.assertRaisesRegex(GameplayContractError, "required"):
            document = _skill_document()
            document["effects"][0]["commitment"] = "conditional"
            _skill(document)
        with self.assertRaisesRegex(GameplayContractError, "budget"):
            document = _skill_document()
            document["budget"]["limit"] = 5.3
            _skill(document)
        with self.assertRaisesRegex(
            GameplayContractError, "effects exceeds material effect authorization"
        ):
            parse_skill_blueprint(
                _skill_document(),
                basic_registry().statuses,
                material_authority((_material(6.0, "damage"),)),
            )

        first = _profile("first_relation_profile", relation_id="first_link")
        second = _profile(
            "second_relation_profile",
            relation_id="second_link",
            max_duration=6,
        )
        self.assertNotEqual(first.profile_hash, second.profile_hash)
        laws = build_relation_laws((first, second))
        ids = tuple(law["id"] for law in laws)
        self.assertEqual(ids, tuple(sorted(ids)))
        self.assertEqual(len(ids), len(set(ids)))
        self.assertIn(
            f"pmw.v04.sandbox.relation.{first.id}.modify.on", ids
        )
        self.assertIn(
            f"pmw.v04.sandbox.relation.{first.id}.modify.off", ids
        )
        self.assertNotIn(f"pmw.v04.sandbox.relation.{first.id}.modify", ids)
        self.assertTrue(any(RELATION_EXPIRE_EVENT in json.dumps(law) for law in laws))
        self.assertFalse(hasattr(first, "enabled"))
        self.assertFalse(hasattr(first, "effective_enabled"))

    def test_atomic_activation_denials_owner_type_marker_scope_limit_and_staleness(self):
        profile = _profile()
        session, controller = _session(profile)
        before = _snapshot(session)
        for enabled in (1, 0, None, "true"):
            with self.subTest(enabled=enabled), self.assertRaisesRegex(
                GameplayContractError, "strict boolean"
            ):
                _modify(session, controller, profile, enabled=enabled)
            self.assertEqual(_snapshot(session), before)
        for duration in (0, -1, True, 9):
            with self.subTest(duration=duration), self.assertRaisesRegex(
                GameplayContractError, "positive integer|trusted maximum|duration"
            ):
                _modify(session, controller, profile, duration=duration)
            self.assertEqual(_snapshot(session), before)
        with self.assertRaisesRegex(GameplayContractError, "owner"):
            _modify(session, controller, profile, owner=NPC)
        self.assertEqual(_snapshot(session), before)
        with self.assertRaisesRegex(GameplayContractError, "unknown Relation profile"):
            controller.prepare_modify(
                session, "unknown_profile", owner=PLAYER,
                enabled=True, duration_ticks=1,
            )
        self.assertEqual(_snapshot(session), before)
        with self.assertRaisesRegex(GameplayContractError, "strict boolean"):
            instantiate_relation(profile, base_enabled=1)

        for field, value, pattern in (
            ("type", "wrong_type", "endpoints/type"),
            ("source", REMOTE_SOURCE, "endpoints/type"),
        ):
            broken = deepcopy(session.state)
            setattr(broken.relations[RELATION_ID], field, value)
            current = build_runtime(broken, extra_laws=controller.laws)
            current_before = _snapshot(current)
            with self.subTest(field=field), self.assertRaisesRegex(
                GameplayContractError, pattern
            ):
                _modify(current, controller, profile)
            self.assertEqual(_snapshot(current), current_before)

        missing_marker = deepcopy(session.state)
        del missing_marker.entities[SOURCE].components[SOURCE_MARKER]
        current = build_runtime(missing_marker, extra_laws=controller.laws)
        current_before = _snapshot(current)
        with self.assertRaisesRegex(GameplayContractError, "source markers"):
            _modify(current, controller, profile)
        self.assertEqual(_snapshot(current), current_before)

        owner_remote = deepcopy(session.state)
        owner_remote.relations = {
            key: value for key, value in owner_remote.relations.items()
            if not (
                value.type == "located_in"
                and value.source == PLAYER
            )
        }
        owner_remote.relations["located:player:remote"] = Relation(
            "located:player:remote", "located_in", PLAYER, REMOTE
        )
        current = build_runtime(owner_remote, extra_laws=controller.laws)
        current_before = _snapshot(current)
        with self.assertRaisesRegex(
            GameplayContractError, "missing, remote, or ambiguous"
        ):
            _modify(current, controller, profile)
        self.assertEqual(_snapshot(current), current_before)

        # Wrong capability type is a real Action-path denial. The controller
        # itself deliberately receives no candidate relation_types field.
        wrong_scope = _skill(
            {**_skill_document(), "scope": {
                "selectors": ["current_area"],
                "relation_types": ["other_type"],
            }}
        )
        scope_runtime, _ = _runtime((profile,), (wrong_scope,))
        scope_before = _snapshot(scope_runtime.session)
        with self.assertRaisesRegex(
            GameplayContractError, "capability|relation type|authorize"
        ):
            _cast(scope_runtime, "wrong_scope_cast", PLAYER, wrong_scope)
        self.assertEqual(_snapshot(scope_runtime.session), scope_before)

        first = _profile("first_relation_profile", relation_id="first_link")
        second = _profile("second_relation_profile", relation_id="second_link")
        limit_session, limit_controller = _session(
            first, second, limits=RelationLimits(max_instances=2, max_active=1)
        )
        _modify(limit_session, limit_controller, first, duration=3)
        limit_before = _snapshot(limit_session)
        with self.assertRaisesRegex(GameplayContractError, "max_active"):
            _modify(limit_session, limit_controller, second, duration=1)
        self.assertEqual(_snapshot(limit_session), limit_before)

        with self.assertRaisesRegex(GameplayContractError, "share a Relation slot"):
            RelationController((
                profile,
                replace(profile, id="duplicate_relation_profile"),
            ))
        with self.assertRaisesRegex(GameplayContractError, "max_instances"):
            RelationController(
                (profile, _profile("second_profile", relation_id="second_link")),
                RelationLimits(max_instances=1, max_active=1),
            )

    def test_isolated_real_cascade_and_late_paid_tick_rollback(self):
        profile = _profile()
        skill = _skill()
        runtime, compiled = _runtime((profile,), (skill,))
        self.assertTrue(compiled.laws)
        exploding = build_runtime(
            deepcopy(runtime.session.state),
            extra_laws=(
                *runtime.static_laws,
                *build_action_laws(runtime.action_registry),
                {
                    "id": "pmw.v04.review.relation_modify_explode",
                    "mode": "event",
                    "priority": 100,
                    "bindings": {
                        "link": {
                            "kind": "relation",
                            "requires": [RELATION_COMPONENT],
                        },
                    },
                    "when": {"all": [
                        {"event.type": {"eq": RELATION_MODIFY_EVENT}},
                        {"ref": "$link.id", "eq": RELATION_ID},
                    ]},
                    "effects": [{
                        "op": "set",
                        "target": f"$link.{RELATION_COMPONENT}.active",
                        "value": {"div": [1, 0]},
                    }],
                },
            ),
        )
        before = _snapshot(exploding)
        with self.assertRaises(ZeroDivisionError):
            submit_timed_primary_action(
                exploding,
                runtime.action_registry,
                ActionRequest("cascade_cast", PLAYER, skill.id),
            )
        self.assertEqual(_snapshot(exploding), before)

        real_tick = time_ledger.advance_world_tick
        calls = 0

        def fail_tick(working, **kwargs):
            nonlocal calls
            calls += 1
            result = real_tick(working, **kwargs)
            if calls == 1:
                raise RuntimeError("review late tick failure")
            return result

        before = _snapshot(runtime.session)
        with patch.object(time_ledger, "advance_world_tick", side_effect=fail_tick):
            with self.assertRaisesRegex(RuntimeError, "late tick"):
                _cast(runtime, "late_denied", PLAYER, skill)
        self.assertEqual(calls, 1)
        self.assertEqual(_snapshot(runtime.session), before)

    def test_checkpoint_static_profile_mismatch_projection_and_basic_wait(self):
        profile = _profile("checkpoint_relation_profile")
        skill = _skill(_skill_document(profile_id=profile.id))
        runtime, compiled = _runtime((profile,), (skill,))
        _cast(runtime, "checkpoint_cast", PLAYER, skill)
        temp_root = Path("docs/agent_bootstrap/evidence/c3_relation_review_tmp")
        temp_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=temp_root) as directory:
            path = Path(directory) / "checkpoint.json"
            save_registry_checkpoint(path, runtime)
            restored = load_registry_checkpoint(path, compiled)
            changed = _profile_changed(profile, max_duration_ticks=7)
            changed_controller = RelationController((changed,))
            changed_compiled = CompiledGate3Content(
                make_content(
                    ActionRegistry(
                        (
                            row for row in runtime.action_registry.actions.values()
                            if row.id != skill.id
                        ),
                        runtime.action_registry.statuses.values(),
                        relation_controller=changed_controller,
                    ),
                    skills=(runtime.blueprints[(skill.id, 1)],),
                    material_ids=(MATERIAL_ID,),
                ),
                (
                    *(
                        law for law in compiled.laws
                        if not law["id"].startswith("pmw.v04.sandbox.relation.")
                    ),
                    *changed_controller.laws,
                ),
            )
            with self.assertRaisesRegex(
                GameplayContractError, "static Law|profile"
            ):
                load_registry_checkpoint(path, changed_compiled)

        expiry_time = _component(restored.session, profile)["expires_at"]
        while (
            restored.session.state.entities["pmw:v04:clock"].components[
                "pmw_gameplay_clock"
            ]["last_completed_step"]
            < expiry_time
        ):
            advance_world_tick(restored.session)
        self.assertFalse(_component(restored.session, profile)["active"])

        observation = ActorObservationBuilder().build(
            restored.session,
            restored.action_registry,
            PLAYER,
            ObservationDisclosure.create(),
        )
        rendered = json.dumps(observation.to_dict(), sort_keys=True)
        self.assertNotIn(RELATION_COMPONENT, rendered)
        self.assertNotIn(SOURCE, rendered)
        self.assertNotIn(TARGET, rendered)
        self.assertNotIn(PROFILE_ID, rendered)
        simulator = SandboxSimulator(restored.action_registry)
        projected, projected_registry, _ = simulator._build(observation)
        self.assertIsNone(projected_registry.relation_controller)
        self.assertNotIn(skill.id, projected_registry.actions)
        self.assertIn("basic_wait", projected_registry.actions)
        result = simulator.simulate(
            observation,
            ActionRequest("projected_wait", PLAYER, "basic_wait"),
        )
        self.assertTrue(result.legal, result.rejection)
        self.assertTrue(result.next_observation.to_dict()["area"]["fields"])


if __name__ == "__main__":
    unittest.main()
