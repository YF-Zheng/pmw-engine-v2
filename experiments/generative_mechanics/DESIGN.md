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

Skill deltas are bounded to `[-1, 1]` and trigger thresholds to `[0, 1]`.
Aggregate state is truly normalized: traced PMW closure laws saturate all eight
channels to `[0, 1]`, and explicit `lab.dissipate` roots relax them toward
frozen neutral values. The runner never performs an untraced Python clamp.

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

## Scenario and Oracle contract

The public benchmark has six `calibration` and six disjoint `evaluation`
scenarios. A deterministic hidden `oracle` distribution reconstructs 144 more
micro-scenarios from a frozen manifest. Each distribution covers short combat,
long combat, resource-limited, multi-target, environmental hazard, and
aftermath. A scenario strictly declares its environment and variant, public
initial-field overrides, 10-item backpack, 6-item active build,
cast/step/advance program, three ordered horizons, a horizon-weight vector, and
a five-dimensional capability-weight vector. Every rollout loads a clean world
and creates a new PMW Runtime.

All 144 Oracle cases define the intrinsic target. Because exact 10-to-11 build
search is substantially more expensive, the contextual target defaults to a
preregistered 24-case subset with one case per category/environment stratum.
The deterministic 12- and 18-case profiles are strictly nested within it and
exist for sensitivity analysis, not as alternative post-hoc samples.

## PowerProfile

For scenario scalar scores `s_1..s_n`:

```text
Typical Power = arithmetic mean(s)
P90 Power     = sorted(s)[ceil(0.9*n)-1]       # nearest rank
Ceiling Power = max(s)
```

The five capability dimensions are `Combat`, `Survival`, `Control`, `Utility`,
and `ExplorationWorldImpact`. Let `d_h(x)` be the build-minus-empty delta at
horizon `h`, with fields/processes averaged across targets and discrete outcomes
summed across targets. Each horizon gets a capability vector and the scenario
score is the declared weighted sum of combat-end, short, and medium vectors.

```text
Combat = 20*d(discharges) + 12*d(charged_ore) + 5*max(0,d(fire_intensity))
Survival = 10*d(ground_stability) + 6*d(visibility)
           - 4*max(0,d(fire_intensity)) - 3*max(0,d(water_level))
Control = 4*sum(abs(d(x)))
          for x in wetness,electric_field,sound_level,visibility,ground_stability
Utility = 3*sum(abs(d(x))) for x in temperature,water_level,visibility
          + 2*abs(d(alert))
ExplorationWorldImpact = 5*number_of_differing_zone_leaves
Scenario score = sum_h horizon_weight[h] * dot(capability[h], scenario weights)
```

`Interaction Surface` is the mean count of additional distinct `gm.world.*`
laws. `Persistent World Impact` alone is measured at the medium horizon.
Calibration, evaluation, and Oracle profiles are requested explicitly and never
pooled. All execution-based routes share `PowerScaleContract v0.2`; there is no
batch-only scale.

Every serialized PowerProfile contains the eight formal metrics: Typical Power, P90 Power, Ceiling Power, Personalized Build Delta, Synergy Amplification, Interaction Surface, Exploit Risk, and Persistent World Impact, plus the capability vector. For active build `B`, `SynergyAmplification = V(B) - sum(V({s})) + (|B|-1)*V(empty)` on the same split and scenarios. `ExploitRisk` is the maximum static severity over the combined compiled laws in `B`. `PersonalizedBuildDelta` is undefined outside a candidate-before/after context and is serialized as `null`, never a fabricated zero. `evaluate_candidate` fills it with exhaustive `best(pool + candidate) - best(pool)`.

## Build search

A player backpack contains 10 unique specs. Candidate evaluation compares the
exact legal optimum before with the exact optimum after adding the eleventh
candidate, subject to active count `<= 6` and summed `slot_cost <= 6`. Equal
scores use lexicographic skill-ID tie-breaking. The resulting
`ContextualMarginalPower` is separate from intrinsic absolute power.

## Emergent Reach

Attribution is a paired counterfactual: run the same clean scenario and canonical program with the candidate present, then with only that candidate removed. Direct laws are candidate `gm.skill.<id>.*` activations. Downstream laws are positive multiset differences in `gm.world.*` execution. Downstream addresses are independently extracted from committed trace deltas whose `law_ids` contain `gm.world.*`, then differenced as Counters. Affected subsystems come only from those additional addresses; persistent consequences count only additional downstream addresses whose paired final values still differ. Direct skill field writes are therefore excluded. Conservative causal depth is 0 for no direct effect, 1 for direct-only, and 2 when an attributable generic world law also executes.

