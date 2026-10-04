# PMW Engine v2.8

v2.8 adds a deterministic, default-deny Observation projection between true world state and actor-facing integrations. v2.7.1 temporal handles, lifecycle locality, matcher, COW, closure, topology, Scheduler, trace, and revision semantics remain frozen. Observation policy is Engine configuration and never persisted into `WorldState`. The suite contains 254 tests with no expected failures, including fixed-seed 1000-case information-noninterference and observation-matcher differentials.

> **WorldState is truth, not perception.**

> **Observation is an information boundary, not merely a convenience serializer.**

## True State vs Observation

`WorldRuntime`, its `state`, and mutation/Scheduler methods are the privileged simulation and administration interface. `WorldSnapshot`, `EventResult`, and `CausalTrace` are privileged diagnostics and tooling interfaces; a snapshot is not actor-safe merely because it is read-only. `ObserverView` and `Observation` are the designated actor-facing information boundary:

```python
rules = load_observation_rules("observation.json")
runtime = Engine(laws, observation_rules=rules).attach(world)
view = runtime.observer("npc:alice")
actor_json = view.observe().to_dict()
# Equivalent: runtime.observe("npc:alice")
```

AI and player integrations should receive `ObserverView` or an `Observation`, never `WorldRuntime`, `WorldState`, `WorldSnapshot`, raw trace, or runtime stats. The boundary prevents accidental or model-facing world-information disclosure when applications use the designated actor API. It is not an OS/process security sandbox against hostile Python code that already holds a `WorldRuntime` reference.

Observation is derived on demand as `true state + observation policy -> projection`; it is not stored and does not add memory, known facts, visibility caches, or observations to `WorldState`. Calling `observe()` cannot settle laws, create events or traces, change tick/time/revisions, touch the Scheduler, or change `state_closure_known`. It may only increment observation instrumentation.

### Observation Rules

Observation rules are independent world-mechanics data loaded by `load_observation_rules()`. They reuse the frozen binding grammar, Condition DSL, `MatchPlan`, indexed matcher, and persistent `WorldIndex`; there is no second visibility expression language. Every rule receives a reserved entity binding named `$observer`, seeded directly from the requested ID. Authors may not declare `bindings.observer`, and `$event` is invalid everywhere because projection has no causal event.

```json
{
  "schema_version": "2.0",
  "observation_rules": [{
    "id": "observe-visible-entity",
    "bindings": {
      "subject": {"kind": "entity"},
      "visibility": {"kind": "relation", "type": "visible_to", "source": "$observer", "target": "$subject"}
    },
    "when": {"all": []},
    "subject": "$subject",
    "reveal": {
      "core": ["archetype", "name"],
      "tags": ["wounded", "burning"],
      "components": ["appearance", "health.visible_state"]
    }
  }]
}
```

`subject` is exactly `$observer` or a declared root binding, and each match grants one Entity or Relation. Self-visibility is not special: it requires an ordinary rule with `subject: "$observer"`. A missing/non-Entity observer raises `MissingObserverError`. Plans compile once in `Engine`, and the seeded observer makes self-only matching scan-free while relation-gated rules query only the observer's indexed neighborhood.

### Default-Deny Projection

With no matching grant, `entities` and `relations` are empty, including for the observer itself. A granted object's `id` is always present as its stable reference; every other field is explicitly allowlisted:

- Entity core fields: `archetype`, `name`.
- Relation core fields: `type`, `source`, `target`.
- Tags: only named tags that both exist and appear in `reveal.tags`.
- Components: exact dict paths such as `appearance` or `health.hp`; wildcards and array traversal are unsupported.

A whole-component grant deep-copies that component. A nested grant copies only the named path. Missing paths and paths crossing a list are omitted without error. Empty `tags`/`components` are omitted. Projected values are deeply owned, so later world changes and mutations to `to_dict()` cannot affect one another.

