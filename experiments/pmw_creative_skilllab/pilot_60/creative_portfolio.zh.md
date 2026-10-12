# PMW Creative SkillLab：60 技能盲评作品集

本文件不包含创造者自评分。每项“实际观察”均由相同初态、相同世界时间的 Baseline/Treatment 真实运行产生；完整 Blueprint、状态序列和 CausalTrace 见对应证据。

## skill_001 · 逆流接地

- 身份：主动；Creator A；战斗与环境操纵
- 材料：`forked_fulgurite`（rare / scarce），词条 `forked_fulgurite_craft`
- 触发与成本：`on_use`；Mana 3；Duration 1
- 创造意图：把高导电环境当作一次性弹药：强击会同步接地，后续同技能失去条件。
- 实际机制：damage -> target_actor (amount=8)；modify_field -> current_area (amount=-0.35, field_id=conductivity)
- 测试场景：`storm_plateau`；4 World Tick；变化步骤 [1, 2, 3, 4, 5]
- 实际观察：hero.mana: 45 -> 42；target.hp: 80 -> 72；field.conductivity.value: 0.70059 -> 0.449852
- 触发 Law：`pmw.v04.action.conductive_reversal.v1.329d215a0c7c.cost`, `pmw.v04.action.conductive_reversal.v1.329d215a0c7c.effect.drain_charge`, `pmw.v04.action.conductive_reversal.v1.329d215a0c7c.effect.ground_arc`, `pmw.v04.dynamics.200.pilot_area.biomass.base.all`, `pmw.v04.dynamics.200.pilot_area.conductivity.base.all`, `pmw.v04.dynamics.200.pilot_area.electric_field.base.all`, `pmw.v04.dynamics.200.pilot_area.light.base.all`, `pmw.v04.dynamics.200.pilot_area.mist.base.all`, `pmw.v04.dynamics.200.pilot_area.ore.base.all`, `pmw.v04.dynamics.200.pilot_area.smoke.base.all`, `pmw.v04.dynamics.200.pilot_area.stability.base.all`, `pmw.v04.dynamics.200.pilot_area.temperature.base.all`
- 反例：未装备或错误 Trigger 被拒绝，WorldState 原子不变（`action is not an exact currently equipped active skill`）。
- 已知限制：雷暴/潮湿区爆发；消耗公共导电场。；技能不会自动消费世界时间；runner 对两组推进相同 Tick。
- 证据：`skills/skill_001_conductive_reversal.json`；`evidence/skill_001.json`；`tests/test_pilot_60.py`

## skill_002 · 控燃术

- 身份：主动；Creator A；战斗与环境操纵
- 材料：`ember_spore`（fine / uncommon），词条 `ember_spore_craft`
- 触发与成本：`on_use`；Mana 2；Duration 1
- 创造意图：用充足生物量点燃目标，同时消耗生态存量并制造烟雾。烟雾可触发通用天气热反馈。
- 实际机制：damage -> target_actor (amount=5)；modify_field -> current_area (amount=-0.25, field_id=biomass)；modify_field -> current_area (amount=0.5, field_id=smoke)
- 测试场景：`wet_forest`；4 World Tick；变化步骤 [1, 2, 3, 4, 5]
- 实际观察：hero.mana: 45 -> 43；target.hp: 80 -> 75；field.biomass.value: 0.628803 -> 0.449705；field.smoke.value: 0.199115 -> 0.557311；field.temperature.value: 28.1399 -> 41.9716
- 触发 Law：`pmw.v04.action.controlled_burn.v1.ec15fffaf652.cost`, `pmw.v04.action.controlled_burn.v1.ec15fffaf652.effect.burn_target`, `pmw.v04.action.controlled_burn.v1.ec15fffaf652.effect.consume_growth`, `pmw.v04.action.controlled_burn.v1.ec15fffaf652.effect.raise_smoke`, `pmw.v04.dynamics.200.pilot_area.biomass.base.all`, `pmw.v04.dynamics.200.pilot_area.conductivity.base.all`, `pmw.v04.dynamics.200.pilot_area.electric_field.base.all`, `pmw.v04.dynamics.200.pilot_area.light.base.all`, `pmw.v04.dynamics.200.pilot_area.mist.base.all`, `pmw.v04.dynamics.200.pilot_area.ore.base.all`, `pmw.v04.dynamics.200.pilot_area.smoke.base.all`, `pmw.v04.dynamics.200.pilot_area.stability.base.all`
- 反例：未装备或错误 Trigger 被拒绝，WorldState 原子不变（`action is not an exact currently equipped active skill`）。
- 已知限制：伤害换生态退化和后续升温。；技能不会自动消费世界时间；runner 对两组推进相同 Tick。
- 证据：`skills/skill_002_controlled_burn.json`；`evidence/skill_002.json`；`tests/test_pilot_60.py`

## skill_003 · 闪霜抽湿

- 身份：主动；Creator A；战斗与环境操纵
- 材料：`rime_reed`（fine / uncommon），词条 `rime_reed_craft`
- 触发与成本：`on_use`；Mana 3；Duration 1
- 创造意图：只在湿地生效，把水分和热量一起抽走并造成小额伤害。
- 实际机制：damage -> target_actor (amount=4)；modify_field -> current_area (amount=-30, field_id=temperature)；modify_field -> current_area (amount=-0.2, field_id=wetness)
- 测试场景：`wet_forest`；3 World Tick；变化步骤 [1, 2, 3, 4]
- 实际观察：hero.mana: 45 -> 42；target.hp: 80 -> 76；field.temperature.value: 31.3957 -> 16.38；field.wetness.value: 0.718033 -> 0.562295；weather state differs; inspect the evidence timeline
- 触发 Law：`pmw.v04.action.flash_freeze.v1.a8c726c11402.cost`, `pmw.v04.action.flash_freeze.v1.a8c726c11402.effect.bind_water`, `pmw.v04.action.flash_freeze.v1.a8c726c11402.effect.freeze_area`, `pmw.v04.action.flash_freeze.v1.a8c726c11402.effect.rime_cut`, `pmw.v04.dynamics.200.pilot_area.biomass.base.all`, `pmw.v04.dynamics.200.pilot_area.conductivity.base.all`, `pmw.v04.dynamics.200.pilot_area.electric_field.base.all`, `pmw.v04.dynamics.200.pilot_area.light.base.all`, `pmw.v04.dynamics.200.pilot_area.mist.base.all`, `pmw.v04.dynamics.200.pilot_area.ore.base.all`, `pmw.v04.dynamics.200.pilot_area.smoke.base.all`, `pmw.v04.dynamics.200.pilot_area.stability.base.all`
- 反例：未装备或错误 Trigger 被拒绝，WorldState 原子不变（`action is not an exact currently equipped active skill`）。
- 已知限制：干燥区失败；可能破坏依赖湿度的后续构筑。；技能不会自动消费世界时间；runner 对两组推进相同 Tick。
- 证据：`skills/skill_003_flash_freeze.json`；`evidence/skill_003.json`；`tests/test_pilot_60.py`

## skill_004 · 热势倒转

- 身份：主动；Creator A；战斗与环境操纵
- 材料：`inverse_thermite`（epic / scarce），词条 `inverse_thermite_craft`
- 触发与成本：`on_use`；Mana 1；Duration 1
- 创造意图：短期把区域温度吸引子拉向严寒，但施法者承担逐 Tick 法力债。
- 实际机制：modify_attractor -> current_area (amount=10, field_id=temperature, duration=3)；apply_status -> self (status_id=thermal_debt)
- 测试场景：`dry_basin`；5 World Tick；变化步骤 [1, 2, 3, 4, 5, 6]
- 实际观察：hero.mana: 45 -> 38；field.temperature.value: 71.1997 -> 69.8124
- 触发 Law：`pmw.v04.action.thermal_inversion.v1.ed8d98e499fb.cost`, `pmw.v04.action.thermal_inversion.v1.ed8d98e499fb.effect.cold_attractor.slot_0.apply`, `pmw.v04.action.thermal_inversion.v1.ed8d98e499fb.effect.thermal_debt_self`, `pmw.v04.dynamics.200.pilot_area.biomass.base.all`, `pmw.v04.dynamics.200.pilot_area.conductivity.base.all`, `pmw.v04.dynamics.200.pilot_area.electric_field.base.all`, `pmw.v04.dynamics.200.pilot_area.light.base.all`, `pmw.v04.dynamics.200.pilot_area.mist.base.all`, `pmw.v04.dynamics.200.pilot_area.ore.base.all`, `pmw.v04.dynamics.200.pilot_area.smoke.base.all`, `pmw.v04.dynamics.200.pilot_area.stability.base.all`, `pmw.v04.dynamics.200.pilot_area.temperature.base.all`
- 反例：未装备或错误 Trigger 被拒绝，WorldState 原子不变（`action is not an exact currently equipped active skill`）。
- 已知限制：持续控场与明确个人机会成本。；技能不会自动消费世界时间；runner 对两组推进相同 Tick。
- 证据：`skills/skill_004_thermal_inversion.json`；`evidence/skill_004.json`；`tests/test_pilot_60.py`

## skill_005 · 灰幕

- 身份：主动；Creator A；战斗与环境操纵
- 材料：`hollow_charcoal`（fine / abundant），词条 `hollow_charcoal_craft`
- 触发与成本：`on_use`；Mana 2；Duration 1
- 创造意图：烟雾不是装饰：施法者获得临时护盾，同时把战场推进烟雾天气阈值。
- 实际机制：modify_field -> current_area (amount=0.35, field_id=smoke)；shield -> self (amount=6)
- 测试场景：`depleted_grove`；4 World Tick；变化步骤 [1, 2, 3, 4, 5]
- 实际观察：hero.mana: 45 -> 43；hero.shield: 0 -> 6；hero.shield_layers: [{"active": true, "granted": 6.0, "layer_id": "slot_0", "owner_id": "pilot_hero", "remaining": 6.0, "sequence": 1, "source_id": "ash_veil:veil_shield", "status_instance_id": null}]；field.biomass.value: 0.285393 -> 0.245393；field.smoke.value: 0.442689 -> 0.693426；field.temperature.value: 56.7948 -> 70.6265；weather state differs; inspect the evidence timeline
- 触发 Law：`pmw.v04.action.ash_veil.v1.38dd4b1b1b08.cost`, `pmw.v04.action.ash_veil.v1.38dd4b1b1b08.effect.veil_shield`, `pmw.v04.action.ash_veil.v1.38dd4b1b1b08.effect.veil_smoke`, `pmw.v04.dynamics.200.pilot_area.biomass.base.all`, `pmw.v04.dynamics.200.pilot_area.conductivity.base.all`, `pmw.v04.dynamics.200.pilot_area.electric_field.base.all`, `pmw.v04.dynamics.200.pilot_area.light.base.all`, `pmw.v04.dynamics.200.pilot_area.mist.base.all`, `pmw.v04.dynamics.200.pilot_area.ore.base.all`, `pmw.v04.dynamics.200.pilot_area.smoke.base.all`, `pmw.v04.dynamics.200.pilot_area.stability.base.all`, `pmw.v04.dynamics.200.pilot_area.temperature.base.all`
- 反例：未装备或错误 Trigger 被拒绝，WorldState 原子不变（`action is not an exact currently equipped active skill`）。
- 已知限制：眼前防御可能触发后续环境热化。；技能不会自动消费世界时间；runner 对两组推进相同 Tick。
- 证据：`skills/skill_005_ash_veil.json`；`evidence/skill_005.json`；`tests/test_pilot_60.py`

## skill_006 · 沼锁

- 身份：主动；Creator A；战斗与环境操纵
- 材料：`bog_iron`（rare / uncommon），词条 `bog_iron_craft`
- 触发与成本：`on_use`；Mana 2；Duration 1
- 创造意图：利用高湿区域令湿度恢复变慢，并给目标施加可被其他规则识别的 mire_bound 状态。
- 实际机制：modify_rate -> current_area (amount=-0.08, field_id=wetness, duration=3)；apply_status -> target_actor (status_id=mire_bound)
- 测试场景：`wet_forest`；4 World Tick；变化步骤 [1, 2, 3, 4, 5]
- 实际观察：hero.mana: 45 -> 43；target.statuses: [{"active": true, "clock_unit": "owner_turn", "expiry_handle": null, "granted_traits": ["mire_bound"], "instance_id": "cast_skill_006:bind_in_mire", "owner_id": "pilot_hero", "remaining": 2, "shield_layer_slot": null, "source_id": "bog_lock", "spec_hash": "ac5252108c150a9b679fb56c23dfe45d6003fb5de94bb878874c0843f4298b38", "spec_id": "mire_bound", "stacks": 1}]；field.wetness.value: 0.70059 -> 0.736992
- 触发 Law：`pmw.v04.action.bog_lock.v1.081bf87e7caf.cost`, `pmw.v04.action.bog_lock.v1.081bf87e7caf.effect.bind_in_mire`, `pmw.v04.action.bog_lock.v1.081bf87e7caf.effect.stagnate_wetland.slot_0.apply`, `pmw.v04.dynamics.200.pilot_area.biomass.base.all`, `pmw.v04.dynamics.200.pilot_area.conductivity.base.all`, `pmw.v04.dynamics.200.pilot_area.electric_field.base.all`, `pmw.v04.dynamics.200.pilot_area.light.base.all`, `pmw.v04.dynamics.200.pilot_area.mist.base.all`, `pmw.v04.dynamics.200.pilot_area.ore.base.all`, `pmw.v04.dynamics.200.pilot_area.smoke.base.all`, `pmw.v04.dynamics.200.pilot_area.stability.base.all`, `pmw.v04.dynamics.200.pilot_area.temperature.base.all`
- 反例：未装备或错误 Trigger 被拒绝，WorldState 原子不变（`action is not an exact currently equipped active skill`）。
- 已知限制：强环境依赖；离开湿地无效。；技能不会自动消费世界时间；runner 对两组推进相同 Tick。
- 证据：`skills/skill_006_bog_lock.json`；`evidence/skill_006.json`；`tests/test_pilot_60.py`

## skill_007 · 冷压泄放

- 身份：主动；Creator A；战斗与环境操纵
- 材料：`cryovent_glass`（rare / scarce），词条 `cryovent_glass_craft`
- 触发与成本：`on_use`；Mana 1；Duration 1
- 创造意图：仅在低温区把冷储备转成治疗，代价是显著升温并放出烟雾。
- 实际机制：heal -> self (amount=8)；modify_field -> current_area (amount=15, field_id=temperature)；modify_field -> current_area (amount=0.15, field_id=smoke)
- 测试场景：`mist_cavern`；3 World Tick；变化步骤 [1, 2, 3, 4]
- 实际观察：hero.hp: 62 -> 70；hero.mana: 45 -> 44；field.smoke.value: 0.25082 -> 0.367623；field.temperature.value: 20.7789 -> 34.0499
- 触发 Law：`pmw.v04.action.pressure_vent.v1.4aa755e3eb37.cost`, `pmw.v04.action.pressure_vent.v1.4aa755e3eb37.effect.dump_heat`, `pmw.v04.action.pressure_vent.v1.4aa755e3eb37.effect.vent_haze`, `pmw.v04.action.pressure_vent.v1.4aa755e3eb37.effect.vent_heal`, `pmw.v04.dynamics.200.pilot_area.biomass.base.all`, `pmw.v04.dynamics.200.pilot_area.conductivity.base.all`, `pmw.v04.dynamics.200.pilot_area.electric_field.base.all`, `pmw.v04.dynamics.200.pilot_area.light.base.all`, `pmw.v04.dynamics.200.pilot_area.mist.base.all`, `pmw.v04.dynamics.200.pilot_area.ore.base.all`, `pmw.v04.dynamics.200.pilot_area.smoke.base.all`, `pmw.v04.dynamics.200.pilot_area.stability.base.all`
- 反例：未装备或错误 Trigger 被拒绝，WorldState 原子不变（`action is not an exact currently equipped active skill`）。
- 已知限制：不能连续无脑治疗，使用会消耗自身成立条件。；技能不会自动消费世界时间；runner 对两组推进相同 Tick。
- 证据：`skills/skill_007_pressure_vent.json`；`evidence/skill_007.json`；`tests/test_pilot_60.py`

## skill_008 · 风暴蓄电

