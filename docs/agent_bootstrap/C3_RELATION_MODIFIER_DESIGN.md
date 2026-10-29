# C3 Bounded Existing-Link Modifier Design

Architecture only, queued after C2 acceptance. Do not implement before the
current Drive scope is frozen/tested/checkpointed. Full P1 remains open.

## Target And Honest Limit

Expose typed temporary enable/disable of an EXISTING trusted local Relation,
with actual downstream World Laws reading its effective state. This directly
addresses the missing formal Relation Operator without rewriting Core or
inventing path/victory flags. C3 does not create/delete/retarget graph edges or
claim a generic topology solver, full Relation language or Alpha UI integration.
Existing topology is retained; source/target IDs/types must still be validated.

The native Core Relation has its own components and typed source/target; this
must be a REAL Relation in WorldState.relations, not a proxy Entity or an
invented completion flag. The trusted helper returns a detached Relation.
Existing locality/adjacency selectors read topology, not this new effective
component. C3 therefore targets an opt-in World link rule (e.g. supply
availability) that explicitly reads effective_enabled; it does not claim that
all existing travel/linked_object semantics become disabled. No selector/Core
rewrite or task-control authority expansion is in this increment.

Use a new relations.py controller with immutable RelationProfile data and
preallocated owned Relation component. Profile fields: id, relation_id,
relation_type, source_entity_id, target_entity_id, owner, area_id,
source_components, target_components, max_duration_ticks. Existing Entity
component markers provide trusted endpoint type requirements; no candidate
authors endpoints, arbitrary component paths, task outcomes or Relation types.
RelationLimits(max_instances=16,max_active=8) are finite and validated.

Frozen shared exports: RELATION_COMPONENT, RELATION_MODIFY_EVENT,
RELATION_EXPIRE_EVENT, RelationLimits, RelationProfile, RelationController,
instantiate_relation(profile, *, base_enabled=True)->Relation. Profile fields
listed above use source_components/target_components as immutable tuples of
required component marker names. Controller constructor accepts profiles and
optional limits; pure prepare_modify(session, profile_id, *, owner, enabled,
duration_ticks) returns the activation payload. Initial component contains
profile_id/profile_hash/owner/base_enabled/effective_enabled, active=False,
enabled=None, started_at/expires_at/expiry_handle=None. Relation type and fixed
endpoints are checked against the profile, not changed by any candidate.

## Layered Boolean State

Dedicated pmw_gameplay_link component owns profile hash/owner, base_enabled,
effective_enabled and one temporary modifier slot with active/enabled/owner,
start/expiry/handle. A trusted helper creates the initial Relation in detached
world content, never in a candidate action. Profile relation ID/type/endpoints
and all markers must match at preflight. Two configured profiles may not write
the same Relation slot. One active modifier per slot; no silent overwrite.

Existing state-Law closure derives effective_enabled from active modifier when
present, otherwise CURRENT base_enabled. Expiry removes only its owned slot,
not a captured old base. Thus World base changes made during a modifier are
preserved on expiry; no restoring stale values over World state. This is a
bounded single-slot policy, not proof of arbitrary multi-source Relation layers.
Base and effective booleans are typed; input integer0/1 is not a candidate bool.

## Formal Action And Lifetime

Effect relation_modifier: relation_profile_id, relation_enabled (strict bool),
duration (positive integer within trusted max), required/current_area/active
on_use, no targeting/attribute bypass. Material permission is explicit Operator
and selector budget; trusted owner/profile defines which fixed link parameter
can be controlled. Action capability relation_types must include the profile's
actual type. No JSON endpoint/type/path injection or victory/death state write.
Base capability-budget cost five plus existing bounded duration cost.
At most one Process/Drive/Relation control per Action; retain old error guards.

Relation and both endpoints must exist, retain trusted type/component markers,
be local to the acting Area and match owner. Pure prepare_modify yields typed
event payload. Existing activation/expiry Laws and derived state closure own
all mutations; Action confirms exact profile Law, slot/effective state and
scheduled expiry. Existing staging/timed submission rolls back full cascade
and paid ticks. Profile controller is static configuration, not a World writer.

Expiry at T remains before World Tick T. Each cast owns distinct deterministic
handle identity; stale earlier expiry cannot remove a new modifier. Link state
continues until expiry if actor leaves, without granting cross-Area activation.
Existing World Rules can compute actual powered/availability Derived state
from link effective_enabled; generated Effect cannot write those Derived values.

## Integration And Acceptance

Preserve relation_controller through ActionRegistry/content compilation,
registry rebuild/checkpoint static-Law hash comparison. Actor-safe projection
excludes controller/Relation modifier actions/private link state until its own
authorized forecasting gate; basic wait remains functional. Public semantic
footprint may identify relation profile influence, not hidden endpoint values.

After C2: bounded DeepSeek ownership of new relations.py plus effects/actions/
action_compiler/skills/content_compiler/registry/build_analysis/simulation and
one new owner test. Independent QA owns a distinct new review test/report.
Main owns architecture/source review, governance, frozen full regression and
accounting/checkpoint. No old tests, Engine/runtime/clock/Observation/Alpha edits.

Gate: parsed normal player/NPC timed Skills actually alter link and downstream
World rule results; boolean/numeric/null/unknown/type/scope/owner/endpoint/profile/
active/budget denials; exact expiry and source isolation; base change during
temporary control preserved on expiry; stale expiry rejection; actual cascade
and late-tick rollback; static-profile/save-load replay; private projection.
Do not substitute admin fixture edits or fake world flags for formal positives.
Do not promote bounded existing-link control to full P1 or start game generation.
