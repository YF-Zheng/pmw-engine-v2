# build_d · 烟幕积累与热浪放大 Replay

目标：在两次准备行动内触发烟雾热锋，同时比较护盾、伤害和公共升温代价。

技能：skill_005, skill_053；敌方行动：`basic_attack`；每臂 4 个正式 Combat Round。

## 场景 `sensitive_threshold`

环境：`dry_basin`；覆盖值：`{"smoke": 0.05, "temperature": 60, "wetness": 0.25}`；初始资源：`{"hero_hp": 80, "hero_mana": 45, "target_hp": 80, "target_mana": 20, "target_traits": []}`。

### `a_only`

|轮|请求动作|实际动作|拒绝|Hero HP/Mana/Shield|Target HP|Wet|Elec|Smoke|Temp|Biomass|生态|天气|Hook|
|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---:|
|1|`ash_veil`|`ash_veil`|-|74/43/0|80|0.270|0.224|0.408|59.60|0.338|balanced|-|0|
|2|`basic_wait`|`basic_wait`|-|62/48/0|80|0.288|0.246|0.415|59.22|0.355|balanced|-|0|
|3|`basic_wait`|`basic_wait`|-|50/53/0|80|0.305|0.266|0.422|58.85|0.371|balanced|-|0|
|4|`basic_wait`|`basic_wait`|-|38/58/0|80|0.321|0.285|0.428|58.49|0.385|balanced|-|0|

终局：target_damage=0, hero_hp_loss=42, final_ecology=balanced, weather=[], rejections=0

### `a_then_b`

|轮|请求动作|实际动作|拒绝|Hero HP/Mana/Shield|Target HP|Wet|Elec|Smoke|Temp|Biomass|生态|天气|Hook|
|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---:|
|1|`ash_veil`|`ash_veil`|-|74/43/0|80|0.270|0.224|0.408|59.60|0.338|balanced|-|0|
|2|`widows_last_match`|`widows_last_match`|-|62/42/0|79|0.288|0.246|0.829|64.22|0.355|balanced|smoke_heat_front|0|
|3|`basic_wait`|`basic_wait`|-|50/47/0|79|0.305|0.266|0.803|68.65|0.371|balanced|smoke_heat_front|0|
|4|`basic_wait`|`basic_wait`|-|38/52/0|79|0.321|0.285|0.779|72.90|0.385|balanced|smoke_heat_front|0|

终局：target_damage=1, hero_hp_loss=42, final_ecology=balanced, weather=['smoke_heat_front'], rejections=0

### `b_only`

|轮|请求动作|实际动作|拒绝|Hero HP/Mana/Shield|Target HP|Wet|Elec|Smoke|Temp|Biomass|生态|天气|Hook|
|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---:|
|1|`widows_last_match`|`widows_last_match`|-|68/44/0|79|0.270|0.224|0.500|64.60|0.338|balanced|smoke_heat_front|0|
|2|`basic_wait`|`basic_wait`|-|56/49/0|79|0.288|0.246|0.500|69.02|0.355|balanced|smoke_heat_front|0|
|3|`basic_wait`|`basic_wait`|-|44/54/0|79|0.305|0.266|0.500|73.26|0.371|balanced|smoke_heat_front|0|
|4|`basic_wait`|`basic_wait`|-|32/59/0|79|0.321|0.285|0.500|72.33|0.345|balanced|heat_haze|0|

终局：target_damage=1, hero_hp_loss=48, final_ecology=balanced, weather=['heat_haze', 'smoke_heat_front'], rejections=0

### `b_then_a`

|轮|请求动作|实际动作|拒绝|Hero HP/Mana/Shield|Target HP|Wet|Elec|Smoke|Temp|Biomass|生态|天气|Hook|
|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---:|
|1|`widows_last_match`|`widows_last_match`|-|68/44/0|79|0.270|0.224|0.500|64.60|0.338|balanced|smoke_heat_front|0|
|2|`ash_veil`|`ash_veil`|-|62/42/0|79|0.288|0.246|0.822|69.02|0.355|balanced|smoke_heat_front|0|
|3|`basic_wait`|`basic_wait`|-|50/47/0|79|0.305|0.266|0.796|73.26|0.371|balanced|smoke_heat_front|0|
|4|`basic_wait`|`basic_wait`|-|38/52/0|79|0.321|0.285|0.773|72.33|0.345|balanced|heat_haze|0|

