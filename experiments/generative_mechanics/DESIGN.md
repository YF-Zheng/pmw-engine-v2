# Generative Mechanics Lab: Experimental Design Freeze

## Research boundary

The lab tests whether a generated mechanism can perturb a fixed public substrate and acquire context-dependent consequences from generic world laws. PMW v2.8 is a frozen dependency. This directory owns experiment data, validation, compilation, execution, analysis, and no engine behavior.

The compiler is deliberately boring: untrusted generation never emits PMW, entity IDs, component paths, operations, scheduler IDs, damage, victory, collapse, transformation, or NPC outcomes. It emits `SkillSpec v0.1`; deterministic trusted code emits PMW.

## Frozen channels

Every zone exposes exactly eight normalized public channels:

1. `temperature`
2. `wetness`
3. `electric_field`
4. `fire_intensity`
5. `sound_level`
6. `ground_stability`
7. `water_level`
8. `visibility`

Skill deltas are bounded to `[-1, 1]`. Trigger thresholds are bounded to `[0, 1]`. The present PMW substrate does not clamp aggregate state; evaluator work must measure excursions rather than silently alter them.

## SkillSpec v0.1

The top-level object is strict and contains exactly:

```text
id, name, target_scope, effects, duration, periodic,
trigger_conditions, resource_cost, charges, slot_cost
```

`target_scope` is `zone`. An effect is exactly `{field, delta}` and its field must be one of the eight channels. A trigger condition is exactly `{field, op, value}` and may read only those channels. `duration` is finite in `[0, 300]`. `periodic` is null or `{interval, repeats}`, with a positive finite interval and `1..12` repeats. Costs are finite and non-negative; charges are `1..99`; slot cost is `1` or `2`.

IDs use local lowercase identifiers. Reserved `gm_`, `pmw_`, and `lab_` prefixes are rejected. Unknown fields, PMW operations, hidden reads, outcome declarations, non-finite values, unbounded schedules, negative costs, and arbitrary targets are rejected before compilation.

## Compiler contract

Compilation is a pure deterministic function and canonical JSON uses sorted keys with compact separators. Generated laws live under `gm.skill.<skill-id>.*`. Activation is always `lab.skill.activate`, sourced by the actor and targeted at a zone.

The compiler may bind only:

- a zone with `zone` and `fields` components;
- an actor with `resource.energy`;
- a skill instance with `skill.spec_id`, `skill.owner`, and `skill.charges`.

It may directly mutate only `zone.fields.<channel>`, `actor.resource.energy`, and `skill.skill.charges`. It cannot create/delete entities or relations, emit outcomes, or access environment-private components.

Three finite templates are supported:

- Immediate: apply channel deltas once during activation.
- Duration: apply once, schedule one caller-supplied `expiry_event_id`, then apply the exact inverse.
- Periodic: apply on activation and schedule a statically expanded finite set of caller-supplied `pulse_NN_event_id` impulse handles.

The trusted runner places `skill_id`, `skill_instance_id`, and every required unique handle ID in the activation payload. Laws match both IDs, so loading multiple compiled skills cannot cause cross-activation. Handle IDs are stable for a canonical activation ID but distinct across overlapping activations. Missing handles are rejected at the experiment boundary before PMW runs. The finite periodic expansion has no recursive scheduling. `duration > 0` and non-null `periodic` are mutually exclusive in v0.1; the validator rejects the ambiguous combination.

Every emitted law is passed through `pmw.parse_law`. Checked-in compiled output is not authoritative; SkillSpec is the source and compilation is repeatable.

## World-law contract

Generic laws live under `gm.world.*` and cannot mention skill IDs or activation events. Non-idempotent processes are event laws driven by explicit `lab.step`; state laws are reserved for idempotent closure. This prevents accidental endless fixed-point accumulation.

The four environments share actor, zone, and skill-instance shapes. They differ only in initial public fields and environment material/process state. Thus a skill specifies the same perturbation everywhere, while discharge, steam, visibility, fuel, stability, alert, and charged-ore consequences belong to the world.

## Phase 2 scenario contract

The benchmark has six `calibration` and six disjoint `held_out` executable scenarios. Each split covers short combat, long combat, resource-limited, multi-target, environmental hazard, and aftermath. A scenario strictly declares its environment, 10-item backpack, 6-item default active build, cast/step/advance program, three ordered horizons, and a normalized five-dimensional weight vector. Every rollout loads a clean world and creates a new PMW Runtime; runtime state is never shared across evaluations.

## PowerProfile

For scenario scalar scores `s_1..s_n`:

```text
Typical Power = arithmetic mean(s)
P90 Power     = sorted(s)[ceil(0.9*n)-1]       # nearest rank
Ceiling Power = max(s)
```

The five capability dimensions are `Combat`, `Survival`, `Control`, `Utility`, and `ExplorationWorldImpact`. Let `d(x)` be the build-minus-empty medium-horizon delta, with fields/processes averaged across targets and discrete outcomes summed across targets:

```text
Combat = 20*d(discharges) + 12*d(charged_ore) + 5*max(0,d(fire_intensity))
Survival = 10*d(ground_stability) + 6*d(visibility)
           - 4*max(0,d(fire_intensity)) - 3*max(0,d(water_level))
Control = 4*sum(abs(d(x)))
          for x in wetness,electric_field,sound_level,visibility,ground_stability
Utility = 3*sum(abs(d(x))) for x in temperature,water_level,visibility
          + 2*abs(d(alert))
ExplorationWorldImpact = 5*number_of_differing_zone_leaves
Scenario score = dot(capability vector, scenario weight vector)
```