Relation endpoint identity is protected in two phases. The projector first computes all visible Entity IDs, then includes a granted Relation's `source` or `target` only when that endpoint Entity was separately granted. Revealing a relation therefore cannot leak an otherwise-hidden object ID.

Multiple matching rules form a monotonic set union; there are no deny, priority, or mask overrides. Rule IDs and output objects are sorted, tags are sorted, repeated rule/subject grants are deduplicated, and input rule order cannot affect canonical output.

Observation never contains `world_id`, tick, `sim_time`, runtime/object revision, Scheduler state, RNG state, index details, stats, law/proposal IDs, `EventResult`, or trace. Tick is especially sensitive because a hidden scheduled root increments it even when no visible fact changes. If actors should know time, model a clock as an ordinary Entity/component and grant it explicitly.

`RuntimeStats` exposes observation calls, rules, matches, raw/deduplicated grants, returned Entity/Relation counts, component paths copied, and matcher candidate rows. These privileged counters never enter actor output. Run `PYTHONPATH=src python3 benchmarks/observation_bench.py` for SELF_ONLY, LOCAL_RELATION, FIELD_REDACTION, MANY_OBSERVERS, and FIXED_DEGREE_WORLD_SCALE. Executable policy sketches for NPC public/private state, a discovered trap, and actors with asymmetric knowledge are in `examples/observation_prototypes.py`.

Spatial visibility is not hard-coded into the projection engine. A future spatial layer may maintain ordinary relations/components consumed by Observation rules, but line of sight, distance, room graphs, sound, actor memory, event perception, and action authorization are outside v2.8.

## Temporal Handles

`emit_event` expresses causal derivation and retains Engine-generated IDs. An emitted event at or before `sim_time` remains in the current causal cascade; a future one is persisted for later dispatch. `schedule_event` instead expresses a named independent scheduled root, requires an explicit ID, and always enters the Scheduler, including when its time equals `sim_time`:

```json
{
  "op": "schedule_event",
  "event": {
    "id": "$event.payload.expiry_event_id",
    "type": "status_expire",
    "time": {"add": ["$event.time", "$event.payload.duration"]},
    "source": "$event.source",
    "target": "$event.target",
    "payload": {"status_id": "$event.payload.status_id"}
  }
}
```

The explicit event requires non-empty `id` and `type`, finite `time >= runtime.sim_time`, string-or-null endpoints, and a finite JSON object payload. Author provenance is forbidden; Engine records `{"kind":"scheduled","parent_event":"<current event id>"}`. Applications should use stable, structured, non-recycled temporal IDs such as `expire:buff:001`, `complete:craft:842`, or `pulse:poison:17`; Engine treats their structure as opaque.

Event laws may use `cancel_scheduled` with a Value DSL expression resolving to a non-empty event ID, or `reschedule_scheduled` with an `{id,time}` value. Cancellation is idempotent. Rescheduling a missing ID raises `MissingScheduledEventError`; rescheduling to the existing time is a no-op. Direct runtime equivalents share the same preflight and publication implementation:

```python
runtime.cancel_scheduled(event_id)             # pending -> True, missing -> False
runtime.reschedule_scheduled(event_id, time)   # changed -> True, same -> False
```

All three scheduler effects are Event-Law-only. Cancellation and rescheduling never implicitly modify Entity/Relation state, and object deletion never implicitly cancels a handle. A world law must state both sides of the temporal contract explicitly.

### Duration And Recurrence

A finite status stores its owned handle in ordinary data, for example `duration.expiry_event_id = "expire:buff:001"`. Its start law creates the status Relation and schedules that ID; its expiry law binds the Relation by the payload's exact `status_id` and deletes it. Dispel/channel interruption atomically delete their Relation and cancel the stored handle. Refresh reschedules the one existing expiry instead of creating a second event.