- 身份：被动；Creator A；战斗与环境操纵
- 材料：`storm_capacitor`（epic / scarce），词条 `storm_capacitor_craft`
- 触发与成本：`weather_changed`；Mana 0；Duration 1
- 创造意图：被动只监听真实 weather_changed，捕获高导电天气的能量并使环境接地。
- 实际机制：add_resource -> self (amount=2, resource=mana)；modify_field -> current_area (amount=-0.1, field_id=conductivity)
- 测试场景：`storm_plateau`；3 World Tick；变化步骤 [1, 2, 3, 4]
- 实际观察：hero.mana: 45 -> 47；field.conductivity.value: 0.70059 -> 0.622721
- 触发 Law：`pmw.v04.action.storm_battery.v1.58cbafae5af8.effect.capture_charge.hook`, `pmw.v04.action.storm_battery.v1.58cbafae5af8.effect.ground_storm`, `pmw.v04.dynamics.200.pilot_area.biomass.base.all`, `pmw.v04.dynamics.200.pilot_area.conductivity.base.all`, `pmw.v04.dynamics.200.pilot_area.electric_field.base.all`, `pmw.v04.dynamics.200.pilot_area.light.base.all`, `pmw.v04.dynamics.200.pilot_area.mist.base.all`, `pmw.v04.dynamics.200.pilot_area.ore.base.all`, `pmw.v04.dynamics.200.pilot_area.smoke.base.all`, `pmw.v04.dynamics.200.pilot_area.stability.base.all`, `pmw.v04.dynamics.200.pilot_area.temperature.base.all`, `pmw.v04.dynamics.200.pilot_area.toxin.base.all`
- 反例：未装备或错误 Trigger 被拒绝，WorldState 原子不变（`hook trigger mismatch`）。
- 已知限制：天气事件专用；触发会削弱下一次触发条件。；技能不会自动消费世界时间；runner 对两组推进相同 Tick。
- 证据：`skills/skill_008_storm_battery.json`；`evidence/skill_008.json`；`tests/test_pilot_60.py`

## skill_009 · 迟燃烙印

- 身份：主动；Creator A；战斗与环境操纵
- 材料：`slow_cinder`（rare / uncommon），词条 `slow_cinder_craft`
- 触发与成本：`on_use`；Mana 2；Duration 1
- 创造意图：把即时施法转为按战斗轮结算的持续生命损失，同时留下少量烟雾。
- 实际机制：apply_status -> target_actor (status_id=cinder_marked)；modify_field -> current_area (amount=0.1, field_id=smoke)
- 测试场景：`dry_basin`；3 World Tick；变化步骤 [1, 2, 3, 4]
- 实际观察：hero.mana: 45 -> 43；target.hp: 80 -> 74；field.smoke.value: 0.313115 -> 0.390984
- 触发 Law：`pmw.v04.action.cinder_mark.v1.b45826c1ed13.cost`, `pmw.v04.action.cinder_mark.v1.b45826c1ed13.effect.brand_target`, `pmw.v04.action.cinder_mark.v1.b45826c1ed13.effect.seed_haze`, `pmw.v04.dynamics.200.pilot_area.biomass.base.all`, `pmw.v04.dynamics.200.pilot_area.conductivity.base.all`, `pmw.v04.dynamics.200.pilot_area.electric_field.base.all`, `pmw.v04.dynamics.200.pilot_area.light.base.all`, `pmw.v04.dynamics.200.pilot_area.mist.base.all`, `pmw.v04.dynamics.200.pilot_area.ore.base.all`, `pmw.v04.dynamics.200.pilot_area.smoke.base.all`, `pmw.v04.dynamics.200.pilot_area.stability.base.all`, `pmw.v04.dynamics.200.pilot_area.temperature.base.all`
- 反例：未装备或错误 Trigger 被拒绝，WorldState 原子不变（`action is not an exact currently equipped active skill`）。
- 已知限制：需要战斗轮推进；状态堆叠仍受上限约束。；技能不会自动消费世界时间；runner 对两组推进相同 Tick。
- 证据：`skills/skill_009_cinder_mark.json`；`evidence/skill_009.json`；`tests/test_pilot_60.py`

## skill_010 · 裂雨锋

- 身份：主动；Creator A；战斗与环境操纵
- 材料：`saltwind_seed`（rare / scarce），词条 `saltwind_seed_craft`
- 触发与成本：`on_use`；Mana 3；Duration 1
- 创造意图：临时把湿度吸引子拉向干燥，同时降低生物量恢复率，制造跨系统干旱窗口。
- 实际机制：modify_attractor -> current_area (amount=0.1, field_id=wetness, duration=4)；modify_rate -> current_area (amount=-0.04, field_id=biomass, duration=4)
- 测试场景：`wet_forest`；5 World Tick；变化步骤 [1, 2, 3, 4, 5, 6]
- 实际观察：hero.mana: 45 -> 42；field.biomass.value: 0.622499 -> 0.632372；field.wetness.value: 0.684543 -> 0.647079
- 触发 Law：`pmw.v04.action.rain_shear.v1.19532bbc7eb2.cost`, `pmw.v04.action.rain_shear.v1.19532bbc7eb2.effect.drying_front.slot_0.apply`, `pmw.v04.action.rain_shear.v1.19532bbc7eb2.effect.growth_drag.slot_0.apply`, `pmw.v04.dynamics.200.pilot_area.biomass.base.all`, `pmw.v04.dynamics.200.pilot_area.conductivity.base.all`, `pmw.v04.dynamics.200.pilot_area.electric_field.base.all`, `pmw.v04.dynamics.200.pilot_area.light.base.all`, `pmw.v04.dynamics.200.pilot_area.mist.base.all`, `pmw.v04.dynamics.200.pilot_area.ore.base.all`, `pmw.v04.dynamics.200.pilot_area.smoke.base.all`, `pmw.v04.dynamics.200.pilot_area.stability.base.all`, `pmw.v04.dynamics.200.pilot_area.temperature.base.all`
- 反例：未装备或错误 Trigger 被拒绝，WorldState 原子不变（`action is not an exact currently equipped active skill`）。
- 已知限制：无即时伤害；数 Tick 后才显现生态代价。；技能不会自动消费世界时间；runner 对两组推进相同 Tick。
- 证据：`skills/skill_010_rain_shear.json`；`evidence/skill_010.json`；`tests/test_pilot_60.py`

## skill_011 · 血契抵押

- 身份：主动；Creator B；防御状态与反制
- 材料：`sanguine_iron`（rare / scarce），词条 `sanguine_iron_authority`
- 触发与成本：`on_use`；Mana 10；Duration 1
- 创造意图：抵押 10 Mana 换取两次自身回合前有效的 18 点临时盾；错误时机将耗尽施法余量，盾到期会严格清理。
- 实际机制：shield -> self (amount=18)；apply_status -> self (status_id=blood_guarded)
- 测试场景：`wet_forest`；2 World Tick；变化步骤 [1, 2, 3, 4, 5]
- 实际观察：hero.mana: 45 -> 35
- 触发 Law：`pmw.v04.action.blood_mortgage.v1.a3639a5868a3.cost`, `pmw.v04.action.blood_mortgage.v1.a3639a5868a3.effect.borrowed_guard`, `pmw.v04.action.blood_mortgage.v1.a3639a5868a3.effect.guard_clock`, `pmw.v04.dynamics.200.pilot_area.biomass.base.all`, `pmw.v04.dynamics.200.pilot_area.conductivity.base.all`, `pmw.v04.dynamics.200.pilot_area.electric_field.base.all`, `pmw.v04.dynamics.200.pilot_area.light.base.all`, `pmw.v04.dynamics.200.pilot_area.mist.base.all`, `pmw.v04.dynamics.200.pilot_area.ore.base.all`, `pmw.v04.dynamics.200.pilot_area.smoke.base.all`, `pmw.v04.dynamics.200.pilot_area.stability.base.all`, `pmw.v04.dynamics.200.pilot_area.temperature.base.all`
- 反例：未装备或错误 Trigger 被拒绝，WorldState 原子不变（`action is not an exact currently equipped active skill`）。
- 已知限制：数值仍属于 Pilot 人工约束，未做全局平衡。
- 证据：`skills/skill_011_blood_mortgage.json`；`evidence/skill_011.json`；`tests/test_pilot_60.py`

## skill_012 · 迟付红利

- 身份：主动；Creator B；防御状态与反制
- 材料：`hourglass_resin`（rare / scarce），词条 `hourglass_resin_authority`
- 触发与成本：`on_use`；Mana 1；Duration 1
- 创造意图：三次世界 Tick 各失去 4 HP，完整撑过后才把 Mana 设置为 40；高 Mana 时可能亏损，提前取消也会按正式取消语义结算。
- 实际机制：apply_status -> self (status_id=deferred_burden)
- 测试场景：`dry_basin`；3 World Tick；变化步骤 [1, 2, 3, 4]
- 实际观察：hero.hp: 80 -> 68；hero.mana: 45 -> 40
- 触发 Law：`pmw.v04.action.deferred_dividend.v1.08ce0b663efa.cost`, `pmw.v04.action.deferred_dividend.v1.08ce0b663efa.effect.accept_burden`, `pmw.v04.dynamics.200.pilot_area.biomass.base.all`, `pmw.v04.dynamics.200.pilot_area.conductivity.base.all`, `pmw.v04.dynamics.200.pilot_area.electric_field.base.all`, `pmw.v04.dynamics.200.pilot_area.light.base.all`, `pmw.v04.dynamics.200.pilot_area.mist.base.all`, `pmw.v04.dynamics.200.pilot_area.ore.base.all`, `pmw.v04.dynamics.200.pilot_area.smoke.base.all`, `pmw.v04.dynamics.200.pilot_area.stability.base.all`, `pmw.v04.dynamics.200.pilot_area.temperature.base.all`, `pmw.v04.dynamics.200.pilot_area.toxin.base.all`
- 反例：未装备或错误 Trigger 被拒绝，WorldState 原子不变（`action is not an exact currently equipped active skill`）。
- 已知限制：数值仍属于 Pilot 人工约束，未做全局平衡。
- 证据：`skills/skill_012_deferred_dividend.json`；`evidence/skill_012.json`；`tests/test_pilot_60.py`

## skill_013 · 空盾回响

- 身份：被动；Creator B；防御状态与反制
- 材料：`hollow_scale`（rare / scarce），词条 `hollow_scale_authority`
- 触发与成本：`damage_resolved`；Mana 0；Duration 1
- 创造意图：伤害结算后若盾已耗尽，生成一层 6 点持续到被击碎的护盾；不是自动减伤，且每根事件因果链仅触发一次。
- 实际机制：shield -> self (amount=6)
- 测试场景：`wet_forest`；2 World Tick；变化步骤 [1, 2, 3]
- 实际观察：hero.shield: 0 -> 6；hero.shield_layers: [{"active": true, "granted": 6.0, "layer_id": "slot_0", "owner_id": "pilot_hero", "remaining": 6.0, "sequence": 1, "source_id": "empty_aegis:emergency_layer", "status_instance_id": null}]
- 触发 Law：`pmw.v04.action.basic_attack.v1.ac7edec9eac8.cost`, `pmw.v04.action.basic_attack.v1.ac7edec9eac8.effect.strike`, `pmw.v04.action.empty_aegis.v1.18efe1cf1570.effect.emergency_layer`, `pmw.v04.dynamics.200.pilot_area.biomass.base.all`, `pmw.v04.dynamics.200.pilot_area.conductivity.base.all`, `pmw.v04.dynamics.200.pilot_area.electric_field.base.all`, `pmw.v04.dynamics.200.pilot_area.light.base.all`, `pmw.v04.dynamics.200.pilot_area.mist.base.all`, `pmw.v04.dynamics.200.pilot_area.ore.base.all`, `pmw.v04.dynamics.200.pilot_area.smoke.base.all`, `pmw.v04.dynamics.200.pilot_area.stability.base.all`, `pmw.v04.dynamics.200.pilot_area.temperature.base.all`
- 反例：未装备或错误 Trigger 被拒绝，WorldState 原子不变（`hook trigger mismatch`）。
- 已知限制：数值仍属于 Pilot 人工约束，未做全局平衡。；当前没有统一自动 Hook dispatcher；runner 在真实触发动作后调用受支持 execute_hook。
- 证据：`skills/skill_013_empty_aegis.json`；`evidence/skill_013.json`；`tests/test_pilot_60.py`

## skill_014 · 荆棘盟约

- 身份：被动；Creator B；防御状态与反制
- 材料：`widow_thorn`（rare / scarce），词条 `widow_thorn_authority`
- 触发与成本：`damage_resolved`；Mana 0；Duration 1
- 创造意图：低血量受击后反伤 7 并自伤 3；能抢节奏，也可能在临界生命时把自己推向死亡。
- 实际机制：damage -> target_actor (amount=7)；damage -> self (amount=3)
- 测试场景：`dry_basin`；2 World Tick；变化步骤 [1, 2, 3]
- 实际观察：hero.hp: 28 -> 25；target.hp: 80 -> 73
- 触发 Law：`pmw.v04.action.basic_attack.v1.ac7edec9eac8.cost`, `pmw.v04.action.basic_attack.v1.ac7edec9eac8.effect.strike`, `pmw.v04.action.thorn_covenant.v1.c55561086110.effect.reprisal`, `pmw.v04.action.thorn_covenant.v1.c55561086110.effect.thorn_tithe`, `pmw.v04.dynamics.200.pilot_area.biomass.base.all`, `pmw.v04.dynamics.200.pilot_area.conductivity.base.all`, `pmw.v04.dynamics.200.pilot_area.electric_field.base.all`, `pmw.v04.dynamics.200.pilot_area.light.base.all`, `pmw.v04.dynamics.200.pilot_area.mist.base.all`, `pmw.v04.dynamics.200.pilot_area.ore.base.all`, `pmw.v04.dynamics.200.pilot_area.smoke.base.all`, `pmw.v04.dynamics.200.pilot_area.stability.base.all`
- 反例：未装备或错误 Trigger 被拒绝，WorldState 原子不变（`hook trigger mismatch`）。
- 已知限制：数值仍属于 Pilot 人工约束，未做全局平衡。；当前没有统一自动 Hook dispatcher；runner 在真实触发动作后调用受支持 execute_hook。
- 证据：`skills/skill_014_thorn_covenant.json`；`evidence/skill_014.json`；`tests/test_pilot_60.py`

## skill_015 · 守势回声

- 身份：被动；Creator B；防御状态与反制
- 材料：`resonant_buckle`（fine / scarce），词条 `resonant_buckle_authority`
- 触发与成本：`status_changed`；Mana 0；Duration 1
- 创造意图：基础格挡状态改变且仍处于 guarding 时返还 3 Mana；无关状态事件不应触发。
- 实际机制：add_resource -> self (amount=3, resource=mana)
- 测试场景：`wet_forest`；2 World Tick；变化步骤 [1, 2, 3]
- 实际观察：hero.mana: 45 -> 48
- 触发 Law：`pmw.v04.action.basic_guard.v1.dc25094f1b1a.cost`, `pmw.v04.action.basic_guard.v1.dc25094f1b1a.effect.guard_duration`, `pmw.v04.action.basic_guard.v1.dc25094f1b1a.effect.guard_shield`, `pmw.v04.action.guard_echo.v1.adcf14878bd7.effect.recover_focus.hook`, `pmw.v04.dynamics.200.pilot_area.biomass.base.all`, `pmw.v04.dynamics.200.pilot_area.conductivity.base.all`, `pmw.v04.dynamics.200.pilot_area.electric_field.base.all`, `pmw.v04.dynamics.200.pilot_area.light.base.all`, `pmw.v04.dynamics.200.pilot_area.mist.base.all`, `pmw.v04.dynamics.200.pilot_area.ore.base.all`, `pmw.v04.dynamics.200.pilot_area.smoke.base.all`, `pmw.v04.dynamics.200.pilot_area.stability.base.all`
- 反例：未装备或错误 Trigger 被拒绝，WorldState 原子不变（`hook trigger mismatch`）。
- 已知限制：数值仍属于 Pilot 人工约束，未做全局平衡。；当前没有统一自动 Hook dispatcher；runner 在真实触发动作后调用受支持 execute_hook。
- 证据：`skills/skill_015_guard_echo.json`；`evidence/skill_015.json`；`tests/test_pilot_60.py`

## skill_016 · 末路豪赌

