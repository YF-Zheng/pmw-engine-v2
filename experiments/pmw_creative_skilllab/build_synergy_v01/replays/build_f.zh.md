# build_f · 用未来生命偿还当前能力 Replay

目标：在四轮内越过热浪阈值并存活，记录为此支付的生命与法力机会成本。

技能：skill_056, skill_060；敌方行动：`basic_wait`；每臂 4 个正式 Combat Round。

## 场景 `far_high_hp_low_mana`

环境：`frozen_hollow`；覆盖值：`{"temperature": 20}`；初始资源：`{"hero_hp": 80, "hero_mana": 0, "target_hp": 80, "target_mana": 20, "target_traits": []}`。

### `a_only`

|轮|请求动作|实际动作|拒绝|Hero HP/Mana/Shield|Target HP|Wet|Elec|Smoke|Temp|Biomass|生态|天气|Hook|
|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---:|
|1|`fermentation_mana`|`fermentation_mana`|-|77/8/0|80|0.574|0.187|0.068|21.20|0.320|balanced|-|0|
|2|`basic_wait`|`basic_wait`|-|74/13/0|80|0.568|0.212|0.102|22.35|0.338|stressed|-|0|
|3|`basic_wait`|`basic_wait`|-|71/18/0|80|0.562|0.235|0.134|23.46|0.336|stressed|-|0|
|4|`basic_wait`|`basic_wait`|-|71/23/0|80|0.557|0.256|0.163|24.52|0.333|stressed|-|0|

终局：target_damage=0, hero_hp_loss=9, final_ecology=stressed, weather=[], rejections=0

### `a_then_b`

|轮|请求动作|实际动作|拒绝|Hero HP/Mana/Shield|Target HP|Wet|Elec|Smoke|Temp|Biomass|生态|天气|Hook|
|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---:|
|1|`fermentation_mana`|`fermentation_mana`|-|77/8/0|80|0.574|0.187|0.068|21.20|0.320|balanced|-|0|
|2|`fever_key`|`fever_key`|-|69/7/0|80|0.568|0.212|0.102|46.35|0.338|stressed|-|0|
|3|`basic_wait`|`basic_wait`|-|66/12/0|80|0.562|0.235|0.134|46.50|0.336|stressed|-|0|
|4|`basic_wait`|`basic_wait`|-|66/17/0|80|0.557|0.256|0.163|46.64|0.333|stressed|-|0|

终局：target_damage=0, hero_hp_loss=14, final_ecology=stressed, weather=[], rejections=0

### `b_only`

|轮|请求动作|实际动作|拒绝|Hero HP/Mana/Shield|Target HP|Wet|Elec|Smoke|Temp|Biomass|生态|天气|Hook|
|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---:|
|1|`fever_key`|`basic_wait`|insufficient mana|80/5/0|80|0.574|0.187|0.068|21.20|0.320|balanced|-|0|
|2|`basic_wait`|`basic_wait`|-|80/10/0|80|0.568|0.212|0.102|22.35|0.338|stressed|-|0|
|3|`basic_wait`|`basic_wait`|-|80/15/0|80|0.562|0.235|0.134|23.46|0.336|stressed|-|0|
|4|`basic_wait`|`basic_wait`|-|80/20/0|80|0.557|0.256|0.163|24.52|0.333|stressed|-|0|

终局：target_damage=0, hero_hp_loss=0, final_ecology=stressed, weather=[], rejections=1

### `b_then_a`

|轮|请求动作|实际动作|拒绝|Hero HP/Mana/Shield|Target HP|Wet|Elec|Smoke|Temp|Biomass|生态|天气|Hook|
|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---:|
|1|`fever_key`|`basic_wait`|insufficient mana|80/5/0|80|0.574|0.187|0.068|21.20|0.320|balanced|-|0|
|2|`fermentation_mana`|`fermentation_mana`|-|77/13/0|80|0.568|0.212|0.102|22.35|0.338|stressed|-|0|
|3|`basic_wait`|`basic_wait`|-|74/18/0|80|0.562|0.235|0.134|23.46|0.336|stressed|-|0|
|4|`basic_wait`|`basic_wait`|-|71/23/0|80|0.557|0.256|0.163|24.52|0.333|stressed|-|0|

