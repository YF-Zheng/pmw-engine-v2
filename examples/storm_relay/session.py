"""Authoritative playable session for the Storm Relay M0 demo.

This is intentionally a coordinator, not a second world model.  Every durable
quest write is a PMW event consumed by ``session_laws``; gameplay actions,
skills, registry changes, combat and the clock use the v0.4 public APIs.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from pmw import Event

from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.basics import basic_registry
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.content_compiler import (
    CompiledGate3Content, build_content_session, compile_content, make_content,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.contracts import GameplayContractError
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.loadout import change_loadout, skill_ref
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.materials import MaterialAuthority
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.registry import MechanismRegistryRuntime
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.runtime import build_runtime, discover_profiles
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.skills import parse_skill_blueprint
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.time_ledger import spend_world_time
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.shields import (
    absorb_damage, neutral_shield_layer,
)

from .commands import COMMAND_LABELS, Command, CommandError
from .content import (AREA_COMPONENT, CLOCK_ID, GUARD_ID, MATERIAL_IDS,
                      PLAYER_ID, SHALLOWS_ID, TOWER_ID, make_storm_relay_world)
from .laws import WEATHER_EVALUATE_EVENT, m0_laws
from .session_laws import (COMBAT_EVENT, GUARD_EXPIRE_EVENT, RELAY_SHIELD_EVENT,
                           SESSION_EVENT, session_laws)

GAMEPLAY_ACTOR = "pmw_gameplay_actor"


class SessionError(ValueError):
    """A rejected public command; the live runtime has not been changed."""


_RECIPES = {
    "lightning_seed": (("wet_moss", 1), ("thunder_crystal", 1)),
    "fog_echo": (("wet_moss", 2), ("thunder_crystal", 1)),
    "storm_glass_relay": (("storm_glass", 1), ("thunder_crystal", 1)),
}


@dataclass
class StormRelaySession:
    """One complete M0 runtime envelope and its browser-safe command surface."""

    _session: Any
    _registry: MechanismRegistryRuntime
    _events: list[dict[str, Any]]
    _budget: int

    @classmethod
    def new_game(cls, *, time_budget: int = 23) -> "StormRelaySession":
        if isinstance(time_budget, bool) or not isinstance(time_budget, int) or time_budget < 1:
            raise ValueError("time_budget must be a positive integer")
        world = make_storm_relay_world(time_budget=time_budget)
        # Detached initial-world decoration is allowed; after this point all
        # state changes occur via PMW events or public Gameplay APIs.
        world.entities[PLAYER_ID].components["storm_relay_player"] = {}
        world.entities[SHALLOWS_ID].components["storm_relay_stock_wet_moss"] = {}
        world.entities[SHALLOWS_ID].components["storm_relay_stock_thunder_crystal"] = {}
        world.entities[TOWER_ID].components["storm_relay_stock_storm_glass"] = {}
        player_state = world.entities[PLAYER_ID].components["storm_relay_actor"]
        player_state.update({"current_area": SHALLOWS_ID, "relay_equipped": False,
                             "relay_shield": 0.0, "relay_shield_ticks": 0,
                             "outcome": "playing", "last_message": None,
                             "combat_attack_base": 4.0})
        world.entities[GUARD_ID].components["storm_relay_actor"]["combat_attack_base"] = 5.0
        # Slot-free basics are identity-pinned by Gameplay's security boundary.
        # Use the canonical shipped registry; authored skills remain runtime
        # registry entries with their own exact hashes.
        content = make_content(basic_registry(), material_ids=MATERIAL_IDS)
        compiled = compile_content(content)
        combined = CompiledGate3Content(content, tuple(sorted(
            (*compiled.laws, *m0_laws(), *session_laws()), key=lambda law: law["id"]
        )))
        session = build_content_session(world, combined)
        registry = MechanismRegistryRuntime.from_compiled_content(session, combined)
        return cls(registry.session, registry, [], time_budget)

    @property
    def state(self):
        return self._session.state

    def restart(self) -> None:
        fresh = self.new_game(time_budget=self._budget)
        self._session, self._registry, self._events = fresh._session, fresh._registry, fresh._events

    def _clone(self) -> "StormRelaySession":
        # A clone is rebuilt through the same Law configuration.  Registry
        # blueprints are immutable dataclasses, but copy the mapping to prevent
        # failed install attempts escaping into the live registry.
        state = deepcopy(self._session.state)
        staged = build_runtime(state, discover_profiles(state), self._registry.static_laws)
        registry = MechanismRegistryRuntime(staged, self._registry.base_registry,
                                            self._registry.static_laws,
                                            dict(self._registry.blueprints),
                                            self._registry.status_slots,
                                            self._registry.dynamics_slots)
        registry._rebuild()
        return StormRelaySession(registry.session, registry, deepcopy(self._events), self._budget)

    def perform(self, action: str, target: str | None = None, slot: int | None = None) -> dict[str, Any]:
        try:
            command = Command.parse({"action": action, "target": target, "slot": slot})
            if not any(row["action"] == command.action and
                       (row.get("target") in (None, command.target)) for row in self.legal_actions()):
                raise SessionError("action is not legal in the current world state")
            staged = self._clone()
            staged._perform(command)
        except (CommandError, GameplayContractError, SessionError) as error:
            raise SessionError(str(error)) from error
        self._session, self._registry, self._events = staged._session, staged._registry, staged._events
        return self.public_state()

    def _perform(self, command: Command) -> None:
        action = command.action
        if action.startswith("investigate_"):
            recipes = list(self._actor_state()["known_recipes"])
            if action == "investigate_inscription":
                recipes.extend(["lightning_seed", "fog_echo"])
                self._formal(action, recipes=sorted(set(recipes)))
            else:
                recipes.append("storm_glass_relay")
                # Discovery and harvesting are deliberately separate actions:
                # the relay is learned from the wreck, then its single glass
                # shard is collected through the normal material authority.
                self._formal(action, recipes=sorted(set(recipes)))
            self._spend(1, "exploration")
        elif action.startswith("harvest_"):
            material = action.removeprefix("harvest_")
            self._harvest(material)
            self._spend(1, "harvest")
        elif action in {"travel_tower", "travel_shallows"}:
            self._formal(action)
            self._relocate(TOWER_ID if action == "travel_tower" else SHALLOWS_ID)
            self._spend(1, "move")
        elif action.startswith("craft_"):
            recipe = action.removeprefix("craft_")
            self._craft("fog_echo" if recipe == "mist_echo" else recipe)
        elif action in {"equip_active", "equip_passive", "unload_active", "unload_passive"}:
            self._loadout(action, command.target, command.slot)
        elif action in {"cast_lightning_seed", "cast_mist_echo"}:
            self._cast(action.removeprefix("cast_"))
        elif action == "start_core":
            self._formal("start_core")
            self._spend(1, "exploration")
        elif action in {"attack", "guard", "wait"}:
            self._combat(action)
        elif action == "close_core":
            self._formal("close_core")
            self._spend(1, "exploration")
        else:
            raise SessionError("unknown action")
        self._evaluate_terminal()

    def _formal(self, action: str, **extra: Any) -> None:
        actor = self._actor_state()
        payload = {"action": action, "serial": actor["action_serial"] + 1, **extra}
        result = self._session.runtime.run_event(Event(
            f"pmw:m0:session:{action}:{payload['serial']:06d}", SESSION_EVENT,
            self.state.sim_time, PLAYER_ID,
            self._current_area() if action.startswith("harvest_") else None, payload,
        ))
        if not result.changed:
            raise SessionError(f"formal command {action} did not match")
        self._record(action, "player", result)

    def _relocate(self, destination: str) -> None:
        location = next((relation for relation in self.state.relations.values()
                         if relation.type == "located_in" and relation.source == PLAYER_ID), None)
        if location is None:
            raise SessionError("player has no authoritative location relation")
        replacement = {"id": f"located:{PLAYER_ID}:{destination}", "type": "located_in",
                       "source": PLAYER_ID, "target": destination, "tags": [], "components": {}}
        result = self._session.runtime.run_event(Event(
            f"pmw:m0:relocate:{self._actor_state()['action_serial']:06d}", "pmw.m0.session.relocate",
            self.state.sim_time, PLAYER_ID, location.id, {"replacement": replacement},
        ))
        if not result.changed:
            raise SessionError("formal relocation did not commit")
        self._record("relocate", "world", result)

    def _spend(self, duration: int, reason: str) -> None:
        result = spend_world_time(self._session, duration, reason=reason)
        self._registry.session = self._session
        for tick in result.ticks:
            self._record("world_tick", "world", tick.event_result)
            self._dispatch_weather_passives(tick.event_result)
            self._expire_relay_shield_if_due()

    def _dispatch_weather_passives(self, event_result: Any) -> None:
        """Dispatch a passive only from formal derived weather events."""
        if not self._actor_state().get("relay_equipped"):
            return
        events = event_result.trace.to_dict().get("events", [])
        changes = [row["event"] for row in events if row.get("event", {}).get("type") == "pmw.m0.weather_changed"]
        for change in changes:
            if change.get("target") != self._current_area():
                continue
            weather = change.get("payload", {}).get("new")
            if weather in {"fog", "storm"}:
                self._grant_relay_shield(weather, change["id"])

    def _grant_relay_shield(self, weather: str, parent_event_id: str) -> None:
        """Install/refresh exactly the relay-owned shield layer by PMW Event."""
        amount = 6.0 if weather == "storm" else 4.0
        actor = deepcopy(self.state.entities[PLAYER_ID].components[GAMEPLAY_ACTOR])
        shields = deepcopy(self.state.entities[PLAYER_ID].components["pmw_gameplay_shields"])
        slots = shields["slots"]
        found = next(((name, layer) for name, layer in sorted(slots.items())
                      if layer.get("active") and layer.get("source_id") == "storm_glass_relay:relay_shield" and
                      layer.get("owner_id") == PLAYER_ID), None)
        if found is None:
            slot = next((name for name, layer in sorted(slots.items()) if not layer.get("active")), None)
            if slot is None:
                raise SessionError("no shield slot is available for storm glass relay")
            sequence = max((layer.get("sequence", -1) for layer in slots.values() if layer.get("active")), default=-1) + 1
            layer = {"active": True, "layer_id": slot, "source_id": "storm_glass_relay:relay_shield",
                     "owner_id": PLAYER_ID, "granted": amount, "remaining": amount,
                     "sequence": sequence, "status_instance_id": None}
            slots[slot] = layer
        else:
            _, layer = found
            layer["granted"] = amount
            layer["remaining"] = amount
        layer["created_tick"] = self.state.tick
        layer["expires_after_tick"] = self.state.tick + 3
        actor["shield"] = sum(row["remaining"] for row in slots.values() if row.get("active"))
        result = self._session.runtime.run_event(Event(
            f"pmw:m0:relay-grant:{self.state.tick:08d}", RELAY_SHIELD_EVENT,
            self.state.sim_time, "storm_glass_relay", PLAYER_ID,
            {"weather": weather, "amount": amount, "shield": actor["shield"], "shields": shields,
             "parent_event_id": parent_event_id},
        ))
        if not result.changed:
            raise SessionError("relay shield event did not commit")
        self._record("storm_glass_relay", "passive", result)

    def _expire_relay_shield_if_due(self) -> None:
        # Decay is a formal World Tick Law.  Once it reaches zero, remove only
        # the source-owned relay layer through another PMW event.
        if self._actor_state().get("relay_shield_ticks") != 0:
            return
        actor = self.state.entities[PLAYER_ID].components[GAMEPLAY_ACTOR]
        shields = deepcopy(self.state.entities[PLAYER_ID].components["pmw_gameplay_shields"])
        changed = False
        for layer in shields["slots"].values():
            if layer.get("active") and layer.get("source_id") == "storm_glass_relay:relay_shield" and layer.get("owner_id") == PLAYER_ID:
                layer.clear(); layer.update(neutral_shield_layer()); changed = True
        if not changed:
            return
        shield = sum(row["remaining"] for row in shields["slots"].values() if row["active"])
        result = self._session.runtime.run_event(Event(
            f"pmw:m0:relay-expire:{self.state.tick:08d}", "pmw.m0.session.relay_expire",
            self.state.sim_time, "m0_passive", PLAYER_ID, {"shield": shield, "shields": shields},
        ))
        if not result.changed:
            raise SessionError("relay shield expiry did not commit")
        self._record("storm_glass_relay_expire", "passive", result)

    def _harvest(self, material: str) -> None:
        area = self._area_state(self._current_area())
        stock = area["stock"].get(material, 0)
        if stock < 1:
            raise SessionError("resource stock is exhausted")
        quantities = self._inventory()
        self._formal(f"harvest_{material}", before_stock=stock, after_stock=stock - 1,
                     before_material=quantities[material], after_material=quantities[material] + 1)

    def _craft(self, recipe: str) -> None:
        if recipe not in self._actor_state()["known_recipes"]:
            raise SessionError("recipe has not been discovered")
        inventory = dict(self._inventory())
        for material, count in _RECIPES[recipe]:
            if inventory[material] < count:
                raise SessionError("insufficient crafting materials")
            inventory[material] -= count
        receipts = list(self._actor_state()["crafted_receipts"])
        if recipe in receipts:
            raise SessionError("recipe was already crafted")
        receipts.append(recipe)
        self._formal("craft", inventory=inventory, receipts=receipts)
        blueprint = parse_skill_blueprint(_blueprint_document(recipe), self._registry.base_registry.statuses,
                                          _authority(recipe))
        self._registry.install_blueprint(blueprint)
        self._session = self._registry.session
        self._spend(2, "exploration")
        self._record(f"craft_{recipe}", "registry", None)

    def _loadout(self, action: str, target: str | None, slot: int | None) -> None:
        if slot is None:
            raise SessionError("a loadout slot is required")
        actor = self.state.entities[PLAYER_ID].components[GAMEPLAY_ACTOR]
        equipped_relay = False
        if action.startswith("equip"):
            if target is None:
                raise SessionError("a crafted skill id is required")
            candidates = [item for item in self._registry.blueprints.values() if item.id == target]
            if len(candidates) != 1:
                raise SessionError("skill is not installed")
            kind = candidates[0].kind
            expected = "equip_passive" if kind == "passive_blueprint" else "equip_active"
            if action != expected:
                raise SessionError("skill type does not match requested loadout")
            change_loadout(self._session, self._registry.manifest, actor_id=PLAYER_ID,
                           operation=action, skill=skill_ref(candidates[0]), slot=slot)
            if target == "storm_glass_relay":
                # This flag is read by the formal weather-event dispatcher.
                self._formal("set_relay_equipped", enabled=True)
                equipped_relay = True
        else:
            operation = "unload_active" if action == "unload_active" else "unload_passive"
            current = actor["active_equipped" if operation == "unload_active" else "passive_equipped"][slot]
            change_loadout(self._session, self._registry.manifest, actor_id=PLAYER_ID, operation=operation, slot=slot)
            if current and current["id"] == "storm_glass_relay":
                self._formal("set_relay_equipped", enabled=False)
        self._spend(1, "exploration")
        if equipped_relay and self._area_state(self._current_area())["weather"] in {"storm", "fog"}:
            # Equipping into an already active weather state has the same
            # backend-only dispatch semantics as a later weather transition.
            self._grant_relay_shield(self._area_state(self._current_area())["weather"], "relay_equip")
        self._record(action, "loadout", None)

    def _cast(self, skill: str) -> None:
        action_id = {"lightning_seed": "lightning_seed", "mist_echo": "fog_echo"}[skill]
        from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.actions import resolve_action
        from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.actions import ActionRequest
        resolved = resolve_action(self._session, self._registry.action_registry, ActionRequest(
            f"m0_{action_id}_{self._actor_state()['action_serial'] + 1}", PLAYER_ID, action_id))
        self._record(f"cast_{skill}", "player", resolved.event_result)
        # Active skills are immediate.  Evaluate the changed Area before the
        # action's declared time cost advances its attractors; otherwise a
        # threshold crossed by a legal cast could be pulled back below the
        # threshold before the authoritative weather law ever observes it.
        weather = self._session.runtime.run_event(Event(
            f"pmw:m0:weather:cast:{self.state.tick:08d}:{action_id}", WEATHER_EVALUATE_EVENT,
            self.state.sim_time, PLAYER_ID, self._current_area(),
            {"area_id": self._current_area(), "tick": self.state.tick},
        ))
        # A cast is valid even when it does not cross a threshold; the
        # no-transition evaluation is still useful causal bookkeeping.
        self._record("weather_evaluate", "world", weather)
        if weather.changed:
            self._dispatch_weather_passives(weather)
        self._spend(1, "exploration")

    def _combat(self, action: str) -> None:
        if not self._combat_active():
            raise SessionError("the core encounter is not active")
        self._resolve_combat_action(PLAYER_ID, action, GUARD_ID if action == "attack" else None)
        if self.state.entities[GUARD_ID].components[GAMEPLAY_ACTOR]["hp"] > 0:
            self._resolve_combat_action(GUARD_ID, "attack", PLAYER_ID)
        if action == "guard":
            self._expire_guard_shield()
        self._spend(1, "combat")

    def _resolve_combat_action(self, actor_id: str, action: str, target_id: str | None) -> None:
        """Resolve one M0 Action for either controller against shared WorldState."""
        if action not in {"attack", "guard", "wait"}:
            raise SessionError("unknown combat action")
        actor = deepcopy(self.state.entities[actor_id].components[GAMEPLAY_ACTOR])
        other_id = GUARD_ID if actor_id == PLAYER_ID else PLAYER_ID
        other = deepcopy(self.state.entities[other_id].components[GAMEPLAY_ACTOR])
        actor_shields = deepcopy(self.state.entities[actor_id].components["pmw_gameplay_shields"])
        other_shields = deepcopy(self.state.entities[other_id].components["pmw_gameplay_shields"])
        if action == "attack":
            if target_id != other_id:
                raise SessionError("attack target is invalid")
            amount = float(self.state.entities[actor_id].components["storm_relay_actor"].get("combat_attack_base", 4.0)) + actor["power"]
            if actor_id == GUARD_ID:
                weather = self._area_state(TOWER_ID)["weather"]
                amount = 7.0 if weather == "storm" else 2.0 if weather == "fog" else 5.0
            absorbed = absorb_damage(other, other_shields, amount)
            other["hp"] = max(0.0, other["hp"] - (amount - absorbed))
        elif action == "guard":
            slots = actor_shields["slots"]
            slot = next((name for name, row in sorted(slots.items()) if not row.get("active")), None)
            if slot is None:
                raise SessionError("no shield slot is available for guard")
            amount = 2.0 * actor["resilience"] + 2.0
            slots[slot] = {"active": True, "layer_id": slot, "source_id": f"m0_guard:{actor_id}",
                           "owner_id": actor_id, "granted": amount, "remaining": amount,
                           "sequence": max((row.get("sequence", -1) for row in slots.values() if row.get("active")), default=-1) + 1,
                           "status_instance_id": None}
            actor["shield"] = sum(row["remaining"] for row in slots.values() if row.get("active"))
        else:
            actor["hp"] = min(actor["max_hp"], actor["hp"] + 2.0)
            actor["mana"] = min(actor["max_mana"], actor["mana"] + 2.0)
        payload = {
            "action": action, "actor_id": actor_id, "target_id": target_id,
            "player": self._combat_payload(PLAYER_ID, actor if actor_id == PLAYER_ID else other,
                                           actor_shields if actor_id == PLAYER_ID else other_shields),
            "guard": self._combat_payload(GUARD_ID, actor if actor_id == GUARD_ID else other,
                                          actor_shields if actor_id == GUARD_ID else other_shields),
        }
        result = self._session.runtime.run_event(Event(
            f"pmw:m0:combat:{self.state.tick:08d}:{actor_id}:{action}", COMBAT_EVENT,
            self.state.sim_time, actor_id, target_id, payload,
        ))
        if not result.changed:
            raise SessionError("combat action did not commit")
        self._record(action, "combat", result)

    def _combat_payload(self, actor_id: str, actor: dict[str, Any], shields: dict[str, Any]) -> dict[str, Any]:
        return {"id": actor_id, "hp": actor["hp"], "mana": actor["mana"], "shield": actor["shield"], "shields": shields}

    def _expire_guard_shield(self) -> None:
        actor = deepcopy(self.state.entities[PLAYER_ID].components[GAMEPLAY_ACTOR])
        shields = deepcopy(self.state.entities[PLAYER_ID].components["pmw_gameplay_shields"])
        for row in shields["slots"].values():
            if row.get("active") and row.get("source_id") == f"m0_guard:{PLAYER_ID}" and row.get("owner_id") == PLAYER_ID:
                row.clear(); row.update(neutral_shield_layer())
        actor["shield"] = sum(row["remaining"] for row in shields["slots"].values() if row.get("active"))
        result = self._session.runtime.run_event(Event(
            f"pmw:m0:guard-expire:{self.state.tick:08d}", GUARD_EXPIRE_EVENT,
            self.state.sim_time, "m0_combat", PLAYER_ID, {"shield": actor["shield"], "shields": shields},
        ))
        if not result.changed:
            raise SessionError("guard shield expiry did not commit")

    def _evaluate_terminal(self) -> None:
        actor = self._actor_state()
        if actor.get("outcome") == "victory":
            return
        if self.state.entities[PLAYER_ID].components[GAMEPLAY_ACTOR]["hp"] <= 0:
            self._formal("terminal_defeat")
        elif self._remaining() == 0:
            self._formal("terminal_defeat")

    def _record(self, action: str, source: str, result: Any) -> None:
        self._events.append({"id": f"m0-{len(self._events)+1}", "type": action,
                             "message": COMMAND_LABELS.get(action, action), "source": source,
                             "area": self._current_area(), "tick": self.state.tick})
        self._events[:] = self._events[-32:]

    def _actor_state(self) -> dict[str, Any]:
        return self.state.entities[PLAYER_ID].components["storm_relay_actor"]

    def _current_area(self) -> str:
        return self._actor_state()["current_area"]

    def _area_state(self, area_id: str) -> dict[str, Any]:
        return self.state.entities[area_id].components[AREA_COMPONENT]

    def _inventory(self) -> dict[str, float]:
        return self.state.entities[PLAYER_ID].components["pmw_gameplay_material_inventory"]["quantities"]

    def _remaining(self) -> int:
        return self.state.entities[CLOCK_ID].components["pmw_gameplay_time_budget"]["remaining_ticks"]

    def _combat_active(self) -> bool:
        return bool(self.state.entities[GUARD_ID].components["storm_relay_actor"]["encounter_active"] and
                    self.state.entities[GUARD_ID].components[GAMEPLAY_ACTOR]["hp"] > 0)

    def legal_actions(self) -> list[dict[str, Any]]:
        if self._actor_state().get("outcome") != "playing":
            return []
        area, state, result = self._current_area(), self._actor_state(), []
        if self._combat_active():
            return [{"action": action, "label": COMMAND_LABELS[action]} for action in ("attack", "guard", "wait")]
        if area == SHALLOWS_ID:
            if "lightning_seed" not in state["known_recipes"]:
                result.append({"action": "investigate_inscription", "label": COMMAND_LABELS["investigate_inscription"]})
            for material in ("wet_moss", "thunder_crystal"):
                if self._area_state(area)["stock"][material] > 0:
                    result.append({"action": f"harvest_{material}", "label": COMMAND_LABELS[f"harvest_{material}"]})
            result.append({"action": "travel_tower", "label": COMMAND_LABELS["travel_tower"]})
        else:
            if "storm_glass_relay" not in state["known_recipes"]:
                result.append({"action": "investigate_storm_glass", "label": COMMAND_LABELS["investigate_storm_glass"]})
            if self._area_state(area)["stock"]["storm_glass"] > 0:
                result.append({"action": "harvest_storm_glass", "label": "采集风暴玻璃"})
            result.append({"action": "travel_shallows", "label": "返回风暴浅滩"})
            guard_hp = self.state.entities[GUARD_ID].components[GAMEPLAY_ACTOR]["hp"]
            if not self.state.entities[GUARD_ID].components["storm_relay_actor"]["encounter_active"]:
                result.append({"action": "start_core", "label": COMMAND_LABELS["start_core"]})
            elif guard_hp <= 0:
                result.append({"action": "close_core", "label": COMMAND_LABELS["close_core"]})
        for recipe in state["known_recipes"]:
            if recipe not in state["crafted_receipts"]:
                action = "craft_mist_echo" if recipe == "fog_echo" else f"craft_{recipe}"
                result.append({"action": action, "label": COMMAND_LABELS[action]})
        for blueprint in self._registry.blueprints.values():
            result.append({"action": "equip_passive" if blueprint.kind == "passive_blueprint" else "equip_active",
                           "target": blueprint.id, "slot": 0, "label": f"装备 {blueprint.id}"})
        equipped = self.state.entities[PLAYER_ID].components[GAMEPLAY_ACTOR]["active_equipped"]
        if any(row and row["id"] == "lightning_seed" for row in equipped):
            result.append({"action": "cast_lightning_seed", "label": COMMAND_LABELS["cast_lightning_seed"]})
        if any(row and row["id"] == "fog_echo" for row in equipped):
            result.append({"action": "cast_mist_echo", "label": COMMAND_LABELS["cast_mist_echo"]})
        return result

    def public_state(self) -> dict[str, Any]:
        actor = self.state.entities[PLAYER_ID].components[GAMEPLAY_ACTOR]
        areas = []
        for area_id in (SHALLOWS_ID, TOWER_ID):
            entity = self.state.entities[area_id]
            dynamics = entity.components["pmw_gameplay_dynamics"]["fields"]
            areas.append({"id": area_id, "weather": entity.components[AREA_COMPONENT]["weather"],
                          "stock": dict(entity.components[AREA_COMPONENT]["stock"]),
                          "fields": {name: round(row["value"], 3) for name, row in dynamics.items()}})
        return {"outcome": self._actor_state()["outcome"],
                "time": {"remaining": self._remaining(), "total": self._budget},
                "current_area": self._current_area(),
                "player": {"id": PLAYER_ID, "hp": actor["hp"], "max_hp": actor["max_hp"],
                           "mana": actor["mana"], "max_mana": actor["max_mana"],
                           "attributes": {name: actor[name] for name in ("power", "control", "resilience", "agility")},
                           "relay_shield": self._actor_state()["relay_shield"]},
                "areas": areas, "inventory": [{"id": name, "count": count} for name, count in sorted(self._inventory().items())],
                "discoveries": list(self._actor_state()["known_recipes"]), "recipes": list(self._actor_state()["known_recipes"]),
                "registered_skills": [{"id": row.skill_id, "version": row.version, "kind": row.kind} for row in self._registry.manifest.entries if row.enabled],
                "equipped_skills": [row for key in ("active_equipped", "passive_equipped") for row in actor[key] if row],
                "combat": {"active": self._combat_active(), "guard_hp": self.state.entities[GUARD_ID].components[GAMEPLAY_ACTOR]["hp"]},
                "recent_events": list(self._events), "legal_actions": self.legal_actions()}


def _authority(recipe: str) -> MaterialAuthority:
    if recipe == "storm_glass_relay":
        return MaterialAuthority(("storm_glass",), ("shield",), ("self",), 10.0)
    return MaterialAuthority(tuple(sorted(item for item, _ in _RECIPES[recipe])), ("modify_field",), ("current_area",), 10.0)


def _blueprint_document(recipe: str) -> dict[str, Any]:
    if recipe == "lightning_seed":
        effects = [
            {"id": "seed_charge", "kind": "modify_field", "target": {"kind": "current_area"}, "commitment": "required", "field_id": "charge", "amount": .30},
            {"id": "seed_humidity", "kind": "modify_field", "target": {"kind": "current_area"}, "commitment": "required", "field_id": "humidity", "amount": .25},
        ]
        materials, kind, trigger = ["thunder_crystal", "wet_moss"], "skill_blueprint", "on_use"
    elif recipe == "fog_echo":
        effects = [{"id": "echo_humidity", "kind": "modify_field", "target": {"kind": "current_area"}, "commitment": "required", "field_id": "humidity", "amount": .35}]
        materials, kind, trigger = ["thunder_crystal", "wet_moss"], "skill_blueprint", "on_use"
    else:
        effects = [{"id": "relay_shield", "kind": "shield", "target": {"kind": "self"}, "commitment": "required", "amount": 6.0}]
        materials, kind, trigger = ["storm_glass"], "passive_blueprint", "weather_changed"
    return {"protocol": "pmw-gameplay-v0.4", "kind": kind, "id": recipe, "version": 1,
            "trigger": trigger, "condition": None, "duration": None,
            "cost": {"duration": 1, "mana": 3.0 if recipe != "storm_glass_relay" else 0.0},
            "scope": {"selectors": ["self"] if recipe == "storm_glass_relay" else ["current_area"], "relation_types": []},
            "effects": effects, "budget": {"limit": 10.0}, "max_firings_per_root": 1,
            "material_ids": materials}