## Exploit v0

The static detector reports causal SCC, no-cost positive feedback, resource self-generation, scheduler queue explosion, and unbounded state growth at `LOW/MEDIUM/HIGH/CRITICAL`. It is deliberately conservative and is not a proof of safety.

## Generation protocol and controls

`gm-generation-v0.2-controlled` is the Controlled Invention collection
protocol. Its strict JSONL envelope contains master-seed/sample-index request
coordinates, a re-derived unique sample ID, nonce and seed, baseline, target
band, source kind, canonical prompt hash, provider/model identity, raw response
ID, mechanic, and optional declared power. The prompt discloses public channel
semantics, a compact public projection of generic laws, and exactly six
calibration-only examples matching the current baseline schema: two per power
band. The frozen calibration artifact contains 18 examples total, and every
score is rebuilt with that baseline's compiler and world setup. It discloses
neither evaluation environment state nor Oracle cases.

Archived `gm-generation-v0.2` envelopes retain a separate compatibility path
that reconstructs the original shared-six-example prompt. Legacy and Controlled
prompt hashes cannot be interchanged. `v0.1` is frozen only for historical
fixture replay.

The experiment has three intentionally separate conditions:

- `world_substrate` emits SkillSpec v0.1 and can mutate only the eight public channels.
- `isolated_direct_effect` is the narrow manipulation control formerly named
  `direct_effect`.
- `matched_direct_outcome` matches effect count, public conditions, temporal
  mode, cost, charges and slots, but writes only `direct_outcome.*`.

Both paths use PMW execution, identical scenarios, resource/charge accounting, and the same evaluation table. Direct effects contribute only to their matching capability proxy and must have zero downstream world-law reach.

The checked-in 240-sample v0.1 fixture remains a replay artifact. A v0.2 pilot
with 15 samples in each of nine cells contains 135 genuine provider requests.
Fixture rows have `source_kind=deterministic_fixture`; they are never model
findings.

## Free Invention scaffold

`gm-free-invention-v0.3` removes power bands, scored examples, declared power,
and revision policy. The implemented scaffold freezes coordinate-bound request
identity, a public-only prompt, strict response ingestion, trusted compilation,
and static contract evidence. It declares the intended invention dimensions,
but dynamic interaction surface, causal depth, cross-environment
differentiation, downstream consequences, combinatorial potential, and
self-containment remain unavailable until paired execution evaluators and their
reporting protocol are frozen. No dynamic Free benchmark result is claimed.

## Batch and targeted revision

Batch execution is fault-isolated and resumable under a versioned config hash. Rates use staged denominators:

```text
schema validity    = schema-valid / all input lines
compile rate       = compiled / schema-valid
execution validity = executed / compiled
```

Structural diversity removes IDs/names and bins numeric parameters; parametric
diversity retains exact values. Evaluator analysis has two tasks. Intrinsic
estimators predict `OracleIntrinsicPower`; contextual estimators predict
`OraclePersonalizedDelta`. Error is never computed across the two estimands.
Both are formal realized-utility targets under the declared scoring function
and preregistered world-state distribution. They are not human annotations or
claims of objective game balance.

The deterministic controller gets one revision attempt. It rescales bounded
mechanic parameters, validates and recompiles the revised spec, and reruns the
same evaluation scenarios. It never edits a score and is not LLM self-revision.

## Cross-environment and aftermath analysis

Each unchanged mechanic is paired against an empty run in Mine, Wetland,
Industrial Yard, and Fragile Bridge. Primary aggregate tables are stratified by
baseline; an overall value may appear only as a secondary diagnostic.

Kill criteria cover substrate collapse into self-contained effects, downstream scarcity, environment sameness, validity bottlenecks, and contextual evaluator advantage. The last item requires independent ground truth. Without it the status is `UNAVAILABLE`, and no correlation, error, or advantage is fabricated.

Figures 1-5 are rendered from result tables as PDF, SVG, and 300 dpi PNG. Figure 4 displays an unavailable panel when ground truth is absent. Deterministic fixture figures are labeled pipeline artifacts, not paper conclusions.

## Deferred external work

Provider execution, the 135-response genuine-model pilot, statistical tests,
dynamic Free Invention evaluation, and paper claims remain external experiment
runs. Hidden Oracle execution is formal machine ground truth under the declared
utility function rather than human scalar annotation. The repository stays
provider-neutral and does not contain credentials or an implicit network call.