A recurring discrete process consumes `pulse` as a scheduled root, applies an effect, and schedules the next `pulse` with the same ID. Reuse is legal because the current root is consume-on-dispatch. A condition simply stops scheduling the next root. PMW does not introduce a first-class Process object: durable process semantics are Entity/Relation data plus explicit scheduled-event handles. Continuous integration, per-tick laws, interpolation, spatial semantics, and ODEs remain outside this version.

## Dynamic Object Lifecycle

`create_entity`, `create_relation`, `delete_entity`, and `delete_relation` are deterministic world effects with normal proposal and trace provenance. Creation is event-law-only; state laws may delete a bound object but may not create objects. IDs are supplied explicitly by application/world data and share one Entity/Relation namespace.

Lifecycle preflight validates final relation endpoints and rejects duplicate IDs, create/delete conflicts, dangling relations, and deletion of an Entity that still has incident Relations. Relations must be explicitly deleted in the same transaction; deletion never cascades implicitly. Scheduled event source/target values remain opaque IDs and are never rewritten on deletion.

Lifecycle structural validation is local. Namespace and endpoint checks use direct map membership only for IDs participating in the transaction, while Entity deletion uses persistent source/target incident-relation postings. Production preflight never materializes a copy of the complete Entity/Relation ID namespace or final Entity set. Its structural work is proportional to lifecycle batch size, created Relation endpoints, and deleted Entity degree; large numbers of independent duration expirations therefore do not repeatedly scan unrelated world objects.

`RuntimeStats.lifecycle_id_membership_checks`, `lifecycle_endpoint_checks`, `lifecycle_incident_relation_checks`, and `lifecycle_global_scans` expose that contract. Production keeps `lifecycle_global_scans == 0`. The extended `duration_bench.py` reports DURATION_STATUS through 5000 active handles, fixed-status world scaling through 500k unrelated entities, and MANY_SMALL versus ONE_BATCH. `benchmarks/lifecycle_preflight_profile.py` reproduces the 100k-entity/100-expiry profile gate.

### Creation Contract

`create_entity.value` resolves through the ordinary Value DSL to an object with required non-empty string `id`, optional string `archetype`, optional string-or-null `name`, unique string `tags`, and finite JSON object `components`. `create_relation.value` additionally requires non-empty string `type`, `source`, and `target`. PMW does not allocate hidden IDs. Applications should use non-recycled, generation-aware IDs when stale references matter.

Create proposals use root addresses such as `entity:projectile-42`, and delete proposals target the bound object's root address. Create/create, create/delete, entity-create/relation-create, and delete/value-write combinations on one object ID are hard conflicts. Duplicate deletes merge into one action while preserving all proposal and law provenance.

### Structural Mutation Atomicity

`PreparedWorldMutation` separates preparation from publication. Ordinary COW replacements, lifecycle creations/deletions, final ID and relation integrity, future scheduler membership, index changes, and lifecycle `StateDelta` values are all prepared before the live world changes. Expected validation failures leave the world, queue, revisions, and existing index contents untouched. Publication explicitly removes relations before entities, inserts entities before relations, then publishes COW replacements and the prepared scheduler batch.

Lifecycle deltas use root paths: creation records `old=null` and a deep-copied object representation in `new`; deletion records the inverse. They therefore flow through `EventResult`, `CausalTrace`, semantic projection, and incremental State Closure without a parallel result system. A new relation can immediately activate a structural relation join, while a deleted object never becomes a synthetic seed.

Future event references remain opaque identifiers. Deleting an object does not rewrite queued event `source`, `target`, or `payload`; applications requiring stale-reference safety should use non-recycled object IDs and explicit laws for missing targets.

## Simulation Time And Scheduler

`WorldState.sim_time` is the finite, monotonic logical clock. `WorldState.tick` counts scheduled root-event dispatches, not fixed-duration frames. Immediate intervention through `runtime.run_event(event)` remains compatible and never advances either scheduler time or tick.

