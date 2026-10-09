# Experiment 2 - Interface Experiment Plan

Status: `PLANNED`; sample size and fixed model configuration require a later
owner decision before a dedicated freeze. No collection is authorized here.

## Question And Conditions

Does representation change realized system behavior when a generated object is
expressed through one of three interfaces?

1. `isolated_direct_effect`
2. `matched_direct_outcome`
3. `world_substrate`

The claim concerns the interface, not model creativity. Use one or a small
fixed set of model configurations. Within each model, canonical generation
coordinates are matched across conditions, condition order is randomized and
interleaved, and request budgets are held fixed under the selected inference
policy. Any unavoidable prompt-byte differences are part of the interface
treatment and must be archived.

## Hypotheses And Endpoints

Directional hypotheses, specified independently of the DEV pilot, are that
`world_substrate` produces:

- greater realized world-law participation;
- greater mechanism-level realized dependency depth;
- more environment-conditioned outcomes and/or causal paths.

Primary endpoint candidates are a mechanism-level world-law participation
indicator/rate, median realized dependency depth across activated arms, and
fractions of outcome- and path-differentiated contexts. Exact definitions must
be frozen only after verifying cross-interface construct comparability; a
WorldSubstrate-only structural registry is not applied across schemas.

## Unit And Analysis

The independent unit is a generated mechanism/request coordinate. Interface
arms matched on a canonical coordinate form a block; execution arms remain
repeated measurements. Primary contrasts are prespecified pairwise interface
differences with block-respecting permutation tests and mechanism-block
bootstrap CIs. If several models are used, report interface effects within
model and a preregistered stratified aggregate; do not convert model identities
into extra replicates.

Validity is always reported for all requests. Invalid outputs have behavioral
metrics NA. Valid mechanisms that never activate have activation 0 and frozen
activation-conditional depths NA. Multiplicity, blinding, immutable raw data,
transport-only retry, content non-retry, stopping, and version-replacement rules
follow the Free experiment unless the later frozen protocol states a stricter
rule.

## Required Pre-Collection Decisions

- fixed model configuration(s) and exact version IDs;
- comparable prompt and output contracts for all three interfaces;
- endpoint mapping and any structurally unavailable constructs;
- N per interface per model and collection-order seed;
- inference-budget policy and token limits;
- analysis implementation, fixture verification, manifest, hashes, and tag.

No Interface data are collected until those items are resolved and frozen.
