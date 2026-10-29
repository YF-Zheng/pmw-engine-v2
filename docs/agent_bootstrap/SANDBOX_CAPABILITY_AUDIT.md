# P0 Sandbox Capability Audit

日期：2026-10-28。基线：`feature/alpha-v02-seventh-night`，
`1433e957d5391b880b71e92da4b5cf2ebd9751cd`。未重写 Engine。

分类：V=已实现并本轮验证；I=实现但不满足完整契约；
E=实验模块（可能真实调用 Engine，不等于已接入 Alpha）；
N=尚未实现；D=已复现的契约风险/缺陷。

## Baseline Evidence

本轮现有测试：Core 254 / v06 170 / Gameplay 172 / Alpha+M0 48，
合计 **644 passed**，并有 3,033 个 pytest subtests。四份完整命令与结果位于
`evidence/p0_*_qa_pytest.txt`；耗时分别 32.75 / 32.13 / 96.91 / 129.59 秒。
本地 Python 3.12、`PYTHONPATH=src`，未安装网络依赖。

另实际执行：

```powershell
$env:PYTHONPATH = 'src'
python -m experiments.generative_mechanics.next_tracks_v06.demos.run_demos --output docs/agent_bootstrap/evidence/p0_mechanisms
```

五个机制轨迹（含 Law、proposal/delta、scheduler、causal trace、最终真实
WorldState）保存于新 evidence 目录。未覆盖历史 demo/results。
`test_worlds_demos.py:74` 验证字节确定性，`:108` 校验历史结果可重建。

## Six State Types

| Capability | Status | Code / real verification | Gap |
| --- | --- | --- | --- |
| Field | V/I | v06 `spec.py:32`; Gameplay `contracts.py:23`, `blueprints.py:52`; Gate1 dynamics tests | catalog单位/观察权限需统一；Alpha未暴露完整目录 |
| Stock | E/I | v06 `spec.py:49`, `validator.py:249`, `compiler.py:331`; runtime tests `test_stock_transfer_is_conserved` | Alpha仍是 Area库存字典；无统一来源/容量适配 |
| Process | E/I | v06 `spec.py:65`, `worlds/thermal.py`, `worlds/electric.py`; runtime tests process_start/modify | 操作既有 Process；模板及过程规则固定，非通用输入输出过程实例 |
| Relation | V/E/I | core `types.py:25`, Engine lifecycle preflight; v06 `spec.py:81`, compiler relation create/delete/modify tests | Alpha路径关系存在，生成技能拓扑权限未接入 |
| Discrete | E/I | v06 `spec.py:96`, validator transitions; Gameplay weather/ecology Laws and Gate3 tests | 有真实转换；完整目录与技能条件暴露仍缺失 |
| Derived | E/I | v06 `spec.py:108`; `test_structural_derived_is_world_law_output`; compiler拒绝派生写入 | read-only 是受信 compiler 的权限边界，Core本身仍允许管理员Law写组件 |

Core保存 Entity/Relation 的有限 JSON components，不原生声明上述六类目录。
六类类型在 v06 catalog 层；不能把目录类的存在当作 Alpha 已全面支持。

## Seven Operators

通用 v06 lowering：`compiler.py:262`（activation）、`:295`（expiry）、
`:331`（持续流）；`validator.py:451` 参数权限验证；`:582` 后续预算检查。

| Operator | Status | Verified behavior | Alpha gap |
| --- | --- | --- | --- |
| impulse | V/E | `test_runtime.py:28`、`:35`，仅改变当前量 | Gameplay有modify_field/damage等，但目录尚未统一 |
| drive/source | E/I | `test_runtime.py:47`、`:175`，有界流、守恒转移和到期 | Gameplay可用 effect 列表无持续源/转移通用入口 |
| attractor_modifier | V/I | `test_runtime.py:41`，Gate1 persistent/temp source tests | weighted target可用；偏移/倍率语义未完整暴露 |
| dynamics_modifier | V/I | v06 alpha/conductivity；Gameplay rate/multiplier/curve priority | Blueprint只暴露modify_rate，非完整curve/params |
| process_start | E/I | `test_runtime.py:155`：真实 Process 驱动 Law | 缺通用模板实例与 Actor行动桥接 |
| process_modify | E/I | `test_runtime.py:161`：改变消耗速率 | 暂停/恢复/进度/剩余持续期未形成统一语言 |
| relation_modifier | V/E/I | `test_runtime.py:168`、`:185`、`:195`，影响实际关系和后续规则 | 权限/作用域/生命周期仍需 Gameplay桥接 |

七类 Operator 已真实执行，**但都属于完整实现且已接入 Alpha**这一说法不成立。
未来技能不得靠名称分支、专属 Python 函数或 UI 自行结算。

## Dynamics, Clock And Transactions

