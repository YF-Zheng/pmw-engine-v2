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

### Shared Interface For Disjoint Workers

drives.py exports DRIVE_COMPONENT, DRIVE_START_EVENT, DRIVE_STEP_EVENT,
DRIVE_EXPIRE_EVENT, DriveLimits(max_instances=16,max_active=8), DriveProfile,
DriveController and instantiate_drive(profile)->Entity. Frozen profile field
names: id, drive_entity_id, owner, area_id, field (existing FieldDefinition),
stock (existing StockRef), stock_unit, field_per_stock, max_rate,
max_duration_ticks. Controller constructor accepts profiles and optional limits;
prepare_start(session,profile_id,owner=...,rate=...,duration_ticks=...) is pure.
An optional native start with the same parameters stages through existing Laws.

Initial Drive component is inactive, with profile_id/profile_hash/owner, rate0,
started_at/expires_at/expiry_handle None, last_step=-1 and last_delta=0. Active
rate is positive; each accepted cast owns a distinct expiry identity derived
from trusted action/time identity, not a candidate field. Expired profile is
inactive and reusable without stale-expiry interference. Raw Effect fields:
id,kind=drive_source,target=current_area,commitment=required,drive_profile_id,
drive_rate,duration (plus existing optional condition/targeting/attribute keys,
with targeting/attribute bypass rejected). Unit/coefficient is profile-only.

Use Field domains from the trusted FieldDefinition; source target is an Area
Field only, not Actor Mana mirrors. Profile source/Drive entity must be local
at activation. Active source continues in its own Area if the actor leaves.
No negative/sink/open-source branch in C2. Supporting World fixture mutations
must not be mistaken for normal equipment, registration or gameplay action.

### Main Review Clarifications

Root Tick matching uses the BEFORE-dynamics state. Emit the bounded child for
an active valid profile even when that pre-state Field is full; the root's
natural recovery may create headroom before the child executes. Stock/headroom
and accepted paired conversion checks belong to the child. A full previous
Field with recovery toward a lower target must still receive its same-Tick
source contribution after recovery, with actual fuel debit.

Float conversion must change both represented Field and Stock, or neither.
Huge Stock/tiny rate and high Field/tiny rate may be unrepresentable; these
cases are a conservative no-op, not free production or wasted fuel. Preserve
ordinary proportional conversion and last-step duplicate prevention. This is
a bounded numeric guarantee, not a universal dimensional arithmetic catalog.

Do not extend make_content with unrelated materials or impose equality of all
skill material sets merely to accommodate a new review fixture. Use existing
parse/link/material authorization and the necessary controller integration.

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
