# Executable Invention Benchmark Tracks

This document separates the paper's research question from any one generation
protocol. The benchmark asks whether a model can invent mechanisms inside a
transparent, executable world without changing its underlying laws.

## Implemented tracks

### Free Invention

Question: can a model invent a non-trivial executable mechanism from the public
world rules?

The task supplies public channel semantics, generic public-law summaries, a
strict mechanic schema, and a unique request identity. It supplies no power
band, balance objective, scored calibration example, or revision controller.
High realized power is not a task failure. Evaluation reports independent
properties including structural novelty, interaction surface, causal depth,
cross-environment differentiation, downstream consequences, combinatorial
potential, and self-containment.

### Controlled Invention

Question: can a model invent a mechanism whose formally realized utility falls
inside a requested range?

Protocol v0.2-Controlled supplies Low/Mid/High targets and baseline-specific,
schema-matched calibration examples. Each baseline's examples are scored
through the same compiler and execution route used for that baseline. A
deterministic parameter controller is a separate baseline and is never called
LLM self-revision.

## Reserved tracks

Goal-directed Invention and Constrained Invention remain benchmark-design
positions, not implemented protocol claims. They require separately frozen
goals, constraints, success measures, and contamination boundaries before any
model collection.

## Oracle semantics

`OracleIntrinsicPower` estimates expected realized utility over the complete
pre-registered hidden distribution. `OraclePersonalizedDelta` uses a smaller
pre-registered stratified set of build contexts because exact 10-to-11 search
is substantially more expensive.

These are machine-verifiable targets under a declared utility function. They
are not claims about an objective human notion of game balance. The supported
paper claim is that a compact evaluator predicts realized utility over a larger
hidden world-state distribution.

## Reporting boundary

Free and Controlled results are separate tasks. Power controllability cannot
stand in for invention quality, and novelty cannot stand in for controllability.
Fixture data validates infrastructure only; genuine-model claims require
provider responses with preserved provenance.