The Scheduler API is `runtime.schedule(event)`, `runtime.cancel_scheduled(id)`, `runtime.reschedule_scheduled(id,time)`, `runtime.step()`, `runtime.advance_to(target_time)`, `runtime.advance_by(delta)`, and `runtime.peek_next_time()`. Scheduled roots use canonical `(time, event_id)` ordering. A root completes its entire immediate causal cascade and state closure before the next scheduled root dispatches, including at the same timestamp. Thus lexical-first `A@5` can cancel `B@5` before B dispatches, postpone B outside the current advance, or pull a later B into the same advance.

`WorldState.scheduled_events` is the persisted source of truth. `RuntimeScheduleQueue` is a lazy, runtime-only versioned heap of `(time,id,version)` entries plus an ID-to-persisted-list position map. Cancel is O(1) swap-delete and version invalidation; reschedule is O(1) lookup/replacement plus one O(log N) heap push. Peek/pop discard stale versions, so cancel-and-reuse cannot dispatch an old entry. When `heap > 2 * live + 1024`, a deterministic size-only compaction rebuilds it. `scheduler_stale_entries_skipped` and `scheduler_heap_compactions` expose this behavior; the test-only `rebuild_each_operation` mode is the differential oracle.

An emitted derived event with `time > sim_time` becomes a persisted future scheduled event. Same-time or overdue derived events remain in the current immediate causal cascade. Future scheduling is preflighted before COW publication, so a duplicate future ID cannot partially commit accompanying state writes. A scheduled root is consume-on-dispatch: its pending entry is removed, time/tick advance, and any later execution error does not requeue it.

Time-only advancement does not run state closure. Real schedule/cancel/reschedule mutations advance runtime revision but not `object_revision`; missing cancel and same-time reschedule do neither. The persistent `WorldIndex` therefore remains reusable. `PreparedSchedulerMutation` carries additions, cancellations, and owned-copy reschedules inside `PreparedWorldMutation`; all scheduler, COW, lifecycle, endpoint, and collision checks finish before publication. Any preflight failure leaves world objects, lifecycle, queue, revisions, and index unchanged. Run `PYTHONPATH=src python3 benchmarks/duration_bench.py` for CANCEL_WARM, RESCHEDULE_WARM, CHURN, HEAP_COMPACTION, DURATION_STATUS, and RECURRING results.

Scheduler instrumentation includes `scheduled_pushes`, `scheduled_pops`, `scheduled_cancellations`, `scheduled_reschedules`, queue builds/reuses, cancel/reschedule membership checks, stale entries skipped, and heap compactions. The 100k warm structural regressions require one cancel to preserve heap size and one reschedule to add exactly one heap entry without a queue rebuild, unless the deterministic compaction threshold is crossed.

## Runtime Session

`WorldState` remains the serializable source of world facts. `WorldRuntime` is runtime-only and owns `state`, `revision`, validation trust, and instrumentation. Use `engine.attach(world)` for a long-lived hot loop; `engine.run_event(world, event)` remains the safe convenience API and attaches for one event.

`WorldSnapshot` is the public, shallow stable snapshot: it freezes the id-to-object reference mapping, not a deep copy of the world. Snapshot stability is guaranteed because commits replace modified Entity/Relation objects instead of mutating objects visible to prior snapshots. Mapping copies are shallow and are recorded by `RuntimeStats.snapshot_mapping_copies`.

## Runtime Index Lifetime

`WorldIndex` is a derived, lazy `WorldRuntime` cache, never part of `WorldState` or `WorldSnapshot`. Engine collection uses an internal, nonescaping zero-copy evaluation view; public snapshots remain an explicit API and retain their shallow-copy isolation contract. An exact-id-only workload does not materialize an index.

The cache is owned by one runtime and is not thread-safe. It is built on the first indexed query, reuses the live runtime mappings, and is retained across commits. Entity lifecycle patches component postings locally. Relation lifecycle patches type, source, target, composite-key, and component postings locally; a warm create/delete does not rebuild the index. Ordinary nested component field writes do not alter component-root postings. A patch failure invalidates only the cache after the WorldState commit has already succeeded. `runtime.revalidate()` invalidates the cache because external mutation is an explicit ownership boundary.

