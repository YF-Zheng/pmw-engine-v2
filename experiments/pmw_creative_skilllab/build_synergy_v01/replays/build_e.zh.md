# build_e · 防御与生态维护共用能力 Replay

目标：四轮敌方攻击后保持存活，并阻止生态进入 stressed。

技能：skill_027, skill_042；敌方行动：`basic_attack`；每臂 4 个正式 Combat Round。

## 场景 `collapse_edge`

环境：`depleted_grove`；覆盖值：`{"biomass": 0.3, "smoke": 0.1, "temperature": 50}`；初始资源：`{"hero_hp": 80, "hero_mana": 45, "target_hp": 80, "target_mana": 20, "target_traits": []}`。

### `a_only`

|轮|请求动作|实际动作|拒绝|Hero HP/Mana/Shield|Target HP|Wet|Elec|Smoke|Temp|Biomass|生态|天气|Hook|
|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---:|
|1|`ash_nurse`|`ash_nurse`|-|68/43/0|80|0.353|0.334|0.132|50.00|0.370|balanced|-|0|
|2|`basic_wait`|`basic_wait`|-|56/48/0|80|0.365|0.348|0.161|50.00|0.420|balanced|-|0|
|3|`basic_wait`|`basic_wait`|-|44/53/0|80|0.375|0.360|0.189|50.00|0.457|balanced|-|0|
|4|`basic_wait`|`basic_wait`|-|32/58/0|80|0.385|0.371|0.213|50.00|0.464|balanced|-|0|

终局：target_damage=0, hero_hp_loss=48, final_ecology=balanced, weather=[], rejections=0

### `a_then_b`

|轮|请求动作|实际动作|拒绝|Hero HP/Mana/Shield|Target HP|Wet|Elec|Smoke|Temp|Biomass|生态|天气|Hook|
|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---:|
|1|`ash_nurse`|`ash_nurse`|-|68/43/0|80|0.353|0.334|0.132|50.00|0.370|balanced|-|0|
|2|`root_circuit`|`root_circuit`|-|64/40/0|80|0.365|0.348|0.161|50.00|0.442|balanced|-|0|
|3|`basic_wait`|`basic_wait`|-|52/45/0|80|0.375|0.360|0.189|50.00|0.485|balanced|-|0|
|4|`basic_wait`|`basic_wait`|-|40/50/0|80|0.385|0.371|0.213|50.00|0.490|balanced|-|0|

终局：target_damage=0, hero_hp_loss=40, final_ecology=balanced, weather=[], rejections=0

### `b_only`

|轮|请求动作|实际动作|拒绝|Hero HP/Mana/Shield|Target HP|Wet|Elec|Smoke|Temp|Biomass|生态|天气|Hook|
|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---:|
|1|`root_circuit`|`root_circuit`|-|76/42/0|80|0.353|0.334|0.132|50.00|0.350|balanced|-|0|
|2|`basic_wait`|`basic_wait`|-|64/47/0|80|0.365|0.348|0.161|50.00|0.390|balanced|-|0|
|3|`basic_wait`|`basic_wait`|-|52/52/0|80|0.375|0.360|0.189|50.00|0.403|balanced|-|0|
|4|`basic_wait`|`basic_wait`|-|40/57/0|80|0.385|0.371|0.213|50.00|0.415|balanced|-|0|

终局：target_damage=0, hero_hp_loss=40, final_ecology=balanced, weather=[], rejections=0

### `b_then_a`

|轮|请求动作|实际动作|拒绝|Hero HP/Mana/Shield|Target HP|Wet|Elec|Smoke|Temp|Biomass|生态|天气|Hook|
|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---:|
|1|`root_circuit`|`root_circuit`|-|76/42/0|80|0.353|0.334|0.132|50.00|0.350|balanced|-|0|
|2|`ash_nurse`|`ash_nurse`|-|64/40/0|80|0.365|0.348|0.161|50.00|0.430|balanced|-|0|
|3|`basic_wait`|`basic_wait`|-|52/45/0|80|0.375|0.360|0.189|50.00|0.464|balanced|-|0|
|4|`basic_wait`|`basic_wait`|-|40/50/0|80|0.385|0.371|0.213|50.00|0.488|balanced|-|0|

终局：target_damage=0, hero_hp_loss=40, final_ecology=balanced, weather=[], rejections=0