- 身份：主动；Creator B；防御状态与反制
- 材料：`redline_core`（rare / scarce），词条 `redline_core_authority`
- 触发与成本：`on_use`；Mana 4；Duration 1
- 创造意图：仅在 HP 不高于 30 时可用：高伤与自伤同时结算。门槛不满足时整个动作原子拒绝。
- 实际机制：damage -> target_actor (amount=18)；damage -> self (amount=6)
- 测试场景：`dry_basin`；2 World Tick；变化步骤 [1, 2, 3]
- 实际观察：hero.hp: 28 -> 22；hero.mana: 45 -> 41；target.hp: 80 -> 62
- 触发 Law：`pmw.v04.action.last_stand_gambit.v1.2ae729fb18ae.cost`, `pmw.v04.action.last_stand_gambit.v1.2ae729fb18ae.effect.all_in`, `pmw.v04.action.last_stand_gambit.v1.2ae729fb18ae.effect.recoil`, `pmw.v04.dynamics.200.pilot_area.biomass.base.all`, `pmw.v04.dynamics.200.pilot_area.conductivity.base.all`, `pmw.v04.dynamics.200.pilot_area.electric_field.base.all`, `pmw.v04.dynamics.200.pilot_area.light.base.all`, `pmw.v04.dynamics.200.pilot_area.mist.base.all`, `pmw.v04.dynamics.200.pilot_area.ore.base.all`, `pmw.v04.dynamics.200.pilot_area.smoke.base.all`, `pmw.v04.dynamics.200.pilot_area.stability.base.all`, `pmw.v04.dynamics.200.pilot_area.temperature.base.all`
- 反例：未装备或错误 Trigger 被拒绝，WorldState 原子不变（`action is not an exact currently equipped active skill`）。
- 已知限制：数值仍属于 Pilot 人工约束，未做全局平衡。
- 证据：`skills/skill_016_last_stand_gambit.json`；`evidence/skill_016.json`；`tests/test_pilot_60.py`

## skill_017 · 雾锁壁垒

- 身份：主动；Creator B；防御状态与反制
- 材料：`clouded_glass`（rare / scarce），词条 `clouded_glass_authority`
- 触发与成本：`on_use`；Mana 3；Duration 1
- 创造意图：获得一回合临时盾，同时增浓全场迷雾；防御收益私有，但环境变化对双方公开且可能帮助敌人。
- 实际机制：shield -> self (amount=10)；apply_status -> self (status_id=fogbound_guarded)；modify_field -> current_area (amount=0.35, field_id=mist)
- 测试场景：`mist_cavern`；3 World Tick；变化步骤 [1, 2, 3, 4, 5]
- 实际观察：hero.mana: 45 -> 42；field.mist.value: 0.74918 -> 0.889344
- 触发 Law：`pmw.v04.action.fogbound_bastion.v1.90ef24986987.cost`, `pmw.v04.action.fogbound_bastion.v1.90ef24986987.effect.blind_field`, `pmw.v04.action.fogbound_bastion.v1.90ef24986987.effect.mist_clock`, `pmw.v04.action.fogbound_bastion.v1.90ef24986987.effect.mist_layer`, `pmw.v04.dynamics.200.pilot_area.biomass.base.all`, `pmw.v04.dynamics.200.pilot_area.conductivity.base.all`, `pmw.v04.dynamics.200.pilot_area.electric_field.base.all`, `pmw.v04.dynamics.200.pilot_area.light.base.all`, `pmw.v04.dynamics.200.pilot_area.mist.base.all`, `pmw.v04.dynamics.200.pilot_area.ore.base.all`, `pmw.v04.dynamics.200.pilot_area.smoke.base.all`, `pmw.v04.dynamics.200.pilot_area.stability.base.all`
- 反例：未装备或错误 Trigger 被拒绝，WorldState 原子不变（`action is not an exact currently equipped active skill`）。
- 已知限制：数值仍属于 Pilot 人工约束，未做全局平衡。
- 证据：`skills/skill_017_fogbound_bastion.json`；`evidence/skill_017.json`；`tests/test_pilot_60.py`

## skill_018 · 生命转输

- 身份：主动；Creator B；防御状态与反制
- 材料：`mercy_needle`（rare / scarce），词条 `mercy_needle_authority`
- 触发与成本：`on_use`；Mana 2；Duration 1
- 创造意图：用自身 12 HP 为目标恢复 15 HP；目标已满血时仍会支付自伤，形成真实误用风险。
- 实际机制：damage -> self (amount=12)；heal -> target_actor (amount=15)
- 测试场景：`wet_forest`；2 World Tick；变化步骤 [1, 2, 3]
- 实际观察：hero.hp: 70 -> 58；hero.mana: 45 -> 43；target.hp: 55 -> 70
- 触发 Law：`pmw.v04.action.life_transfusion.v1.44845437ea14.cost`, `pmw.v04.action.life_transfusion.v1.44845437ea14.effect.donor_wound`, `pmw.v04.action.life_transfusion.v1.44845437ea14.effect.recipient_heal`, `pmw.v04.dynamics.200.pilot_area.biomass.base.all`, `pmw.v04.dynamics.200.pilot_area.conductivity.base.all`, `pmw.v04.dynamics.200.pilot_area.electric_field.base.all`, `pmw.v04.dynamics.200.pilot_area.light.base.all`, `pmw.v04.dynamics.200.pilot_area.mist.base.all`, `pmw.v04.dynamics.200.pilot_area.ore.base.all`, `pmw.v04.dynamics.200.pilot_area.smoke.base.all`, `pmw.v04.dynamics.200.pilot_area.stability.base.all`, `pmw.v04.dynamics.200.pilot_area.temperature.base.all`
- 反例：未装备或错误 Trigger 被拒绝，WorldState 原子不变（`action is not an exact currently equipped active skill`）。
- 已知限制：数值仍属于 Pilot 人工约束，未做全局平衡。
- 证据：`skills/skill_018_life_transfusion.json`；`evidence/skill_018.json`；`tests/test_pilot_60.py`

## skill_019 · 破盾印记

- 身份：主动；Creator B；防御状态与反制
- 材料：`fault_salt`（rare / scarce），词条 `fault_salt_authority`
- 触发与成本：`on_use`；Mana 2；Duration 1
- 创造意图：只对当前有盾目标合法：先削盾并留下两回合 brittle_guard Trait，供其他显式条件技能组合使用。
- 实际机制：damage -> target_actor (amount=4)；apply_status -> target_actor (status_id=fractured_guard)
- 测试场景：`storm_plateau`；2 World Tick；变化步骤 [1, 2, 3]
- 实际观察：hero.mana: 45 -> 43；target.shield: 7 -> 3；target.statuses: [{"active": true, "clock_unit": "owner_turn", "expiry_handle": null, "granted_traits": ["guarding"], "instance_id": "setup_skill_019_0:guard_duration", "owner_id": "pilot_target", "remaining": 1, "shield_layer_slot": "slot_0", "source_id": "basic_guard", "spec_hash": "26a09807646c1d29a56b7eedccc244b0cbfa58bb3a2524748bbae4df0bc7e58b", "spec_id": "basic_guarding", "stacks": 1}, {"active": true, "clock_unit": "owner_turn", "expiry_handle": null, "granted_traits": ["brittle_guard"], "instance_id": "cast_skill_019:leave_fault", "owner_id": "pilot_hero", "remaining": 2, "shield_layer_slot": null, "source_id": "breaker_mark", "spec_hash": "e676dc1090d00553e2cad22532f9868e042b4dad6e7f5864b349b43e3ed51fb5", "spec_id": "fractured_guard", "stacks": 1}]；target.shield_layers: [{"active": true, "granted": 7.0, "layer_id": "slot_0", "owner_id": "pilot_target", "remaining": 3.0, "sequence": 1, "source_id": "basic_guard:guard_shield", "status_instance_id": "setup_skill_019_0:guard_duration"}]
- 触发 Law：`pmw.v04.action.basic_guard.v1.dc25094f1b1a.cost`, `pmw.v04.action.basic_guard.v1.dc25094f1b1a.effect.guard_duration`, `pmw.v04.action.basic_guard.v1.dc25094f1b1a.effect.guard_shield`, `pmw.v04.action.breaker_mark.v1.1a30782aaf01.cost`, `pmw.v04.action.breaker_mark.v1.1a30782aaf01.effect.chip_guard`, `pmw.v04.action.breaker_mark.v1.1a30782aaf01.effect.leave_fault`, `pmw.v04.dynamics.200.pilot_area.biomass.base.all`, `pmw.v04.dynamics.200.pilot_area.conductivity.base.all`, `pmw.v04.dynamics.200.pilot_area.electric_field.base.all`, `pmw.v04.dynamics.200.pilot_area.light.base.all`, `pmw.v04.dynamics.200.pilot_area.mist.base.all`, `pmw.v04.dynamics.200.pilot_area.ore.base.all`
- 反例：未装备或错误 Trigger 被拒绝，WorldState 原子不变（`action is not an exact currently equipped active skill`）。
- 已知限制：数值仍属于 Pilot 人工约束，未做全局平衡。
- 证据：`skills/skill_019_breaker_mark.json`；`evidence/skill_019.json`；`tests/test_pilot_60.py`

## skill_020 · 逆转储备

- 身份：主动；Creator B；防御状态与反制
- 材料：`inversion_plate`（rare / scarce），词条 `inversion_plate_authority`
- 触发与成本：`on_use`；Mana 8；Duration 1
- 创造意图：以高 Mana 门槛与成本换取短暂自保并治疗队友；技能结束时自盾清零，队友治疗保留。
- 实际机制：shield -> self (amount=14)；apply_status -> self (status_id=reversal_guarded)；heal -> target_actor (amount=6)
- 测试场景：`depleted_grove`；2 World Tick；变化步骤 [1, 2, 3, 4]
- 实际观察：hero.mana: 45 -> 37；target.hp: 60 -> 66
- 触发 Law：`pmw.v04.action.reversal_reserve.v1.0d4c6caaadb0.cost`, `pmw.v04.action.reversal_reserve.v1.0d4c6caaadb0.effect.ally_relief`, `pmw.v04.action.reversal_reserve.v1.0d4c6caaadb0.effect.reserve_clock`, `pmw.v04.action.reversal_reserve.v1.0d4c6caaadb0.effect.reserve_layer`, `pmw.v04.dynamics.200.pilot_area.biomass.base.all`, `pmw.v04.dynamics.200.pilot_area.conductivity.base.all`, `pmw.v04.dynamics.200.pilot_area.electric_field.base.all`, `pmw.v04.dynamics.200.pilot_area.light.base.all`, `pmw.v04.dynamics.200.pilot_area.mist.base.all`, `pmw.v04.dynamics.200.pilot_area.ore.base.all`, `pmw.v04.dynamics.200.pilot_area.smoke.base.all`, `pmw.v04.dynamics.200.pilot_area.stability.base.all`
- 反例：未装备或错误 Trigger 被拒绝，WorldState 原子不变（`action is not an exact currently equipped active skill`）。
- 已知限制：数值仍属于 Pilot 人工约束，未做全局平衡。
- 证据：`skills/skill_020_reversal_reserve.json`；`evidence/skill_020.json`；`tests/test_pilot_60.py`

## skill_021 · 露种

- 身份：主动；Creator C；天气生态与世界演化
- 材料：`mat_dew_seed`（rare / uncommon），词条 `trait_dew_seed`
- 触发与成本：`on_use`；Mana 2；Duration 1
- 创造意图：把湿度的临时吸引子抬高；在恢复快的区域可跨过降雨阈值，在迟钝干地只留下短暂回潮。
- 实际机制：modify_attractor -> current_area (amount=0.9, field_id=wetness, duration=4)
- 测试场景：`rain_edge`；6 World Tick；变化步骤 [1, 2, 3, 4, 5, 6, 7]
- 实际观察：hero.mana: 45 -> 43；field.wetness.value: 0.58489 -> 0.619356
- 触发 Law：`pmw.v04.action.dew_seed.v1.ac8b14d0b9e2.cost`, `pmw.v04.action.dew_seed.v1.ac8b14d0b9e2.effect.effect_dew_seed.slot_0.apply`, `pmw.v04.dynamics.200.pilot_area.biomass.base.all`, `pmw.v04.dynamics.200.pilot_area.conductivity.base.all`, `pmw.v04.dynamics.200.pilot_area.electric_field.base.all`, `pmw.v04.dynamics.200.pilot_area.light.base.all`, `pmw.v04.dynamics.200.pilot_area.mist.base.all`, `pmw.v04.dynamics.200.pilot_area.ore.base.all`, `pmw.v04.dynamics.200.pilot_area.smoke.base.all`, `pmw.v04.dynamics.200.pilot_area.stability.base.all`, `pmw.v04.dynamics.200.pilot_area.temperature.base.all`, `pmw.v04.dynamics.200.pilot_area.toxin.base.all`
- 反例：未装备或错误 Trigger 被拒绝，WorldState 原子不变（`action is not an exact currently equipped active skill`）。
- 已知限制：低恢复率干地在修正到期前不能跨过降雨阈值。；modify_attractor 使用绝对临时 target；modify_rate 使用 additive rate。
- 证据：`skills/skill_021_dew_seed.json`；`evidence/skill_021.json`；`tests/test_pilot_60.py`

## skill_022 · 雨脚刹

- 身份：主动；Creator C；天气生态与世界演化
- 材料：`mat_rain_brake`（fine / abundant），词条 `trait_rain_brake`
- 触发与成本：`on_use`；Mana 2；Duration 1
- 创造意图：减慢风暴电荷向基线恢复；它不清除风暴，只为采集或撤离争取数个 Tick。
- 实际机制：modify_rate -> current_area (amount=-0.09, field_id=electric_field, duration=5)
- 测试场景：`storm_plateau`；5 World Tick；变化步骤 [1, 2, 3, 4, 5, 6]
- 实际观察：hero.mana: 45 -> 43；field.electric_field.value: 0.644998 -> 0.7024
- 触发 Law：`pmw.v04.action.rain_brake.v1.1136cd89dd6f.cost`, `pmw.v04.action.rain_brake.v1.1136cd89dd6f.effect.effect_rain_brake.slot_0.apply`, `pmw.v04.dynamics.200.pilot_area.biomass.base.all`, `pmw.v04.dynamics.200.pilot_area.conductivity.base.all`, `pmw.v04.dynamics.200.pilot_area.electric_field.base.all`, `pmw.v04.dynamics.200.pilot_area.light.base.all`, `pmw.v04.dynamics.200.pilot_area.mist.base.all`, `pmw.v04.dynamics.200.pilot_area.ore.base.all`, `pmw.v04.dynamics.200.pilot_area.smoke.base.all`, `pmw.v04.dynamics.200.pilot_area.stability.base.all`, `pmw.v04.dynamics.200.pilot_area.temperature.base.all`, `pmw.v04.dynamics.200.pilot_area.toxin.base.all`
- 反例：未装备或错误 Trigger 被拒绝，WorldState 原子不变（`action is not an exact currently equipped active skill`）。
- 已知限制：已经越过阈值的风暴不会被负 rate 立即清除。；modify_attractor 使用绝对临时 target；modify_rate 使用 additive rate。
- 证据：`skills/skill_022_rain_brake.json`；`evidence/skill_022.json`；`tests/test_pilot_60.py`

## skill_023 · 演替火花

- 身份：主动；Creator C；天气生态与世界演化
- 材料：`mat_succession_spark`（rare / scarce），词条 `trait_succession_spark`
- 触发与成本：`on_use`；Mana 2；Duration 1
- 创造意图：一次性推进生态演替指标；只有持续越过通用生态阈值时才会真正换挡。
- 实际机制：modify_field -> current_area (amount=0.3, field_id=biomass)
- 测试场景：`wet_forest`；4 World Tick；变化步骤 [1, 2, 3, 4, 5]
- 实际观察：hero.mana: 45 -> 43；field.biomass.value: 0.628803 -> 0.843721；field.toxin.value: 0.227771 -> 0.0505163；weather state differs; inspect the evidence timeline
- 触发 Law：`pmw.v04.action.succession_spark.v1.8aec163c8d41.cost`, `pmw.v04.action.succession_spark.v1.8aec163c8d41.effect.effect_succession_spark`, `pmw.v04.dynamics.200.pilot_area.biomass.base.all`, `pmw.v04.dynamics.200.pilot_area.conductivity.base.all`, `pmw.v04.dynamics.200.pilot_area.electric_field.base.all`, `pmw.v04.dynamics.200.pilot_area.light.base.all`, `pmw.v04.dynamics.200.pilot_area.mist.base.all`, `pmw.v04.dynamics.200.pilot_area.ore.base.all`, `pmw.v04.dynamics.200.pilot_area.smoke.base.all`, `pmw.v04.dynamics.200.pilot_area.stability.base.all`, `pmw.v04.dynamics.200.pilot_area.temperature.base.all`, `pmw.v04.dynamics.200.pilot_area.toxin.base.all`
- 反例：未装备或错误 Trigger 被拒绝，WorldState 原子不变（`action is not an exact currently equipped active skill`）。
- 已知限制：阈值只维持一个 Tick 时生态计数器会复位。；modify_attractor 使用绝对临时 target；modify_rate 使用 additive rate。
- 证据：`skills/skill_023_succession_spark.json`；`evidence/skill_023.json`；`tests/test_pilot_60.py`

## skill_024 · 旱相诱导

