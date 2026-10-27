"""Authoritative PMW-backed session for the Alpha exploration vertical slice."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.basics import basic_registry
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.content_compiler import build_content_session, compile_content, make_content
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.registry import MechanismRegistryRuntime
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.runtime import build_runtime, discover_profiles
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.time_ledger import spend_world_time

from .content import (ACTOR_COMPONENT, AREA_COMPONENT, AREA_IDS, ASH_OBSERVATORY_ID, CLOCK_ID,
                      FROST_FOREST_ID, MATERIAL_IDS, MIST_CAMP_ID, MOSS_SHALLOWS_ID,
                      PLAYER_ID, STARTING_MAP_EDGES, THUNDER_MINE_ID, make_alpha_world)
from .savegame import SingleSlotSave


class AlphaSessionError(ValueError): pass

NAMES = {MIST_CAMP_ID: "雾栖营地", MOSS_SHALLOWS_ID: "雾苔浅滩", THUNDER_MINE_ID: "鸣雷矿穴", FROST_FOREST_ID: "霜痕森林", ASH_OBSERVATORY_ID: "灰烬观测站"}
DESCRIPTIONS = {MIST_CAMP_ID: "余烬在雾中微明。领悟台、补给火与北境地图守着出发前的片刻安宁。", MOSS_SHALLOWS_ID: "潮湿苔藓铺满浅滩，水文碑半沉在雾里。", THUNDER_MINE_ID: "矿穴深处的导线仍有微弱鸣响，升降机停在断电的井口。", FROST_FOREST_ID: "霜痕压低了树林。生物量尚未恢复，根桥的残骸埋在林心。", ASH_OBSERVATORY_ID: "观测站的灰烬控制台仍在等待一个足以改变第七夜的决定。"}
RESOURCES = {"moss_bed": ("wet_moss", 3), "crystal_vein": ("thunder_crystal", 3), "spore_bed": ("spore_bud", 3), "ash_reliquary": ("ash_cinder", 2)}
INTERACTIONS = {MIST_CAMP_ID: ("insight_dais", "supply_fire", "survey_map"), MOSS_SHALLOWS_ID: ("hydrology_stele", "moss_bed", "fungal_grove", "mist_beast"), THUNDER_MINE_ID: ("damaged_conduit", "crystal_vein", "mine_lift", "sentinel"), FROST_FOREST_ID: ("forest_heart", "spore_bed", "withered_grove", "root_bridge"), ASH_OBSERVATORY_ID: ("stabilizer_array", "ash_reliquary", "core_console", "ash_observer")}

@dataclass
class AlphaSession:
    _session: Any
    _registry: MechanismRegistryRuntime
    _events: list[dict[str, Any]]
    _feedback: list[str]

    @classmethod
    def new_game(cls) -> "AlphaSession":
        world = make_alpha_world()
        player = world.entities[PLAYER_ID].components[ACTOR_COMPONENT]
        player.update({"current_area": MIST_CAMP_ID, "knowledge": [], "visited": [MIST_CAMP_ID], "outcome": "playing", "xp": 0, "level": 1, "lift_powered": False, "root_bridge_formed": False, "boss_defeated": False, "core_closed": False})
        for area_id in AREA_IDS:
            area = world.entities[area_id].components[AREA_COMPONENT]
            area["stock"] = {material: amount for point, (material, amount) in RESOURCES.items() if point in INTERACTIONS[area_id]}
            area["inspected"] = []
        content = make_content(basic_registry(), material_ids=MATERIAL_IDS)
        compiled = compile_content(content)
        gameplay = build_content_session(world, compiled)
        return cls(gameplay, MechanismRegistryRuntime.from_compiled_content(gameplay, compiled), [], ["第七夜尚未来临。先在雾栖营地查看地图，或前往已知边境。"])

    @property
    def state(self): return self._session.state

    def _clone(self) -> "AlphaSession":
        staged = build_runtime(deepcopy(self.state), discover_profiles(self.state), self._registry.static_laws)
        registry = MechanismRegistryRuntime(staged, self._registry.base_registry, self._registry.static_laws, dict(self._registry.blueprints), self._registry.status_slots, self._registry.dynamics_slots); registry._rebuild()
        return AlphaSession(registry.session, registry, deepcopy(self._events), deepcopy(self._feedback))

    def perform(self, action: str, *, target: str | None = None, slot: int | None = None) -> dict[str, Any]:
        if not any(row["action"] == action and row.get("target") in (None, target) for row in self.controls()): raise AlphaSessionError("该行动当前不可执行")
        staged = self._clone(); staged._perform(action, target); self._session, self._registry, self._events, self._feedback = staged._session, staged._registry, staged._events, staged._feedback
        return self.public_state()

    def _perform(self, action: str, target: str | None) -> None:
        if action == "travel": self._travel(target or "")
        elif action == "inspect": self._inspect(target or "")
        elif action == "harvest": self._harvest(target or "")
        elif action == "rest": self._rest()
        elif action == "restore_forest": self._restore_forest()
        elif action == "power_lift": self._power_lift()
        else: raise AlphaSessionError("未知行动")
        self._terminal()

    def _spend(self, ticks: int, reason: str) -> None:
        result = spend_world_time(self._session, ticks, reason=reason); self._registry.session = self._session
        for tick in result.ticks: self._events.append({"source": "世界", "message": f"世界推进至第 {self.state.tick} 刻。", "tick": self.state.tick})

    def _travel(self, destination: str) -> None:
        origin = self._player()["current_area"]
        if destination not in self._neighbors(origin): raise AlphaSessionError("路径尚未形成")
        self._player()["current_area"] = destination; self._player()["visited"] = sorted(set(self._player()["visited"] + [destination])); self._spend(2, "move")
        self._note(f"抵达{NAMES[destination]}。{DESCRIPTIONS[destination]}")

    def _inspect(self, point: str) -> None:
        if point not in INTERACTIONS[self._player()["current_area"]]: raise AlphaSessionError("这里没有该调查对象")
        if point not in self._area()["inspected"]: self._area()["inspected"].append(point)
        clues = {"survey_map": "北境地图标记了两条通向观测站的失落路线：矿井升降机与森林根桥。", "hydrology_stele": "水文碑指出：湿度越过阈值会生雾；雾既遮蔽物资，也会改变潮兽的狩猎。", "damaged_conduit": "导管需要高电荷持续供能。安全启动升降机后，观测站可能反向得到能量。", "forest_heart": "林心的生物量恢复得很慢。改变吸引子后离开几刻，根桥才可能真正生长。", "stabilizer_array": "稳定装置需要一条安全路径、受控供能与恢复的生态；否则只能强行切断。"}
        message = clues.get(point, "你记录了这个交互点的可观察特征。它或许会和别处的规律连在一起。")
        self._player()["knowledge"] = sorted(set(self._player()["knowledge"] + [point])); self._spend(1, "exploration"); self._note(message)

    def _harvest(self, point: str) -> None:
        if point not in RESOURCES or point not in INTERACTIONS[self._player()["current_area"]]: raise AlphaSessionError("这里不能采集该资源")
        material, _ = RESOURCES[point]; stock = self._area()["stock"].get(material, 0)
        if stock <= 0: raise AlphaSessionError("资源已经耗尽")
        self._area()["stock"][material] = stock - 1; inv = self._inventory(); inv[material] += 1; self._spend(2, "harvest")
        self._note(f"获得 1 {_material_name(material)}。库存减少；持续采集会让环境恢复得更困难。")

    def _rest(self) -> None:
        actor = self.state.entities[PLAYER_ID].components["pmw_gameplay_actor"]; actor["hp"] = actor["max_hp"]; actor["mana"] = actor["max_mana"]; self._spend(3, "exploration"); self._note("补给火驱散了疲惫。生命与法力已恢复，但世界仍向第七夜靠近。")

    def _restore_forest(self) -> None:
        inv = self._inventory()
        if inv["spore_bud"] < 2: raise AlphaSessionError("需要 2 孢芽")
        inv["spore_bud"] -= 2; fields = self.state.entities[FROST_FOREST_ID].components["pmw_gameplay_dynamics"]["fields"]; fields["biomass"]["target"] = .78; fields["biomass"]["rate"] = .08; self._spend(2, "exploration"); self._note("孢芽融入林心。生物量的恢复目标已被改变；离开并让世界推进几刻，再回来观察根桥。")

    def _power_lift(self) -> None:
        fields = self.state.entities[THUNDER_MINE_ID].components["pmw_gameplay_dynamics"]["fields"]
        if fields["charge"]["value"] < .60: raise AlphaSessionError("矿穴电荷仍不足；先调查导管，或寻找能改变电荷的机制")
        self._player()["lift_powered"] = True; self._spend(2, "exploration"); self._note("升降机在持续供能下启动。矿穴至观测站的通路已经建立；这项供能也可能增强观测站。")

    def _terminal(self) -> None:
        if self._remaining() <= 0 and not self._player()["core_closed"]: self._player()["outcome"] = "seventh_night"; self._note("第七夜降临，核心仍未关闭。")

    def _neighbors(self, origin: str) -> set[str]:
        edges = {tuple(edge) for edge in STARTING_MAP_EDGES}; p = self._player()
        if p["lift_powered"]: edges.add((THUNDER_MINE_ID, ASH_OBSERVATORY_ID))
        if p["root_bridge_formed"]: edges.add((FROST_FOREST_ID, ASH_OBSERVATORY_ID))
        return {b if a == origin else a for a, b in edges if origin in (a, b)}

    def controls(self) -> list[dict[str, Any]]:
        if self._player()["outcome"] != "playing": return []
        area = self._player()["current_area"]; rows = [{"action": "travel", "target": dest, "label": f"前往{NAMES[dest]}", "description": "移动消耗 2 个世界刻。"} for dest in sorted(self._neighbors(area))]
        for point in INTERACTIONS[area]:
            if point not in self._area()["inspected"]: rows.append({"action": "inspect", "target": point, "label": "仔细调查", "description": "消耗 1 个世界刻，获得可复用的规律线索。"})
            if point in RESOURCES and self._area()["stock"].get(RESOURCES[point][0], 0) > 0: rows.append({"action": "harvest", "target": point, "label": f"采集{_material_name(RESOURCES[point][0])}", "description": "消耗 2 个世界刻，资源会减少。"})
        if area == MIST_CAMP_ID: rows.append({"action": "rest", "label": "在补给火休整", "description": "消耗 3 个世界刻，恢复生命与法力。"})
        if area == FROST_FOREST_ID and "forest_heart" in self._player()["knowledge"] and self._inventory()["spore_bud"] >= 2: rows.append({"action": "restore_forest", "label": "以孢芽修复林心", "description": "消耗 2 孢芽与 2 个世界刻，改变长期生物量恢复。"})
        if area == THUNDER_MINE_ID and "damaged_conduit" in self._player()["knowledge"]: rows.append({"action": "power_lift", "label": "尝试启动升降机", "description": "需要当前电荷达到 0.60；成功后会永久建立通路。"})
        return rows

    def public_state(self) -> dict[str, Any]:
        area_id = self._player()["current_area"]; actor = self.state.entities[PLAYER_ID].components["pmw_gameplay_actor"]
        areas = [{"id": aid, "name": NAMES[aid], "discovered": aid in self._player()["visited"], "current": aid == area_id, "locked": aid == ASH_OBSERVATORY_ID and aid not in self._neighbors(THUNDER_MINE_ID) | self._neighbors(FROST_FOREST_ID), "description": DESCRIPTIONS[aid]} for aid in AREA_IDS]
        fields = self.state.entities[area_id].components["pmw_gameplay_dynamics"]["fields"]
        return {"title": "第七夜之前", "time": self.state.tick, "remaining_time": self._remaining(), "area": {"id": area_id, "name": NAMES[area_id], "description": DESCRIPTIONS[area_id], "fields": {key: round(value["value"], 3) for key, value in fields.items()}}, "map": {"areas": areas}, "player": {"name": "第七夜行者", "hp": actor["hp"], "max_hp": actor["max_hp"], "mana": actor["mana"], "max_mana": actor["max_mana"], "shield": actor["shield"], "level": self._player()["level"], "xp": self._player()["xp"], "attributes": {key: actor[key] for key in ("power", "control", "resilience", "agility")}, "inventory": self._inventory()}, "interactions": [{"id": point, "name": _interaction_name(point), "description": "已调查" if point in self._area()["inspected"] else "尚未调查", "state": "已知" if point in self._area()["inspected"] else "可观察"} for point in INTERACTIONS[area_id]], "recipes": [], "skills": [], "combat": {"active": False}, "recent_events": self._events[-24:], "feedback": self._feedback, "outcome": self._player()["outcome"], "controls": self.controls()}

    def export_save_metadata(self) -> dict[str, Any]: return {"events": self._events[-24:], "feedback": self._feedback}
    def save(self, directory: str | Path) -> None: SingleSlotSave(directory).save(self)
    @classmethod
    def load(cls, directory: str | Path) -> "AlphaSession": raise AlphaSessionError("Alpha save hydration will be enabled with the compiled action registry")
    def _player(self) -> dict[str, Any]: return self.state.entities[PLAYER_ID].components[ACTOR_COMPONENT]
    def _area(self) -> dict[str, Any]: return self.state.entities[self._player()["current_area"]].components[AREA_COMPONENT]
    def _inventory(self) -> dict[str, float]: return self.state.entities[PLAYER_ID].components["pmw_gameplay_material_inventory"]["quantities"]
    def _remaining(self) -> int: return self.state.entities[CLOCK_ID].components["pmw_gameplay_time_budget"]["remaining_ticks"]
    def _note(self, message: str) -> None: self._feedback = [message]; self._events.append({"source": "世界", "message": message, "tick": self.state.tick})

def _material_name(material: str) -> str: return {"wet_moss": "潮湿苔藓", "thunder_crystal": "雷晶", "spore_bud": "孢芽", "ash_cinder": "灰烬晶"}.get(material, material)
def _interaction_name(point: str) -> str: return {"insight_dais": "技能领悟台", "supply_fire": "补给火", "survey_map": "北境地图", "hydrology_stele": "水文碑", "moss_bed": "苔藓群落", "fungal_grove": "隐蔽菌圃", "mist_beast": "潮雾潜伏兽", "damaged_conduit": "破损供能设备", "crystal_vein": "雷晶矿脉", "mine_lift": "矿井升降机", "sentinel": "导电哨兵", "spore_bed": "可采集孢芽", "forest_heart": "森林核心", "withered_grove": "退化林地", "root_bridge": "根桥遗迹", "stabilizer_array": "环境稳定装置", "ash_reliquary": "灰烬匣", "core_console": "核心控制台", "ash_observer": "灰烬观测者"}.get(point, point)