终局：target_damage=0, hero_hp_loss=9, final_ecology=stressed, weather=[], rejections=1

### `matched_alternative`

|轮|请求动作|实际动作|拒绝|Hero HP/Mana/Shield|Target HP|Wet|Elec|Smoke|Temp|Biomass|生态|天气|Hook|
|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---:|
|1|`basic_wait`|`basic_wait`|-|80/5/0|80|0.574|0.187|0.068|21.20|0.320|balanced|-|0|
|2|`fever_key`|`fever_key`|-|75/4/0|80|0.568|0.212|0.102|46.35|0.338|stressed|-|0|
|3|`basic_wait`|`basic_wait`|-|75/9/0|80|0.562|0.235|0.134|46.50|0.336|stressed|-|0|
|4|`basic_wait`|`basic_wait`|-|75/14/0|80|0.557|0.256|0.163|46.64|0.333|stressed|-|0|

终局：target_damage=0, hero_hp_loss=5, final_ecology=stressed, weather=[], rejections=0

### `no_skill`

|轮|请求动作|实际动作|拒绝|Hero HP/Mana/Shield|Target HP|Wet|Elec|Smoke|Temp|Biomass|生态|天气|Hook|
|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---:|
|1|`basic_wait`|`basic_wait`|-|80/5/0|80|0.574|0.187|0.068|21.20|0.320|balanced|-|0|
|2|`basic_wait`|`basic_wait`|-|80/10/0|80|0.568|0.212|0.102|22.35|0.338|stressed|-|0|
|3|`basic_wait`|`basic_wait`|-|80/15/0|80|0.562|0.235|0.134|23.46|0.336|stressed|-|0|
|4|`basic_wait`|`basic_wait`|-|80/20/0|80|0.557|0.256|0.163|24.52|0.333|stressed|-|0|

终局：target_damage=0, hero_hp_loss=0, final_ecology=stressed, weather=[], rejections=0

## 场景 `near_high_hp_full_mana`

环境：`fever_marsh`；覆盖值：`{"temperature": 55}`；初始资源：`{"hero_hp": 80, "hero_mana": 45, "target_hp": 80, "target_mana": 20, "target_traits": []}`。

### `a_only`

|轮|请求动作|实际动作|拒绝|Hero HP/Mana/Shield|Target HP|Wet|Elec|Smoke|Temp|Biomass|生态|天气|Hook|
|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---:|
|1|`fermentation_mana`|`fermentation_mana`|-|77/53/0|80|0.776|0.298|0.150|50.80|0.688|balanced|rain_front|0|
|2|`basic_wait`|`basic_wait`|-|74/58/0|80|0.754|0.314|0.178|46.77|0.677|balanced|rain_front|0|
|3|`basic_wait`|`basic_wait`|-|71/60/0|80|0.734|0.329|0.204|42.90|0.667|balanced|rain_front|0|
|4|`basic_wait`|`basic_wait`|-|71/60/0|80|0.715|0.342|0.228|39.18|0.657|balanced|rain_front|0|

终局：target_damage=0, hero_hp_loss=9, final_ecology=balanced, weather=['rain_front'], rejections=0

### `a_then_b`

|轮|请求动作|实际动作|拒绝|Hero HP/Mana/Shield|Target HP|Wet|Elec|Smoke|Temp|Biomass|生态|天气|Hook|
|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---:|
|1|`fermentation_mana`|`fermentation_mana`|-|77/53/0|80|0.776|0.298|0.150|50.80|0.688|balanced|rain_front|0|
|2|`fever_key`|`fever_key`|-|69/52/0|80|0.754|0.314|0.178|70.77|0.637|balanced|heat_haze,rain_front|0|
|3|`basic_wait`|`basic_wait`|-|66/57/0|80|0.734|0.329|0.204|65.94|0.590|balanced|heat_haze,rain_front|0|
|4|`basic_wait`|`basic_wait`|-|66/60/0|80|0.715|0.342|0.228|61.30|0.547|balanced|heat_haze,rain_front|0|