- 身份：主动；Creator C；天气生态与世界演化
- 材料：`mat_drought_lure`（rare / uncommon），词条 `trait_drought_lure`
- 触发与成本：`on_use`；Mana 2；Duration 1
- 创造意图：临时把湿度拉向零，可让降雨提前退出，但也会损害依赖湿润环境的资源恢复。
- 实际机制：modify_attractor -> current_area (amount=0.0, field_id=wetness, duration=4)
- 测试场景：`wet_forest`；6 World Tick；变化步骤 [1, 2, 3, 4, 5, 6, 7]
- 实际观察：hero.mana: 45 -> 43；field.temperature.value: 25.8537 -> 29.8537；field.wetness.value: 0.669779 -> 0.626696；weather state differs; inspect the evidence timeline
- 触发 Law：`pmw.v04.action.drought_lure.v1.be8e48b0881e.cost`, `pmw.v04.action.drought_lure.v1.be8e48b0881e.effect.effect_drought_lure.slot_0.apply`, `pmw.v04.dynamics.200.pilot_area.biomass.base.all`, `pmw.v04.dynamics.200.pilot_area.conductivity.base.all`, `pmw.v04.dynamics.200.pilot_area.electric_field.base.all`, `pmw.v04.dynamics.200.pilot_area.light.base.all`, `pmw.v04.dynamics.200.pilot_area.mist.base.all`, `pmw.v04.dynamics.200.pilot_area.ore.base.all`, `pmw.v04.dynamics.200.pilot_area.smoke.base.all`, `pmw.v04.dynamics.200.pilot_area.stability.base.all`, `pmw.v04.dynamics.200.pilot_area.temperature.base.all`, `pmw.v04.dynamics.200.pilot_area.toxin.base.all`
- 反例：未装备或错误 Trigger 被拒绝，WorldState 原子不变（`action is not an exact currently equipped active skill`）。
- 已知限制：低热惯性湿地可能在修正到期后迅速回湿。；modify_attractor 使用绝对临时 target；modify_rate 使用 additive rate。
- 证据：`skills/skill_024_drought_lure.json`；`evidence/skill_024.json`；`tests/test_pilot_60.py`

## skill_025 · 热逆层

- 身份：主动；Creator C；天气生态与世界演化
- 材料：`mat_thermal_inversion`（rare / scarce），词条 `trait_thermal_inversion`
- 触发与成本：`on_use`；Mana 2；Duration 1
- 创造意图：让温度朝低位吸引子演化；价值取决于区域热惯性，而非立即固定降温。
- 实际机制：modify_attractor -> current_area (amount=20.0, field_id=temperature, duration=5)
- 测试场景：`dry_basin`；5 World Tick；变化步骤 [1, 2, 3, 4, 5, 6]
- 实际观察：hero.mana: 45 -> 43；field.temperature.value: 71.1997 -> 69.0303
- 触发 Law：`pmw.v04.action.thermal_sink.v1.acbe1cdd9597.cost`, `pmw.v04.action.thermal_sink.v1.acbe1cdd9597.effect.effect_thermal_inversion.slot_0.apply`, `pmw.v04.dynamics.200.pilot_area.biomass.base.all`, `pmw.v04.dynamics.200.pilot_area.conductivity.base.all`, `pmw.v04.dynamics.200.pilot_area.electric_field.base.all`, `pmw.v04.dynamics.200.pilot_area.light.base.all`, `pmw.v04.dynamics.200.pilot_area.mist.base.all`, `pmw.v04.dynamics.200.pilot_area.ore.base.all`, `pmw.v04.dynamics.200.pilot_area.smoke.base.all`, `pmw.v04.dynamics.200.pilot_area.stability.base.all`, `pmw.v04.dynamics.200.pilot_area.temperature.base.all`, `pmw.v04.dynamics.200.pilot_area.toxin.base.all`
- 反例：未装备或错误 Trigger 被拒绝，WorldState 原子不变（`action is not an exact currently equipped active skill`）。
- 已知限制：基础 rate 很低时临时吸引子未必来得及产生显著降温。；modify_attractor 使用绝对临时 target；modify_rate 使用 additive rate。
- 证据：`skills/skill_025_thermal_sink.json`；`evidence/skill_025.json`；`tests/test_pilot_60.py`

## skill_026 · 雾库开闸

- 身份：主动；Creator C；天气生态与世界演化
- 材料：`mat_fog_bank`（fine / uncommon），词条 `trait_fog_bank`
- 触发与成本：`on_use`；Mana 2；Duration 1
- 创造意图：在湿度至少 0.5 时把水汽转为雾；干燥环境中 required 条件会原子拒绝。
- 实际机制：modify_field -> current_area (amount=0.25, field_id=mist)
- 测试场景：`wet_forest`；4 World Tick；变化步骤 [1, 2, 3, 4, 5]
- 实际观察：hero.mana: 45 -> 43；field.light.value: 0.53582 -> 0.383114；field.mist.value: 0.571639 -> 0.750738
- 触发 Law：`pmw.v04.action.fog_bank.v1.99e47c3b0071.cost`, `pmw.v04.action.fog_bank.v1.99e47c3b0071.effect.effect_fog_bank`, `pmw.v04.dynamics.200.pilot_area.biomass.base.all`, `pmw.v04.dynamics.200.pilot_area.conductivity.base.all`, `pmw.v04.dynamics.200.pilot_area.electric_field.base.all`, `pmw.v04.dynamics.200.pilot_area.light.base.all`, `pmw.v04.dynamics.200.pilot_area.mist.base.all`, `pmw.v04.dynamics.200.pilot_area.ore.base.all`, `pmw.v04.dynamics.200.pilot_area.smoke.base.all`, `pmw.v04.dynamics.200.pilot_area.stability.base.all`, `pmw.v04.dynamics.200.pilot_area.temperature.base.all`, `pmw.v04.dynamics.200.pilot_area.toxin.base.all`
- 反例：未装备或错误 Trigger 被拒绝，WorldState 原子不变（`action is not an exact currently equipped active skill`）。
- 已知限制：humidity < 0.5 时 required 条件使整个动作拒绝。；modify_attractor 使用绝对临时 target；modify_rate 使用 additive rate。
- 证据：`skills/skill_026_fog_bank.json`；`evidence/skill_026.json`；`tests/test_pilot_60.py`

## skill_027 · 灰圃催生

- 身份：主动；Creator C；天气生态与世界演化
- 材料：`mat_ash_nurse`（rare / uncommon），词条 `trait_ash_nurse`
- 触发与成本：`on_use`；Mana 2；Duration 1
- 创造意图：临时加快药草丰度向既有目标恢复；贫瘠生态的低目标会限制收益。
- 实际机制：modify_rate -> current_area (amount=0.2, field_id=biomass, duration=4)
- 测试场景：`depleted_grove`；5 World Tick；变化步骤 [1, 2, 3, 4, 5, 6]
- 实际观察：hero.mana: 45 -> 43；field.biomass.value: 0.284331 -> 0.452066；field.biomass.effective_target: 0.25 -> 0.55；field.biomass.effective_rate: 0.03 -> 0.08；ecology.current: stressed -> balanced
- 触发 Law：`pmw.v04.action.ash_nurse.v1.073e73d85d37.cost`, `pmw.v04.action.ash_nurse.v1.073e73d85d37.effect.effect_ash_nurse.slot_0.apply`, `pmw.v04.dynamics.200.pilot_area.biomass.base.all`, `pmw.v04.dynamics.200.pilot_area.conductivity.base.all`, `pmw.v04.dynamics.200.pilot_area.electric_field.base.all`, `pmw.v04.dynamics.200.pilot_area.light.base.all`, `pmw.v04.dynamics.200.pilot_area.mist.base.all`, `pmw.v04.dynamics.200.pilot_area.ore.base.all`, `pmw.v04.dynamics.200.pilot_area.smoke.base.all`, `pmw.v04.dynamics.200.pilot_area.stability.base.all`, `pmw.v04.dynamics.200.pilot_area.temperature.base.all`, `pmw.v04.dynamics.200.pilot_area.toxin.base.all`
- 反例：未装备或错误 Trigger 被拒绝，WorldState 原子不变（`action is not an exact currently equipped active skill`）。
- 已知限制：低丰度 target 限制恢复，rate 增益不能凭空抬高 target。；modify_attractor 使用绝对临时 target；modify_rate 使用 additive rate。
- 证据：`skills/skill_027_ash_nurse.json`；`evidence/skill_027.json`；`tests/test_pilot_60.py`

## skill_028 · 引雷林

- 身份：主动；Creator C；天气生态与世界演化
- 材料：`mat_lightning_rod_grove`（epic / scarce），词条 `trait_lightning_rod_grove`
- 触发与成本：`on_use`；Mana 2；Duration 1
- 创造意图：提高环境导电性，同时消耗湿度；它创造雷暴联动表面，也制造干燥副作用。
- 实际机制：modify_field -> current_area (amount=0.25, field_id=electric_field)；modify_field -> current_area (amount=-0.15, field_id=wetness)
- 测试场景：`mist_cavern`；4 World Tick；变化步骤 [1, 2, 3, 4, 5]
- 实际观察：hero.mana: 45 -> 43；field.electric_field.value: 0.428361 -> 0.607459；field.temperature.value: 17.9477 -> 29.0131；field.wetness.value: 0.628951 -> 0.769648；weather state differs; inspect the evidence timeline
- 触发 Law：`pmw.v04.action.lightning_rod_grove.v1.4db1dc678cf9.cost`, `pmw.v04.action.lightning_rod_grove.v1.4db1dc678cf9.effect.dry_canopy`, `pmw.v04.action.lightning_rod_grove.v1.4db1dc678cf9.effect.effect_lightning_rod_grove`, `pmw.v04.dynamics.200.pilot_area.biomass.base.all`, `pmw.v04.dynamics.200.pilot_area.conductivity.base.all`, `pmw.v04.dynamics.200.pilot_area.electric_field.base.all`, `pmw.v04.dynamics.200.pilot_area.light.base.all`, `pmw.v04.dynamics.200.pilot_area.mist.base.all`, `pmw.v04.dynamics.200.pilot_area.ore.base.all`, `pmw.v04.dynamics.200.pilot_area.smoke.base.all`, `pmw.v04.dynamics.200.pilot_area.stability.base.all`, `pmw.v04.dynamics.200.pilot_area.temperature.base.all`
- 反例：未装备或错误 Trigger 被拒绝，WorldState 原子不变（`action is not an exact currently equipped active skill`）。
- 已知限制：无雷暴通用 Law 的区域只有导电/干燥改变，不会虚构雷击。；modify_attractor 使用绝对临时 target；modify_rate 使用 additive rate。
- 证据：`skills/skill_028_lightning_rod_grove.json`；`evidence/skill_028.json`；`tests/test_pilot_60.py`

## skill_029 · 潮汐锁

- 身份：主动；Creator C；天气生态与世界演化
- 材料：`mat_tide_lock`（rare / uncommon），词条 `trait_tide_lock`
- 触发与成本：`on_use`；Mana 2；Duration 1
- 创造意图：把水位暂时牵向高位；快流区迅速见效，慢渗区可能在到达前就失效。
- 实际机制：modify_attractor -> current_area (amount=0.8, field_id=wetness, duration=6)
- 测试场景：`dry_basin`；6 World Tick；变化步骤 [1, 2, 3, 4, 5, 6, 7]
- 实际观察：hero.mana: 45 -> 43；field.wetness.value: 0.293839 -> 0.340886
- 触发 Law：`pmw.v04.action.tide_lock.v1.5522f5642c74.cost`, `pmw.v04.action.tide_lock.v1.5522f5642c74.effect.effect_tide_lock.slot_0.apply`, `pmw.v04.dynamics.200.pilot_area.biomass.base.all`, `pmw.v04.dynamics.200.pilot_area.conductivity.base.all`, `pmw.v04.dynamics.200.pilot_area.electric_field.base.all`, `pmw.v04.dynamics.200.pilot_area.light.base.all`, `pmw.v04.dynamics.200.pilot_area.mist.base.all`, `pmw.v04.dynamics.200.pilot_area.ore.base.all`, `pmw.v04.dynamics.200.pilot_area.smoke.base.all`, `pmw.v04.dynamics.200.pilot_area.stability.base.all`, `pmw.v04.dynamics.200.pilot_area.temperature.base.all`, `pmw.v04.dynamics.200.pilot_area.toxin.base.all`
- 反例：未装备或错误 Trigger 被拒绝，WorldState 原子不变（`action is not an exact currently equipped active skill`）。
- 已知限制：慢渗区域在 duration 内接近不了高水位。；modify_attractor 使用绝对临时 target；modify_rate 使用 additive rate。
- 证据：`skills/skill_029_tide_lock.json`；`evidence/skill_029.json`；`tests/test_pilot_60.py`

## skill_030 · 物候回拨

- 身份：主动；Creator C；天气生态与世界演化
- 材料：`mat_phenology_reset`（fine / abundant），词条 `trait_phenology_reset`
- 触发与成本：`on_use`；Mana 2；Duration 1
- 创造意图：把开花指标回拨，推迟依赖持续高开花值的生态转换，以时间换取采集窗口。
- 实际机制：modify_field -> current_area (amount=-0.4, field_id=biomass)
- 测试场景：`wet_forest`；4 World Tick；变化步骤 [1, 2, 3, 4, 5]
- 实际观察：hero.mana: 45 -> 43；field.biomass.value: 0.628803 -> 0.30132；field.biomass.effective_target: 0.55 -> 0.25；field.biomass.effective_rate: 0.08 -> 0.03；ecology.current: balanced -> stressed
- 触发 Law：`pmw.v04.action.phenology_reset.v1.0f8ea782d950.cost`, `pmw.v04.action.phenology_reset.v1.0f8ea782d950.effect.effect_phenology_reset`, `pmw.v04.dynamics.200.pilot_area.biomass.base.all`, `pmw.v04.dynamics.200.pilot_area.conductivity.base.all`, `pmw.v04.dynamics.200.pilot_area.electric_field.base.all`, `pmw.v04.dynamics.200.pilot_area.light.base.all`, `pmw.v04.dynamics.200.pilot_area.mist.base.all`, `pmw.v04.dynamics.200.pilot_area.ore.base.all`, `pmw.v04.dynamics.200.pilot_area.smoke.base.all`, `pmw.v04.dynamics.200.pilot_area.stability.base.all`, `pmw.v04.dynamics.200.pilot_area.temperature.base.all`, `pmw.v04.dynamics.200.pilot_area.toxin.base.all`
- 反例：未装备或错误 Trigger 被拒绝，WorldState 原子不变（`action is not an exact currently equipped active skill`）。
- 已知限制：低 bloom 本就远离阈值时只有很小策略价值。；modify_attractor 使用绝对临时 target；modify_rate 使用 additive rate。
- 证据：`skills/skill_030_phenology_reset.json`；`evidence/skill_030.json`；`tests/test_pilot_60.py`

## skill_031 · 可控防火带

- 身份：主动；Creator D；探索资源与非战斗
- 材料：`ash_salt`（fine / uncommon），词条 `dry_clearance`
- 触发与成本：`on_use`；Mana 0；Duration 1
- 创造意图：同时清除局部植被与雾气，牺牲资源换取干燥通道。当前引擎没有导航收益，因此只把它认定为可执行环境改造，不夸称已经开路。
- 实际机制：modify_field -> current_area (amount=-0.18, field_id=biomass)；modify_field -> current_area (amount=-0.12, field_id=mist)
- 测试场景：`wet_forest`；4 World Tick；变化步骤 [1, 2, 3, 4, 5]
- 实际观察：field.biomass.value: 0.628803 -> 0.499852；field.mist.value: 0.571639 -> 0.485672
- 触发 Law：`pmw.v04.action.controlled_firebreak.v1.4bd73e88c5cd.cost`, `pmw.v04.action.controlled_firebreak.v1.4bd73e88c5cd.effect.clear_biomass`, `pmw.v04.action.controlled_firebreak.v1.4bd73e88c5cd.effect.open_dry_lane`, `pmw.v04.dynamics.200.pilot_area.biomass.base.all`, `pmw.v04.dynamics.200.pilot_area.conductivity.base.all`, `pmw.v04.dynamics.200.pilot_area.electric_field.base.all`, `pmw.v04.dynamics.200.pilot_area.light.base.all`, `pmw.v04.dynamics.200.pilot_area.mist.base.all`, `pmw.v04.dynamics.200.pilot_area.ore.base.all`, `pmw.v04.dynamics.200.pilot_area.smoke.base.all`, `pmw.v04.dynamics.200.pilot_area.stability.base.all`, `pmw.v04.dynamics.200.pilot_area.temperature.base.all`
- 反例：未装备或错误 Trigger 被拒绝，WorldState 原子不变（`action is not an exact currently equipped active skill`）。
- 已知限制：探索 Trait 只是显式组合接口；当前没有自动导航或发现系统。；资源场变化不等于材料已经采入背包，除非另行执行正式 harvest。
- 证据：`skills/skill_031_controlled_firebreak.json`；`evidence/skill_031.json`；`tests/test_pilot_60.py`

