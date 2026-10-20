"""Public, typed commands accepted by the Storm Relay game session.

The browser and route runners use only these IDs.  They never select laws,
component paths, damage values, materials, or time costs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


class CommandError(ValueError):
    """Raised before a command commits any authoritative game state."""


@dataclass(frozen=True, slots=True)
class Command:
    action: str
    target: str | None = None
    slot: int | None = None

    @classmethod
    def parse(cls, raw: Mapping[str, Any]) -> "Command":
        if not isinstance(raw, Mapping):
            raise CommandError("command must be an object")
        unknown = set(raw) - {"action", "target", "slot"}
        if unknown:
            raise CommandError(f"unknown command fields: {sorted(unknown)}")
        action = raw.get("action")
        target = raw.get("target")
        slot = raw.get("slot")
        if not isinstance(action, str) or not action:
            raise CommandError("action must be a non-empty string")
        if target is not None and (not isinstance(target, str) or not target):
            raise CommandError("target must be a non-empty string when supplied")
        if slot is not None and (isinstance(slot, bool) or not isinstance(slot, int) or not 0 <= slot < 6):
            raise CommandError("slot must be an integer from 0 through 5")
        return cls(action=action, target=target, slot=slot)


# The complete public verb vocabulary.  Legality is generated from the current
# authoritative world, so presence here never makes a command legal by itself.
COMMAND_LABELS = {
    "investigate_inscription": "调查古老残铭",
    "harvest_wet_moss": "采集潮湿苔藓",
    "harvest_thunder_crystal": "采集雷晶",
    "travel_tower": "前往旧引雷塔",
    "investigate_storm_glass": "调查破碎风暴玻璃",
    "craft_lightning_seed": "制作引雷播种",
    "craft_mist_echo": "制作雾幕回响",
    "craft_storm_glass_relay": "制作风暴玻璃继电",
    "equip_active": "装备主动技能",
    "equip_passive": "装备被动技能",
    "unload_active": "卸下主动技能",
    "unload_passive": "卸下被动技能",
    "cast_lightning_seed": "使用引雷播种",
    "cast_mist_echo": "使用雾幕回响",
    "start_core": "启动核心舱",
    "attack": "攻击",
    "guard": "防御",
    "wait": "等待",
    "close_core": "关闭继电核心",
}