`Interaction Surface` is the mean count of additional distinct `gm.world.*` laws. `Persistent World Impact` is the mean count of differing zone leaves at the medium horizon. Calibration and held-out profiles are requested explicitly and never pooled. Multi-target scenarios set `target_count > 1`; the runner clones independent zones, casts against each canonical target, advances all zones, and aggregates them only at scoring time.

Every serialized PowerProfile contains the eight formal metrics: Typical Power, P90 Power, Ceiling Power, Personalized Build Delta, Synergy Amplification, Interaction Surface, Exploit Risk, and Persistent World Impact, plus the capability vector. For active build `B`, `SynergyAmplification = V(B) - sum(V({s})) + (|B|-1)*V(empty)` on the same split and scenarios. `ExploitRisk` is the maximum static severity over the combined compiled laws in `B`. `PersonalizedBuildDelta` is undefined outside a candidate-before/after context and is serialized as `null`, never a fabricated zero. `evaluate_candidate` fills it with exhaustive `best(pool + candidate) - best(pool)`.

## Build search

A backpack contains at most 10 unique SkillSpecs. Exhaustive search emits each unique sorted subset exactly once, including the empty build, subject to active count `<= 6` and summed `slot_cost <= 6`. Equal scores use lexicographic skill-ID tie-breaking. Pairwise synergy is `V(a,b)-V(a)-V(b)+V(empty)`. Personalized delta is `best(pool + candidate)-best(pool)`.

## Emergent Reach

Attribution is a paired counterfactual: run the same clean scenario and canonical program with the candidate present, then with only that candidate removed. Direct laws are candidate `gm.skill.<id>.*` activations. Downstream laws are positive multiset differences in `gm.world.*` execution. Downstream addresses are independently extracted from committed trace deltas whose `law_ids` contain `gm.world.*`, then differenced as Counters. Affected subsystems come only from those additional addresses; persistent consequences count only additional downstream addresses whose paired final values still differ. Direct skill field writes are therefore excluded. Conservative causal depth is 0 for no direct effect, 1 for direct-only, and 2 when an attributable generic world law also executes.

## Exploit v0

The static detector reports causal SCC, no-cost positive feedback, resource self-generation, scheduler queue explosion, and unbounded state growth at `LOW/MEDIUM/HIGH/CRITICAL`. It is deliberately conservative and is not a proof of safety.

## Generation protocol and controls

`gm-generation-v0.1` is a strict JSONL envelope containing a sample ID, baseline, target band, source kind, canonical prompt hash, provider/model identity, seed, raw response ID, mechanic, and optional declared power. The prompt hash must match the frozen request. Invalid lines are isolated and never enter compilation.

The experiment has two intentionally separate controls:

- `world_substrate` emits SkillSpec v0.1 and can mutate only the eight public channels.
- `direct_effect` emits restricted DirectEffectSpec v0.1 (`damage/heal/buff/debuff`). Trusted code writes only an experimental `direct_outcome` component. Generic world laws never read it, so a direct control cannot accidentally become a substrate mechanism.

Both paths use PMW execution, identical scenarios, resource/charge accounting, and the same evaluation table. Direct effects contribute only to their matching capability proxy and must have zero downstream world-law reach.

The checked-in fixture protocol creates 240 balanced samples: 40 per `(baseline, Low/Mid/High)` cell. It includes immediate, finite-duration, and finite-periodic mechanics. These samples have `source_kind=deterministic_fixture`; they validate infrastructure and are never model findings.

## Batch and targeted revision

Batch execution is fault-isolated and resumable under a versioned config hash. Rates use staged denominators:

```text
schema validity    = schema-valid / all input lines
compile rate       = compiled / schema-valid
execution validity = executed / compiled
```

Mechanic diversity hashes structure after removing `id` and `name`. The four evaluator columns are declared LLM self-rating (unavailable when absent), static heuristic, standard PMW simulation, and PMW simulation plus exhaustive contextual search. The experiment proxy is reported on a frozen scale of 8 so requested bands `[20,30]`, `[40,50]`, and `[60,70]` are readable in the same table; this scale is not learned from held-out results.

Guided revision gets one attempt. It changes bounded mechanic parameters, validates and recompiles the revised spec, and reruns the same held-out scenarios. It never edits an evaluator score.

## Cross-environment and aftermath analysis

Each unchanged mechanic is paired against an empty run in Mine, Wetland, Industrial Yard, and Fragile Bridge. Reports contain additional `gm.world.*` signatures, an environment-difference rate, and state-difference trajectories at `combat_end`, `short`, and `medium`. Direct controls must keep identical direct outcomes across environments and zero additional world laws. Duration fixtures explicitly cover recovery by the medium horizon.

Kill criteria cover substrate collapse into self-contained effects, downstream scarcity, environment sameness, validity bottlenecks, and contextual evaluator advantage. The last item requires independent ground truth. Without it the status is `UNAVAILABLE`, and no correlation, error, or advantage is fabricated.

Figures 1-5 are rendered from result tables as PDF, SVG, and 300 dpi PNG. Figure 4 displays an unavailable panel when ground truth is absent. Deterministic fixture figures are labeled pipeline artifacts, not paper conclusions.

## Deferred external work

Online provider calls, collection of 200-500 actual model responses, independent ground-truth annotation, statistical hypothesis tests, and paper claims remain external experiment runs. The repository supplies provider-neutral JSONL import so those runs use the same frozen pipeline.