### `matched_alternative`

|轮|请求动作|实际动作|拒绝|Hero HP/Mana/Shield|Target HP|Wet|Elec|Smoke|Temp|Biomass|生态|天气|Hook|
|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---:|
|1|`basic_guard`|`basic_guard`|-|75/45/0|80|0.353|0.334|0.132|50.00|0.320|balanced|-|0|
|2|`basic_guard`|`basic_guard`|-|70/45/0|80|0.365|0.348|0.161|50.00|0.338|stressed|-|0|
|3|`basic_wait`|`basic_wait`|-|58/50/0|80|0.375|0.360|0.189|50.00|0.336|stressed|-|0|
|4|`basic_wait`|`basic_wait`|-|46/55/0|80|0.385|0.371|0.213|50.00|0.333|stressed|-|0|

终局：target_damage=0, hero_hp_loss=34, final_ecology=stressed, weather=[], rejections=0

### `no_skill`

|轮|请求动作|实际动作|拒绝|Hero HP/Mana/Shield|Target HP|Wet|Elec|Smoke|Temp|Biomass|生态|天气|Hook|
|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---:|
|1|`basic_wait`|`basic_wait`|-|68/50/0|80|0.353|0.334|0.132|50.00|0.320|balanced|-|0|
|2|`basic_wait`|`basic_wait`|-|56/55/0|80|0.365|0.348|0.161|50.00|0.338|stressed|-|0|
|3|`basic_wait`|`basic_wait`|-|44/60/0|80|0.375|0.360|0.189|50.00|0.336|stressed|-|0|
|4|`basic_wait`|`basic_wait`|-|32/60/0|80|0.385|0.371|0.213|50.00|0.333|stressed|-|0|

终局：target_damage=0, hero_hp_loss=48, final_ecology=stressed, weather=[], rejections=0

## 场景 `far_from_threshold`

环境：`lush_grove`；覆盖值：`{"biomass": 0.78, "smoke": 0.05, "temperature": 45}`；初始资源：`{"hero_hp": 80, "hero_mana": 45, "target_hp": 80, "target_mana": 20, "target_traits": []}`。

### `a_only`

|轮|请求动作|实际动作|拒绝|Hero HP/Mana/Shield|Target HP|Wet|Elec|Smoke|Temp|Biomass|生态|天气|Hook|
|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---:|
|1|`ash_nurse`|`ash_nurse`|-|68/43/0|80|0.702|0.206|0.086|41.20|0.716|balanced|rain_front,verdant_surge|0|
|2|`basic_wait`|`basic_wait`|-|56/48/0|80|0.686|0.229|0.119|37.55|0.669|balanced|rain_front,verdant_surge|0|
|3|`basic_wait`|`basic_wait`|-|44/53/0|80|0.671|0.251|0.150|34.05|0.636|balanced|rain_front,verdant_surge|0|
|4|`basic_wait`|`basic_wait`|-|32/58/0|80|0.658|0.271|0.178|30.69|0.629|balanced|rain_front,verdant_surge|0|

终局：target_damage=0, hero_hp_loss=48, final_ecology=balanced, weather=['rain_front', 'verdant_surge'], rejections=0

### `a_then_b`

|轮|请求动作|实际动作|拒绝|Hero HP/Mana/Shield|Target HP|Wet|Elec|Smoke|Temp|Biomass|生态|天气|Hook|
|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---:|
|1|`ash_nurse`|`ash_nurse`|-|68/43/0|80|0.702|0.206|0.086|41.20|0.716|balanced|rain_front,verdant_surge|0|
|2|`root_circuit`|`root_circuit`|-|64/40/0|80|0.686|0.229|0.119|37.55|0.649|balanced|rain_front,verdant_surge|0|
|3|`basic_wait`|`basic_wait`|-|52/45/0|80|0.671|0.251|0.150|34.05|0.610|balanced|rain_front,verdant_surge|0|
|4|`basic_wait`|`basic_wait`|-|40/50/0|80|0.658|0.271|0.178|30.69|0.605|balanced|rain_front,verdant_surge|0|

终局：target_damage=0, hero_hp_loss=40, final_ecology=balanced, weather=['rain_front', 'verdant_surge'], rejections=0

### `b_only`