`RuntimeStats` exposes runtime index builds/reuses/patches/invalidations, lifecycle counts and preflight failures, entity/relation component-posting changes, relation topology posting adds/removes, evaluation views, and public snapshots. The test-only `_runtime_index_mode="rebuild_each_view"` backend is a cache-free correctness oracle. Run `PYTHONPATH=src python3 benchmarks/lifecycle_bench.py` for CREATE_ENTITY, CREATE_RELATION, DELETE_RELATION, cold/warm DELETE_ENTITY_ISOLATED, DELETE_ENTITY_WITH_RELATIONS, and 10k-relation TOPOLOGY_CHURN output.

## Copy-on-Write Commit

Accepted proposals are grouped by target object. A touched object is cloned once, all changes are prepared on that clone, and only after preparation succeeds are references swapped into the live state. Untouched object identities remain shared. A failed prepare never leaks a partial mutation. Runtime revision advances only when real StateDelta exists.

After attaching a runtime, external callers must not mutate `runtime.state` objects directly. Call `runtime.revalidate()` after deliberate external tooling changes to restore the validation boundary. `revalidate()` is an explicit ownership-boundary operation and advances the runtime revision; normal event processing validates only the root event and the objects it is about to publish.

Revision tracks semantic world-state mutation, not internal runtime replacement: no-op transactions do not clone, swap, or replace identity. All committed component values belong to PMW's finite JSON-compatible state-value domain: `null`, booleans, strings, integers, finite floats, and recursive lists/objects with string keys. Long-lived Runtime performs full validation at attach/revalidate boundaries and validates the complete touched-object write set before any COW swap.

`RuntimeStats` reports snapshot/mapping-copy counts, cloned and swapped objects, full-world validations, root-event validations, prepared/committed/no-op transactions, and locally validated objects. It deliberately records `full_world_deepcopies = 0`: production commits never deep-copy `WorldState`.

PMW 是一个 frozen-code、data-driven 的世界演化内核。Engine 只理解 `Entity`、`Relation`、`Event`、`Law`、`EffectProposal`、`WorldState` 与时间；火、水、技能、NPC、战斗及其他世界语义一律属于外部数据。

## Event Law 与 State Law

Law 的 `mode` 为 `event` 或 `state`，省略时默认为 `event`。

- **Event law**：对当前真实事件只匹配、执行一次；可读取 `$event`、当前 WorldState 和绑定对象。它不会因之后的状态结算而再次运行。
- **State law**：在 event phase 提交后执行，用于 `A -> B -> C` 这类纯状态级联；它是纯 WorldState 闭包，不能访问 event 或 provenance。

一次 root event 的完整流程为：

```text
event laws on S0 -> resolve -> atomic commit S1
state laws on S1 -> resolve -> atomic commit S2
state laws on S2 -> ... -> local fixed point
derived events enter causal queue -> each repeats the same flow
```

## Incremental State Closure

State Law 的 authoring contract 不变，但 `Engine` 现在会编译 runtime-only `StateDependencyPlan`，保守追踪每一个能够改变 binding candidate set、condition truth、computed effect value 或 effect 是否已经满足的 world-state 输入。依赖来源包括 condition reads、tag/component predicate、binding `requires`、effect value expression，以及 set/delta target 与 tag-write target。首次 closure（或 `runtime.revalidate()` 后）使用保守 full scan；成功后 runtime 记为 state-closed。增量 closure 是 frontier-driven：每一轮只重新考虑被最近 `StateDelta` frontier 变得可能 stale 的规则，并以 dirty object 作为 matcher seed 继续复用 MatchPlan、relation join 和 canonical ordering。

Condition comparator RHS、`has_tag` operand 与 `has_component` operand 都使用完整 Value DSL。动态 membership operand 若结果不是 string，condition 为 false；无法进行 `gt/gte/lt/lte` 比较时会抛出明确的 `DSLConditionTypeError`。