终局：target_damage=0, hero_hp_loss=14, final_ecology=balanced, weather=['heat_haze', 'rain_front'], rejections=0

### `b_only`

|轮|请求动作|实际动作|拒绝|Hero HP/Mana/Shield|Target HP|Wet|Elec|Smoke|Temp|Biomass|生态|天气|Hook|
|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---:|
|1|`fever_key`|`fever_key`|-|75/44/0|80|0.776|0.298|0.150|74.80|0.648|balanced|heat_haze,rain_front|0|
|2|`basic_wait`|`basic_wait`|-|75/49/0|80|0.754|0.314|0.178|69.81|0.600|balanced|heat_haze,rain_front|0|
|3|`basic_wait`|`basic_wait`|-|75/54/0|80|0.734|0.329|0.204|65.02|0.556|balanced|heat_haze,rain_front|0|
|4|`basic_wait`|`basic_wait`|-|75/59/0|80|0.715|0.342|0.228|60.42|0.516|balanced|heat_haze,rain_front|0|

终局：target_damage=0, hero_hp_loss=5, final_ecology=balanced, weather=['heat_haze', 'rain_front'], rejections=0

### `b_then_a`

|轮|请求动作|实际动作|拒绝|Hero HP/Mana/Shield|Target HP|Wet|Elec|Smoke|Temp|Biomass|生态|天气|Hook|
|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---:|
|1|`fever_key`|`fever_key`|-|75/44/0|80|0.776|0.298|0.150|74.80|0.648|balanced|heat_haze,rain_front|0|
|2|`fermentation_mana`|`fermentation_mana`|-|72/52/0|80|0.754|0.314|0.178|69.81|0.600|balanced|heat_haze,rain_front|0|
|3|`basic_wait`|`basic_wait`|-|69/57/0|80|0.734|0.329|0.204|65.02|0.556|balanced|heat_haze,rain_front|0|
|4|`basic_wait`|`basic_wait`|-|66/60/0|80|0.715|0.342|0.228|60.42|0.516|balanced|heat_haze,rain_front|0|

终局：target_damage=0, hero_hp_loss=14, final_ecology=balanced, weather=['heat_haze', 'rain_front'], rejections=0

### `matched_alternative`

|轮|请求动作|实际动作|拒绝|Hero HP/Mana/Shield|Target HP|Wet|Elec|Smoke|Temp|Biomass|生态|天气|Hook|
|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---:|
|1|`basic_wait`|`basic_wait`|-|80/50/0|80|0.776|0.298|0.150|50.80|0.688|balanced|rain_front|0|
|2|`fever_key`|`fever_key`|-|75/49/0|80|0.754|0.314|0.178|70.77|0.637|balanced|heat_haze,rain_front|0|
|3|`basic_wait`|`basic_wait`|-|75/54/0|80|0.734|0.329|0.204|65.94|0.590|balanced|heat_haze,rain_front|0|
|4|`basic_wait`|`basic_wait`|-|75/59/0|80|0.715|0.342|0.228|61.30|0.547|balanced|heat_haze,rain_front|0|

终局：target_damage=0, hero_hp_loss=5, final_ecology=balanced, weather=['heat_haze', 'rain_front'], rejections=0

### `no_skill`

|轮|请求动作|实际动作|拒绝|Hero HP/Mana/Shield|Target HP|Wet|Elec|Smoke|Temp|Biomass|生态|天气|Hook|
|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---:|
|1|`basic_wait`|`basic_wait`|-|80/50/0|80|0.776|0.298|0.150|50.80|0.688|balanced|rain_front|0|
|2|`basic_wait`|`basic_wait`|-|80/55/0|80|0.754|0.314|0.178|46.77|0.677|balanced|rain_front|0|
|3|`basic_wait`|`basic_wait`|-|80/60/0|80|0.734|0.329|0.204|42.90|0.667|balanced|rain_front|0|
|4|`basic_wait`|`basic_wait`|-|80/60/0|80|0.715|0.342|0.228|39.18|0.657|balanced|rain_front|0|

终局：target_damage=0, hero_hp_loss=0, final_ecology=balanced, weather=['rain_front'], rejections=0

## 场景 `near_high_hp_low_mana`