## skill_032 · 育种苗床

- 身份：主动；Creator D；探索资源与非战斗
- 材料：`seed_clay`（rare / uncommon），词条 `deferred_yield`
- 触发与成本：`on_use`；Mana 1；Duration 1
- 创造意图：立即消耗一部分 herbs 作为种源，换取五 Tick 高目标值。短期必亏、长期可能回本，且受临时槽容量和自然动力学约束。
- 实际机制：modify_field -> current_area (amount=-0.1, field_id=biomass)；modify_attractor -> current_area (amount=1.0, field_id=biomass, duration=5)
- 测试场景：`depleted_grove`；5 World Tick；变化步骤 [1, 2, 3, 4, 5, 6]
- 实际观察：hero.mana: 45 -> 44；field.biomass.value: 0.284331 -> 0.260122
- 触发 Law：`pmw.v04.action.cultivation_bed.v1.9d3230543f02.cost`, `pmw.v04.action.cultivation_bed.v1.9d3230543f02.effect.set_cultivation_target.slot_0.apply`, `pmw.v04.action.cultivation_bed.v1.9d3230543f02.effect.spend_seed_stock`, `pmw.v04.dynamics.200.pilot_area.biomass.base.all`, `pmw.v04.dynamics.200.pilot_area.conductivity.base.all`, `pmw.v04.dynamics.200.pilot_area.electric_field.base.all`, `pmw.v04.dynamics.200.pilot_area.light.base.all`, `pmw.v04.dynamics.200.pilot_area.mist.base.all`, `pmw.v04.dynamics.200.pilot_area.ore.base.all`, `pmw.v04.dynamics.200.pilot_area.smoke.base.all`, `pmw.v04.dynamics.200.pilot_area.stability.base.all`, `pmw.v04.dynamics.200.pilot_area.temperature.base.all`
- 反例：未装备或错误 Trigger 被拒绝，WorldState 原子不变（`action is not an exact currently equipped active skill`）。
- 已知限制：探索 Trait 只是显式组合接口；当前没有自动导航或发现系统。；资源场变化不等于材料已经采入背包，除非另行执行正式 harvest。
- 证据：`skills/skill_032_cultivation_bed.json`；`evidence/skill_032.json`；`tests/test_pilot_60.py`

## skill_033 · 露线集水器

- 身份：主动；Creator D；探索资源与非战斗
- 材料：`wicked_moss`（fine / uncommon），词条 `capillary_exchange`
- 触发与成本：`on_use`；Mana 1；Duration 1
- 创造意图：把高雾环境中的水分导入可采植被：即时提高 herbs，但消耗 mist。它不是凭空产资源，而是交换两个公共场量；干燥环境会整次原子失败。
- 实际机制：modify_field -> current_area (amount=0.12, field_id=biomass)；modify_field -> current_area (amount=-0.15, field_id=mist)
- 测试场景：`mist_cavern`；4 World Tick；变化步骤 [1, 2, 3, 4, 5]
- 实际观察：hero.mana: 45 -> 44；field.biomass.value: 0.442541 -> 0.528508；field.mist.value: 0.729246 -> 0.621787
- 触发 Law：`pmw.v04.action.dewline_condenser.v1.51dcdb88e032.cost`, `pmw.v04.action.dewline_condenser.v1.51dcdb88e032.effect.collect_dew`, `pmw.v04.action.dewline_condenser.v1.51dcdb88e032.effect.consume_mist`, `pmw.v04.dynamics.200.pilot_area.biomass.base.all`, `pmw.v04.dynamics.200.pilot_area.conductivity.base.all`, `pmw.v04.dynamics.200.pilot_area.electric_field.base.all`, `pmw.v04.dynamics.200.pilot_area.light.base.all`, `pmw.v04.dynamics.200.pilot_area.mist.base.all`, `pmw.v04.dynamics.200.pilot_area.ore.base.all`, `pmw.v04.dynamics.200.pilot_area.smoke.base.all`, `pmw.v04.dynamics.200.pilot_area.stability.base.all`, `pmw.v04.dynamics.200.pilot_area.temperature.base.all`
- 反例：未装备或错误 Trigger 被拒绝，WorldState 原子不变（`action is not an exact currently equipped active skill`）。
- 已知限制：探索 Trait 只是显式组合接口；当前没有自动导航或发现系统。；资源场变化不等于材料已经采入背包，除非另行执行正式 harvest。
- 证据：`skills/skill_033_dewline_condenser.json`；`evidence/skill_033.json`；`tests/test_pilot_60.py`

## skill_034 · 野地口粮

- 身份：主动；Creator D；探索资源与非战斗
- 材料：`bitter_tuber`（fine / uncommon），词条 `foraged_recovery`
- 触发与成本：`on_use`；Mana 0；Duration 1
- 创造意图：只有 herbs 足够时才可消耗公共食物恢复生命。它把非战斗治疗绑定到可枯竭环境，并以原子失败阻止低资源透支。
- 实际机制：modify_field -> current_area (amount=-0.1, field_id=biomass)；heal -> self (amount=4)
- 测试场景：`wet_forest`；3 World Tick；变化步骤 [1, 2, 3, 4]
- 实际观察：hero.hp: 80 -> 84；field.biomass.value: 0.635656 -> 0.557787
- 触发 Law：`pmw.v04.action.field_ration.v1.40a384eec8d4.cost`, `pmw.v04.action.field_ration.v1.40a384eec8d4.effect.consume_local_food`, `pmw.v04.action.field_ration.v1.40a384eec8d4.effect.recover_from_foraging`, `pmw.v04.dynamics.200.pilot_area.biomass.base.all`, `pmw.v04.dynamics.200.pilot_area.conductivity.base.all`, `pmw.v04.dynamics.200.pilot_area.electric_field.base.all`, `pmw.v04.dynamics.200.pilot_area.light.base.all`, `pmw.v04.dynamics.200.pilot_area.mist.base.all`, `pmw.v04.dynamics.200.pilot_area.ore.base.all`, `pmw.v04.dynamics.200.pilot_area.smoke.base.all`, `pmw.v04.dynamics.200.pilot_area.stability.base.all`, `pmw.v04.dynamics.200.pilot_area.temperature.base.all`
- 反例：未装备或错误 Trigger 被拒绝，WorldState 原子不变（`action is not an exact currently equipped active skill`）。
- 已知限制：探索 Trait 只是显式组合接口；当前没有自动导航或发现系统。；资源场变化不等于材料已经采入背包，除非另行执行正式 harvest。
- 证据：`skills/skill_034_field_ration.json`；`evidence/skill_034.json`；`tests/test_pilot_60.py`

## skill_035 · 雾途罗盘

- 身份：主动；Creator D；探索资源与非战斗
- 材料：`lodestone_glass`（fine / uncommon），词条 `mist_orientation`
- 触发与成本：`on_use`；Mana 0；Duration 1
- 创造意图：浓雾中赋予短时 fogway_marked 标记，供合法 Condition/Weather 内容联动。现有场景没有消费该 Trait，所以证据只支持‘建立工具状态’，不支持移动加速。
- 实际机制：grant_trait -> self (trait_id=fogway_marked, duration=3)
- 测试场景：`mist_cavern`；3 World Tick；变化步骤 [1, 2, 3, 4]
- 实际观察：hero.statuses: [{"active": true, "clock_unit": "owner_turn", "expiry_handle": null, "granted_traits": ["fogway_marked"], "instance_id": "cast_skill_035:mark_fog_bearing", "owner_id": "pilot_hero", "remaining": 3, "shield_layer_slot": null, "source_id": "fogway_compass", "spec_hash": "trait:fogway_marked", "spec_id": "trait_fogway_marked", "stacks": 1}]
- 触发 Law：`pmw.v04.action.fogway_compass.v1.3848ff2c2a67.cost`, `pmw.v04.action.fogway_compass.v1.3848ff2c2a67.effect.mark_fog_bearing`, `pmw.v04.dynamics.200.pilot_area.biomass.base.all`, `pmw.v04.dynamics.200.pilot_area.conductivity.base.all`, `pmw.v04.dynamics.200.pilot_area.electric_field.base.all`, `pmw.v04.dynamics.200.pilot_area.light.base.all`, `pmw.v04.dynamics.200.pilot_area.mist.base.all`, `pmw.v04.dynamics.200.pilot_area.ore.base.all`, `pmw.v04.dynamics.200.pilot_area.smoke.base.all`, `pmw.v04.dynamics.200.pilot_area.stability.base.all`, `pmw.v04.dynamics.200.pilot_area.temperature.base.all`, `pmw.v04.dynamics.200.pilot_area.toxin.base.all`
- 反例：未装备或错误 Trigger 被拒绝，WorldState 原子不变（`action is not an exact currently equipped active skill`）。
- 已知限制：探索 Trait 只是显式组合接口；当前没有自动导航或发现系统。；资源场变化不等于材料已经采入背包，除非另行执行正式 harvest。
- 证据：`skills/skill_035_fogway_compass.json`；`evidence/skill_035.json`；`tests/test_pilot_60.py`

## skill_036 · 菌群侦察

- 身份：主动；Creator D；探索资源与非战斗
- 材料：`whisper_cap`（fine / uncommon），词条 `living_survey`
- 触发与成本：`on_use`；Mana 0；Duration 1
- 创造意图：植被丰盛时记录短时调查标记。技能自身不直接给材料，适合作为后续天气或收获规则的公开前置条件。
- 实际机制：grant_trait -> self (trait_id=dense_growth_surveyed, duration=2)
- 测试场景：`wet_forest`；3 World Tick；变化步骤 [1, 2, 3, 4]
- 实际观察：hero.statuses: [{"active": true, "clock_unit": "owner_turn", "expiry_handle": null, "granted_traits": ["dense_growth_surveyed"], "instance_id": "cast_skill_036:mark_dense_growth", "owner_id": "pilot_hero", "remaining": 2, "shield_layer_slot": null, "source_id": "mushroom_scout", "spec_hash": "trait:dense_growth_surveyed", "spec_id": "trait_dense_growth_surveyed", "stacks": 1}]
- 触发 Law：`pmw.v04.action.mushroom_scout.v1.37e21710c7f6.cost`, `pmw.v04.action.mushroom_scout.v1.37e21710c7f6.effect.mark_dense_growth`, `pmw.v04.dynamics.200.pilot_area.biomass.base.all`, `pmw.v04.dynamics.200.pilot_area.conductivity.base.all`, `pmw.v04.dynamics.200.pilot_area.electric_field.base.all`, `pmw.v04.dynamics.200.pilot_area.light.base.all`, `pmw.v04.dynamics.200.pilot_area.mist.base.all`, `pmw.v04.dynamics.200.pilot_area.ore.base.all`, `pmw.v04.dynamics.200.pilot_area.smoke.base.all`, `pmw.v04.dynamics.200.pilot_area.stability.base.all`, `pmw.v04.dynamics.200.pilot_area.temperature.base.all`, `pmw.v04.dynamics.200.pilot_area.toxin.base.all`
- 反例：未装备或错误 Trigger 被拒绝，WorldState 原子不变（`action is not an exact currently equipped active skill`）。
- 已知限制：探索 Trait 只是显式组合接口；当前没有自动导航或发现系统。；资源场变化不等于材料已经采入背包，除非另行执行正式 harvest。
- 证据：`skills/skill_036_mushroom_scout.json`；`evidence/skill_036.json`；`tests/test_pilot_60.py`

## skill_037 · 静滞保鲜布

- 身份：主动；Creator D；探索资源与非战斗
- 材料：`stillfiber`（fine / uncommon），词条 `metabolic_brake`
- 触发与成本：`on_use`；Mana 1；Duration 1
- 创造意图：暂时降低 herbs 的恢复速率。它可减慢任意方向的生态变化，既可能延缓枯竭，也会拖慢复苏，是依赖当前吸引子方向的双刃工具。
- 实际机制：modify_rate -> current_area (amount=-0.08, field_id=biomass, duration=3)
- 测试场景：`wet_forest`；5 World Tick；变化步骤 [1, 2, 3, 4, 5, 6]
- 实际观察：hero.mana: 45 -> 44；field.biomass.value: 0.622499 -> 0.635656
- 触发 Law：`pmw.v04.action.preservation_wrap.v1.4fccea26b991.cost`, `pmw.v04.action.preservation_wrap.v1.4fccea26b991.effect.slow_herb_dynamics.slot_0.apply`, `pmw.v04.dynamics.200.pilot_area.biomass.base.all`, `pmw.v04.dynamics.200.pilot_area.conductivity.base.all`, `pmw.v04.dynamics.200.pilot_area.electric_field.base.all`, `pmw.v04.dynamics.200.pilot_area.light.base.all`, `pmw.v04.dynamics.200.pilot_area.mist.base.all`, `pmw.v04.dynamics.200.pilot_area.ore.base.all`, `pmw.v04.dynamics.200.pilot_area.smoke.base.all`, `pmw.v04.dynamics.200.pilot_area.stability.base.all`, `pmw.v04.dynamics.200.pilot_area.temperature.base.all`, `pmw.v04.dynamics.200.pilot_area.toxin.base.all`
- 反例：未装备或错误 Trigger 被拒绝，WorldState 原子不变（`action is not an exact currently equipped active skill`）。
- 已知限制：探索 Trait 只是显式组合接口；当前没有自动导航或发现系统。；资源场变化不等于材料已经采入背包，除非另行执行正式 harvest。
- 证据：`skills/skill_037_preservation_wrap.json`；`evidence/skill_037.json`；`tests/test_pilot_60.py`

## skill_038 · 复生苗桩

- 身份：主动；Creator D；探索资源与非战斗
- 材料：`root_memory_wood`（rare / scarce），词条 `slow_cultivation`
- 触发与成本：`on_use`；Mana 2；Duration 1
- 创造意图：先消耗一小部分 herbs 整理苗床，再安装 duration=4 的临时高吸引子。真实调度下它影响之后三次动力学更新，并在 time=4 的更新前到期；玩家必须留出世界时间等待。
- 实际机制：modify_field -> current_area (amount=-0.05, field_id=biomass)；modify_attractor -> current_area (amount=0.95, field_id=biomass, duration=4)
- 测试场景：`depleted_grove`；5 World Tick；变化步骤 [1, 2, 3, 4, 5, 6]
- 实际观察：hero.mana: 45 -> 43；field.biomass.value: 0.284331 -> 0.283624
- 触发 Law：`pmw.v04.action.regrowth_stakes.v1.b6831b61f6a6.cost`, `pmw.v04.action.regrowth_stakes.v1.b6831b61f6a6.effect.prepare_regrowth_bed`, `pmw.v04.action.regrowth_stakes.v1.b6831b61f6a6.effect.raise_regrowth_target.slot_0.apply`, `pmw.v04.dynamics.200.pilot_area.biomass.base.all`, `pmw.v04.dynamics.200.pilot_area.conductivity.base.all`, `pmw.v04.dynamics.200.pilot_area.electric_field.base.all`, `pmw.v04.dynamics.200.pilot_area.light.base.all`, `pmw.v04.dynamics.200.pilot_area.mist.base.all`, `pmw.v04.dynamics.200.pilot_area.ore.base.all`, `pmw.v04.dynamics.200.pilot_area.smoke.base.all`, `pmw.v04.dynamics.200.pilot_area.stability.base.all`, `pmw.v04.dynamics.200.pilot_area.temperature.base.all`
- 反例：未装备或错误 Trigger 被拒绝，WorldState 原子不变（`action is not an exact currently equipped active skill`）。
- 已知限制：探索 Trait 只是显式组合接口；当前没有自动导航或发现系统。；资源场变化不等于材料已经采入背包，除非另行执行正式 harvest。
- 证据：`skills/skill_038_regrowth_stakes.json`；`evidence/skill_038.json`；`tests/test_pilot_60.py`

## skill_039 · 风暴虹吸