`runtime.settle()` 可显式建立初始 closure；当它已知 closed 时是 no-op，`runtime.settle(force_full=True)` 用于调试/reference。依赖无法精确归因的 state law 保持 global fallback，每一轮最多 full-match 一次。`RuntimeStats` 公开 full/incremental scan、activation、dirty delta、seeded candidate 和 global fallback 计数。运行 `PYTHONPATH=src python3 benchmarks/state_closure_bench.py` 可查看 100k-object 的 LOCAL_CHAIN、LOCAL_RELATION、TEN_DIRTY 与 GLOBAL_FALLBACK 结构指标。

## Snapshot 与提交语义

同一 event phase 或同一 state-settling round 的所有 Law 都读取同一个只读 evaluation view。Law 只创建 `EffectProposal`，不能直接修改 WorldState。所有提案先经 Resolver，再以一次原子提交写入世界。该 view 仅供 Engine 内部使用，绝不替代公开的 `WorldSnapshot`。

因此 Python 的容器遍历顺序、JSON 文件中 law 的排列顺序，都不能成为世界规律的一部分。Law、绑定对象、提案地址均采用稳定排序。

## Resolver 冲突矩阵

| 同一地址的提案 | 冻结行为 |
| --- | --- |
| `delta` + `delta` | 数值求和，成为一个规范化事务操作。 |
| `set` + `set`（不同值） | 优先级高者获胜；相同优先级时 `law_id` 字典序更小者获胜，并记录 conflict。 |
| `set` + `delta` | 硬冲突，抛出 `ProposalConflictError`。 |
| `add_tag` + `add_tag` | 幂等合并。 |
| `remove_tag` + `remove_tag` | 幂等合并。 |
| `add_tag` + `remove_tag` | 使用与 `set` 相同的优先级/law-id 决策，并记录 conflict。 |
| `emit_event` | 全部保留，不参与状态地址冲突。 |
| `cancel_scheduled` + `cancel_scheduled` | 幂等合并并保留全部 provenance。 |
| 相同时间的 `reschedule_scheduled` | 幂等合并并保留全部 provenance。 |
| 不同时间的 reschedule，或 cancel + reschedule | `scheduled:<id>` temporal domain 硬冲突。 |
| 同 ID 的任意 `schedule_event` 组合 | 硬冲突；已 pending ID 在 preflight 抛 `DuplicateScheduledEventError`。 |

`max_settle_iterations` 默认是 100。若 state law 持续改变世界而未收敛，引擎抛出 `NonConvergentWorldError`，给出涉及的 law 与目标地址。无变化的 `set` 不生成 StateDelta，因而会自然收敛。

## Derived Event、ID 与 Trace

一个 cascade 中提案 ID 形如 `proposal:<root-id>:000001`，派生事件 ID 形如 `derived:<root-id>:000001`。二者各自在单次 cascade 内严格单调且不重复，不使用 UUID 或随机数。

`EventResult.trace` 是可序列化的 `CausalTrace`。`trace.to_dict()` 记录 root event、每个匹配的 law 与 binding、提案接受/拒绝原因、commit、StateDelta 和派生事件。真实 `StateDelta` 明确保存 address、old、new、cause proposal IDs 与 law IDs。

Scheduler mutation 不是伪造的 StateDelta。`CommitTrace` 与 semantic projection 独立记录 canonical `scheduled_event_ids`、`cancelled_event_ids` 和 `{id,old_time,new_time}` reschedules；`EventResult` 也直接暴露 scheduled/cancelled/rescheduled IDs，因此调用方无需 diff pending queue 才能理解 temporal effects。

## Simulation Tick 与 Microstep

`run_event()` **不自动推进** `world.tick` 或 `world.sim_time`。一个 root event 及其所有 causal cascade 都由内部 `microstep` 在 Trace 中排序；Scheduler 的 `step()`、`advance_to()` 和 `advance_by()` 独立拥有时间推进与 tick 语义。