环境：`fever_marsh`；覆盖值：`{"temperature": 55}`；初始资源：`{"hero_hp": 80, "hero_mana": 0, "target_hp": 80, "target_mana": 20, "target_traits": []}`。

### `a_only`

|轮|请求动作|实际动作|拒绝|Hero HP/Mana/Shield|Target HP|Wet|Elec|Smoke|Temp|Biomass|生态|天气|Hook|
|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---:|
|1|`fermentation_mana`|`fermentation_mana`|-|77/8/0|80|0.776|0.298|0.150|50.80|0.688|balanced|rain_front|0|
|2|`basic_wait`|`basic_wait`|-|74/13/0|80|0.754|0.314|0.178|46.77|0.677|balanced|rain_front|0|
|3|`basic_wait`|`basic_wait`|-|71/18/0|80|0.734|0.329|0.204|42.90|0.667|balanced|rain_front|0|
|4|`basic_wait`|`basic_wait`|-|71/23/0|80|0.715|0.342|0.228|39.18|0.657|balanced|rain_front|0|

终局：target_damage=0, hero_hp_loss=9, final_ecology=balanced, weather=['rain_front'], rejections=0

### `a_then_b`

|轮|请求动作|实际动作|拒绝|Hero HP/Mana/Shield|Target HP|Wet|Elec|Smoke|Temp|Biomass|生态|天气|Hook|
|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---:|
|1|`fermentation_mana`|`fermentation_mana`|-|77/8/0|80|0.776|0.298|0.150|50.80|0.688|balanced|rain_front|0|
|2|`fever_key`|`fever_key`|-|69/7/0|80|0.754|0.314|0.178|70.77|0.637|balanced|heat_haze,rain_front|0|
|3|`basic_wait`|`basic_wait`|-|66/12/0|80|0.734|0.329|0.204|65.94|0.590|balanced|heat_haze,rain_front|0|
|4|`basic_wait`|`basic_wait`|-|66/17/0|80|0.715|0.342|0.228|61.30|0.547|balanced|heat_haze,rain_front|0|

终局：target_damage=0, hero_hp_loss=14, final_ecology=balanced, weather=['heat_haze', 'rain_front'], rejections=0

### `b_only`

|轮|请求动作|实际动作|拒绝|Hero HP/Mana/Shield|Target HP|Wet|Elec|Smoke|Temp|Biomass|生态|天气|Hook|
|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---:|
|1|`fever_key`|`basic_wait`|insufficient mana|80/5/0|80|0.776|0.298|0.150|50.80|0.688|balanced|rain_front|0|
|2|`basic_wait`|`basic_wait`|-|80/10/0|80|0.754|0.314|0.178|46.77|0.677|balanced|rain_front|0|
|3|`basic_wait`|`basic_wait`|-|80/15/0|80|0.734|0.329|0.204|42.90|0.667|balanced|rain_front|0|
|4|`basic_wait`|`basic_wait`|-|80/20/0|80|0.715|0.342|0.228|39.18|0.657|balanced|rain_front|0|

终局：target_damage=0, hero_hp_loss=0, final_ecology=balanced, weather=['rain_front'], rejections=1

### `b_then_a`

|轮|请求动作|实际动作|拒绝|Hero HP/Mana/Shield|Target HP|Wet|Elec|Smoke|Temp|Biomass|生态|天气|Hook|
|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---:|
|1|`fever_key`|`basic_wait`|insufficient mana|80/5/0|80|0.776|0.298|0.150|50.80|0.688|balanced|rain_front|0|
|2|`fermentation_mana`|`fermentation_mana`|-|77/13/0|80|0.754|0.314|0.178|46.77|0.677|balanced|rain_front|0|
|3|`basic_wait`|`basic_wait`|-|74/18/0|80|0.734|0.329|0.204|42.90|0.667|balanced|rain_front|0|
|4|`basic_wait`|`basic_wait`|-|71/23/0|80|0.715|0.342|0.228|39.18|0.657|balanced|rain_front|0|

终局：target_damage=0, hero_hp_loss=9, final_ecology=balanced, weather=['rain_front'], rejections=1

### `matched_alternative`

