# Adversarial Measurement Audit Report

## Decision

**Recommendation: `MAJOR_REVISION`.**

The implementation is substantially more robust after two narrow corrections,
but the v0.4 measurement protocol should not be frozen for scientific claims.
The remaining problems concern what the constructs mean: necessity ablation
misses redundant causation, cross-environment reporting conflates outcome and
path-count differentiation, and exact structural novelty saturates on trivial
near-copies and simple recombinations. Those issues cannot be repaired by
making tests green.

Controlled v0.2, Free generation v0.3, PMW Core, and Engine semantics were not
changed.

## Preregistration and execution order

The suite was written and hashed before any case execution:

```text
base commit:              de5451ceaeb020b2ceac1ce6b87752ade0988244
cases:                    48
causal / cross / novelty: 16 / 16 / 16
cross-metric tags:        8 overlapping cases
case digest:              4330f15b294c8b5ee255b95c70476eec0b37c3d8543384cea63970274927088f
```

Execution then followed the required order: preregister suite, run original
logic, seal raw output, judge each case, classify findings, and only then apply
local corrections. The original raw result digest is:

```text
ac6935e6caf072bf5e373a1f3c432f921e1c78fa8bf4169fe50f55f9950b7b47
```

Original judgements were `36 PASS / 9 SUSPECT / 3 FAIL`. Full per-case evidence
is in `adversarial_results.jsonl`; no failed observation was deleted. Post-fix
results are `39 PASS / 9 SUSPECT / 0 FAIL` with digest:

```text
781855351894f4418ca1dcbd14bef652a5dbaa7ebdc211dea75ae3011f389556
```

## Evidence strength

The 48 preregistered cases are exact measurement attacks. Causal cases use
controlled `ScenarioRun` traces; cross-environment cases use controlled
`EnvironmentEffect` inputs and the production DiD implementation; novelty
cases use legal SkillSpecs and the production registry evaluator. Synthetic
inputs are necessary for interventions the frozen SkillSpec language cannot
express, such as replacing event identities or injecting redundant generic
world-law paths.

Twelve supplemental production validations use actual validated SkillSpecs,
trusted compilation, fresh worlds, the four registered environment assets,
real world laws, and production evaluator entry points. They include:

- zero effect with distinct backgrounds: one empty signature, no differentiation;
- equal nonzero effect (`all_low`, temperature -0.8): one signature;
- one-plus-three partition (`all_low`, wetness +0.8): two signatures;
- two-plus-two partition (`all_low`, electric field +0.4): two signatures;
- depth 2 with one invariant environment signature (`all_low`, wetness +0.4);
- depth 0 with two environment signatures (`all_low`, fire intensity -0.8);
- an exact-novel three-effect declaration with low depth 1;
- simple electric-field write: causal depth 3 and three environment signatures;
- multi-field fanout: realized depth 7 through actual downstream chains;
- periodic repetition: realized depth 4 without counting candidate laws;
- scheduled duration/expiry: realized depth 3;
- impossible trigger: no activation, no differentiation, novelty unavailable.

Production validation artifact SHA-256:
`0470a79a328deba7c4205177220a069420785d5518f71e84085e1f8724725ebb`.

## Causal depth findings

**Parallel and repeated activity.** Two- and four-law fanout remained depth 1;
delaying sibling events did not increase depth. Repeated execution of one law
also remained one structural layer. Real depth-1/2/3 chains produced the
expected staircase, and delayed chains remained countable.

**Alternative paths.** CD-08 exposed a real construct limitation. When A and B
are individually sufficient for C, removing either leaves C, so the current
law-by-law necessity criterion rejects both A-to-C and B-to-C edges. C is
genuinely downstream of the candidate but disappears from the retained graph.
This is an overdetermination false negative, not a coding typo.

**Execution identity.** CD-09 and CD-10 were confirmed measurement failures.
The original occurrence key included command id, event id, and absolute time;
changing only event id or timestamp made a semantically preserved C appear
removed. The correction pairs by event type, phase, law id, bindings, canonical
reads/writes, canonical committed old/new results, and Counter multiplicity.
Event identity and absolute time are no longer causal evidence. A multiplicity
regression confirms two same-signature occurrences do not collapse to one.

Binding identity remains in the key. CD-11 is therefore still SUSPECT: bindings
normally identify semantic entities, and treating two bindings as equivalent
requires an explicit observational-equivalence policy rather than silently
discarding them.

**Last writer and no-op commits.** Overwrite and unrelated-write cases behaved
as defined: only the last writer of the read address received attribution, and
an unrelated later write did not steal it. A matched rule with no committed
state delta did not become a causal root.

## Cross-environment findings

**Background subtraction.** Large state and law-count background differences
cancelled correctly. Zero-effect production execution also yielded one empty
signature across four distinct environments. Missing sparse coordinates and
explicit zeros were equivalent; 12-decimal normalization suppressed numeric
dust.

