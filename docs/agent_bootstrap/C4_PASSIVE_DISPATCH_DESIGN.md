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
