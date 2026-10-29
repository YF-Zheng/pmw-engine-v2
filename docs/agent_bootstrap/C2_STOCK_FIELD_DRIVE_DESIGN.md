# C2 Bounded Stock-To-Field Drive Design

Architecture pending implementation/independent acceptance. Full P1 is open.
Implements only finite Stock-fed positive Field source, not arbitrary sinks,
open-system creation, Stock transfer, Alpha UI or a complete Drive language.
Chosen because sustained environmental investment is missing from the Skill
bridge and directly serves the existing playtest's delayed-world-change needs.

## Catalog And Authority

Use NEW drives.py with immutable trusted DriveProfile/DriveController data,
not candidate-authored Laws or executable code. A profile has a stable ID,
preallocated Drive entity, acting owner, local Area/Field definition, finite
input Stock reference and unit, trusted positive Field-units-per-Stock conversion
coefficient, maximum positive rate and bounded duration. Source is explicitly
that finite Stock; candidate JSON cannot invent a source or coefficient.
Field domain and Stock unit/domain must match their trusted definitions.
Current Field definitions lack a universal unit catalog; report this existing
catalog gap honestly rather than claiming a full dimensional type system.

Effect kind drive_source: drive_profile_id, drive_rate and duration; required,
current_area, active on_use only, no attribute/sensing/evadability bypass.
All numeric values finite/non-bool/positive; duration positive integer within
trusted max. Material authorization is explicit; base cost five points plus
existing bounded duration cost. One control operation per Action across
Process start/modify and Drive; preserve old two-start rejection messages.
Resolve exactly one matching trusted profile for actor/Area and verify complete
Stock/Drive locality. Refuse active profile, empty input or full target Field.
Finite per-controller profile/active limits must be explicit and tested.

## One Clock And Atomic Conversion

Reuse WORLD_TICK_EVENT and existing Engine causal event publication. An active
profile emits a typed drive step child event after root dynamics/clock/closure;
the child reads the now-evolved Field. No extra clock, Python per-tick mutator
or test-only authoritative simulator. Freeze this extension to Tick ordering
explicitly and verify source effect, ecology closure and expiry boundaries.

Per child event compute once conceptually:

field_delta = min(active_rate, available_stock * trusted_coefficient,
                  trusted_field_max - current_field_value)
stock_delta = -field_delta / trusted_coefficient

Publish Field and Stock changes atomically through one trusted Law. No fuel
consumption without actual accepted Field change; no negative Stock/overflow.
Positive-source profiles sharing a Field execute by stable sorted profile ID,
not container order. Distinct profiles may not share an input Stock. C2 takes a
conservative static exclusion: no Drive input Stock may overlap ANY configured
Process input/output Stock. Reject at content compilation, even if inactive;
this is not a generic concurrent-writer solver or constant-work proof.

Track last_step so one world tick converts at most once. Scheduler expiry at
T runs before WORLD_TICK T, as before; activation at0 duration4 converts at
ticks1,2,3 only. Each profile owns its handle/lifecycle; one expiry cannot clear
another Drive. Inactive after expiry may be activated again normally with
finite Stock still charged; stale expiry identity must not terminate a new cast.

## Formal Bridge And Rebuild

Read-only prepare_start validates and prepares trusted before/after payload.
Action compiler emits the native typed activation event; existing staged Action
and timed submission own full cascade/tick failure rollback. Confirm exact
profile activation Law, active component/rate/expiry and actual schedule, not
just mana charge or suffix match. Native helper may exist only for supporting
trusted setup/tests; formal player/NPC evidence needs parsed Skill -> normal
equipment -> shared Action -> real paid ticks.

ActionRegistry carries trusted drive_controller alongside process_controller.
Preserve it in make_content, compile_content, registry rebuild/configuration and
checkpoint restore. Static Drive Laws enter existing static Law hash comparison.
Actor-safe projection excludes Drive Actions/controller/private Stock until a
separate authorized forecast gate; basic wait still works. Public semantics may
expose trusted profile source influence, never private state.

## Write Ownership And Gates

After C1 is accepted, one DeepSeek implementer owns new drives.py plus effects,
actions, action_compiler, skills, content_compiler, registry, build_analysis,
simulation and new test_sandbox_drive_source.py only. No old test or Engine,
clock/runtime/Observation/Alpha edits. If another file is necessary ask Main
before expanding scope. Independent QA owns a separate new review test/report.
Main owns design/source review, status/plan/spec/audit/accounting, full frozen
regression and local checkpoints. No source edits during frozen regression.

Acceptance: quantitative normal player/NPC paid ticks, none/linear recovery
versus impulse/attractor, finite source scaling and capacity clamp, multi-source
owned expiry and stable order, scope/owner/unit/profile/mixed-control/budget
denials, actual child-cascade and late-tick rollback, registry/checkpoint replay,
changed static profile rejection, private projection and old suites unchanged.
Do not promote this bounded positive-source implementation to full P1.
