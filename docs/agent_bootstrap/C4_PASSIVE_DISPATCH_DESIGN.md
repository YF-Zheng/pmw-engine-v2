# C4 Follow-Up: Bounded Automatic Damage Passive Dispatch

Architecture only, queued after C3 and condition limits. Full P1/P2 remain
open. Do not edit current workers' production scope to implement this yet.

## Actual Baseline

evidence/c4_passive_dispatch_before.json records a real offline Gameplay path
at9f75122: parse_material/material_authority -> runtime.install passive Skill ->
normal equip_passive -> NPC submit_timed_primary_action basic_attack on owner.
Registered hook exists and passive is equipped, but owner HP40->30, shield0->0;
one Tick is paid and the Action trace contains only pmw.v04.action.resolve.
The damage_resolved shield passive never automatically responds. Source hashes
before/after match. This is not an API-generation call or browser playtest.

Current hooks.py supports manual execute_hook and a HookLineage helper; the
action compiler installs hook cooldown Laws but does not emit/dispatch damage
notifications. Helper tests do not prove contract scenario6. Alpha advertises
automatic passive response while its general Skill pipeline shares this gap.

## Bounded Target

Automatically dispatch ONLY damage_resolved for formally equipped passive
Skills, using existing effect/Action Laws and one staged primary transaction.
Do not pretend this covers all six legacy trigger names, on_tick/on_expire,
arbitrary World events, full multi-trigger IR, or global CPU/query budgets.
Do not replace an effect with a special shield/recipe-name branch.

### Cause And Ordering

The actual compiled damage Effect Law emits a typed semantic child notification
when its prepared applied damage commits. Use real Engine child provenance
with parent Action event, effect ID, attacker and affected Actor IDs; no
synthetic victory/world flags or candidate-authored code. Define whether zero
accepted damage notifies (preferred: positive resolved damage only, including
shield absorption), and freeze this in tests before implementation.

After the root Action's synchronous Engine cascade/closure has succeeded, the
managed Action adapter consumes actual notifications in deterministic FIFO
order, resolves affected-owner equipment and executes the registered Hook's
exact effect bundle through existing _resolve_action(execution_kind=hook).
Hook Actions may emit their own real damage notifications; append them to the
same bounded queue rather than recursively calling a new primary transaction.
Run dispatch before the primary's paid ticks, inside its existing staged copy.
No extra Mana/time charge for passive response and no second clock.

Each auto Hook Action has deterministic unique request identity including the
primary root, notification, hook and owner, with trusted causal provenance
linking it to the actual notification. Do not reuse hook_<depth>_<id> across
owners/roots. Preserve manual execute_hook compatibility as a privileged
helper; it must not become the claimed automatic-transaction proof.

### Authority And Limits

Resolve only current owner's exact equipped passive ref (ID/version/hash/kind)
against the installed registered blueprint/action/hook; disabled, unloaded,
stowed, forged, different-owner, dead-owner or unknown refs do not fire.
Check owner locality against attacker/affected Actor and define self/target
context so a victim's target_actor means the real attacker, never an arbitrary
remote ID. Conditions and cooldowns are evaluated on current staged state.
False condition/cooldown/dedup are explainable skips, not half-committed errors.

One shared root budget applies across siblings and descendants, not reset per
hook. Proposed conservative limits: depth16 and total32 successful firings.
Deduplicate the same owner+hook source within one primary root, so counter
passives cannot ping-pong forever; a new legitimate root resets that budget.
Preserve existing max_firings_per_root as an upper bound, not permission to
exceed dedup/global ceilings. Exceeding a hard queue/depth budget rejects the
whole managed primary/timed transaction with GameplayContractError. No silent
loss of costs, schedule, source contributions or pending queue on failure.

## Required Review Before Code

Main must finalize exact notification schema, result/trace exposure and
checkpoint-static-law impact after C3 and conditions are accepted. Prefer
preserving existing ActionOutcome fields and exposing an additional bounded
dispatch record rather than misleadingly rewriting the root causal trace.
Every World mutation remains a PMW Action/Effect/Law event; no direct Python
Actor HP/shield assignment in the dispatcher. Static notification Laws and
controller/configuration must survive registry rebuild/checkpoint comparison.
Projection must not copy private equipped passive/controller authority.

Worker ownership will be bounded to hooks/actions/action_compiler and necessary
registry/content/checkpoint integration plus one NEW owner test, not Engine,
clock, Observation, Alpha, old tests or unrelated configuration. Independent
QA owns a disjoint new test/report. Source scope and shared interface will be
frozen before dispatching those workers; this document is not authorization
for current C3 workers to expand scope.

## Gate