- 身份：主动；Creator D；探索资源与非战斗
- 材料：`storm_reed`（rare / uncommon），词条 `ambient_siphon`
- 触发与成本：`on_use`；Mana 0；Duration 1
- 创造意图：在高雾代理的带电湿环境中，将公共 mist 换成个人 Mana。低于门槛会原子拒绝，避免无环境成本充能。
- 实际机制：modify_field -> current_area (amount=-0.2, field_id=mist)；add_resource -> self (amount=3, resource=mana)
- 测试场景：`mist_cavern`；4 World Tick；变化步骤 [1, 2, 3, 4, 5]
- 实际观察：hero.mana: 45 -> 48；field.light.value: 0.118049 -> 0.270754；field.mist.value: 0.729246 -> 0.585967
- 触发 Law：`pmw.v04.action.storm_siphon.v1.5d4dc2c0e54b.cost`, `pmw.v04.action.storm_siphon.v1.5d4dc2c0e54b.effect.drain_charged_mist`, `pmw.v04.dynamics.200.pilot_area.biomass.base.all`, `pmw.v04.dynamics.200.pilot_area.conductivity.base.all`, `pmw.v04.dynamics.200.pilot_area.electric_field.base.all`, `pmw.v04.dynamics.200.pilot_area.light.base.all`, `pmw.v04.dynamics.200.pilot_area.mist.base.all`, `pmw.v04.dynamics.200.pilot_area.ore.base.all`, `pmw.v04.dynamics.200.pilot_area.smoke.base.all`, `pmw.v04.dynamics.200.pilot_area.stability.base.all`, `pmw.v04.dynamics.200.pilot_area.temperature.base.all`, `pmw.v04.dynamics.200.pilot_area.toxin.base.all`
- 反例：未装备或错误 Trigger 被拒绝，WorldState 原子不变（`action is not an exact currently equipped active skill`）。
- 已知限制：探索 Trait 只是显式组合接口；当前没有自动导航或发现系统。；资源场变化不等于材料已经采入背包，除非另行执行正式 harvest。
- 证据：`skills/skill_039_storm_siphon.json`；`evidence/skill_039.json`；`tests/test_pilot_60.py`

## skill_040 · 蕨粉路标

- 身份：主动；Creator D；探索资源与非战斗
- 材料：`chalkfern`（fine / uncommon），词条 `visible_corridor`
- 触发与成本：`on_use`；Mana 0；Duration 1
- 创造意图：降低局部 mist 并赋予短时 return_path_marked。前者是真实场量改变，后者只是可供其他机制读取的状态；不虚构未实现的地图传送。
- 实际机制：modify_field -> current_area (amount=-0.15, field_id=mist)；grant_trait -> self (trait_id=return_path_marked, duration=2)
- 测试场景：`mist_cavern`；3 World Tick；变化步骤 [1, 2, 3, 4]
- 实际观察：hero.statuses: [{"active": true, "clock_unit": "owner_turn", "expiry_handle": null, "granted_traits": ["return_path_marked"], "instance_id": "cast_skill_040:mark_return_path", "owner_id": "pilot_hero", "remaining": 2, "shield_layer_slot": null, "source_id": "trail_marker", "spec_hash": "trait:return_path_marked", "spec_id": "trait_return_path_marked", "stacks": 1}]；field.mist.value: 0.74918 -> 0.632377
- 触发 Law：`pmw.v04.action.trail_marker.v1.64f568eaf1e4.cost`, `pmw.v04.action.trail_marker.v1.64f568eaf1e4.effect.mark_return_path`, `pmw.v04.action.trail_marker.v1.64f568eaf1e4.effect.thin_local_fog`, `pmw.v04.dynamics.200.pilot_area.biomass.base.all`, `pmw.v04.dynamics.200.pilot_area.conductivity.base.all`, `pmw.v04.dynamics.200.pilot_area.electric_field.base.all`, `pmw.v04.dynamics.200.pilot_area.light.base.all`, `pmw.v04.dynamics.200.pilot_area.mist.base.all`, `pmw.v04.dynamics.200.pilot_area.ore.base.all`, `pmw.v04.dynamics.200.pilot_area.smoke.base.all`, `pmw.v04.dynamics.200.pilot_area.stability.base.all`, `pmw.v04.dynamics.200.pilot_area.temperature.base.all`
- 反例：未装备或错误 Trigger 被拒绝，WorldState 原子不变（`action is not an exact currently equipped active skill`）。
- 已知限制：探索 Trait 只是显式组合接口；当前没有自动导航或发现系统。；资源场变化不等于材料已经采入背包，除非另行执行正式 harvest。
- 证据：`skills/skill_040_trail_marker.json`；`evidence/skill_040.json`；`tests/test_pilot_60.py`

## skill_041 · 引雷播种

- 身份：主动；Creator E；天气/状态跨系统
- 材料：`stormglass_seed`（epic / scarce），词条 `stormglass_seed_affinity`
- 触发与成本：`on_use`；Mana 4；Duration 1
- 创造意图：先同时抬升雨量与电场，再让施术者进入导体态。导体态本身逐 Tick 回蓝，而通用雷暴规则还会额外读取该 Trait，形成环境越危险、法力回流越强的多段反馈。
- 实际机制：modify_field -> current_area (amount=0.25, field_id=wetness)；modify_field -> current_area (amount=0.22, field_id=electric_field)；apply_status -> self (status_id=conductor_charge)
- 测试场景：`storm_plateau`；4 World Tick；变化步骤 [1, 2, 3, 4, 5]
- 实际观察：field.electric_field.value: 0.657606 -> 0.815213；field.temperature.value: 40.1723 -> 36.6333；field.wetness.value: 0.834123 -> 1；weather state differs; inspect the evidence timeline
- 触发 Law：`pmw.v04.action.storm_seed_conductor.v1.b1dce3f6fde0.cost`, `pmw.v04.action.storm_seed_conductor.v1.b1dce3f6fde0.effect.become_conductor`, `pmw.v04.action.storm_seed_conductor.v1.b1dce3f6fde0.effect.seed_charge`, `pmw.v04.action.storm_seed_conductor.v1.b1dce3f6fde0.effect.seed_rain`, `pmw.v04.dynamics.200.pilot_area.biomass.base.all`, `pmw.v04.dynamics.200.pilot_area.conductivity.base.all`, `pmw.v04.dynamics.200.pilot_area.electric_field.base.all`, `pmw.v04.dynamics.200.pilot_area.light.base.all`, `pmw.v04.dynamics.200.pilot_area.mist.base.all`, `pmw.v04.dynamics.200.pilot_area.ore.base.all`, `pmw.v04.dynamics.200.pilot_area.smoke.base.all`, `pmw.v04.dynamics.200.pilot_area.stability.base.all`
- 反例：未装备或错误 Trigger 被拒绝，WorldState 原子不变（`action is not an exact currently equipped active skill`）。
- 已知限制：制造雷暴所需的公开电场也会影响区域内所有对象；收益延迟出现。；动作解析器不自动推进世界时间，基线与处理组由 runner 等时推进。；Creator 提议中的领域字段被映射到公开的规范字段：rain->wetness, electric->electric_field.
- 证据：`skills/skill_041_storm_seed_conductor.json`；`evidence/skill_041.json`；`tests/test_pilot_60.py`

## skill_042 · 根网蓄势

- 身份：主动；Creator E；防御/场动力学
- 材料：`living_circuit_bark`（rare / uncommon），词条 `living_circuit_bark_affinity`
- 触发与成本：`on_use`；Mana 3；Duration 1
- 创造意图：把短期护盾与有所有权的 rooted 状态绑定，同时暂时加速生物量场恢复。角色得以守住一轮，区域却会在数 Tick 内更快向生态吸引子回归。
- 实际机制：shield -> self (amount=8)；apply_status -> self (status_id=rooted_guard)；modify_rate -> current_area (amount=0.12, field_id=biomass, duration=3)
- 测试场景：`depleted_grove`；4 World Tick；变化步骤 [1, 2, 3, 4, 5, 6, 7, 8]
- 实际观察：hero.mana: 45 -> 42；field.biomass.value: 0.285393 -> 0.345595
- 触发 Law：`pmw.v04.action.root_circuit.v1.994109615913.cost`, `pmw.v04.action.root_circuit.v1.994109615913.effect.accelerate_biomass.slot_0.apply`, `pmw.v04.action.root_circuit.v1.994109615913.effect.root_contract`, `pmw.v04.action.root_circuit.v1.994109615913.effect.root_shield`, `pmw.v04.dynamics.200.pilot_area.biomass.base.all`, `pmw.v04.dynamics.200.pilot_area.conductivity.base.all`, `pmw.v04.dynamics.200.pilot_area.electric_field.base.all`, `pmw.v04.dynamics.200.pilot_area.light.base.all`, `pmw.v04.dynamics.200.pilot_area.mist.base.all`, `pmw.v04.dynamics.200.pilot_area.ore.base.all`, `pmw.v04.dynamics.200.pilot_area.smoke.base.all`, `pmw.v04.dynamics.200.pilot_area.stability.base.all`
- 反例：未装备或错误 Trigger 被拒绝，WorldState 原子不变（`action is not an exact currently equipped active skill`）。
- 已知限制：护盾随状态到期精确撤销，不能永久囤积；增长率也会按时失效。；动作解析器不自动推进世界时间，基线与处理组由 runner 等时推进。；Creator 提议中的领域字段被映射到公开的规范字段：.
- 证据：`skills/skill_042_root_circuit.json`；`evidence/skill_042.json`；`tests/test_pilot_60.py`

## skill_043 · 热债转存

- 身份：主动；Creator E；战斗/环境权衡
- 材料：`phasechange_ember`（rare / scarce），词条 `phasechange_ember_affinity`
- 触发与成本：`on_use`；Mana 3；Duration 1
- 创造意图：立即灼伤敌人，却把区域温度吸引子暂时压低；施术者承担持续热债。它不是单纯火球，而是以自损换取数 Tick 后的战场降温。
- 实际机制：damage -> target_actor (amount=6)；modify_attractor -> current_area (amount=0.25, field_id=temperature, duration=3)；apply_status -> self (status_id=heat_debt)
- 测试场景：`dry_basin`；4 World Tick；变化步骤 [1, 2, 3, 4, 5]
- 实际观察：hero.hp: 80 -> 77；hero.mana: 45 -> 42；target.hp: 80 -> 74；field.temperature.value: 72.083 -> 70.2857
- 触发 Law：`pmw.v04.action.thermal_bank.v1.cb098850484f.cost`, `pmw.v04.action.thermal_bank.v1.cb098850484f.effect.cooling_target.slot_0.apply`, `pmw.v04.action.thermal_bank.v1.cb098850484f.effect.release_heat`, `pmw.v04.action.thermal_bank.v1.cb098850484f.effect.take_heat_debt`, `pmw.v04.dynamics.200.pilot_area.biomass.base.all`, `pmw.v04.dynamics.200.pilot_area.conductivity.base.all`, `pmw.v04.dynamics.200.pilot_area.electric_field.base.all`, `pmw.v04.dynamics.200.pilot_area.light.base.all`, `pmw.v04.dynamics.200.pilot_area.mist.base.all`, `pmw.v04.dynamics.200.pilot_area.ore.base.all`, `pmw.v04.dynamics.200.pilot_area.smoke.base.all`, `pmw.v04.dynamics.200.pilot_area.stability.base.all`
- 反例：未装备或错误 Trigger 被拒绝，WorldState 原子不变（`action is not an exact currently equipped active skill`）。
- 已知限制：热债持续扣血；若仍触发热浪，通用天气交互会让债务更重。；动作解析器不自动推进世界时间，基线与处理组由 runner 等时推进。；Creator 提议中的领域字段被映射到公开的规范字段：.
- 证据：`skills/skill_043_thermal_bank.json`；`evidence/skill_043.json`；`tests/test_pilot_60.py`

## skill_044 · 潮汐换血

- 身份：主动；Creator E；条件治疗/环境代价
- 材料：`brine_heart`（rare / uncommon），词条 `brine_heart_affinity`
- 触发与成本：`on_use`；Mana 2；Duration 1
- 创造意图：在足够湿润时才治疗同伴，但无论治疗是否成立都会提高盐度。玩家必须决定是否为一次治疗承担后续环境偏移。
- 实际机制：heal -> target_actor (amount=7)，有条件；modify_field -> current_area (amount=0.12, field_id=wetness)
- 测试场景：`wet_forest`；3 World Tick；变化步骤 [1, 2, 3, 4]
- 实际观察：hero.mana: 45 -> 43；target.hp: 55 -> 62；field.wetness.value: 0.718033 -> 0.811475
- 触发 Law：`pmw.v04.action.tidal_exchange.v1.b0cb796512a8.cost`, `pmw.v04.action.tidal_exchange.v1.b0cb796512a8.effect.salt_aftertaste`, `pmw.v04.action.tidal_exchange.v1.b0cb796512a8.effect.wet_heal`, `pmw.v04.dynamics.200.pilot_area.biomass.base.all`, `pmw.v04.dynamics.200.pilot_area.conductivity.base.all`, `pmw.v04.dynamics.200.pilot_area.electric_field.base.all`, `pmw.v04.dynamics.200.pilot_area.light.base.all`, `pmw.v04.dynamics.200.pilot_area.mist.base.all`, `pmw.v04.dynamics.200.pilot_area.ore.base.all`, `pmw.v04.dynamics.200.pilot_area.smoke.base.all`, `pmw.v04.dynamics.200.pilot_area.stability.base.all`, `pmw.v04.dynamics.200.pilot_area.temperature.base.all`
- 反例：未装备或错误 Trigger 被拒绝，WorldState 原子不变（`action is not an exact currently equipped active skill`）。
- 已知限制：干燥环境只留下盐度副作用；治疗是 conditional 而非伪造成功。；动作解析器不自动推进世界时间，基线与处理组由 runner 等时推进。；Creator 提议中的领域字段被映射到公开的规范字段：salinity->wetness.
- 证据：`skills/skill_044_tidal_exchange.json`；`evidence/skill_044.json`；`tests/test_pilot_60.py`

## skill_045 · 捕食者信标

- 身份：主动；Creator E；天气/生态风险
- 材料：`pheromone_resin`（epic / scarce），词条 `pheromone_resin_affinity`
- 触发与成本：`on_use`；Mana 3；Duration 1
- 创造意图：提高气味场并暂时把猎物丰度吸引子拉高，看似利于狩猎，却给自己挂上气味标记。通用捕食压力天气会消耗猎物并伤害带标记者。
- 实际机制：modify_field -> current_area (amount=0.3, field_id=toxin)；modify_attractor -> current_area (amount=0.85, field_id=biomass, duration=4)；apply_status -> self (status_id=marked_scent)
- 测试场景：`depleted_grove`；5 World Tick；变化步骤 [1, 2, 3, 4, 5, 6]
- 实际观察：hero.mana: 45 -> 42；field.biomass.value: 0.284331 -> 0.313827；field.toxin.value: 0.447273 -> 0.644998
- 触发 Law：`pmw.v04.action.predator_lure.v1.3c776d022230.cost`, `pmw.v04.action.predator_lure.v1.3c776d022230.effect.draw_prey.slot_0.apply`, `pmw.v04.action.predator_lure.v1.3c776d022230.effect.mark_hunter`, `pmw.v04.action.predator_lure.v1.3c776d022230.effect.raise_scent`, `pmw.v04.dynamics.200.pilot_area.biomass.base.all`, `pmw.v04.dynamics.200.pilot_area.conductivity.base.all`, `pmw.v04.dynamics.200.pilot_area.electric_field.base.all`, `pmw.v04.dynamics.200.pilot_area.light.base.all`, `pmw.v04.dynamics.200.pilot_area.mist.base.all`, `pmw.v04.dynamics.200.pilot_area.ore.base.all`, `pmw.v04.dynamics.200.pilot_area.smoke.base.all`, `pmw.v04.dynamics.200.pilot_area.stability.base.all`
- 反例：未装备或错误 Trigger 被拒绝，WorldState 原子不变（`action is not an exact currently equipped active skill`）。
- 已知限制：短期聚集资源，随后可能触发生态转变和自身伤害。；动作解析器不自动推进世界时间，基线与处理组由 runner 等时推进。；Creator 提议中的领域字段被映射到公开的规范字段：scent->toxin, prey->biomass.
- 证据：`skills/skill_045_predator_lure.json`；`evidence/skill_045.json`；`tests/test_pilot_60.py`

## skill_046 · 共振献偿