|轮|请求动作|实际动作|拒绝|Hero HP/Mana/Shield|Target HP|Wet|Elec|Smoke|Temp|Biomass|生态|天气|Hook|
|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---:|
|1|`basic_wait`|`basic_wait`|-|80/5/0|80|0.776|0.298|0.150|50.80|0.688|balanced|rain_front|0|
|2|`fever_key`|`fever_key`|-|75/4/0|80|0.754|0.314|0.178|70.77|0.637|balanced|heat_haze,rain_front|0|
|3|`basic_wait`|`basic_wait`|-|75/9/0|80|0.734|0.329|0.204|65.94|0.590|balanced|heat_haze,rain_front|0|
|4|`basic_wait`|`basic_wait`|-|75/14/0|80|0.715|0.342|0.228|61.30|0.547|balanced|heat_haze,rain_front|0|

终局：target_damage=0, hero_hp_loss=5, final_ecology=balanced, weather=['heat_haze', 'rain_front'], rejections=0

### `no_skill`

|轮|请求动作|实际动作|拒绝|Hero HP/Mana/Shield|Target HP|Wet|Elec|Smoke|Temp|Biomass|生态|天气|Hook|
|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---:|
|1|`basic_wait`|`basic_wait`|-|80/5/0|80|0.776|0.298|0.150|50.80|0.688|balanced|rain_front|0|
|2|`basic_wait`|`basic_wait`|-|80/10/0|80|0.754|0.314|0.178|46.77|0.677|balanced|rain_front|0|
|3|`basic_wait`|`basic_wait`|-|80/15/0|80|0.734|0.329|0.204|42.90|0.667|balanced|rain_front|0|
|4|`basic_wait`|`basic_wait`|-|80/20/0|80|0.715|0.342|0.228|39.18|0.657|balanced|rain_front|0|

终局：target_damage=0, hero_hp_loss=0, final_ecology=balanced, weather=['rain_front'], rejections=0

## 场景 `near_low_hp_low_mana`

环境：`fever_marsh`；覆盖值：`{"temperature": 55}`；初始资源：`{"hero_hp": 14, "hero_mana": 0, "target_hp": 80, "target_mana": 20, "target_traits": []}`。

### `a_only`

|轮|请求动作|实际动作|拒绝|Hero HP/Mana/Shield|Target HP|Wet|Elec|Smoke|Temp|Biomass|生态|天气|Hook|
|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---:|
|1|`fermentation_mana`|`fermentation_mana`|-|11/8/0|80|0.776|0.298|0.150|50.80|0.688|balanced|rain_front|0|
|2|`basic_wait`|`basic_wait`|-|8/13/0|80|0.754|0.314|0.178|46.77|0.677|balanced|rain_front|0|
|3|`basic_wait`|`basic_wait`|-|5/18/0|80|0.734|0.329|0.204|42.90|0.667|balanced|rain_front|0|
|4|`basic_wait`|`basic_wait`|-|5/23/0|80|0.715|0.342|0.228|39.18|0.657|balanced|rain_front|0|

终局：target_damage=0, hero_hp_loss=9, final_ecology=balanced, weather=['rain_front'], rejections=0

### `a_then_b`

|轮|请求动作|实际动作|拒绝|Hero HP/Mana/Shield|Target HP|Wet|Elec|Smoke|Temp|Biomass|生态|天气|Hook|
|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---:|
|1|`fermentation_mana`|`fermentation_mana`|-|11/8/0|80|0.776|0.298|0.150|50.80|0.688|balanced|rain_front|0|
|2|`fever_key`|`fever_key`|-|3/7/0|80|0.754|0.314|0.178|70.77|0.637|balanced|heat_haze,rain_front|0|
|3|`basic_wait`|`basic_wait`|-|0/12/0|80|0.734|0.329|0.204|65.94|0.590|balanced|heat_haze,rain_front|0|
|4|`basic_wait`|`skipped`|-|0/12/0|80|0.715|0.342|0.228|61.30|0.547|balanced|heat_haze,rain_front|0|

终局：target_damage=0, hero_hp_loss=14, final_ecology=balanced, weather=['heat_haze', 'rain_front'], rejections=0