在相同 World、Event 和 Seed 下，PMW 的结果与 Trace 都是确定的。

## 运行示例

```bash
PYTHONPATH=src python3 -m pmw --world scenarios/v2/world.json --laws scenarios/v2/laws.json --event scenarios/v2/impact.json
```

## 开发验证

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

本版本刻意不实现 automatic ID allocator、component removal、relation endpoint/type mutation、rename、implicit cascade delete、continuous process system、event perception、action authorization、spatial layer 或任何高层玩法系统。

## Validation Pipeline

`load_world()`、`load_laws()` 和 `load_observation_rules()` 在构建运行时对象前先运行 Python semantic validator。`schemas/` 提供 JSON Schema 的基础结构规范；当前运行时依赖 Python validator 执行跨对象和 DSL 语义检查，避免把语义规则塞进 Schema。

合法 PMW 文档在结构或可静态识别的语义歧义存在时，必须在执行前被拒绝。验证异常包括 `PMWValidationError`、`WorldValidationError`、`LawValidationError`、`ObservationValidationError` 和 `ReferenceValidationError`，信息包含 document、rule/law/object id、path 与原因。

Entity 与 Relation 共用同一个 object-id namespace。重复 entity/relation/scheduled-event/law ID、relation 的悬挂端点、非有限时间值、未知 binding 和不合法 effect target 均在加载期失败。

## State Law Purity

State law 是仅关于 WorldState 的纯闭包：它不能在 `when`、effect target/value 或 binding constraint 中引用 `$event`，也不能 `emit_event`、`schedule_event`、`cancel_scheduled` 或 `reschedule_scheduled`。需要事件上下文或 Scheduler mutation 的规则必须是 event law。

## Matcher Architecture

`MatchPlan` 在 Engine 初始化时为每条 Law 编译并缓存；同一 evaluation view 的 `MatchContext` 通过 runtime provider 获取 lazy/shared `WorldIndex`。`WorldIndex` 包含 entity/relation component 倒排表，以及 relation type/source/target 全组合索引。Relation 优先绑定时会把 source/target 反向约束到 entity binding。

v2.4.1 在 `MatchPlan` 增加 runtime-only `ExactConstraint`：它只从顶层 `all` 的独立 `eq` condition 中提取，不改变 Law JSON 或最终 condition evaluation。Entity/Relation 的 `$binding.id == literal/$event.*` 直接使用 snapshot 的 id map，不建立 `WorldIndex`；relation 的 source/target/type equality 则下推到既有 relation index query。多个相同字段约束在 runtime resolve 后冲突会直接返回空候选。`MatchStats` 记录 `exact_constraint_lookups`、`exact_constraint_prunes` 与 `constraint_pushdowns`。

顶层 `all` 中 event-only 条件会在索引构建前判断；binding 依赖已满足的独立 clause 会立即 early prune。复杂 `any`、`not` 和嵌套逻辑仍等待完整 binding 后求值。执行顺序是优化细节，不属于世界语义。匹配结果总按 canonical binding-name/id key 排序，因此 query-plan 变化不能改变 proposal、trace 或 derived-event ID。Cartesian reference matcher 保留为 correctness oracle，并由固定 seed 的 500-case differential suite 与 Engine trace-equivalence 覆盖。

`MatchStats` 可记录 index lookups、candidate rows、partial bindings、condition evaluations、early evaluations/prunes、complete bindings 与返回 matches。运行 `PYTHONPATH=src python3 benchmarks/matcher_bench.py` 可查看 EDGE、CHAIN、STAR、SELECTIVE_COMPONENT、SELECTIVE_CONDITION 与 IRRELEVANT_EVENT 的结构性指标。

DSL 引用只能以 `$event`（event law）或已声明的 `$binding` 为根。`set`/`delta` target 必须是 `$binding.component.field...`；tag effect target 必须是 `$binding` 本身。派生 event 的最终 ID 由 Engine 生成，law 不得提供它。