**Equal and differentiated effects.** Equal nonzero net effects were not
mistaken for differentiation. One-environment, 2+2, magnitude-gradient, and
sign-split attacks were detected. The real production fixtures independently
demonstrated equal, 1+3, and 2+2 partitions.

**Transient effects.** Registered short-horizon coordinates preserve an
intermediate difference even when the final coordinate recovers. In addition,
world-law occurrence signatures retain causal-path activity that later
dissipates.

**What is measured.** CE-05 and CE-15 prove the current output is not purely an
outcome-difference metric. Equal state effects with different world-law ids or
counts are classified as environmentally differentiated. The evidence is
useful, but the single `environmentally_differentiated` boolean combines two
constructs: state-outcome differentiation and causal-path-count
differentiation. They should be reported as separate profile dimensions before
freeze.

## Structural novelty findings

Renaming, numeric tuning, economy parameters, and effect reordering did not
change the fingerprint. Effect polarity did, as documented. A field
substitution also changes the fingerprint: this is semantic-channel-sensitive
structure, not field-agnostic abstract topology, and the paper must name it
accordingly.

The existing zero-delta guard worked for all-zero and mixed-zero cases. SN-07
found a separate dead-code failure: `temperature > 1.0` is legal syntax but
provably unreachable on a normalized public channel, yet the original metric
reported available exact novelty. The scoped correction makes only `> 1` and
`< 0` boundary contradictions unavailable. It deliberately does not pretend
to solve general trigger satisfiability, clamp no-ops, or downstream
cancellation.

Exact novelty saturates quickly. Both a one-trigger edit and a one-effect edit
to a registered seed became exact-novel. A simple union of two registered
modules also became exact-novel. These are not implementation bugs: exact set
membership behaves as specified. They are construct limitations showing that
`exact_novel_against_registry` cannot stand alone as evidence of genuinely new
causal topology. Recombination and near-copy rates need explicit reporting.

## Cross-metric separation

The suite and production supplement jointly exhibit:

- high/possible structural novelty with zero dynamic behavior: unreachable
  trigger before correction;
- low structural novelty with high realized reach: registered-shape electric
  mechanisms reach depth 3 and differentiate environments;
- high depth with no environment difference: the production wetness mechanism
  has depth 2 and one net signature;
- low depth with high environment difference: the production fire-reduction
  mechanism has depth 0 and two net signatures;
- complex declared structure with low reach: inert/guarded multi-part specs;
- old but powerful: magnitude retuning preserves a registered fingerprint.

The three dimensions are therefore not numerically identical. Their remaining
problem is construct validity and labeling, not simple collinearity.

## Corrections made

1. Causal counterfactual matching no longer uses generated command/event ids or
   absolute timestamps. It retains semantic signatures and multiplicity.
2. Structural novelty fails closed for triggers provably unreachable at the
   normalized field boundaries.

No correction was made for redundant causation, binding equivalence,
outcome/path aggregation, field-sensitive topology, near-copy saturation, or
recombination. Those require protocol decisions and new preregistration.

## Hashes and isolation

```text
Core manifest (unchanged):       0cb9271e7dcfa9b1882246190f78afddfb1f153e699c7609182cbcd921cacf5d
cross-env semantic contract:     d36d2e9c46b806de9fee3cc82e2e2486f57297ca6ad989ce1600141d270e83cb
reference projection:            bffb8ff4bbaaf678bcacd81af867c77b31147fe5c6c44ee2f51a0f95e77383cc
reference source manifest:        7f3fe174c9c9820b2ad7572fd42a28113018cd614ff3bb3676a1bd59a1ce6d91
v0.4 protocol file after fix:     0e72395b5d0880fa28ce4fbc8a51b8608b510e43ab628f42ada56677851c934a
```

`git diff -- src/pmw tests` is empty. Core, Engine, Controlled v0.2, and Free
generation v0.3 have no semantic changes.

Final regression run:

```text
Generative Mechanics: 264/264 passed
PMW Core:              254/254 passed
JSON/JSONL validation: passed
git diff --check:      passed
```

## Required revision before freeze

1. Split cross-environment outcome differentiation from causal-path
   differentiation; do not combine them in one headline boolean.
2. Decide and preregister how redundant/overdetermined causation contributes to
   causal depth. The current necessity graph is conservative but incomplete.
3. Report exact match, near-copy edit profile, and recombinational novelty as
   distinct structural evidence. Do not call exact non-membership genuinely new
   topology.
4. State whether field identity is part of structure and whether any bindings
   may be observationally equivalent.
5. Add a behavioral-inertness limitation to reporting; the static guard only
   catches provable boundary dead code.

Until these decisions are made and preregistered, v0.4 should remain an
implementation candidate under **`MAJOR_REVISION`**, not a frozen measurement
protocol.