终局：target_damage=1, hero_hp_loss=42, final_ecology=balanced, weather=['heat_haze', 'smoke_heat_front'], rejections=0

### `matched_alternative`

|轮|请求动作|实际动作|拒绝|Hero HP/Mana/Shield|Target HP|Wet|Elec|Smoke|Temp|Biomass|生态|天气|Hook|
|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---:|
|1|`basic_guard`|`basic_guard`|-|75/45/0|80|0.270|0.224|0.086|59.60|0.338|balanced|-|0|
|2|`basic_attack`|`basic_attack`|-|63/45/0|68|0.288|0.246|0.119|59.22|0.355|balanced|-|0|
|3|`basic_wait`|`basic_wait`|-|51/50/0|68|0.305|0.266|0.150|58.85|0.371|balanced|-|0|
|4|`basic_wait`|`basic_wait`|-|39/55/0|68|0.321|0.285|0.178|58.49|0.385|balanced|-|0|

终局：target_damage=12, hero_hp_loss=41, final_ecology=balanced, weather=[], rejections=0

### `no_skill`

|轮|请求动作|实际动作|拒绝|Hero HP/Mana/Shield|Target HP|Wet|Elec|Smoke|Temp|Biomass|生态|天气|Hook|
|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---:|
|1|`basic_wait`|`basic_wait`|-|68/50/0|80|0.270|0.224|0.086|59.60|0.338|balanced|-|0|
|2|`basic_wait`|`basic_wait`|-|56/55/0|80|0.288|0.246|0.119|59.22|0.355|balanced|-|0|
|3|`basic_wait`|`basic_wait`|-|44/60/0|80|0.305|0.266|0.150|58.85|0.371|balanced|-|0|
|4|`basic_wait`|`basic_wait`|-|32/60/0|80|0.321|0.285|0.178|58.49|0.385|balanced|-|0|

终局：target_damage=0, hero_hp_loss=48, final_ecology=balanced, weather=[], rejections=0

## 场景 `weather_absent_counterexample`

环境：`frozen_hollow`；覆盖值：`{"smoke": 0.0, "temperature": 20, "wetness": 0.4}`；初始资源：`{"hero_hp": 80, "hero_mana": 45, "target_hp": 80, "target_mana": 20, "target_traits": []}`。

### `a_only`

|轮|请求动作|实际动作|拒绝|Hero HP/Mana/Shield|Target HP|Wet|Elec|Smoke|Temp|Biomass|生态|天气|Hook|
|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---:|
|1|`ash_veil`|`ash_veil`|-|74/43/0|80|0.408|0.187|0.362|21.20|0.320|balanced|-|0|
|2|`basic_wait`|`basic_wait`|-|62/48/0|80|0.415|0.212|0.373|22.35|0.338|stressed|-|0|
|3|`basic_wait`|`basic_wait`|-|50/53/0|80|0.422|0.235|0.383|23.46|0.336|stressed|-|0|
|4|`basic_wait`|`basic_wait`|-|38/58/0|80|0.428|0.256|0.393|24.52|0.333|stressed|-|0|

终局：target_damage=0, hero_hp_loss=42, final_ecology=stressed, weather=[], rejections=0

### `a_then_b`

|轮|请求动作|实际动作|拒绝|Hero HP/Mana/Shield|Target HP|Wet|Elec|Smoke|Temp|Biomass|生态|天气|Hook|
|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---:|
|1|`ash_veil`|`ash_veil`|-|74/43/0|80|0.408|0.187|0.362|21.20|0.320|balanced|-|0|
|2|`widows_last_match`|`widows_last_match`|-|62/42/0|79|0.415|0.212|0.787|22.35|0.338|stressed|-|0|
|3|`basic_wait`|`basic_wait`|-|50/47/0|79|0.422|0.235|0.764|23.46|0.336|stressed|-|0|
|4|`basic_wait`|`basic_wait`|-|38/52/0|79|0.428|0.256|0.743|24.52|0.333|stressed|-|0|

