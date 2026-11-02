"""Trusted time-zero worlds and controllers for the P2.2 reference library."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Callable, Mapping

from pmw import Entity, Relation

from ..basics import basic_registry
from ..blueprints import (
    instantiate_actor,
    instantiate_area,
    parse_actor_blueprint,
    parse_area_blueprint,
)
from ..contracts import FieldDefinition, GameplayContractError
from ..derived import DerivedSpec, parse_derived_spec
from ..drives import DriveController, DriveProfile, instantiate_drive
from ..materials import MaterialAuthority, material_authority, parse_material
from ..processes import (
    ConversionPort,
    ProcessController,
    ProcessLimits,
    ProcessProfile,
    ProcessTemplate,
    StockBinding,
    StockRef,
    instantiate_process,
    stock_entity,
)
from ..relations import RelationController, RelationProfile, instantiate_relation
from ..runtime import clock_entity
from ..time_ledger import initialize_time_budget
from ..worlds import build_gameplay_world


PLAYER = "p22_player"
NPC = "p22_npc"
AREA = "p22_area"
OTHER_AREA = "p22_other_area"
CLOCK_ID = "pmw:v04:clock"
TIME_BUDGET = 30

PROFILES = (
    "field",
    "stock",
    "process",
    "relation",
    "combat",
    "travel",
    "derived",
)

_FIELD_KINDS = (
    "modify_field",
    "modify_attractor",
    "modify_rate",
    "dynamics_modifier",
)
_STOCK_KINDS = ("add_resource", "drive_source")
_PROCESS_KINDS = ("process_start", "process_modify")
_RELATION_KINDS = ("relation_modifier",)
_COMBAT_KINDS = (
    "damage",
    "heal",
    "shield",
    "apply_status",
    "grant_trait",
)
_TRAVEL_KINDS = ("move_actor", "add_resource", "shield", "modify_field")
_DERIVED_KINDS = (
    "modify_field",
    "modify_attractor",
    "modify_rate",
    "dynamics_modifier",
    "damage",
    "heal",
    "shield",
    "add_resource",
)

_KINDS_BY_PROFILE = {
    "field": _FIELD_KINDS,
    "stock": _STOCK_KINDS,
    "process": _PROCESS_KINDS,
    "relation": _RELATION_KINDS,
    "combat": _COMBAT_KINDS,
    "travel": _TRAVEL_KINDS,
    "derived": _DERIVED_KINDS,
}


@dataclass(frozen=True, slots=True)
class ReferenceFixture:
    profile: str
    world: Any
    statuses: Mapping[str, Any]
    authority: MaterialAuthority
    material_id: str
    process_controller: ProcessController | None = None
    drive_controller: DriveController | None = None
    relation_controller: RelationController | None = None
    derived_by_area: Mapping[str, tuple[DerivedSpec, ...]] = (
        MappingProxyType({})
    )


def build_fixture(profile: str, *, primary_actor: str = PLAYER) -> ReferenceFixture:
    """Build one fresh time-zero fixture from the closed profile set."""
    if primary_actor not in {PLAYER, NPC}:
        raise GameplayContractError("unknown reference primary Actor")
    try:
        builder = _BUILDERS[profile]
    except (KeyError, TypeError) as error:
        raise GameplayContractError(
            f"unknown reference fixture profile {profile!r}"
        ) from error
    material_id = f"p22_{profile}_material"
    authority = _authority_for(profile, material_id)
    world, process, drive, relation, derived = builder(primary_actor)
    return ReferenceFixture(
        profile,
        world,
        basic_registry().statuses,
        authority,
        material_id,
        process,
        drive,
        relation,
        MappingProxyType(dict(derived)),
    )


def _authority_for(profile: str, material_id: str) -> MaterialAuthority:
    material = parse_material({
        "id": material_id,
        "tier": "rare",
        "region_rarity": "scarce",
        "traits": [{
            "id": f"{profile}_authority",
            "effect_kinds": list(_KINDS_BY_PROFILE[profile]),
            "selectors": [
                "self",
                "target_actor",
                "current_area",
                "adjacent_area",
                "linked_object",
            ],
            "budget_points": 200.0,
        }],
    })
    return material_authority((material,))


def _field(
    field_id: str,
    *,
    initial: float = 0.2,
    target: float = 0.8,
    rate: float = 0.2,
    curve: str = "linear",
    maximum: float = 1.0,
) -> dict[str, Any]:
    return {
        "id": field_id,
        "domain": {"min": 0.0, "max": maximum},
        "initial": initial,
        "target": target,
        "rate": rate,
        "curve": curve,
        "max_persistent_patches": 4,
        "max_temporary_modifiers": 4,
    }


def _area(area_id: str) -> Entity:
    blueprint = parse_area_blueprint({
        "protocol": "pmw-gameplay-v0.4",
        "kind": "area_blueprint",
        "id": f"{area_id}_blueprint",
        "fields": [
            _field("humidity"),
            _field(
                "temperature",
                initial=0.4,
                target=0.4,
                rate=0.0,
                curve="none",
            ),
            _field(
                "fuel",
                initial=1.0,
                target=1.0,
                rate=0.0,
                curve="none",
                maximum=10.0,
            ),
        ],
    })
    return instantiate_area(blueprint, area_id)


def _actor(actor_id: str, controller: str) -> Entity:
    blueprint = parse_actor_blueprint({
        "protocol": "pmw-gameplay-v0.4",
        "kind": "actor_blueprint",
        "id": f"{actor_id}_blueprint",
        "hp": {"max": 50.0, "initial": 30.0},
        "mana": {"max": 100.0, "initial": 30.0, "dynamics": None},
        "attributes": {
            "power": 4.0,
            "control": 4.0,
            "resilience": 4.0,
            "agility": 4.0,
        },
        "traits": [],
    })
    return instantiate_actor(blueprint, actor_id, controller=controller)


def _world(
    *,
    extra_entities: tuple[Entity, ...] = (),
    extra_relations: tuple[Relation, ...] = (),
    adjacent: bool = False,
) -> Any:
    areas = (_area(AREA), _area(OTHER_AREA))
    actors = (_actor(PLAYER, "human"), _actor(NPC, "ai"))
    world = build_gameplay_world(
        "p22_reference_world",
        areas=areas,
        actors=actors,
        placements=((PLAYER, AREA), (NPC, AREA)),
        adjacencies=((AREA, OTHER_AREA),) if adjacent else (),
    )
    for entity in extra_entities:
        world.entities[entity.id] = entity
    for relation in extra_relations:
        world.relations[relation.id] = relation
    world.entities[CLOCK_ID] = clock_entity()
    return initialize_time_budget(world, TIME_BUDGET)


def _locate(area_id: str, *entity_ids: str) -> tuple[Relation, ...]:
    return tuple(
        Relation(
            f"located:{entity_id}:{area_id}",
            "located_in",
            entity_id,
            area_id,
        )
        for entity_id in entity_ids
    )


def _field_fixture(primary_actor: str) -> tuple:
    return _world(adjacent=True), None, None, None, {}


def _stock_fixture(primary_actor: str) -> tuple:
    definition = parse_area_blueprint({
        "protocol": "pmw-gameplay-v0.4",
        "kind": "area_blueprint",
        "id": "p22_drive_field_blueprint",
        "fields": [
            _field(
                "fuel",
                initial=1.0,
                target=1.0,
                rate=0.0,
                curve="none",
                maximum=10.0,
            ),
        ],
    }).fields[0]
    entities = []
    relations = []
    profile = DriveProfile(
        id="fixture_drive",
        drive_entity_id=f"p22_drive_entity_{primary_actor}",
        owner=primary_actor,
        area_id=AREA,
        field=definition,
        stock=StockRef(f"p22_drive_stock_{primary_actor}"),
        stock_unit="fuel",
        field_per_stock=2.0,
        max_rate=4.0,
        max_duration_ticks=8,
    )
    entities.extend((
        instantiate_drive(profile),
        stock_entity(
            profile.stock.entity_id,
            amount=10.0,
            capacity=20.0,
            unit="fuel",
        ),
    ))
    relations.extend(_locate(
        AREA,
        profile.drive_entity_id,
        profile.stock.entity_id,
    ))
    controller = DriveController((profile,))
    return _world(
        extra_entities=tuple(entities),
        extra_relations=tuple(relations),
    ), None, controller, None, {}


def _process_template(template_id: str) -> ProcessTemplate:
    return ProcessTemplate(
        template_id,
        (ConversionPort("ore", 1.0, "ore"),),
        (ConversionPort("ingot", 1.0, "ingot"),),
        1.0,
        4,
        4.0,
        8,
    )


def _process_profile(actor_id: str, variant: str) -> ProcessProfile:
    template_id = "fixture_refine_mod" if variant == "mod" else "fixture_refine"
    profile_id = f"p22_{variant}_{actor_id}"
    return ProcessProfile(
        profile_id,
        _process_template(template_id),
        f"p22_process_{variant}_{actor_id}",
        actor_id,
        (StockBinding("ore", StockRef(f"p22_ore_{variant}_{actor_id}")),),
        (StockBinding(
            "ingot",
            StockRef(f"p22_ingot_{variant}_{actor_id}"),
        ),),
    )


def _process_fixture(primary_actor: str) -> tuple:
    profiles = tuple(
        _process_profile(primary_actor, variant)
        for variant in ("start", "mod")
    )
    entities = []
    relations = []
    for profile in profiles:
        entities.append(instantiate_process(profile))
        for port, ref in (*profile.input_ports, *profile.output_ports):
            entities.append(stock_entity(
                ref.entity_id,
                amount=8.0 if port.unit == "ore" else 0.0,
                capacity=30.0,
                unit=port.unit,
            ))
        relations.extend(_locate(
            AREA,
            profile.process_entity_id,
            *(ref.entity_id for _, ref in (*profile.input_ports, *profile.output_ports)),
        ))
    controller = ProcessController(
        profiles,
        ProcessLimits(max_instances=4, max_active=4),
    )
    return _world(
        extra_entities=tuple(entities),
        extra_relations=tuple(relations),
    ), controller, None, None, {}


def _relation_profile(actor_id: str) -> RelationProfile:
    return RelationProfile(
        "fixture_link",
        f"p22_supply_link_{actor_id}",
        "fixture_supply",
        f"p22_supply_source_{actor_id}",
        f"p22_supply_sink_{actor_id}",
        actor_id,
        AREA,
        ("p22_supply_source",),
        ("p22_supply_sink",),
        8,
    )


def _relation_fixture(primary_actor: str) -> tuple:
    profiles = (_relation_profile(primary_actor),)
    entities = []
    relations = []
    for profile in profiles:
        entities.extend((
            Entity(
                profile.source_entity_id,
                "p22_relation_endpoint",
                components={"p22_supply_source": {}},
            ),
            Entity(
                profile.target_entity_id,
                "p22_relation_endpoint",
                components={"p22_supply_sink": {}},
            ),
        ))
        relations.append(instantiate_relation(profile, base_enabled=True))
        relations.extend(_locate(
            AREA,
            profile.source_entity_id,
            profile.target_entity_id,
        ))
    controller = RelationController(profiles)
    return _world(
        extra_entities=tuple(entities),
        extra_relations=tuple(relations),
    ), None, None, controller, {}


def _combat_fixture(primary_actor: str) -> tuple:
    link = Relation(
        "p22_combat_link",
        "fixture_link",
        AREA,
        NPC,
    )
    return _world(extra_relations=(link,)), None, None, None, {}


def _travel_fixture(primary_actor: str) -> tuple:
    return _world(adjacent=True), None, None, None, {}


def _comfort_spec() -> DerivedSpec:
    return parse_derived_spec({
        "id": "comfort",
        "kind": "weighted_sum",
        "terms": [["humidity", 2.0], ["temperature", -0.5]],
        "bias": 0.1,
        "minimum": 0.0,
        "maximum": 2.0,
    })


def _derived_fixture(primary_actor: str) -> tuple:
    spec = _comfort_spec()
    return (
        _world(adjacent=True),
        None,
        None,
        None,
        {AREA: (spec,), OTHER_AREA: (spec,)},
    )


_BUILDERS: dict[str, Callable[[str], tuple]] = {
    "field": _field_fixture,
    "stock": _stock_fixture,
    "process": _process_fixture,
    "relation": _relation_fixture,
    "combat": _combat_fixture,
    "travel": _travel_fixture,
    "derived": _derived_fixture,
}

assert tuple(_BUILDERS) == PROFILES
