# build_c · 制造风暴并转成防御 Replay

目标：主动制造天气事件，并在四轮敌方攻击下把它转成可验证的防御收益。

技能：skill_041, skill_049；敌方行动：`basic_attack`；每臂 4 个正式 Combat Round。

被动分发：`manual_trusted_hook_dispatch`。只有 World Tick Trace 中真实出现 `pmw.v04.weather.changed` 派生事件时才调用公共 Hook Executor。

## 场景 `storm_threshold`

环境：`dry_basin`；覆盖值：`{"electric_field": 0.5, "smoke": 0.1, "temperature": 50, "wetness": 0.3}`；初始资源：`{"hero_hp": 80, "hero_mana": 45, "target_hp": 80, "target_mana": 20, "target_traits": []}`。

### `a_only`

|轮|请求动作|实际动作|拒绝|Hero HP/Mana/Shield|Target HP|Wet|Elec|Smoke|Temp|Biomass|生态|天气|Hook|
|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---:|
|1|`storm_seed_conductor`|`storm_seed_conductor`|-|68/42/0|80|0.616|0.702|0.132|50.00|0.338|balanced|thunderfront|0|
|2|`basic_wait`|`basic_wait`|-|56/48/0|80|0.677|0.686|0.161|50.00|0.355|balanced|thunderfront|0|
|3|`basic_wait`|`basic_wait`|-|44/54/0|80|0.733|0.671|0.189|46.00|0.371|balanced|rain_front,thunderfront|0|
|4|`basic_wait`|`basic_wait`|-|32/60/0|80|0.784|0.658|0.213|42.16|0.385|balanced|rain_front,thunderfront|0|

终局：target_damage=0, hero_hp_loss=48, final_ecology=balanced, weather=['rain_front', 'thunderfront'], rejections=0

### `a_then_b`

|轮|请求动作|实际动作|拒绝|Hero HP/Mana/Shield|Target HP|Wet|Elec|Smoke|Temp|Biomass|生态|天气|Hook|
|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---:|
|1|`storm_seed_conductor`|`storm_seed_conductor`|-|68/42/5|80|0.616|0.582|0.132|50.00|0.338|balanced|thunderfront|1|
|2|`basic_wait`|`basic_wait`|-|61/48/0|80|0.677|0.576|0.161|50.00|0.355|balanced|thunderfront|0|
|3|`basic_wait`|`basic_wait`|-|49/54/5|80|0.733|0.450|0.189|46.00|0.371|balanced|rain_front,thunderfront|1|
|4|`basic_wait`|`basic_wait`|-|42/60/0|80|0.784|0.454|0.213|42.16|0.385|balanced|rain_front,thunderfront|0|

终局：target_damage=0, hero_hp_loss=38, final_ecology=balanced, weather=['rain_front', 'thunderfront'], rejections=0

### `b_only`

|轮|请求动作|实际动作|拒绝|Hero HP/Mana/Shield|Target HP|Wet|Elec|Smoke|Temp|Biomass|生态|天气|Hook|
|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---:|
|1|`basic_wait`|`basic_wait`|-|68/50/0|80|0.316|0.500|0.132|50.00|0.338|balanced|-|0|
|2|`basic_wait`|`basic_wait`|-|56/55/0|80|0.331|0.500|0.161|50.00|0.355|balanced|-|0|
|3|`basic_wait`|`basic_wait`|-|44/60/0|80|0.344|0.500|0.189|50.00|0.371|balanced|-|0|
|4|`basic_wait`|`basic_wait`|-|32/60/0|80|0.357|0.500|0.213|50.00|0.385|balanced|-|0|

终局：target_damage=0, hero_hp_loss=48, final_ecology=balanced, weather=[], rejections=0

### `b_then_a`

|轮|请求动作|实际动作|拒绝|Hero HP/Mana/Shield|Target HP|Wet|Elec|Smoke|Temp|Biomass|生态|天气|Hook|
|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---:|
|1|`basic_wait`|`basic_wait`|-|68/50/0|80|0.316|0.500|0.132|50.00|0.338|balanced|-|0|
|2|`storm_seed_conductor`|`storm_seed_conductor`|-|56/47/5|80|0.631|0.582|0.161|50.00|0.355|balanced|thunderfront|1|
|3|`basic_wait`|`basic_wait`|-|49/53/0|80|0.690|0.576|0.189|50.00|0.371|balanced|thunderfront|0|
|4|`basic_wait`|`basic_wait`|-|37/59/5|80|0.745|0.450|0.213|46.00|0.385|balanced|rain_front,thunderfront|1|

终局：target_damage=0, hero_hp_loss=43, final_ecology=balanced, weather=['rain_front', 'thunderfront'], rejections=0

### `matched_alternative`

|轮|请求动作|实际动作|拒绝|Hero HP/Mana/Shield|Target HP|Wet|Elec|Smoke|Temp|Biomass|生态|天气|Hook|
|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---:|
|1|`basic_guard`|`basic_guard`|-|75/45/0|80|0.316|0.500|0.132|50.00|0.338|balanced|-|0|
|2|`basic_wait`|`basic_wait`|-|63/50/0|80|0.331|0.500|0.161|50.00|0.355|balanced|-|0|
|3|`basic_wait`|`basic_wait`|-|51/55/0|80|0.344|0.500|0.189|50.00|0.371|balanced|-|0|
|4|`basic_wait`|`basic_wait`|-|39/60/0|80|0.357|0.500|0.213|50.00|0.385|balanced|-|0|

终局：target_damage=0, hero_hp_loss=41, final_ecology=balanced, weather=[], rejections=0

### `no_skill`

|轮|请求动作|实际动作|拒绝|Hero HP/Mana/Shield|Target HP|Wet|Elec|Smoke|Temp|Biomass|生态|天气|Hook|
|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---:|
|1|`basic_wait`|`basic_wait`|-|68/50/0|80|0.316|0.500|0.132|50.00|0.338|balanced|-|0|
|2|`basic_wait`|`basic_wait`|-|56/55/0|80|0.331|0.500|0.161|50.00|0.355|balanced|-|0|
|3|`basic_wait`|`basic_wait`|-|44/60/0|80|0.344|0.500|0.189|50.00|0.371|balanced|-|0|
|4|`basic_wait`|`basic_wait`|-|32/60/0|80|0.357|0.500|0.213|50.00|0.385|balanced|-|0|

终局：target_damage=0, hero_hp_loss=48, final_ecology=balanced, weather=[], rejections=0

## 判定

`PLAYABLE_BUILD`：播种产生真实天气事件，继电器把事件转成防御并优于一次 Guard；泄放电场又会削弱风暴，是可玩的取舍。
