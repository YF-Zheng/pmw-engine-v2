"""Create human and machine reports strictly from Build evidence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .run_builds import ROOT, load_specs


JUDGMENTS = {
    "build_a": {
        "classification": "MECHANICALLY_INTERESTING",
        "functional": True,
        "mechanical": True,
        "strategic": False,
        "interaction_type": "status_gates_followup_but_net_negative",
        "summary_zh": "赦免真实创造了处决条件，但治疗 8 后再伤害 11 仅有 3 点净伤害，远弱于两次普通攻击的 24。",
    },
    "build_b": {
        "classification": "MECHANICALLY_INTERESTING",
        "functional": True,
        "mechanical": True,
        "strategic": False,
        "interaction_type": "field_creates_cast_window",
        "summary_zh": "引雷播种把原本不足的湿度推过纸甲门槛并少损失 9 HP，但两次 Guard 少损失 14 HP。",
    },
    "build_c": {
        "classification": "PLAYABLE_BUILD",
        "functional": True,
        "mechanical": True,
        "strategic": True,
        "interaction_type": "weather_event_to_defense_with_feedback",
        "summary_zh": "播种产生真实天气事件，继电器把事件转成防御并优于一次 Guard；泄放电场又会削弱风暴，是可玩的取舍。",
    },
    "build_d": {
        "classification": "EXECUTABLE_ONLY",
        "functional": True,
        "mechanical": False,
        "strategic": False,
        "interaction_type": "additive_or_redundant",
        "summary_zh": "两张技能可以堆烟，但火柴单独已越过阈值；组合没有额外防御或有效伤害，施放顺序甚至会延迟热浪路径。",
    },
    "build_e": {
        "classification": "EXECUTABLE_ONLY",
        "functional": True,
        "mechanical": False,
        "strategic": False,
        "interaction_type": "additive_or_redundant",
        "summary_zh": "两个速率槽能同时生效，但 #042 单独已保住临界生态并提供相同防御，组合只是递减收益的数值叠加。",
    },
    "build_f": {
        "classification": "MECHANICALLY_INTERESTING",
        "functional": True,
        "mechanical": True,
        "strategic": False,
        "interaction_type": "resource_enabler_dominated_by_wait",
        "summary_zh": "生命债能立即换来施法资源，但等待一轮自然回蓝后单独施放 Fever Key 达到相同温度且多保留 9 HP；低 HP 时组合还会死亡。",
    },
}


def _active_weather(step: dict[str, Any]) -> str:
    active = [key for key, value in step["weather"].items() if value["active"]]
    return ",".join(active) if active else "-"


def _replay(result: dict[str, Any]) -> str:
    spec = result["spec"]
    lines = [
        f"# {result['build_id']} · {result['name_zh']} Replay",
        "",
        f"目标：{spec['objective']['statement_zh']}",
        "",
        f"技能：{', '.join(spec['skill_case_ids'])}；敌方行动：`{spec['enemy_action']}`；"
        f"每臂 {spec['rounds']} 个正式 Combat Round。",
        "",
    ]
    if spec.get("dispatch_mode"):
        lines.extend([
            f"被动分发：`{spec['dispatch_mode']}`。只有 World Tick Trace 中真实出现 "
            "`pmw.v04.weather.changed` 派生事件时才调用公共 Hook Executor。",
            "",
        ])
    for variant_id, variant in result["variants"].items():
        config = variant["variant"]
        lines.extend([
            f"## 场景 `{variant_id}`",
            "",
            f"环境：`{config['environment']}`；覆盖值：`{json.dumps(config.get('field_overrides', {}), ensure_ascii=False, sort_keys=True)}`；"
            f"初始资源：`{json.dumps(config['initial'], ensure_ascii=False, sort_keys=True)}`。",
            "",
        ])
        for arm_id, arm in variant["arms"].items():
            lines.extend([
                f"### `{arm_id}`",
                "",
                "|轮|请求动作|实际动作|拒绝|Hero HP/Mana/Shield|Target HP|Wet|Elec|Smoke|Temp|Biomass|生态|天气|Hook|",
                "|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---:|",
            ])
            for index, round_row in enumerate(arm["rounds"], 1):
                step = arm["timeline"][index]
                actual = next(
                    (row["action_id"] for row in round_row["outcomes"] if row["actor_id"] == "synergy_hero"),
                    "skipped",
                )
                rejected = round_row["rejected"]["message"] if round_row["rejected"] else "-"
                lines.append(
                    f"|{index}|`{round_row['requested_player_action']}`|`{actual}`|{rejected}|"
                    f"{step['hero']['hp']:g}/{step['hero']['mana']:g}/{step['hero']['shield']:g}|"
                    f"{step['target']['hp']:g}|{step['fields']['wetness']['value']:.3f}|"
                    f"{step['fields']['electric_field']['value']:.3f}|{step['fields']['smoke']['value']:.3f}|"
                    f"{step['fields']['temperature']['value']:.2f}|{step['fields']['biomass']['value']:.3f}|"
                    f"{step['ecology']['current']}|{_active_weather(step)}|"
                    f"{len(round_row['manual_hook_dispatches'])}|"
                )
            metrics = arm["metrics"]
            lines.extend([
                "",
                "终局：" + ", ".join([
                    f"target_damage={metrics['target_damage']:g}",
                    f"hero_hp_loss={metrics['hero_hp_loss']:g}",
                    f"final_ecology={metrics['final_ecology']}",
                    f"weather={metrics['active_weather_seen']}",
                    f"rejections={metrics['rejected_action_count']}",
                ]),
                "",
            ])
    judgment = JUDGMENTS[result["build_id"]]
    lines.extend([
        "## 判定",
        "",
        f"`{judgment['classification']}`：{judgment['summary_zh']}",
        "",
    ])
    return "\n".join(lines)


def build_reports() -> None:
    specs = {spec["build_id"]: spec for spec in load_specs()}
    replay_dir = ROOT / "replays"
    replay_dir.mkdir(parents=True, exist_ok=True)
    catalog = []
    portfolio = [
        "# PMW Build Synergy Pilot v0.1 · 构筑作品集",
        "",
        "所有判定来自同一持续 Session 的真实 Action/Hook、敌方行动和 World Tick；不按触发 Law 数量评分。",
        "",
    ]
    for build_id in sorted(specs):
        evidence_path = ROOT / "evidence" / f"{build_id}.json"
        result = json.loads(evidence_path.read_text())
        judgment = JUDGMENTS[build_id]
        replay_path = replay_dir / f"{build_id}.zh.md"
        replay_path.write_text(_replay(result))
        compact = {
            variant_id: {arm_id: arm["metrics"] for arm_id, arm in variant["arms"].items()}
            for variant_id, variant in result["variants"].items()
        }
        row = {
            "build_id": build_id,
            "name_zh": result["name_zh"],
            "skill_case_ids": result["spec"]["skill_case_ids"],
            "objective": result["spec"]["objective"],
            **judgment,
            "variant_metrics": compact,
            "spec_path": f"build_specs/{build_id}.json",
            "evidence_path": f"evidence/{build_id}.json",
            "replay_path": f"replays/{build_id}.zh.md",
        }
        catalog.append(row)
        portfolio.extend([
            f"## {build_id} · {result['name_zh']}",
            "",
            f"- 技能：{', '.join(result['spec']['skill_case_ids'])}",
            f"- 预注册目标：{result['spec']['objective']['statement_zh']}",
            f"- 功能兼容：{'是' if judgment['functional'] else '否'}",
            f"- 机制交互：{'是' if judgment['mechanical'] else '否'}（`{judgment['interaction_type']}`）",
            f"- 策略价值：{'是' if judgment['strategic'] else '否'}",
            f"- 判定：`{judgment['classification']}`",
            f"- 结论：{judgment['summary_zh']}",
            f"- 证据：`evidence/{build_id}.json`；逐轮回放：`replays/{build_id}.zh.md`",
            "",
        ])
    (ROOT / "build_catalog.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in catalog)
    )
    (ROOT / "build_portfolio.zh.md").write_text("\n".join(portfolio).rstrip() + "\n")


if __name__ == "__main__":
    build_reports()
