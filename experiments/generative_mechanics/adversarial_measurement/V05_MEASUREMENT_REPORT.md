# Free-Invention Dynamic Evaluation v0.5 Measurement Report

## Decision

**Recommendation: `FREEZE_READY` for the v0.5 evaluator contract.** This is not
a claim that a genuine-model pilot has been run. It means the implementation
matches the preregistered constructs, has no unresolved implementation failure,
and names its remaining construct boundaries instead of hiding them in a score.

Generation v0.3, Controlled v0.2, PMW Core, world/system laws, the 36 reference
mechanics, and all v0.4 raw evidence remain unchanged.

## Preregistration and evidence

- Base commit: `b1bdb5bb580ce85a9992bb679eb445be849c8b1b`
- Protocol: `gm-free-evaluation-v0.5-candidate`
- Preregistration: 48 retained v0.4 cases plus 22 new v0.5 cases
- Preregistration digest: `0a4658766b0166602c7410b65bc1dabb313711d6ce6b4b95ad2f43ef19ee44ce`
- Adversarial result: 69 `PASS`, 1 `KNOWN_LIMITATION`, 0 `FAIL`
- Production validation: 20 total, 18 full production stack and 2 explicitly synthetic-only
- Production evidence SHA-256: `acb45ff155d32d3a5c6283a5281981c46e029eb64428fd0abaeb8f47018efd16`
- Adversarial results SHA-256: `45dab8f75c7fabe9f77f426a1366ff2d74d66646e9675b7987541ed0de44421d`
- Adversarial summary SHA-256: `127ee5ab9bd2bd2be7e746f65f28988caf946118725bf0c426ad674f14c0f4fe`
- Ordered pipeline manifest SHA-256: `d097263739fcac961bf624c58b52490217a56d23efa246ab0e5558567ad33740`
- Whole-evaluator semantic contract: `01635c9e500c22250bb8fe3309c54a213bcd9a0638a8429b730f07e8121851d2`
- Binding policy: identity equality; no observational-equivalence classes are registered
- Generative Mechanics tests: 296/296
- PMW Core tests: 254/254
- Core manifest: `0cb9271e7dcfa9b1882246190f78afddfb1f153e699c7609182cbcd921cacf5d`

The semantic contract binds 80 assets: v0.5 evaluator and CLI sources, relevant
shared signature/execution sources, the protocol and mapping, generation v0.3,
environment and scenario assets, world/system laws, the 36 reference sources,
the reference projection registry, and preregistration. A copied environment
asset with one-byte drift fails closed.

## Metric mapping

| v0.4 umbrella/result | v0.5 evidence |
| --- | --- |
| downstream causal depth | realized dependency depth; necessity-backed depth; depth gap |
| environmentally differentiated | outcome differentiation; causal-path differentiation |
| exact novel against registry | exact match; near-copy edits; conservative recombination; semantic structure; abstract topology |
| candidate activated | activation; independently evaluated behavioral inertness |

Necessity-backed depth is a single-law-ablation lower bound. The realized-minus-
necessity gap is compatible with redundancy or overdetermination but does not
prove either. Exact non-match is weak registry evidence. A false recombination
result does not prove non-recombination.

## The ten review questions

### 1. Disposition of the nine v0.4 SUSPECT cases

| Case | v0.5 disposition | Resolution |
| --- | --- | --- |
| CD-08 | `RESOLVED_BY_SPLIT` | realized depth retains the dependency; necessity-backed depth may omit it |
| CD-11 | `RESOLVED_BY_DEFINITION` | binding identity is semantic absent an explicit registered equivalence class |
| CE-05 | `RESOLVED_BY_SPLIT` | equal outcome and different path are separate values |
| CE-15 | `RESOLVED_BY_SPLIT` | multiplicity-sensitive path evidence is separate from outcome evidence |
| SN-06 | `RESOLVED_BY_SPLIT` | semantic structure and abstract topology are both reported |
| SN-10 | `RESOLVED_BY_SPLIT` | conservative recombination evidence is separate from exact match |
| SN-11 | `RESOLVED_BY_SPLIT` | one-trigger edit is an explicit near-copy |
| SN-12 | `RESOLVED_BY_SPLIT` | one-effect edit is an explicit near-copy |
| SN-15 | `KNOWN_LIMITATION` | same-field cancellation is unrepresentable in frozen SkillSpec |

### 2. Redundant causation

The controlled overdetermination case reports realized dependency depth 2,
necessity-backed depth 1, and gap 1. The redundant-then-deeper case reports 3,
1, and gap 2. A production arm also exhibits a 9 versus 7 gap. These are gap
diagnostics, not claims that general actual causality has been solved.

### 3. Outcome/path separation

Both required separation quadrants exist. The preregistered synthetic cases
report same outcome/different path as `false/true`, and different outcome/same
path as `true/false`. Both also occur in production-stack executions. The
remaining `true/true` and `false/false` quadrants are separately tested.

### 4. Exact novelty saturation

Yes. One-point edits quickly become exact non-matches. v0.5 therefore reports
exact match as the weakest registry evidence and never labels exact non-match
as creative, genuinely novel, or a new causal topology.

### 5. Near-copy detection

Both preregistered cases pass. A one-trigger addition yields one `add_trigger`
edit; a one-effect addition yields one `add_effect` edit. Both are also run as
validated SkillSpecs through the production compiler/execution stack.

### 6. Recombination

Yes, for its deliberately conservative scope. The registered simple union has
coverage 1.0, purity 1.0, and an independent contribution from each of two
compatible references, and reports their ids. A negative result has no
converse interpretation.

### 7. Wetness versus sound

`wetness += X` and `sound_level += X` have different semantic fingerprints and
the same abstract-topology fingerprint. Canonical renaming preserves read/write
roles, operators, polarity, temporal form, scope, and cardinality.

### 8. Structurally new but behaviorally inert

The profile retains structural evidence and separately reports
`behaviorally_inert: true` when paired execution has neither an observed-state
difference nor candidate-induced normalized world-law activity. It is not
rewritten as structurally old. This combination occurs in production evidence.

### 9. Cross-dimensional decoupling

All requested examples are present: exact-match/low structural evidence with
realized depth at least 2; semantic non-match with zero dynamic reach; path
differentiation with zero outcome differentiation; and outcome differentiation
with no path differentiation. No aggregate score collapses these profiles.

### 10. Freeze recommendation

`FREEZE_READY`. There are no implementation failures. The only retained old
limitation is the named SkillSpec expressivity ceiling in SN-15. General
causality, inferred binding equivalence, complete program decomposition, and a
converse interpretation of recombination remain explicit non-claims.

## Reproduction artifacts

- `free_evaluation_v05/protocol.json`: frozen construct definitions
- `free_evaluation_v05/design_summary.json`: concise design contract
- `free_evaluation_v05/metric_mapping.json`: old/new field mapping
- `v05_preregistered_cases.jsonl`: expectations written before execution
- `results/v05_pre_revision_baseline.jsonl`: preserved pre-revision baseline
- `v05_results.jsonl`: all 70 post-implementation case results
- `v05_summary.json`: counts, dispositions, and result digests
- `results/v05_production_validation.json`: production and synthetic-only evidence
- `results/v05_pipeline_manifest.json`: byte-identical double production run followed by audit

The CLI defaults to v0.5 and requires `--evaluation-version v0.4` for an exact
historical replay. It does not alter generation prompts or response provenance.
