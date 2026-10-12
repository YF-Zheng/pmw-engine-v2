# PMW Build Synergy Pilot v0.1 · 构筑作品集

所有判定来自同一持续 Session 的真实 Action/Hook、敌方行动和 World Tick；不按触发 Law 数量评分。

## build_a · 赦免与处决

- 技能：skill_051, skill_052
- 预注册目标：四个等时战斗轮内，在玩家存活的前提下尽量降低敌人 HP。
- 功能兼容：是
- 机制交互：是（`status_gates_followup_but_net_negative`）
- 策略价值：否
- 判定：`MECHANICALLY_INTERESTING`
- 结论：赦免真实创造了处决条件，但治疗 8 后再伤害 11 仅有 3 点净伤害，远弱于两次普通攻击的 24。
- 证据：`evidence/build_a.json`；逐轮回放：`replays/build_a.zh.md`

## build_b · 人工雨场与湿纸甲

- 技能：skill_041, skill_055
- 预注册目标：四轮敌方攻击下，用相同的行动机会最大化最终 HP 与剩余护盾。
- 功能兼容：是
- 机制交互：是（`field_creates_cast_window`）
- 策略价值：否
- 判定：`MECHANICALLY_INTERESTING`
- 结论：引雷播种把原本不足的湿度推过纸甲门槛并少损失 9 HP，但两次 Guard 少损失 14 HP。
- 证据：`evidence/build_b.json`；逐轮回放：`replays/build_b.zh.md`

## build_c · 制造风暴并转成防御

- 技能：skill_041, skill_049
- 预注册目标：主动制造天气事件，并在四轮敌方攻击下把它转成可验证的防御收益。
- 功能兼容：是
- 机制交互：是（`weather_event_to_defense_with_feedback`）
- 策略价值：是
- 判定：`PLAYABLE_BUILD`
- 结论：播种产生真实天气事件，继电器把事件转成防御并优于一次 Guard；泄放电场又会削弱风暴，是可玩的取舍。
- 证据：`evidence/build_c.json`；逐轮回放：`replays/build_c.zh.md`

## build_d · 烟幕积累与热浪放大

- 技能：skill_005, skill_053
- 预注册目标：在两次准备行动内触发烟雾热锋，同时比较护盾、伤害和公共升温代价。
- 功能兼容：是
- 机制交互：否（`additive_or_redundant`）
- 策略价值：否
- 判定：`EXECUTABLE_ONLY`
- 结论：两张技能可以堆烟，但火柴单独已越过阈值；组合没有额外防御或有效伤害，施放顺序甚至会延迟热浪路径。
- 证据：`evidence/build_d.json`；逐轮回放：`replays/build_d.zh.md`

## build_e · 防御与生态维护共用能力

- 技能：skill_027, skill_042
- 预注册目标：四轮敌方攻击后保持存活，并阻止生态进入 stressed。
- 功能兼容：是
- 机制交互：否（`additive_or_redundant`）
- 策略价值：否
- 判定：`EXECUTABLE_ONLY`
- 结论：两个速率槽能同时生效，但 #042 单独已保住临界生态并提供相同防御，组合只是递减收益的数值叠加。
- 证据：`evidence/build_e.json`；逐轮回放：`replays/build_e.zh.md`

## build_f · 用未来生命偿还当前能力

- 技能：skill_056, skill_060
- 预注册目标：在四轮内越过热浪阈值并存活，记录为此支付的生命与法力机会成本。
- 功能兼容：是
- 机制交互：是（`resource_enabler_dominated_by_wait`）
- 策略价值：否
- 判定：`MECHANICALLY_INTERESTING`
- 结论：生命债能立即换来施法资源，但等待一轮自然回蓝后单独施放 Fever Key 达到相同温度且多保留 9 HP；低 HP 时组合还会死亡。
- 证据：`evidence/build_f.json`；逐轮回放：`replays/build_f.zh.md`