终局：target_damage=1, hero_hp_loss=42, final_ecology=stressed, weather=[], rejections=0

### `b_only`

|轮|请求动作|实际动作|拒绝|Hero HP/Mana/Shield|Target HP|Wet|Elec|Smoke|Temp|Biomass|生态|天气|Hook|
|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---:|
|1|`widows_last_match`|`widows_last_match`|-|68/44/0|79|0.408|0.187|0.454|21.20|0.320|balanced|-|0|
|2|`basic_wait`|`basic_wait`|-|56/49/0|79|0.415|0.212|0.458|22.35|0.338|stressed|-|0|
|3|`basic_wait`|`basic_wait`|-|44/54/0|79|0.422|0.235|0.461|23.46|0.336|stressed|-|0|
|4|`basic_wait`|`basic_wait`|-|32/59/0|79|0.428|0.256|0.464|24.52|0.333|stressed|-|0|

终局：target_damage=1, hero_hp_loss=48, final_ecology=stressed, weather=[], rejections=0

### `b_then_a`

|轮|请求动作|实际动作|拒绝|Hero HP/Mana/Shield|Target HP|Wet|Elec|Smoke|Temp|Biomass|生态|天气|Hook|
|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---:|
|1|`widows_last_match`|`widows_last_match`|-|68/44/0|79|0.408|0.187|0.454|21.20|0.320|balanced|-|0|
|2|`ash_veil`|`ash_veil`|-|62/42/0|79|0.415|0.212|0.780|22.35|0.338|stressed|-|0|
|3|`basic_wait`|`basic_wait`|-|50/47/0|79|0.422|0.235|0.757|23.46|0.336|stressed|-|0|
|4|`basic_wait`|`basic_wait`|-|38/52/0|79|0.428|0.256|0.737|24.52|0.333|stressed|-|0|

终局：target_damage=1, hero_hp_loss=42, final_ecology=stressed, weather=[], rejections=0

### `matched_alternative`

|轮|请求动作|实际动作|拒绝|Hero HP/Mana/Shield|Target HP|Wet|Elec|Smoke|Temp|Biomass|生态|天气|Hook|
|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---:|
|1|`basic_guard`|`basic_guard`|-|75/45/0|80|0.408|0.187|0.040|21.20|0.320|balanced|-|0|
|2|`basic_attack`|`basic_attack`|-|63/45/0|68|0.415|0.212|0.077|22.35|0.338|stressed|-|0|
|3|`basic_wait`|`basic_wait`|-|51/50/0|68|0.422|0.235|0.111|23.46|0.336|stressed|-|0|
|4|`basic_wait`|`basic_wait`|-|39/55/0|68|0.428|0.256|0.142|24.52|0.333|stressed|-|0|

终局：target_damage=12, hero_hp_loss=41, final_ecology=stressed, weather=[], rejections=0

### `no_skill`

|轮|请求动作|实际动作|拒绝|Hero HP/Mana/Shield|Target HP|Wet|Elec|Smoke|Temp|Biomass|生态|天气|Hook|
|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---:|
|1|`basic_wait`|`basic_wait`|-|68/50/0|80|0.408|0.187|0.040|21.20|0.320|balanced|-|0|
|2|`basic_wait`|`basic_wait`|-|56/55/0|80|0.415|0.212|0.077|22.35|0.338|stressed|-|0|
|3|`basic_wait`|`basic_wait`|-|44/60/0|80|0.422|0.235|0.111|23.46|0.336|stressed|-|0|
|4|`basic_wait`|`basic_wait`|-|32/60/0|80|0.428|0.256|0.142|24.52|0.333|stressed|-|0|

终局：target_damage=0, hero_hp_loss=48, final_ecology=stressed, weather=[], rejections=0

## 判定

`EXECUTABLE_ONLY`：两张技能可以堆烟，但火柴单独已越过阈值；组合没有额外防御或有效伤害，施放顺序甚至会延迟热浪路径。
