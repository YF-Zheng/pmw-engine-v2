"""Three small PMW v2.8 observation-policy prototypes."""

from pmw import Engine, Entity, Relation, WorldState, parse_observation_rule


def rule(identifier, subject, reveal=None, bindings=None, when=None):
    return parse_observation_rule({"id": identifier, "bindings": bindings or {},
        "when": when or {"all": []}, "subject": subject, "reveal": reveal or {}})


def npc_private_public_state():
    world = WorldState(entities={"npc": Entity("npc", name="Mira", components={"profile": {"greeting": "Hello", "private_plan": "steal key"}})})
    policy = rule("npc-self", "$observer", {"core": ["name"], "components": ["profile.greeting"]})
    return Engine([], observation_rules=[policy]).attach(world).observe("npc").to_dict()


def hidden_and_discovered_trap():
    world = WorldState(entities={"hero": Entity("hero"), "trap": Entity("trap", "trap", "Loose Tile")}, relations={"found": Relation("found", "discovered_by", "hero", "trap")})
    policy = rule("discovered", "$trap", {"core": ["archetype", "name"]}, {
        "trap": {"kind": "entity"},
        "discovery": {"kind": "relation", "type": "discovered_by", "source": "$observer", "target": "$trap"},
    })
    return Engine([], observation_rules=[policy]).attach(world).observe("hero").to_dict()


def asymmetric_actors():
    world = WorldState(
        entities={name: Entity(name, name=name.title()) for name in ("alice", "bob", "red_key", "blue_key")},
        relations={"alice-red": Relation("alice-red", "visible_to", "alice", "red_key"), "bob-blue": Relation("bob-blue", "visible_to", "bob", "blue_key")},
    )
    policy = rule("visible", "$subject", {"core": ["name"]}, {
        "subject": {"kind": "entity"},
        "visibility": {"kind": "relation", "type": "visible_to", "source": "$observer", "target": "$subject"},
    })
    runtime = Engine([], observation_rules=[policy]).attach(world)
    return {"alice": runtime.observe("alice").to_dict(), "bob": runtime.observe("bob").to_dict()}


if __name__ == "__main__":
    for name, prototype in (("NPC_PRIVATE_PUBLIC", npc_private_public_state), ("HIDDEN_DISCOVERED_TRAP", hidden_and_discovered_trap), ("ASYMMETRIC_ACTORS", asymmetric_actors)):
        print(name, prototype())