- 身份：主动；Creator E；生命交换/组合铺垫
- 材料：`choir_bone`（rare / scarce），词条 `choir_bone_affinity`
- 触发与成本：`on_use`；Mana 1；Duration 1
- 创造意图：以自身生命为明确成本治疗同伴，同时提升公共共振场。它能救急，也可能为随后依赖共振的其他技能铺垫。
- 实际机制：damage -> self (amount=5)；heal -> target_actor (amount=9)；modify_field -> current_area (amount=0.2, field_id=stability)
- 测试场景：`wet_forest`；3 World Tick；变化步骤 [1, 2, 3, 4]
- 实际观察：hero.hp: 70 -> 65；hero.mana: 45 -> 44；target.hp: 55 -> 64；field.stability.value: 0.655738 -> 0.811475
- 触发 Law：`pmw.v04.action.resonant_sacrifice.v1.1c164b0e810e.cost`, `pmw.v04.action.resonant_sacrifice.v1.1c164b0e810e.effect.mend_ally`, `pmw.v04.action.resonant_sacrifice.v1.1c164b0e810e.effect.pay_blood`, `pmw.v04.action.resonant_sacrifice.v1.1c164b0e810e.effect.raise_resonance`, `pmw.v04.dynamics.200.pilot_area.biomass.base.all`, `pmw.v04.dynamics.200.pilot_area.conductivity.base.all`, `pmw.v04.dynamics.200.pilot_area.electric_field.base.all`, `pmw.v04.dynamics.200.pilot_area.light.base.all`, `pmw.v04.dynamics.200.pilot_area.mist.base.all`, `pmw.v04.dynamics.200.pilot_area.ore.base.all`, `pmw.v04.dynamics.200.pilot_area.smoke.base.all`, `pmw.v04.dynamics.200.pilot_area.stability.base.all`
- 反例：未装备或错误 Trigger 被拒绝，WorldState 原子不变（`action is not an exact currently equipped active skill`）。
- 已知限制：伤害不可被目标治疗抵消，低血量时风险真实；共振场是公共资源。；动作解析器不自动推进世界时间，基线与处理组由 runner 等时推进。；Creator 提议中的领域字段被映射到公开的规范字段：resonance->stability.
- 证据：`skills/skill_046_resonant_sacrifice.json`；`evidence/skill_046.json`；`tests/test_pilot_60.py`

## skill_047 · 灰烬催花

- 身份：主动；Creator E；生态/长期代价
- 材料：`funeral_pollen`（epic / unique），词条 `funeral_pollen_affinity`
- 触发与成本：`on_use`；Mana 2；Duration 1
- 创造意图：把灰烬推过生态阈值并暂时抑制肥力恢复，同时承担逐 Tick 法力债。通用生态规则在持续高灰环境中转入荒芜，造成比单次施法更长的世界后果。
- 实际机制：modify_field -> current_area (amount=0.3, field_id=smoke)；modify_rate -> current_area (amount=-0.08, field_id=biomass, duration=3)；apply_status -> self (status_id=ash_debt)
- 测试场景：`depleted_grove`；4 World Tick；变化步骤 [1, 2, 3, 4, 5]
- 实际观察：hero.mana: 45 -> 40；field.biomass.value: 0.285393 -> 0.200591；field.smoke.value: 0.442689 -> 0.657606；field.temperature.value: 56.7948 -> 70.6265；weather state differs; inspect the evidence timeline
- 触发 Law：`pmw.v04.action.ash_bloom.v1.eb4939edde41.cost`, `pmw.v04.action.ash_bloom.v1.eb4939edde41.effect.bind_ash_debt`, `pmw.v04.action.ash_bloom.v1.eb4939edde41.effect.choke_fertility.slot_0.apply`, `pmw.v04.action.ash_bloom.v1.eb4939edde41.effect.spread_ash`, `pmw.v04.dynamics.200.pilot_area.biomass.base.all`, `pmw.v04.dynamics.200.pilot_area.conductivity.base.all`, `pmw.v04.dynamics.200.pilot_area.electric_field.base.all`, `pmw.v04.dynamics.200.pilot_area.light.base.all`, `pmw.v04.dynamics.200.pilot_area.mist.base.all`, `pmw.v04.dynamics.200.pilot_area.ore.base.all`, `pmw.v04.dynamics.200.pilot_area.smoke.base.all`, `pmw.v04.dynamics.200.pilot_area.stability.base.all`
- 反例：未装备或错误 Trigger 被拒绝，WorldState 原子不变（`action is not an exact currently equipped active skill`）。
- 已知限制：短期无直接战斗收益，且会损失法力并破坏未来资源环境。；动作解析器不自动推进世界时间，基线与处理组由 runner 等时推进。；Creator 提议中的领域字段被映射到公开的规范字段：ash->smoke, fertility->biomass.
- 证据：`skills/skill_047_ash_bloom.json`；`evidence/skill_047.json`；`tests/test_pilot_60.py`

## skill_048 · 记忆雾化

- 身份：主动；Creator E；天气/认知代价
- 材料：`mnemonic_dew`（epic / unique），词条 `mnemonic_dew_affinity`
- 触发与成本：`on_use`；Mana 3；Duration 1
- 创造意图：抬升雾场、暂时把记忆场拉向高位，并让自己获得迷航 Trait。通用记忆雾天气会读取该 Trait，形成以认知代价换环境塑形的时序机制。
- 实际机制：modify_field -> current_area (amount=0.25, field_id=mist)；modify_attractor -> current_area (amount=0.8, field_id=stability, duration=3)；apply_status -> self (status_id=lost_bearing)
- 测试场景：`wet_forest`；4 World Tick；变化步骤 [1, 2, 3, 4, 5, 6, 7, 8]
- 实际观察：hero.mana: 45 -> 42；field.light.value: 0.53582 -> 0.383114；field.mist.value: 0.571639 -> 0.750738；field.stability.value: 0.643279 -> 0.66278
- 触发 Law：`pmw.v04.action.memory_fog.v1.e86dc0bb46af.cost`, `pmw.v04.action.memory_fog.v1.e86dc0bb46af.effect.lose_bearing`, `pmw.v04.action.memory_fog.v1.e86dc0bb46af.effect.pull_memory.slot_0.apply`, `pmw.v04.action.memory_fog.v1.e86dc0bb46af.effect.thicken_fog`, `pmw.v04.dynamics.200.pilot_area.biomass.base.all`, `pmw.v04.dynamics.200.pilot_area.conductivity.base.all`, `pmw.v04.dynamics.200.pilot_area.electric_field.base.all`, `pmw.v04.dynamics.200.pilot_area.light.base.all`, `pmw.v04.dynamics.200.pilot_area.mist.base.all`, `pmw.v04.dynamics.200.pilot_area.ore.base.all`, `pmw.v04.dynamics.200.pilot_area.smoke.base.all`, `pmw.v04.dynamics.200.pilot_area.stability.base.all`
- 反例：未装备或错误 Trigger 被拒绝，WorldState 原子不变（`action is not an exact currently equipped active skill`）。
- 已知限制：迷航期间天气每 Tick 扣减法力；场量恢复后收益自然消失。；动作解析器不自动推进世界时间，基线与处理组由 runner 等时推进。；Creator 提议中的领域字段被映射到公开的规范字段：memory->stability.
- 证据：`skills/skill_048_memory_fog.json`；`evidence/skill_048.json`；`tests/test_pilot_60.py`

## skill_049 · 风暴玻璃继电

- 身份：被动；Creator E；被动 Hook/天气
- 材料：`stormglass_relay_core`（rare / scarce），词条 `stormglass_relay_core_affinity`
- 触发与成本：`weather_changed`；Mana 0；Duration 1
- 创造意图：天气真实切换后，通过受信 Hook 把一部分电场泄放为护盾。它把公共天气事件转成个人防御，但也削弱下一轮雷暴联动。
- 实际机制：shield -> self (amount=5)；modify_field -> current_area (amount=-0.12, field_id=electric_field)
- 测试场景：`storm_plateau`；3 World Tick；变化步骤 [1, 2, 3, 4]
- 实际观察：hero.shield: 0 -> 5；hero.shield_layers: [{"active": true, "granted": 5.0, "layer_id": "slot_0", "owner_id": "pilot_hero", "remaining": 5.0, "sequence": 1, "source_id": "stormglass_relay:relay_shield", "status_instance_id": null}]；field.electric_field.value: 0.657606 -> 0.564164
- 触发 Law：`pmw.v04.action.stormglass_relay.v1.a0568dd5b2eb.effect.bleed_charge`, `pmw.v04.action.stormglass_relay.v1.a0568dd5b2eb.effect.relay_shield`, `pmw.v04.dynamics.200.pilot_area.biomass.base.all`, `pmw.v04.dynamics.200.pilot_area.conductivity.base.all`, `pmw.v04.dynamics.200.pilot_area.electric_field.base.all`, `pmw.v04.dynamics.200.pilot_area.light.base.all`, `pmw.v04.dynamics.200.pilot_area.mist.base.all`, `pmw.v04.dynamics.200.pilot_area.ore.base.all`, `pmw.v04.dynamics.200.pilot_area.smoke.base.all`, `pmw.v04.dynamics.200.pilot_area.stability.base.all`, `pmw.v04.dynamics.200.pilot_area.temperature.base.all`, `pmw.v04.dynamics.200.pilot_area.toxin.base.all`
- 反例：未装备或错误 Trigger 被拒绝，WorldState 原子不变（`hook trigger mismatch`）。
- 已知限制：只在 weather_changed 分发时触发；降电场会与需要高电场的构筑冲突。；Hook 由真实来源事件后显式调用受信执行器；当前没有自动事件路由。；Creator 提议中的领域字段被映射到公开的规范字段：electric->electric_field.
- 证据：`skills/skill_049_stormglass_relay.json`；`evidence/skill_049.json`；`tests/test_pilot_60.py`

## skill_050 · 伤痕回声

- 身份：被动；Creator E；被动 Hook/濒危反馈
- 材料：`scar_tuning_fork`（rare / uncommon），词条 `scar_tuning_fork_affinity`
- 触发与成本：`damage_resolved`；Mana 0；Duration 1
- 创造意图：受到真实伤害事件后，只有生命降到阈值以下才通过 Hook 小幅治疗并提高共振场。它把濒危状态变为后续组合资源，而非无限反伤。
- 实际机制：heal -> self (amount=3)，有条件；modify_field -> current_area (amount=0.08, field_id=stability)，有条件
- 测试场景：`dry_basin`；3 World Tick；变化步骤 [1, 2, 3, 4]
- 实际观察：hero.hp: 23 -> 26；field.stability.value: 0.593443 -> 0.655738
- 触发 Law：`pmw.v04.action.basic_attack.v1.ac7edec9eac8.cost`, `pmw.v04.action.basic_attack.v1.ac7edec9eac8.effect.strike`, `pmw.v04.action.bruised_echo.v1.954ebe635ee0.effect.echo_mend`, `pmw.v04.action.bruised_echo.v1.954ebe635ee0.effect.echo_resonance`, `pmw.v04.dynamics.200.pilot_area.biomass.base.all`, `pmw.v04.dynamics.200.pilot_area.conductivity.base.all`, `pmw.v04.dynamics.200.pilot_area.electric_field.base.all`, `pmw.v04.dynamics.200.pilot_area.light.base.all`, `pmw.v04.dynamics.200.pilot_area.mist.base.all`, `pmw.v04.dynamics.200.pilot_area.ore.base.all`, `pmw.v04.dynamics.200.pilot_area.smoke.base.all`, `pmw.v04.dynamics.200.pilot_area.stability.base.all`
- 反例：未装备或错误 Trigger 被拒绝，WorldState 原子不变（`hook trigger mismatch`）。
- 已知限制：条件不满足时两个 conditional 效果都跳过；每个根事件最多一次。；Hook 由真实来源事件后显式调用受信执行器；当前没有自动事件路由。；Creator 提议中的领域字段被映射到公开的规范字段：resonance->stability.
- 证据：`skills/skill_050_bruised_echo.json`；`evidence/skill_050.json`；`tests/test_pilot_60.py`

## skill_051 · 错误赦免

- 身份：主动；Creator F；异常支援/组合标记
- 材料：`saint_slag`（fine / uncommon），词条 `saint_slag_license`
- 触发与成本：`on_use`；Mana 1；Duration 1
- 创造意图：主动治疗敌人并给它四 Tick 的增益标记；它甚至会周期回蓝。用途不是善良，而是制造一个可被另一技能识别的临时分类。
- 实际机制：heal -> target_actor (amount=8)；apply_status -> target_actor (status_id=mercy_mark)
- 测试场景：`wet_forest`；4 World Tick；变化步骤 [1, 2, 3, 4, 5]
- 实际观察：hero.mana: 45 -> 44；target.hp: 34 -> 42；target.mana: 45 -> 49
- 触发 Law：`pmw.v04.action.false_mercy.v1.eb69b4a059f8.cost`, `pmw.v04.action.false_mercy.v1.eb69b4a059f8.effect.heal_enemy`, `pmw.v04.action.false_mercy.v1.eb69b4a059f8.effect.mark_enemy`, `pmw.v04.dynamics.200.pilot_area.biomass.base.all`, `pmw.v04.dynamics.200.pilot_area.conductivity.base.all`, `pmw.v04.dynamics.200.pilot_area.electric_field.base.all`, `pmw.v04.dynamics.200.pilot_area.light.base.all`, `pmw.v04.dynamics.200.pilot_area.mist.base.all`, `pmw.v04.dynamics.200.pilot_area.ore.base.all`, `pmw.v04.dynamics.200.pilot_area.smoke.base.all`, `pmw.v04.dynamics.200.pilot_area.stability.base.all`, `pmw.v04.dynamics.200.pilot_area.temperature.base.all`
- 反例：未装备或错误 Trigger 被拒绝，WorldState 原子不变（`action is not an exact currently equipped active skill`）。
- 已知限制：敌人立即变强；只有后续构筑能回收投入。；动作不会自动推进世界时间；runner 对 baseline/treatment 使用相同 World Tick 预算。
- 证据：`skills/skill_051_false_mercy.json`；`evidence/skill_051.json`；`tests/test_pilot_60.py`

## skill_052 · 教义例外

- 身份：主动；Creator F；条件攻击/组合回收
- 材料：`heresy_needle`（rare / scarce），词条 `heresy_needle_license`
- 触发与成本：`on_use`；Mana 2；Duration 1
- 创造意图：只伤害带 recently_spared 特征的目标。单独装备几乎是死卡，和错误赦免组合后才成为可控窗口。
- 实际机制：damage -> target_actor (amount=11)，有条件
- 测试场景：`wet_forest`；2 World Tick；变化步骤 [1, 2, 3]
- 实际观察：hero.mana: 45 -> 43；target.hp: 34 -> 23
- 触发 Law：`pmw.v04.action.doctrinal_exception.v1.cae0b5bf6b3c.cost`, `pmw.v04.action.doctrinal_exception.v1.cae0b5bf6b3c.effect.punish_spared`, `pmw.v04.dynamics.200.pilot_area.biomass.base.all`, `pmw.v04.dynamics.200.pilot_area.conductivity.base.all`, `pmw.v04.dynamics.200.pilot_area.electric_field.base.all`, `pmw.v04.dynamics.200.pilot_area.light.base.all`, `pmw.v04.dynamics.200.pilot_area.mist.base.all`, `pmw.v04.dynamics.200.pilot_area.ore.base.all`, `pmw.v04.dynamics.200.pilot_area.smoke.base.all`, `pmw.v04.dynamics.200.pilot_area.stability.base.all`, `pmw.v04.dynamics.200.pilot_area.temperature.base.all`, `pmw.v04.dynamics.200.pilot_area.toxin.base.all`
- 反例：未装备或错误 Trigger 被拒绝，WorldState 原子不变（`action is not an exact currently equipped active skill`）。
- 已知限制：不满足标记时仍消耗行动时间与法力但不造成伤害。；动作不会自动推进世界时间；runner 对 baseline/treatment 使用相同 World Tick 预算。
- 证据：`skills/skill_052_doctrinal_exception.json`；`evidence/skill_052.json`；`tests/test_pilot_60.py`

## skill_053 · 寡妇的最后一根火柴