| Capability | Status | Evidence / precise semantics |
| --- | --- | --- |
| target/rate/curve | V/I | Gameplay `dynamics.py:62` effective_dynamics 与 Law lowering；600-case两曲线独立 oracle |
| no recovery | I | rate=0可模拟；显式curve='none'被 `blueprints.py:69` 拒绝（下方反例） |
| linear/squared bounded recovery | V | `contracts.py:39`, `blueprints.py:75`：线性rate<=1，平方rate*width<=1 |
| multiple modifier ownership | V | Gameplay `runtime.py:106`/`:164`、Gate1临时到期/优先级测试；v06 competing_expiries |
| all-Area evolution, no default diffusion | V | Gate1 `test_adjacent_areas_do_not_implicitly_diffuse`、`test_multiple_active_area_actor_fields_advance_once_each` |
| Law closure / causal parent | V | Core `engine.py:142`/`:201`；Core差分和multilevel trace测试 |
| Scheduler | V | Core `runtime/session.py:228`/`:236`；time/id顺序、取消、重排、持久化测试 |
| gameplay transaction | V | `gameplay_v04/transactions.py:10`, `time_ledger.py:78`；Gate52 staged rollback tests；Alpha `session.py:72` clone/perform |
| whole-cascade Core rollback | D (documented low-level boundary) | Core每个publication可原子，但事件链中后续失败保留先前commit；不可把裸Core API当作玩家事务 |
| Actor/NPC authority | V/I | Gameplay同一Action/runtime；Gate5 AI合同测试；非完整七Operator技能 |
| actor-safe observation | V | Core default-deny Observation，1000-case noninterference；Gameplay隐藏技能/规律不得影响plan |
| execution budgets | I | Core cascade=1000、closure=100、scheduler advance=10000；v06 slots/target/instance budgets，passive per-root<=8 | 

无通用 per-Tick 总触发数、CPU/query复杂度、动态Process总量预算闭环；不能只靠
编译器效果数量限制宣称递归安全完整。唯一生产 Tick 顺序见 `SANDBOX_SPEC_V1.md`。

### Minimal Reproductions

显式 no-recovery 缺口（已执行）：

```python
parse_field_definition(dict(id='finite_stock', domain=dict(min=0, max=10),
                            initial=2, target=8, rate=0.2, curve='none'))
# GameplayContractError: curve must be one of ('linear', 'distance_squared')
```

Core裸事件链的风险（已执行）：root Law把value.amount从0设为1并emit crash；
crash Law执行div(1,0)，抛ZeroDivisionError后真实value.amount仍为1。
这不是644测试中的新回归；是必须遵守的事务边界。世界失败不得靠新增SkillSpec
绕过Gameplay暂存/完整提交机制。Core已有
`tests/test_engine.py:993` 明确 scheduled root failure consume-on-dispatch。

## Skill / Registry / Alpha / M0

Gameplay `skills.py:30` 提供版本、材料权限、budget、canonical hash、condition、
effect序列及**单一trigger**。`:71` 只接受固定主动/被动trigger集合；
`effects.py:15` 不包含 Process/Relation/start/drive；`contracts.py:11`
selector只有5类，不含Matching Processes/Relations等。

v06 `spec.py:164` 的 MechanismSpec 有scope/capability/operators，但缺
完整action成本、装备、玩家材料、display、多trigger。两个语言的既有能力
可复用，不能直接把其中一个改名叫v1 IR。

Alpha `skills.py` 明确生成四种Core×三种Modifier的12张技能，`session.py`
craft/equip/cast进入Gameplay Registry，但森林/升降机交互仍有内容专属动作。
这些世界内容可保留，不能作为新生成技能的效果实现策略。
Alpha已具探索/战斗/路径/终局/存档和UI；M0 Storm Relay现有测试也通过。
保存这些可玩基线；API局内生成与30个自由机制参考技能、200-500候选评估均为N。

## Ten P1 Scenario Gates At Audit Baseline

1. 离区持续变化：既有跨Area动力学/Alpha森林持久性有测试；需要统一IR技能入口。
2. target与rate分离：既有Gameplay source和v06 impulse/attractor对照通过。
3. 多修改独立到期：现有owned slot测试通过。
4. Process消费Stock生产另一Stock：示例有资源Law，但通用转换模板缺失。
5. Process改rate与duration：示例rate通过；统一duration/remaining语义缺失。
6. 被动event及无限递归阻止：既有hook/per-root上限；通用多trigger/global预算缺失。
7. Relation改变供能/通路：v06供能轨迹通过；玩家技能权限桥接缺失。
8. Discrete由Law转换：天气/生态与世界示例通过；统一catalog暴露缺失。
9. Derived依赖变化：structural/thermal示例通过；正式只读目录桥接缺失。
10. Player/NPC同执行：Action系统通过；完整新SkillSpec仍需测试。

## P0 Gate

