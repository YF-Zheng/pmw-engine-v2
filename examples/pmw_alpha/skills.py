"""Deterministic Alpha core/glyph skill catalogue.

This is deliberately data rather than twelve name branches.  Session crafting
uses these documents to present costs and, in the next combat slice, compile
them through the Gameplay registry.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AlphaSkillTemplate:
    id: str; name: str; core: str; glyph: str; kind: str; mana: int; duration: int | None; effect: str; exploration_use: str; combat_use: str


_EFFECTS = {
    "tide": ("湿度 +0.28，使区域趋向浓雾", "湿度目标设为 0.82，持续 4 刻", "雾形成时获得 3 护盾"),
    "thunder": ("电荷 +0.35；导电敌人承受放电", "电荷目标设为 0.78，持续 4 刻", "雷暴时对导电敌人放电 4"),
    "spore": ("生物量 +0.25，资源丰度恢复", "生物量目标设为 0.78，持续 5 刻", "生态恢复时回复 3 HP"),
    "ash": ("温度 +0.30，造成灼热并消耗生物量", "温度目标设为 0.70，持续 4 刻", "受到伤害时获得 3 护盾并升温"),
}
_NAMES = {"tide": "潮息", "thunder": "雷晶", "spore": "孢芽", "ash": "灰烬"}
_GLYPHS = (("instant", "瞬发纹", "active", 3, None), ("sustain", "维持纹", "active", 4, 4), ("echo", "回响纹", "passive", 0, 3))


def skill_catalogue() -> tuple[AlphaSkillTemplate, ...]:
    rows = []
    for core in ("tide", "thunder", "spore", "ash"):
        for index, (glyph, glyph_name, kind, mana, duration) in enumerate(_GLYPHS):
            rows.append(AlphaSkillTemplate(f"{core}_{glyph}", f"{_NAMES[core]}{glyph_name}", core, glyph, kind, mana, duration, _EFFECTS[core][index], _exploration(core, glyph), _combat(core, glyph)))
    return tuple(rows)


def recipe_materials(template: AlphaSkillTemplate) -> dict[str, int]:
    # The elemental part of a recipe is deliberately the material that the
    # player can see and harvest in the matching region.  This makes crafting
    # compete with restoration instead of hiding an unrelated "core" currency
    # behind the UI.
    core_material = {
        "tide": "wet_moss",
        "thunder": "thunder_crystal",
        "spore": "spore_bud",
        "ash": "ash_cinder",
    }[template.core]
    glyph_material = {"instant": "instant_glyph", "sustain": "sustaining_glyph", "echo": "echo_glyph"}[template.glyph]
    return {core_material: 1, glyph_material: 1}


def _exploration(core: str, glyph: str) -> str:
    return {("tide", "instant"): "制造雾以显露菌圃", ("thunder", "sustain"): "为矿井升降机蓄能", ("spore", "sustain"): "投资森林根桥", ("ash", "instant"): "清除雾但伤害生态"}.get((core, glyph), "改变区域规律并留下可观察后果")
def _combat(core: str, glyph: str) -> str:
    return {("tide", "instant"): "改变潮雾潜伏兽的可见性", ("thunder", "instant"): "对导电哨兵的放电窗口造成高收益", ("spore", "echo"): "生态良好时吸收伤害", ("ash", "instant"): "高伤害换取生态代价"}.get((core, glyph), "通过场量、持续或事件触发改变战斗")