|轮|请求动作|实际动作|拒绝|Hero HP/Mana/Shield|Target HP|Wet|Elec|Smoke|Temp|Biomass|生态|天气|Hook|
|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---:|
|1|`root_circuit`|`root_circuit`|-|76/42/0|80|0.702|0.206|0.086|41.20|0.734|balanced|rain_front,verdant_surge|0|
|2|`basic_wait`|`basic_wait`|-|64/47/0|80|0.686|0.229|0.119|37.55|0.697|balanced|rain_front,verdant_surge|0|
|3|`basic_wait`|`basic_wait`|-|52/52/0|80|0.671|0.251|0.150|34.05|0.685|balanced|rain_front,verdant_surge|0|
|4|`basic_wait`|`basic_wait`|-|40/57/0|80|0.658|0.271|0.178|30.69|0.675|balanced|rain_front,verdant_surge|0|

终局：target_damage=0, hero_hp_loss=40, final_ecology=balanced, weather=['rain_front', 'verdant_surge'], rejections=0

### `b_then_a`

|轮|请求动作|实际动作|拒绝|Hero HP/Mana/Shield|Target HP|Wet|Elec|Smoke|Temp|Biomass|生态|天气|Hook|
|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---:|
|1|`root_circuit`|`root_circuit`|-|76/42/0|80|0.702|0.206|0.086|41.20|0.734|balanced|rain_front,verdant_surge|0|
|2|`ash_nurse`|`ash_nurse`|-|64/40/0|80|0.686|0.229|0.119|37.55|0.660|balanced|rain_front,verdant_surge|0|
|3|`basic_wait`|`basic_wait`|-|52/45/0|80|0.671|0.251|0.150|34.05|0.629|balanced|rain_front,verdant_surge|0|
|4|`basic_wait`|`basic_wait`|-|40/50/0|80|0.658|0.271|0.178|30.69|0.607|balanced|rain_front,verdant_surge|0|

终局：target_damage=0, hero_hp_loss=40, final_ecology=balanced, weather=['rain_front', 'verdant_surge'], rejections=0

### `matched_alternative`

|轮|请求动作|实际动作|拒绝|Hero HP/Mana/Shield|Target HP|Wet|Elec|Smoke|Temp|Biomass|生态|天气|Hook|
|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---:|
|1|`basic_guard`|`basic_guard`|-|75/45/0|80|0.702|0.206|0.086|41.20|0.762|balanced|rain_front,verdant_surge|0|
|2|`basic_guard`|`basic_guard`|-|70/45/0|80|0.686|0.229|0.119|37.55|0.745|balanced|rain_front,verdant_surge|0|
|3|`basic_wait`|`basic_wait`|-|58/50/0|80|0.671|0.251|0.150|34.05|0.729|balanced|rain_front,verdant_surge|0|
|4|`basic_wait`|`basic_wait`|-|46/55/0|80|0.658|0.271|0.178|30.69|0.715|balanced|rain_front,verdant_surge|0|

终局：target_damage=0, hero_hp_loss=34, final_ecology=balanced, weather=['rain_front', 'verdant_surge'], rejections=0

### `no_skill`

|轮|请求动作|实际动作|拒绝|Hero HP/Mana/Shield|Target HP|Wet|Elec|Smoke|Temp|Biomass|生态|天气|Hook|
|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---:|
|1|`basic_wait`|`basic_wait`|-|68/50/0|80|0.702|0.206|0.086|41.20|0.762|balanced|rain_front,verdant_surge|0|
|2|`basic_wait`|`basic_wait`|-|56/55/0|80|0.686|0.229|0.119|37.55|0.745|balanced|rain_front,verdant_surge|0|
|3|`basic_wait`|`basic_wait`|-|44/60/0|80|0.671|0.251|0.150|34.05|0.729|balanced|rain_front,verdant_surge|0|
|4|`basic_wait`|`basic_wait`|-|32/60/0|80|0.658|0.271|0.178|30.69|0.715|balanced|rain_front,verdant_surge|0|

终局：target_damage=0, hero_hp_loss=48, final_ecology=balanced, weather=['rain_front', 'verdant_surge'], rejections=0

## 判定

`EXECUTABLE_ONLY`：两个速率槽能同时生效，但 #042 单独已保住临界生态并提供相同防御，组合只是递减收益的数值叠加。
