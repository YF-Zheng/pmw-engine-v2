# build_a · 赦免与处决 Replay

目标：四个等时战斗轮内，在玩家存活的前提下尽量降低敌人 HP。

技能：skill_051, skill_052；敌方行动：`basic_attack`；每臂 4 个正式 Combat Round。

## 场景 `primary`

环境：`wet_forest`；覆盖值：`{}`；初始资源：`{"hero_hp": 80, "hero_mana": 45, "target_hp": 60, "target_mana": 20, "target_traits": []}`。

### `a_only`

|轮|请求动作|实际动作|拒绝|Hero HP/Mana/Shield|Target HP|Wet|Elec|Smoke|Temp|Biomass|生态|天气|Hook|
|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---:|
|1|`false_mercy`|`false_mercy`|-|68/44/0|68|0.758|0.270|0.114|38.32|0.651|balanced|rain_front|0|
|2|`basic_wait`|`basic_wait`|-|56/49/0|68|0.737|0.288|0.145|34.79|0.643|balanced|rain_front|0|
|3|`basic_wait`|`basic_wait`|-|44/54/0|68|0.718|0.305|0.173|31.40|0.636|balanced|rain_front|0|
|4|`basic_wait`|`basic_wait`|-|32/59/0|68|0.701|0.321|0.199|28.14|0.629|balanced|rain_front|0|

终局：target_damage=-8, hero_hp_loss=48, final_ecology=balanced, weather=['rain_front'], rejections=0

### `a_then_b`

|轮|请求动作|实际动作|拒绝|Hero HP/Mana/Shield|Target HP|Wet|Elec|Smoke|Temp|Biomass|生态|天气|Hook|
|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---:|
|1|`false_mercy`|`false_mercy`|-|68/44/0|68|0.758|0.270|0.114|38.32|0.651|balanced|rain_front|0|
|2|`doctrinal_exception`|`doctrinal_exception`|-|56/42/0|57|0.737|0.288|0.145|34.79|0.643|balanced|rain_front|0|
|3|`basic_wait`|`basic_wait`|-|44/47/0|57|0.718|0.305|0.173|31.40|0.636|balanced|rain_front|0|
|4|`basic_wait`|`basic_wait`|-|32/52/0|57|0.701|0.321|0.199|28.14|0.629|balanced|rain_front|0|

终局：target_damage=3, hero_hp_loss=48, final_ecology=balanced, weather=['rain_front'], rejections=0

### `b_only`

|轮|请求动作|实际动作|拒绝|Hero HP/Mana/Shield|Target HP|Wet|Elec|Smoke|Temp|Biomass|生态|天气|Hook|
|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---:|
|1|`doctrinal_exception`|`doctrinal_exception`|-|68/43/0|60|0.758|0.270|0.114|38.32|0.651|balanced|rain_front|0|
|2|`basic_wait`|`basic_wait`|-|56/48/0|60|0.737|0.288|0.145|34.79|0.643|balanced|rain_front|0|
|3|`basic_wait`|`basic_wait`|-|44/53/0|60|0.718|0.305|0.173|31.40|0.636|balanced|rain_front|0|
|4|`basic_wait`|`basic_wait`|-|32/58/0|60|0.701|0.321|0.199|28.14|0.629|balanced|rain_front|0|

终局：target_damage=0, hero_hp_loss=48, final_ecology=balanced, weather=['rain_front'], rejections=0

### `b_then_a`

|轮|请求动作|实际动作|拒绝|Hero HP/Mana/Shield|Target HP|Wet|Elec|Smoke|Temp|Biomass|生态|天气|Hook|
|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---:|
|1|`doctrinal_exception`|`doctrinal_exception`|-|68/43/0|60|0.758|0.270|0.114|38.32|0.651|balanced|rain_front|0|
|2|`false_mercy`|`false_mercy`|-|56/42/0|68|0.737|0.288|0.145|34.79|0.643|balanced|rain_front|0|
|3|`basic_wait`|`basic_wait`|-|44/47/0|68|0.718|0.305|0.173|31.40|0.636|balanced|rain_front|0|
|4|`basic_wait`|`basic_wait`|-|32/52/0|68|0.701|0.321|0.199|28.14|0.629|balanced|rain_front|0|

终局：target_damage=-8, hero_hp_loss=48, final_ecology=balanced, weather=['rain_front'], rejections=0

### `matched_alternative`

|轮|请求动作|实际动作|拒绝|Hero HP/Mana/Shield|Target HP|Wet|Elec|Smoke|Temp|Biomass|生态|天气|Hook|
|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---:|
|1|`basic_attack`|`basic_attack`|-|68/45/0|48|0.758|0.270|0.114|38.32|0.651|balanced|rain_front|0|
|2|`basic_attack`|`basic_attack`|-|56/45/0|36|0.737|0.288|0.145|34.79|0.643|balanced|rain_front|0|
|3|`basic_wait`|`basic_wait`|-|44/50/0|36|0.718|0.305|0.173|31.40|0.636|balanced|rain_front|0|
|4|`basic_wait`|`basic_wait`|-|32/55/0|36|0.701|0.321|0.199|28.14|0.629|balanced|rain_front|0|

终局：target_damage=24, hero_hp_loss=48, final_ecology=balanced, weather=['rain_front'], rejections=0

### `no_skill`

|轮|请求动作|实际动作|拒绝|Hero HP/Mana/Shield|Target HP|Wet|Elec|Smoke|Temp|Biomass|生态|天气|Hook|
|---:|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|---:|
|1|`basic_wait`|`basic_wait`|-|68/50/0|60|0.758|0.270|0.114|38.32|0.651|balanced|rain_front|0|
|2|`basic_wait`|`basic_wait`|-|56/55/0|60|0.737|0.288|0.145|34.79|0.643|balanced|rain_front|0|
|3|`basic_wait`|`basic_wait`|-|44/60/0|60|0.718|0.305|0.173|31.40|0.636|balanced|rain_front|0|
|4|`basic_wait`|`basic_wait`|-|32/60/0|60|0.701|0.321|0.199|28.14|0.629|balanced|rain_front|0|

终局：target_damage=0, hero_hp_loss=48, final_ecology=balanced, weather=['rain_front'], rejections=0

## 判定

`MECHANICALLY_INTERESTING`：赦免真实创造了处决条件，但治疗 8 后再伤害 11 仅有 3 点净伤害，远弱于两次普通攻击的 24。
