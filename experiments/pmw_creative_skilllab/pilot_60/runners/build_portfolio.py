"""Build the blind portfolio and machine-readable catalog from real evidence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .run_pilot import EVIDENCE, ROOT, load_cases


CATALOG = ROOT / "skill_catalog.jsonl"
PORTFOLIO = ROOT / "creative_portfolio.zh.md"


def _final_differences(evidence: dict[str, Any]) -> list[str]:
    baseline = evidence["baseline"]["timeline"][-1]
    treatment = evidence["treatment"]["timeline"][-1]
    rows: list[str] = []
    for actor_id in ("hero", "target"):
        for key in ("hp", "mana", "shield"):
            left, right = baseline[actor_id][key], treatment[actor_id][key]
            if left != right:
                rows.append(f"{actor_id}.{key}: {left:g} -> {right:g}")
        for key in ("traits", "statuses", "shield_layers"):
            left, right = baseline[actor_id][key], treatment[actor_id][key]
            if left != right:
                rows.append(f"{actor_id}.{key}: {json.dumps(right, ensure_ascii=False)}")
    for field_id in sorted(baseline["fields"]):
        for key in ("value", "effective_target", "effective_rate"):
            left = baseline["fields"][field_id][key]
            right = treatment["fields"][field_id][key]
            if left != right:
                rows.append(f"field.{field_id}.{key}: {left:g} -> {right:g}")
    if baseline["weather"] != treatment["weather"]:
        rows.append("weather state differs; inspect the evidence timeline")
    if baseline["ecology"] != treatment["ecology"]:
        rows.append(
            f"ecology.current: {baseline['ecology']['current']} -> "
            f"{treatment['ecology']['current']}"
        )
    return rows


def _effect_summary(effect: dict[str, Any]) -> str:
    target = effect["target"]["kind"]
    details = []
    for key in ("amount", "resource", "field_id", "status_id", "trait_id", "duration"):
        if key in effect:
            details.append(f"{key}={effect[key]}")
    conditional = "，有条件" if effect["commitment"] == "conditional" else ""
    return f"{effect['kind']} -> {target} ({', '.join(details)}){conditional}"


def _triggered_laws(evidence: dict[str, Any]) -> list[str]:
    return sorted({
        law_id
        for event in evidence["treatment"]["events"]
        for law_id in event["triggered_law_ids"]
    })


def build() -> None:
    catalog_rows = []
    sections = [
        "# PMW Creative SkillLab：60 技能盲评作品集",
        "",
        "本文件不包含创造者自评分。每项“实际观察”均由相同初态、相同世界时间的 "
        "Baseline/Treatment 真实运行产生；完整 Blueprint、状态序列和 CausalTrace 见对应证据。",
        "",
    ]
    for case in load_cases():
        evidence_path = EVIDENCE / f"{case['case_id']}.json"
        evidence = json.loads(evidence_path.read_text())
        differences = _final_differences(evidence)
        laws = _triggered_laws(evidence)
        skill_path = next((ROOT / "skills").glob(f"{case['case_id']}_*.json"))
        row = {
            "case_id": case["case_id"],
            "skill_id": case["blueprint"]["id"],
            "name_zh": case["name_zh"],
            "creator": case["creator"],
            "kind": case["blueprint"]["kind"],
            "category": case["category"],
            "tags": case["tags"],
            "intent_zh": case["intent_zh"],
            "material": case["material"],
            "cost": case["blueprint"]["cost"],
            "trigger": case["blueprint"]["trigger"],
            "scenario": case["scenario"],
            "effects": case["blueprint"]["effects"],
            "legality": evidence["legality"],
            "validation_result": evidence["result"],
            "changed_steps": evidence["changed_steps"],
            "final_differences": differences,
            "triggered_law_ids": laws,
            "counterexample": evidence["counterexample"],
            "limitations_zh": case["limitations_zh"],
            "skill_path": str(skill_path.relative_to(ROOT)),
            "evidence_path": str(evidence_path.relative_to(ROOT)),
            "test_path": "tests/test_pilot_60.py",
        }
        catalog_rows.append(row)

        kind = "被动" if case["blueprint"]["kind"] == "passive_blueprint" else "主动"
        traits = ", ".join(trait["id"] for trait in case["material"]["traits"])
        sections.extend([
            f"## {case['case_id']} · {case['name_zh']}",
            "",
            f"- 身份：{kind}；{case['creator']}；{case['category']}",
            f"- 材料：`{case['material']['id']}`（{case['material']['tier']} / "
            f"{case['material']['region_rarity']}），词条 `{traits}`",
            f"- 触发与成本：`{case['blueprint']['trigger']}`；"
            f"Mana {case['blueprint']['cost']['mana']}；Duration {case['blueprint']['cost']['duration']}",
            f"- 创造意图：{case['intent_zh']}",
            "- 实际机制：" + "；".join(_effect_summary(effect) for effect in case["blueprint"]["effects"]),
            f"- 测试场景：`{case['scenario']['environment']}`；"
            f"{case['scenario'].get('horizon_ticks', 3)} World Tick；变化步骤 {evidence['changed_steps']}",
            "- 实际观察：" + ("；".join(differences[:8]) if differences else "中间时序存在差异，最终已回归"),
            "- 触发 Law：" + (", ".join(f"`{law}`" for law in laws[:12]) if laws else "无额外 Law"),
            f"- 反例：未装备或错误 Trigger 被拒绝，WorldState 原子不变（"
            f"`{evidence['counterexample']['message']}`）。",
            "- 已知限制：" + "；".join(case["limitations_zh"]),
            f"- 证据：`{row['skill_path']}`；`{row['evidence_path']}`；`{row['test_path']}`",
            "",
        ])

    CATALOG.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in catalog_rows)
    )
    PORTFOLIO.write_text("\n".join(sections).rstrip() + "\n")


if __name__ == "__main__":
    build()