### `b_only`

|轮|请求动作|实际动作|拒绝|Hero HP/Mana/Shield|Target HP|Wet|Elec|Smoke|Temp|Biomass|生态|天气|Hook|
|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---:|
|1|`fever_key`|`basic_wait`|insufficient mana|14/5/0|80|0.776|0.298|0.150|50.80|0.688|balanced|rain_front|0|
|2|`basic_wait`|`basic_wait`|-|14/10/0|80|0.754|0.314|0.178|46.77|0.677|balanced|rain_front|0|
|3|`basic_wait`|`basic_wait`|-|14/15/0|80|0.734|0.329|0.204|42.90|0.667|balanced|rain_front|0|
|4|`basic_wait`|`basic_wait`|-|14/20/0|80|0.715|0.342|0.228|39.18|0.657|balanced|rain_front|0|

终局：target_damage=0, hero_hp_loss=0, final_ecology=balanced, weather=['rain_front'], rejections=1

### `b_then_a`

|轮|请求动作|实际动作|拒绝|Hero HP/Mana/Shield|Target HP|Wet|Elec|Smoke|Temp|Biomass|生态|天气|Hook|
|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---:|
|1|`fever_key`|`basic_wait`|insufficient mana|14/5/0|80|0.776|0.298|0.150|50.80|0.688|balanced|rain_front|0|
|2|`fermentation_mana`|`fermentation_mana`|-|11/13/0|80|0.754|0.314|0.178|46.77|0.677|balanced|rain_front|0|
|3|`basic_wait`|`basic_wait`|-|8/18/0|80|0.734|0.329|0.204|42.90|0.667|balanced|rain_front|0|
|4|`basic_wait`|`basic_wait`|-|5/23/0|80|0.715|0.342|0.228|39.18|0.657|balanced|rain_front|0|

终局：target_damage=0, hero_hp_loss=9, final_ecology=balanced, weather=['rain_front'], rejections=1

### `matched_alternative`

|轮|请求动作|实际动作|拒绝|Hero HP/Mana/Shield|Target HP|Wet|Elec|Smoke|Temp|Biomass|生态|天气|Hook|
|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---:|
|1|`basic_wait`|`basic_wait`|-|14/5/0|80|0.776|0.298|0.150|50.80|0.688|balanced|rain_front|0|
|2|`fever_key`|`fever_key`|-|9/4/0|80|0.754|0.314|0.178|70.77|0.637|balanced|heat_haze,rain_front|0|
|3|`basic_wait`|`basic_wait`|-|9/9/0|80|0.734|0.329|0.204|65.94|0.590|balanced|heat_haze,rain_front|0|
|4|`basic_wait`|`basic_wait`|-|9/14/0|80|0.715|0.342|0.228|61.30|0.547|balanced|heat_haze,rain_front|0|

终局：target_damage=0, hero_hp_loss=5, final_ecology=balanced, weather=['heat_haze', 'rain_front'], rejections=0

### `no_skill`

|轮|请求动作|实际动作|拒绝|Hero HP/Mana/Shield|Target HP|Wet|Elec|Smoke|Temp|Biomass|生态|天气|Hook|
|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---:|
|1|`basic_wait`|`basic_wait`|-|14/5/0|80|0.776|0.298|0.150|50.80|0.688|balanced|rain_front|0|
|2|`basic_wait`|`basic_wait`|-|14/10/0|80|0.754|0.314|0.178|46.77|0.677|balanced|rain_front|0|
|3|`basic_wait`|`basic_wait`|-|14/15/0|80|0.734|0.329|0.204|42.90|0.667|balanced|rain_front|0|
|4|`basic_wait`|`basic_wait`|-|14/20/0|80|0.715|0.342|0.228|39.18|0.657|balanced|rain_front|0|

终局：target_damage=0, hero_hp_loss=0, final_ecology=balanced, weather=['rain_front'], rejections=0

## 判定

`MECHANICALLY_INTERESTING`：生命债能立即换来施法资源，但等待一轮自然回蓝后单独施放 Fever Key 达到相同温度且多保留 9 HP；低 HP 时组合还会死亡。