**PASS for audit/boundary freeze**，不是P1/P4或新游戏验收。644现有测试
全部通过，能力矩阵与可复用入口明确，现有Core不重写。
首先实施 P1.1 explicit none recovery；随后通用Stock/Process与七Operator
Action桥接。具体文件所有权/任务顺序见 `ALPHA_DEV_PLAN.md`。
Gameplay独立细审与QA补充见 `P0_GAMEPLAY_AUDIT.md` / `P0_BASELINE_QA.md`。

## 2026-10-29 Bounded Capability Updates

The tables above remain the P0 audit baseline, not the current implementation
matrix. Subsequent accepted increments add explicit bounded no-recovery and
live baseline-curve dispatch, plus trusted Stock conversion on the Gameplay
clock. The typed Process start bridge is now formally parsed as an Effect and
SkillBlueprint, capability/budget checked, registered/equipped and dispatched
through the same player/NPC Action entry. Quantitative paid ticks use existing
Process Laws; failed cascade/time requests retain no partial staged state.
Controller profiles and endpoint bindings are trusted static content with
local Area/owner checks and checkpoint comparison, never candidate JSON.

Latest frozen full regression: 742 tests / 3,141 subtests passed, 271 unchanged
Python hashes. Evidence and independent review: `P1_PROCESS_ACTION_INCREMENT.md`
and `P1_PROCESS_ACTION_REVIEW.md`. No old baseline tests were discarded.
Still missing at that start checkpoint: data-authored Process modification/drive/Relation bridges,
full multi-trigger IR/global resource budgets, dynamic template generation,
Alpha inventory/UI and Process Observation/planning. Full P1 remains open.

### Subsequent Bounded Process Modification Update

Verified data-authored `process_modify` now parses and capability/budget checks
rate and remaining duration, registers/equips normally and runs through the same
player/NPC staged Action and existing Process Laws/expiry. All endpoints remain
owner-local. Exact trusted modification Law, after-values and scheduler time
are confirmed; real event and late-tick failures roll back completely.

Owner tests include privileged native start setup, so they are supporting
coverage, not formal-start evidence by themselves. Independent cold-catalog,
normal-equipment paid Action tests provide that formal evidence, quantitative
2 ore -> 1 ingot conversion, hard deadline, replay and Observation boundaries.
Full frozen regression: 759 passed / 3,152 subtests, 273 unchanged Python hashes.
Reports: `P1_PROCESS_MODIFY_INCREMENT.md`, `P1_PROCESS_MODIFY_REVIEW.md`.

Still open: rate-only false rejection after saturated native ticks (real prior
checkpoint reproduction in `evidence/p1_process_modify_saturation_baseline.json`),
Skill pause/resume/progress writes, drive/Relation bridges, full multi-trigger IR,
global budgets/locality and Alpha Stock UI/Process Observation/planning.
No dynamic templates, generator calls, full P1 or P2 acceptance is claimed.

### C1 Native Expiry And Optional Schema Repair

The saturated rate-only guard now validates actual scheduled expiry, not
now + stored productive remaining, and retains exact lifecycle/harddeadline.
Independent pure-rate verification also exposed a genuine prior schema bug:
strict key equality required both supposedly optional numeric fields. Original
rate-only/remaining-only rejection versus both-key acceptance is retained in
c1_optional_fields_before.json; a narrow required/allowed-key repair fixes it.

Independent cold catalog and normal player/NPC pure-rate Primary Actions,
Main's genuinely timed pure-rate calls, expiry, rollback and replay pass.
Complete frozen regression776/3,180, 276 immutable hashes; no old tests changed.
Reports: C1_RATE_EXPIRY_INCREMENT.md and P1_PROCESS_RATE_EXPIRY_REVIEW.md.
This closes those two bounded defects, not full P1 or the wider Process/Drive/
Relation/global-budget/IR/Alpha UI gaps. C2 source design is not yet implementation.

### C2 Finite Stock-To-Field Source Update

C2 bounded finite Stock-to-Field source is ACCEPTED: frozen full regression793 passed/3,195 subtests in388.43s, exit0, all279 Python hashes unchanged. Owner11/7, independent6 methods, Main focused53/30 and complementary8 denials pass. Reports: C2_STOCK_FIELD_DRIVE_INCREMENT.md / C2_STOCK_FIELD_DRIVE_REVIEW.md; complete metadata/log: evidence/c2_drive_frozen_full_regression_meta.json / c2_drive_frozen_full_regression.txt. Existing clock, Engine, staged Action, Observation, Alpha and all87 tracked test files at a4ad912 remain protected. Positive finite source only; no sinks/open source/universal Field units, Alpha UI, complete P1/P2 or generation claim. Local checkpoint subject: feat: add bounded stock-fed field sources. Next independent task C3_RELATION_MODIFIER_DESIGN.md, then C4_CONDITION_BUDGET_DESIGN.md and remaining P1 gates.

Capability limits are finite per trusted controller (defaults16 registered/8 active), not a proved global CPU/query bound. World root matches pre-dynamics; child executes after natural recovery and closure. Field units remain a documented catalog gap. Existing topology selectors are not altered by this source increment.
