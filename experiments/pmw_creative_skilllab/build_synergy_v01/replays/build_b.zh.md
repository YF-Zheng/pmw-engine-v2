# build_b · 人工雨场与湿纸甲 Replay

目标：四轮敌方攻击下，用相同的行动机会最大化最终 HP 与剩余护盾。

技能：skill_041, skill_055；敌方行动：`basic_attack`；每臂 4 个正式 Combat Round。

## 场景 `threshold_dry`

环境：`dry_basin`；覆盖值：`{"electric_field": 0.3, "smoke": 0.1, "temperature": 55, "wetness": 0.55}`；初始资源：`{"hero_hp": 80, "hero_mana": 45, "target_hp": 80, "target_mana": 20, "target_traits": []}`。

### `a_only`

|轮|请求动作|实际动作|拒绝|Hero HP/Mana/Shield|Target HP|Wet|Elec|Smoke|Temp|Biomass|生态|天气|Hook|
|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---:|
|1|`storm_seed_conductor`|`storm_seed_conductor`|-|68/42/0|80|0.776|0.518|0.132|50.80|0.338|balanced|rain_front|0|
|2|`basic_wait`|`basic_wait`|-|56/48/0|80|0.754|0.517|0.161|46.77|0.355|balanced|rain_front|0|
|3|`basic_wait`|`basic_wait`|-|44/54/0|80|0.734|0.516|0.189|42.90|0.371|balanced|rain_front|0|
|4|`basic_wait`|`basic_wait`|-|32/60/0|80|0.715|0.514|0.213|39.18|0.385|balanced|rain_front|0|

终局：target_damage=0, hero_hp_loss=48, final_ecology=balanced, weather=['rain_front'], rejections=0

### `a_then_b`

|轮|请求动作|实际动作|拒绝|Hero HP/Mana/Shield|Target HP|Wet|Elec|Smoke|Temp|Biomass|生态|天气|Hook|
|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---:|
|1|`storm_seed_conductor`|`storm_seed_conductor`|-|68/42/0|80|0.776|0.518|0.132|50.80|0.338|balanced|rain_front|0|
|2|`wet_paper_armor`|`wet_paper_armor`|-|65/42/0|80|0.432|0.517|0.161|50.77|0.355|balanced|-|0|
|3|`basic_wait`|`basic_wait`|-|53/48/0|80|0.437|0.516|0.189|50.74|0.371|balanced|-|0|
|4|`basic_wait`|`basic_wait`|-|41/54/0|80|0.442|0.514|0.213|50.71|0.385|balanced|-|0|

终局：target_damage=0, hero_hp_loss=39, final_ecology=balanced, weather=['rain_front'], rejections=0

### `b_only`

|轮|请求动作|实际动作|拒绝|Hero HP/Mana/Shield|Target HP|Wet|Elec|Smoke|Temp|Biomass|生态|天气|Hook|
|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---:|
|1|`wet_paper_armor`|`wet_paper_armor`|-|68/44/0|80|0.546|0.316|0.132|54.80|0.338|balanced|-|0|
|2|`basic_wait`|`basic_wait`|-|56/49/0|80|0.542|0.331|0.161|54.61|0.355|balanced|-|0|
|3|`basic_wait`|`basic_wait`|-|44/54/0|80|0.539|0.344|0.189|54.42|0.371|balanced|-|0|
|4|`basic_wait`|`basic_wait`|-|32/59/0|80|0.536|0.357|0.213|54.25|0.385|balanced|-|0|

终局：target_damage=0, hero_hp_loss=48, final_ecology=balanced, weather=[], rejections=0

### `b_then_a`

|轮|请求动作|实际动作|拒绝|Hero HP/Mana/Shield|Target HP|Wet|Elec|Smoke|Temp|Biomass|生态|天气|Hook|
|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---:|
|1|`wet_paper_armor`|`wet_paper_armor`|-|68/44/0|80|0.546|0.316|0.132|54.80|0.338|balanced|-|0|
|2|`storm_seed_conductor`|`storm_seed_conductor`|-|56/41/0|80|0.772|0.533|0.161|50.61|0.355|balanced|rain_front|0|
|3|`basic_wait`|`basic_wait`|-|44/47/0|80|0.751|0.530|0.189|46.58|0.371|balanced|rain_front|0|
|4|`basic_wait`|`basic_wait`|-|32/53/0|80|0.730|0.528|0.213|42.72|0.385|balanced|rain_front|0|

终局：target_damage=0, hero_hp_loss=48, final_ecology=balanced, weather=['rain_front'], rejections=0

### `matched_alternative`

|轮|请求动作|实际动作|拒绝|Hero HP/Mana/Shield|Target HP|Wet|Elec|Smoke|Temp|Biomass|生态|天气|Hook|
|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---:|
|1|`basic_guard`|`basic_guard`|-|75/45/0|80|0.546|0.316|0.132|54.80|0.338|balanced|-|0|
|2|`basic_guard`|`basic_guard`|-|70/45/0|80|0.542|0.331|0.161|54.61|0.355|balanced|-|0|
|3|`basic_wait`|`basic_wait`|-|58/50/0|80|0.539|0.344|0.189|54.42|0.371|balanced|-|0|
|4|`basic_wait`|`basic_wait`|-|46/55/0|80|0.536|0.357|0.213|54.25|0.385|balanced|-|0|

终局：target_damage=0, hero_hp_loss=34, final_ecology=balanced, weather=[], rejections=0

### `no_skill`

|轮|请求动作|实际动作|拒绝|Hero HP/Mana/Shield|Target HP|Wet|Elec|Smoke|Temp|Biomass|生态|天气|Hook|
|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---:|
|1|`basic_wait`|`basic_wait`|-|68/50/0|80|0.546|0.316|0.132|54.80|0.338|balanced|-|0|
|2|`basic_wait`|`basic_wait`|-|56/55/0|80|0.542|0.331|0.161|54.61|0.355|balanced|-|0|
|3|`basic_wait`|`basic_wait`|-|44/60/0|80|0.539|0.344|0.189|54.42|0.371|balanced|-|0|
|4|`basic_wait`|`basic_wait`|-|32/60/0|80|0.536|0.357|0.213|54.25|0.385|balanced|-|0|

终局：target_damage=0, hero_hp_loss=48, final_ecology=balanced, weather=[], rejections=0

## 判定

`MECHANICALLY_INTERESTING`：引雷播种把原本不足的湿度推过纸甲门槛并少损失 9 HP，但两次 Guard 少损失 14 HP。