## DSL Grammar 与 Resolution

缺省或空 `when` 会 canonicalize 为 `{"all": []}`，表示恒真。Condition AST 仅允许 `all`、`any`、`not`、`has_tag`、`has_component`、`ref` 加且仅加一个比较器（`eq`/`neq`/`gt`/`gte`/`lt`/`lte`），以及兼容 shorthand `{"event.type":{"eq":"impact"}}`。未知 operator、错误 operand shape 或多个比较器在加载期失败。

Value expression 仅支持 literal、`$reference`、`add`、`sub`、`mul`、`div`、`min`、`max`、`clamp` 和递归 object/list literal。`add`/`mul`/`min`/`max` 至少一个参数，`sub`/`div` 恰好两个，`clamp` 恰好三个。若 object 顶层不含保留 expression operator，它是普通 object literal。

不存在的运行时引用路径会抛 `DSLResolutionError`，其中包含完整 reference 与缺失 segment；不会再将不存在与有效 `None` 混同。

## Event Contract 与 Serialization

`load_event()` 验证 `id`、`type`、有限 `time`、`source`/`target`、object `payload` 和 provenance 结构；省略 provenance 的外部事件会获得 `{kind: external, parent_event: null}`。Law 的 `emit_event.event` 仅可含 `type`、`time`、`source`、`target`、`payload`；Engine 生成 `id` 和 provenance。`schedule_event.event` additionally requires explicit `id` and `time` and forbids author provenance. Both paths perform full validation after dynamic Value DSL materialization.

`Engine` 默认验证直接传入的 Law、WorldState 与 root Event；`save_world()` 也拒绝持久化非法运行时世界。World serialization 按 entity/relation id 与 scheduled event `(time, id)` canonicalize。JSON Schema 是结构/文档契约，Python validator 是权威语义验证层。

## Authoring Conflict 与 Trace Provenance

不同 law 的运行时冲突按 Resolver matrix 处理。**同一个 law 的不同 binding 对同一地址提出不同 `set`，或同一 tag 同时 add/remove，是 authoring conflict，会抛 `ProposalConflictError`。** 引擎绝不以 proposal 顺序替作者决定物理规律。

每个初始 proposal 都携带真实 source proposal/law；合并 delta 后这些来源会完整传入 `StateDelta`、`EventResult.triggered_law_ids` 与 `ProposalTrace`。Proposal trace 还记录值、cause event、source IDs 和直接生成的 derived event ID。`NonConvergentWorldError.trace` 携带失败前的 partial causal trace。

## 已延后内容

`scheduled_events` 是可持久化、按 `(time, id)` canonical serialization 的未来 root-event 队列。Temporal handles 只命名离散 future roots，并不创建隐藏 process registry。本版本不实现 continuous/tick process system、Event Perception、Action/Authority、Spatial 或自动 handle ownership/foreign-key behavior。Observation projection 在 v2.8 冻结，但不会把瞬时 Event/CausalTrace 伪装成 actor percept。

Raw execution trace 是 backend-specific 的优化执行记录；同 backend、同输入下它完全确定。跨 closure backend 的 correctness 使用 `CausalTrace.semantic_projection()`：它保留真实 StateDelta、derived event、conflict 和 source law，排除 full scan 中冗余的 no-op reevaluation。

## Runtime Benchmark

运行 `PYTHONPATH=src python3 benchmarks/runtime_snapshot_bench.py` 会对 1k、5k、10k、50k entities 输出 `NOOP`、`ONE_TOUCH`、`TEN_TOUCH`、`NOOP_PROPOSAL` 与 `STATE_SETTLE` 的耗时和 COW instrumentation。安全 API 是 `engine.run_event(world, event)`；热循环使用 `runtime = engine.attach(world)` 后调用 `runtime.run_event(event)`，避免每个 event 重建 runtime validation boundary。
