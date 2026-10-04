# Ash Observatory: Core Zero

《灰烬观测站：零号核心》是构建在冻结 PMW Engine v2.8 上的可玩 vertical slice。它不是 Engine v2.9，也没有为玩法引入新的引擎语义。一次探索约 15–25 分钟，目标是从零号金库取得 `artifact:core_zero`，再回到起始气闸撤离。

```bash
cd /ssd/zyf/PWM/pmw-engine-v2
PYTHONPATH=src python examples/ash_observatory/play.py
```

世界完全确定，不使用随机数。七个房间是普通 Entity，双向通路是普通 `connected_to` Relation；这不是 PMW Spatial system。位置只是 `components.position.room` 数据。

## Player Commands

```text
look
watch <visible-object>
watch <object-number>
watch here
status
inventory [short]
rawobs

move <visible-room-id-or-short-name>
wait <seconds>

<action-number>
<displayed-action-label>
do <action-number-or-displayed-label>

save <filename>
load <filename>
help [command]
quit
```

`look` 会为当前环境中的对象编号；推荐输入 `watch 1`、`watch Mira`、`watch 医疗箱`，或用 `watch here` 关注当前房间。`watch self`、`watch me` 和 `watch 我` 都关注玩家自身。房间只用于 `move`，不会与普通对象共用 watch 名称空间。`watch` 只建立本地 focus，不产生 Event 或推进时间。

菜单出现后，`1`、`do 1`、`拾取` 和 `do 拾取` 都会由同一个 action resolver 映射到稳定 ActionSpec ID。`do inventory.take` 这类内部 ID 输入仅供高级调试；正常游玩不需要知道它。需要额外输入的操作会继续提示。

默认 CLI 不再接受裸 `repair`、`hack`、`code`、`disable`、`attack`、`use`、`take`、`search` 或 `extract`。这些都是对象绑定的 namespaced ActionSpec。比如面对门使用 `watch door:vault`，再选择“输入密码”；输入值只会提交给当前 focus target。

## Contextual Interaction

`actions.json` 定义 13 个纯 UI/Event-adapter ActionSpec。World Entity 的 `components.interaction.actions` 只绑定 action ID；ActionSpec 描述标签、允许的 interaction context、用途、公开 prerequisite、输入字段、Event type 和公开时间成本。`ActionEventAdapter` 将选定 spec、actor、focus target 与用户输入转换为 PMW Event，不实现任何游戏 outcome。

Playable layer 从 Observation 推导三种本地 context：玩家自身是 `self`，可见 `owned_by` 物品是 `inventory`，当前房间及其本地对象是 `environment`。知识对象和离开房间后的已发现对象不会成为远程交互目标。对象在一次 action 后发生 context 转换时会结束 focus；因此拾取地面医疗箱后不会继续显示旧的“拾取”菜单，重新 watch 时会显示“当前由你持有”。

Affordance filtering 只读取当前 Observation：

- 缺少物品或 actor capability 时隐藏操作，不泄漏玩家尚不具备的路线。
- 可见目标状态暂时阻止操作时保留菜单项，并显示可观察原因，例如“终端未通电”。
- hidden condition 不用于菜单过滤，最终合法性仍由 World Laws 验证。
- focus 对象不再可见、移动到别处或 context 改变时自动清除，不能继续远程操作。
- 每个当前菜单中的 label 必须唯一；重复 label 是 content error。
- `target_state_reason` 会保留并用于 disabled 菜单说明；context 不匹配与 actor capability 缺失则直接隐藏 action。

UI filtering 只是提示而不是 authority。原 Law 仍独立验证 inventory、same-room relation、目标状态、密码和 item ownership。

行动公开耗时：移动、交谈、拿取、使用、维修、拆除、入侵、输入密码、攻击和撤离均为 1 秒；搜索为 2 秒；`wait N` 为 N 秒；查看、存档和读档不推进时间。普通 UI 不显示 Engine `sim_time`、tick 或 Scheduler queue。

## Suggested First Playthrough

- 有三条大致不同的进入金库方式。
- 某些信息并不会自动出现在你的视野里。
- 时间会在行动时推进。
- 尝试开始一个耗时动作后离开房间。
- 尝试在受持续状态影响时使用对应道具。

## World Mechanics

所有 outcome logic 都位于 `world.json`、`laws.json` 和 `observation_rules.json`；`actions.json` 只有 UI prerequisite 与 Event adapter 数据：

- Mira 的公开状态与私密知识分离；治疗只创建普通 Fact 与 `knows` Relation，不公开 `Mira.secret`。
- repair/hack 创建 `channeling` Relation 和有名 Scheduler handle；玩家正在 channeling 时对应 action 不再显示，合法移动会 delete channel 并 cancel handle。
- 发电机完成后由 State Law 推导档案终端供电。
- 隐藏陷阱只有在拥有 `discovered` Relation 且玩家与其同房间时才进入投影；触发陷阱也会建立 discovery，搜索成功后搜索 action 不再显示。
- 流血由 Relation、可复用 pulse handle 和 expiry handle 构成；绷带在一个事务中删除状态并取消两个 handle。
- 爆破未来打开门、触发警报、创建无人机；无人机通过 recurring scheduled attack 工作。
- 无人机和玩家死亡 tag 由 State Closure 推导。
- item inventory、知识、发现、channel、status 和金库入口均通过普通 Entity/Relation topology 表达。

三条主路线共享同一个最终状态：玩家持有核心并回到气闸。Social/Knowledge 路线不需要发电机，Technical 路线不需要 Mira 的密码，Force 路线不需要前两条路线。子系统可自然混合，不存在 Python narration tree。

## Information Boundary

正常 renderer、目标解析、inventory、focus、affordance filtering、胜利和死亡判定只读取 `ObserverView.observe()` 产生的 projected JSON。界面不会读取 `runtime.state`、snapshot、queue、trace 或 stats，也不会根据隐藏事件输出叙事。没有留下可观察状态的瞬时事件，在 v2.8 普通 UI 中不会被宣布。

`save` 是明确的持久化适配器，使用 PMW `save_world()`；`load` 使用 `load_world()`、重新 attach Engine，并重新创建 `ObserverView`。Runtime、index 和 Scheduler heap 不被 pickle。

使用 `--debug` 才会启用：

```text
:truth
:queue
:trace
:stats
```

每次输出都标记 `[PRIVILEGED DEBUG]`。这些命令在普通模式不可用。该对比面用于人工检查 actor Observation 与 true world，不属于玩家信息。

The playable harness constrains user commands at the application layer. PMW v2.8 itself does not yet provide actor action authorization.

## Verification

```bash
PYTHONPATH=src python examples/ash_observatory/verify_scenarios.py
```

验收器中的 Social、Technical、Force 三条胜利路线都通过真实 `watch → label → ActionSpec → Event` 交互层执行。它还覆盖 action 的编号/label/内部 ID 等价性、context 转换、菜单 label 唯一性、diff invariant、陷阱 locality/触发发现/一次性搜索、隐藏信息、流血/绷带、channel cancel、未来无人机、战斗闭包、错误密码和 temporal save/load。成功结束时输出：

```text
ALL PLAYABLE WORLD SCENARIOS PASSED
```