Same parsed shield/counter mechanics normally equipped by player/NPC respond
to actual paid attacks and child notifications; exact Mana/time payment,
effect result and source/parent IDs are verified. Unequipped/disabled/forged/
different-owner/remote/dead/cooldown/false-condition cases do not fire. Two
counter passives terminate deterministically under shared root dedup/budgets.
Actual Hook child exception and late paid-Tick failure roll back entire primary,
hook effects, schedules, revisions/stats and time budget. Replay/save-load and
registry rebuild continue identically; old tests/Alpha baseline remain intact.
Independent review and complete frozen regression precede local acceptance.
No game-generation call until all P1 and P2 gates pass.

## Frozen Implementation Interface (Main 16:18, queued after C4.1)

Write scope: hooks.py, actions.py, action_compiler.py and one NEW owner test.
No registry/content/checkpoint/simulation changes are needed unless Main first
accepts a concrete propagation gap. Independent QA owns a distinct new test,
report and c4_passive_review* evidence only. All existing tests are protected.
This architecture preparation is not concurrent production implementation.

- Notification type: pmw.v04.hook.damage_resolved, emitted by the SAME compiled
  applied damage Effect Law after its hp/shield writes. Source attacker, target
  victim, time Action time. Payload: protocol pmw-gameplay-v0.4, action_id,
  action_hash, effect_id, actor_id, target_actor_id, resolved_damage, hp_loss,
  shield_absorbed. hp_loss is clamped actual positive HP decrease and absorption
  is accepted shield consumption, not nominal damage overkill. Sum must be
  finite and positive; zero accepted damage does not notify. Supporting
  per-effect prepared values must not alter canonical Skill document hashes.
- Engine creates notification ID/provenance itself. Dispatcher accepts ONLY an
  actual notification in the current ActionOutcome trace whose exact payload,
  source/target/time, derived parent ACTION_EVENT ID and accepted emit proposal
  belong to the expected compiled damage Effect Law. Verify the associated
  hp/shield commit delta attribution and actual resolved amount; do not fire
  from a merely typed or nominal/spoofed World notification or a rejected
  damage write. Do not compare only final state after legitimate state Laws.
- Keep _resolve_action as low-level single resolution, manual execute_hook
  compatible and nonautomatic. Managed resolve_action/submit_timed_primary_action
  call one helper that resolves primary, consumes FIFO notifications and calls
  _resolve_action(execution_kind=hook) on SAME staged session. Paid ticks happen
  AFTER hook queue drains. No hook extra Mana/time, nested staging, direct
  World writes, helper-recursive primary call or second clock.
- Add ActionOutcome auto_hooks default empty tuple (all old positional fields
  preserved). Separate immutable HookDispatchRecord holds root event ID, actual
  notification/parent ID, hook ID, owner, depth, status, reason and optional
  hook ActionOutcome. Do not merge/relabel root Engine trace as hook trace.
  Hook Action Event uses trusted derived provenance parent notification ID;
  payload hook context includes root ID, notification ID, depth, hook ID and
  cooldown_until. Deterministic request ID uses bounded SHA256 of root,
  notification, exact hook and owner, not hook_<depth>_<id> shared IDs.
- Formal registry entries and passive_equipped references bind exact blueprint
  id/version/kind/canonical hash/enabled entry to installed hook/action bundle.
  Skill hash and Action hash are DIFFERENT: require exact manifest reference
  plus expected registered action hash, not equality between those hashes.
  Require current live victim/owner and unique same-Area placement with actual
  attacker; self/target context is victim/attacker. Stowed/unloaded/forged/
  disabled/wrong-kind/nonmatching refs, remote/dead owners do not fire. Bare
  hand-installed hooks without formal enabled equipment are manual-only.
- HookDispatchLimits trusted keyword-only argument on managed public functions
  (not ActionRequest/Skill JSON), default max_depth16/max_firings32/
  max_notifications64. Positive non-bool integers bounded by those defaults;
  callers may tighten but not increase. No config/global World mutation.
  Replay caller retains same selected policy; checkpoint World/schema unchanged.
  New damage emission Laws regenerate through existing registry rebuild and
  trusted static configuration checks; verify normal save/load continuation.
- One shared FIFO root counter for notifications (including ignored/skip), one
  successful firing count, per-notification depth and owner+hook source dedup.
  All siblings/descendants share it. Positive eligible next hook beyond depth/
  firing or notification ceiling causes GameplayContractError/whole action
  rollback. Condition/cooldown/dedup skips are records, no partial costs. A new
  legitimate managed root resets budgets. Existing max_firings_per_root remains
  an upper bound, while this bounded slice permits one source firing per root.
- Normal same-catalog Skill can equip player and NPC; quantitative shield and
  two-counter tests must execute actual paid primary attacks and inspect child
  notification + hook traces. Lower trusted limits allow real depth/firing/
  shared-sibling ceiling rollback tests without huge workloads. Actual child
  exception and paid-tick failure preserve World/revisions/stats/schedule/time.

Non-claims: only Action-produced damage notifications are serviced before paid
Ticks; arbitrary World/Tick notifications, other legacy trigger labels,
multi-trigger IR, forecasting/private projection, all global query/CPU budgets
and full P1/P2 are not established by this repair. No Alpha UI or provider call.