- 身份：主动；Creator F；微伤害/天气引信
- 材料：`widow_match`（common / abundant），词条 `widow_match_license`
- 触发与成本：`on_use`；Mana 1；Duration 1
- 创造意图：直接伤害故意只有 1；主要作用是制造烟幕，让公开天气 Law 在后续 Tick 困住热量，并可能进一步触发热旱。
- 实际机制：damage -> target_actor (amount=1)；modify_field -> current_area (amount=0.45, field_id=smoke)
- 测试场景：`dry_basin`；4 World Tick；变化步骤 [1, 2, 3, 4, 5]
- 实际观察：hero.mana: 45 -> 44；target.hp: 80 -> 79；field.smoke.value: 0.328066 -> 0.650443；field.temperature.value: 72.083 -> 85.9147
- 触发 Law：`pmw.v04.action.widows_last_match.v1.bb35d2cd6a9f.cost`, `pmw.v04.action.widows_last_match.v1.bb35d2cd6a9f.effect.almost_no_burn`, `pmw.v04.action.widows_last_match.v1.bb35d2cd6a9f.effect.smoke_signal`, `pmw.v04.dynamics.200.pilot_area.biomass.base.all`, `pmw.v04.dynamics.200.pilot_area.conductivity.base.all`, `pmw.v04.dynamics.200.pilot_area.electric_field.base.all`, `pmw.v04.dynamics.200.pilot_area.light.base.all`, `pmw.v04.dynamics.200.pilot_area.mist.base.all`, `pmw.v04.dynamics.200.pilot_area.ore.base.all`, `pmw.v04.dynamics.200.pilot_area.smoke.base.all`, `pmw.v04.dynamics.200.pilot_area.stability.base.all`, `pmw.v04.dynamics.200.pilot_area.temperature.base.all`
- 反例：未装备或错误 Trigger 被拒绝，WorldState 原子不变（`action is not an exact currently equipped active skill`）。
- 已知限制：慢、公开、会污染所有人的场地。；动作不会自动推进世界时间；runner 对 baseline/treatment 使用相同 World Tick 预算。
- 证据：`skills/skill_053_widows_last_match.json`；`evidence/skill_053.json`；`tests/test_pilot_60.py`

## skill_054 · 无菌花期

- 身份：主动；Creator F；治疗/生态交换
- 材料：`sterile_seed`（fine / uncommon），词条 `sterile_seed_license`
- 触发与成本：`on_use`；Mana 1；Duration 1
- 创造意图：以区域生物量换取治疗。治疗发生在自己身上，生态代价留给整片区域，之后由自然恢复承担。
- 实际机制：heal -> self (amount=9)；modify_field -> current_area (amount=-0.3, field_id=biomass)
- 测试场景：`lush_grove`；3 World Tick；变化步骤 [1, 2, 3, 4]
- 实际观察：hero.hp: 35 -> 44；hero.mana: 45 -> 44；field.biomass.value: 0.729098 -> 0.495492；field.toxin.value: 0.034631 -> 0.172951；weather state differs; inspect the evidence timeline
- 触发 Law：`pmw.v04.action.sterile_bloom.v1.60d7fba3da20.cost`, `pmw.v04.action.sterile_bloom.v1.60d7fba3da20.effect.bloom_heal`, `pmw.v04.action.sterile_bloom.v1.60d7fba3da20.effect.sterilize_soil`, `pmw.v04.dynamics.200.pilot_area.biomass.base.all`, `pmw.v04.dynamics.200.pilot_area.conductivity.base.all`, `pmw.v04.dynamics.200.pilot_area.electric_field.base.all`, `pmw.v04.dynamics.200.pilot_area.light.base.all`, `pmw.v04.dynamics.200.pilot_area.mist.base.all`, `pmw.v04.dynamics.200.pilot_area.ore.base.all`, `pmw.v04.dynamics.200.pilot_area.smoke.base.all`, `pmw.v04.dynamics.200.pilot_area.stability.base.all`, `pmw.v04.dynamics.200.pilot_area.temperature.base.all`
- 反例：未装备或错误 Trigger 被拒绝，WorldState 原子不变（`action is not an exact currently equipped active skill`）。
- 已知限制：连续使用会压低生态存量；收益不是免费的治疗。；动作不会自动推进世界时间；runner 对 baseline/treatment 使用相同 World Tick 预算。
- 证据：`skills/skill_054_sterile_bloom.json`；`evidence/skill_054.json`；`tests/test_pilot_60.py`

## skill_055 · 湿纸甲

- 身份：主动；Creator F；条件防御/公共资源
- 材料：`paper_kelp`（common / abundant），词条 `paper_kelp_license`
- 触发与成本：`on_use`；Mana 1；Duration 1
- 创造意图：只有足够潮湿时纸甲才成立；它吸走水分形成护盾，同时主动破坏自己下一次施放条件。
- 实际机制：shield -> self (amount=9)，有条件；modify_field -> current_area (amount=-0.35, field_id=wetness)，有条件
- 测试场景：`wet_forest`；3 World Tick；变化步骤 [1, 2, 3, 4]
- 实际观察：hero.mana: 45 -> 44；hero.shield: 0 -> 9；hero.shield_layers: [{"active": true, "granted": 9.0, "layer_id": "slot_0", "owner_id": "pilot_hero", "remaining": 9.0, "sequence": 1, "source_id": "wet_paper_armor:paper_shield", "status_instance_id": null}]；field.temperature.value: 31.3957 -> 42.9221；field.wetness.value: 0.718033 -> 0.445492；weather state differs; inspect the evidence timeline
- 触发 Law：`pmw.v04.action.wet_paper_armor.v1.8a6ae525c348.cost`, `pmw.v04.action.wet_paper_armor.v1.8a6ae525c348.effect.drink_puddle`, `pmw.v04.action.wet_paper_armor.v1.8a6ae525c348.effect.paper_shield`, `pmw.v04.dynamics.200.pilot_area.biomass.base.all`, `pmw.v04.dynamics.200.pilot_area.conductivity.base.all`, `pmw.v04.dynamics.200.pilot_area.electric_field.base.all`, `pmw.v04.dynamics.200.pilot_area.light.base.all`, `pmw.v04.dynamics.200.pilot_area.mist.base.all`, `pmw.v04.dynamics.200.pilot_area.ore.base.all`, `pmw.v04.dynamics.200.pilot_area.smoke.base.all`, `pmw.v04.dynamics.200.pilot_area.stability.base.all`, `pmw.v04.dynamics.200.pilot_area.temperature.base.all`
- 反例：未装备或错误 Trigger 被拒绝，WorldState 原子不变（`action is not an exact currently equipped active skill`）。
- 已知限制：干区近乎空技能；护盾以公共湿度为代价。；动作不会自动推进世界时间；runner 对 baseline/treatment 使用相同 World Tick 预算。
- 证据：`skills/skill_055_wet_paper_armor.json`；`evidence/skill_055.json`；`tests/test_pilot_60.py`

## skill_056 · 发酵法力

- 身份：主动；Creator F；延迟生命债
- 材料：`dream_yeast`（rare / uncommon），词条 `dream_yeast_license`
- 触发与成本：`on_use`；Mana 0；Duration 1
- 创造意图：立即借来法力，随后 fermentation_debt 每 Tick 扣血三次。它把资源曲线从先付费改成后付生命。
- 实际机制：add_resource -> self (amount=8, resource=mana)；apply_status -> self (status_id=fermentation_debt)
- 测试场景：`dry_basin`；3 World Tick；变化步骤 [1, 2, 3, 4]
- 实际观察：hero.hp: 42 -> 33；hero.mana: 45 -> 53
- 触发 Law：`pmw.v04.action.fermentation_mana.v1.374175e1578e.cost`, `pmw.v04.action.fermentation_mana.v1.374175e1578e.effect.take_debt`, `pmw.v04.dynamics.200.pilot_area.biomass.base.all`, `pmw.v04.dynamics.200.pilot_area.conductivity.base.all`, `pmw.v04.dynamics.200.pilot_area.electric_field.base.all`, `pmw.v04.dynamics.200.pilot_area.light.base.all`, `pmw.v04.dynamics.200.pilot_area.mist.base.all`, `pmw.v04.dynamics.200.pilot_area.ore.base.all`, `pmw.v04.dynamics.200.pilot_area.smoke.base.all`, `pmw.v04.dynamics.200.pilot_area.stability.base.all`, `pmw.v04.dynamics.200.pilot_area.temperature.base.all`, `pmw.v04.dynamics.200.pilot_area.toxin.base.all`
- 反例：未装备或错误 Trigger 被拒绝，WorldState 原子不变（`action is not an exact currently equipped active skill`）。
- 已知限制：总计九点生命债，不能把后果写成免费回蓝。；动作不会自动推进世界时间；runner 对 baseline/treatment 使用相同 World Tick 预算。
- 证据：`skills/skill_056_fermentation_mana.json`；`evidence/skill_056.json`；`tests/test_pilot_60.py`

## skill_057 · 冷敷终止器

- 身份：主动；Creator F；自关闭环境治疗
- 材料：`winter_moss`（fine / scarce），词条 `winter_moss_license`
- 触发与成本：`on_use`；Mana 1；Duration 1
- 创造意图：极冷环境中的急救术：低温换治疗并把区域升温。它成功一次后往往自行关闭成立条件。
- 实际机制：heal -> self (amount=7)，有条件；modify_field -> current_area (amount=15, field_id=temperature)，有条件
- 测试场景：`frozen_hollow`；3 World Tick；变化步骤 [1, 2, 3, 4]
- 实际观察：hero.hp: 35 -> 42；hero.mana: 45 -> 44；field.temperature.value: 10.1869 -> 23.4579
- 触发 Law：`pmw.v04.action.cold_poultice.v1.8fc57b1d277f.cost`, `pmw.v04.action.cold_poultice.v1.8fc57b1d277f.effect.cold_heal`, `pmw.v04.action.cold_poultice.v1.8fc57b1d277f.effect.spend_cold`, `pmw.v04.dynamics.200.pilot_area.biomass.base.all`, `pmw.v04.dynamics.200.pilot_area.conductivity.base.all`, `pmw.v04.dynamics.200.pilot_area.electric_field.base.all`, `pmw.v04.dynamics.200.pilot_area.light.base.all`, `pmw.v04.dynamics.200.pilot_area.mist.base.all`, `pmw.v04.dynamics.200.pilot_area.ore.base.all`, `pmw.v04.dynamics.200.pilot_area.smoke.base.all`, `pmw.v04.dynamics.200.pilot_area.stability.base.all`, `pmw.v04.dynamics.200.pilot_area.temperature.base.all`
- 反例：未装备或错误 Trigger 被拒绝，WorldState 原子不变（`action is not an exact currently equipped active skill`）。
- 已知限制：常温完全无效；治疗会消耗珍贵的低温窗口。；动作不会自动推进世界时间；runner 对 baseline/treatment 使用相同 World Tick 预算。
- 证据：`skills/skill_057_cold_poultice.json`；`evidence/skill_057.json`；`tests/test_pilot_60.py`

## skill_058 · 死潮钟

- 身份：主动；Creator F；延迟场动力学
- 材料：`tide_clock`（epic / unique），词条 `tide_clock_license`
- 触发与成本：`on_use`；Mana 3；Duration 1
- 创造意图：不直接抽走水，而是四 Tick 改写湿度吸引子并加快向低目标演化，制造迟到且可逆的低潮。
- 实际机制：modify_attractor -> current_area (amount=0.1, field_id=wetness, duration=4)；modify_rate -> current_area (amount=0.08, field_id=wind, duration=4)
- 测试场景：`wet_forest`；5 World Tick；变化步骤 [1, 2, 3, 4, 5, 6]
- 实际观察：hero.mana: 45 -> 42；field.wetness.value: 0.684543 -> 0.647079；field.wind.value: 0.368184 -> 0.399667
- 触发 Law：`pmw.v04.action.dead_tide_clock.v1.52988d03c549.cost`, `pmw.v04.action.dead_tide_clock.v1.52988d03c549.effect.hasten_drying_wind.slot_0.apply`, `pmw.v04.action.dead_tide_clock.v1.52988d03c549.effect.low_tide_target.slot_0.apply`, `pmw.v04.dynamics.200.pilot_area.biomass.base.all`, `pmw.v04.dynamics.200.pilot_area.conductivity.base.all`, `pmw.v04.dynamics.200.pilot_area.electric_field.base.all`, `pmw.v04.dynamics.200.pilot_area.light.base.all`, `pmw.v04.dynamics.200.pilot_area.mist.base.all`, `pmw.v04.dynamics.200.pilot_area.ore.base.all`, `pmw.v04.dynamics.200.pilot_area.smoke.base.all`, `pmw.v04.dynamics.200.pilot_area.stability.base.all`, `pmw.v04.dynamics.200.pilot_area.temperature.base.all`
- 反例：未装备或错误 Trigger 被拒绝，WorldState 原子不变（`action is not an exact currently equipped active skill`）。
- 已知限制：无即时收益；临时 modifier 占槽且到期后世界会回归。；动作不会自动推进世界时间；runner 对 baseline/treatment 使用相同 World Tick 预算。；策展修订：原稿在同一动作中让 wetness 的 attractor 与 rate 争用同一临时槽；速率副作用改为 wind，避免后写覆盖前写。
- 证据：`skills/skill_058_dead_tide_clock.json`；`evidence/skill_058.json`；`tests/test_pilot_60.py`

## skill_059 · 静默钟

- 身份：主动；Creator F；公共风险清除
- 材料：`silence_bronze`（fine / uncommon），词条 `silence_bronze_license`
- 触发与成本：`on_use`；Mana 0；Duration 1
- 创造意图：在浓烟中支付四点法力来清除烟幕，目标是切断烟雾天气的后续热反馈，而不是攻击任何人。
- 实际机制：add_resource -> self (amount=-4, resource=mana)，有条件；modify_field -> current_area (amount=-0.4, field_id=smoke)，有条件
- 测试场景：`depleted_grove`；4 World Tick；变化步骤 [1, 2, 3, 4, 5]
- 实际观察：hero.mana: 45 -> 41；field.smoke.value: 0.442689 -> 0.156131
- 触发 Law：`pmw.v04.action.quiet_bell.v1.35a4c27d3995.cost`, `pmw.v04.action.quiet_bell.v1.35a4c27d3995.effect.drop_smoke`, `pmw.v04.dynamics.200.pilot_area.biomass.base.all`, `pmw.v04.dynamics.200.pilot_area.conductivity.base.all`, `pmw.v04.dynamics.200.pilot_area.electric_field.base.all`, `pmw.v04.dynamics.200.pilot_area.light.base.all`, `pmw.v04.dynamics.200.pilot_area.mist.base.all`, `pmw.v04.dynamics.200.pilot_area.ore.base.all`, `pmw.v04.dynamics.200.pilot_area.smoke.base.all`, `pmw.v04.dynamics.200.pilot_area.stability.base.all`, `pmw.v04.dynamics.200.pilot_area.temperature.base.all`, `pmw.v04.dynamics.200.pilot_area.toxin.base.all`
- 反例：未装备或错误 Trigger 被拒绝，WorldState 原子不变（`action is not an exact currently equipped active skill`）。
- 已知限制：无烟时是空动作；主动牺牲个人资源换公共环境降风险。；动作不会自动推进世界时间；runner 对 baseline/treatment 使用相同 World Tick 预算。
- 证据：`skills/skill_059_quiet_bell.json`；`evidence/skill_059.json`；`tests/test_pilot_60.py`

## skill_060 · 热病钥匙

- 身份：主动；Creator F；自伤/天气引信
- 材料：`fever_key`（rare / scarce），词条 `fever_key_license`
- 触发与成本：`on_use`；Mana 1；Duration 1
- 创造意图：伤害自己五点，将环境推过高温天气阈值。自伤是启动公共世界过程的钥匙，敌我都会承受后续干燥。
- 实际机制：damage -> self (amount=5)；modify_field -> current_area (amount=25, field_id=temperature)
- 测试场景：`fever_marsh`；4 World Tick；变化步骤 [1, 2, 3, 4, 5]
- 实际观察：hero.hp: 50 -> 45；hero.mana: 45 -> 44；field.biomass.value: 0.657459 -> 0.515655；field.temperature.value: 39.1814 -> 60.4151；weather state differs; inspect the evidence timeline
- 触发 Law：`pmw.v04.action.fever_key.v1.e59174dc9d81.cost`, `pmw.v04.action.fever_key.v1.e59174dc9d81.effect.turn_key_in_flesh`, `pmw.v04.action.fever_key.v1.e59174dc9d81.effect.unlock_heat`, `pmw.v04.dynamics.200.pilot_area.biomass.base.all`, `pmw.v04.dynamics.200.pilot_area.conductivity.base.all`, `pmw.v04.dynamics.200.pilot_area.electric_field.base.all`, `pmw.v04.dynamics.200.pilot_area.light.base.all`, `pmw.v04.dynamics.200.pilot_area.mist.base.all`, `pmw.v04.dynamics.200.pilot_area.ore.base.all`, `pmw.v04.dynamics.200.pilot_area.smoke.base.all`, `pmw.v04.dynamics.200.pilot_area.stability.base.all`, `pmw.v04.dynamics.200.pilot_area.temperature.base.all`
- 反例：未装备或错误 Trigger 被拒绝，WorldState 原子不变（`action is not an exact currently equipped active skill`）。
- 已知限制：个人生命换不可专属的场地变化，可能帮助依赖干燥的敌人。；动作不会自动推进世界时间；runner 对 baseline/treatment 使用相同 World Tick 预算。
- 证据：`skills/skill_060_fever_key.json`；`evidence/skill_060.json`；`tests/test_pilot_60.py`
