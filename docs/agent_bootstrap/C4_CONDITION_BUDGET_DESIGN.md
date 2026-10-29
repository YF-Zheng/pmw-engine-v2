# C4 Condition Complexity Safety Design

Architecture queued after C3. This is one independently testable repair in the
remaining P1 budget work, not the entire P1 or P2 language gate.

## Evidence And Target

Current conditions.py recursively parses all/any/not without a depth, total
node or per-branch limit. Skill material effect budget is computed AFTER
parsing, so it cannot bound a single malicious condition tree. The same parser
is used by Actions, Effects, Statuses, Skills and Hooks. Core already has event
cascade and settle ceilings; do not claim that these protect JSON parsing.
Keep the shared parser and existing typed leaves; no new evaluator or clock.

Before repair Main must preserve a minimal deep-tree baseline that reaches
RecursionError rather than GameplayContractError. Build the tree iteratively,
run offline inside repo-only temporary paths and retain actual exception data.
No model-generated Skill calls or giant performance workload are needed.

## Bounded Contract

One parse traversal has a shared node budget, with root depth one. Proposed
conservative defaults: max_depth=16, max_nodes=64, max_children=16. Validate
configuration as finite positive non-bool integers and cap tunable maxima.
Every logical operator AND/OR/NOT and every leaf, including null/always, counts
one node. Siblings share the total budget; do not reset it on recursion.
Reject before descending beyond depth or allocating an over-wide child tuple.
Return GameplayContractError with path and limit kind, never RecursionError.
Do not mutate caller JSON or global counters; budgets are local to each parse.

Retain the public parse_condition(raw, path=...) API and optionally a trusted
keyword-only ConditionLimits. Existing call sites inherit safe defaults. The
candidate cannot raise limits via JSON. No leaf schema, type or comparison
semantic change. Boolean, unknown-key, nonfinite and scope guards survive.
Preserve canonical accepted Skill documents/hashes and Action lowering for
old content. Trusted hand-created ConditionSpec is outside raw JSON acceptance;
do not silently claim arbitrary Python objects have been bounded.

## Ownership And Acceptance

After C3 acceptance, DeepSeek implementation owns conditions.py and one NEW
test_sandbox_condition_limits.py only. Independent QA owns a disjoint new
test_sandbox_condition_limits_review.py plus its report/evidence. Main owns
architecture/source review, old-test immutability, frozen full regression,
accounting and checkpoint. Do not edit old tests, Engine/runtime/clock or
material/global configuration to satisfy this bounded repair.

Verify exact default boundaries and one-over for depth/nodes/children, shared
sibling accounting, alternating AND/OR/NOT, invalid limits, repeated parsing
without budget leaks, caller immutability and unchanged accepted semantics.
Exercise formal parse_skill_blueprint and shared Action/Effect/Status/Hook
entry points, plus a normal timed player/NPC Action with an accepted condition.
Pathological input must fail before execution without resource/registry writes.
Run focused and cross-module regression, independent review and a frozen full
suite before checkpointing. This does not establish CPU/wall-time, global
query/active-source budgets, missing typed Process/Relation/Discrete conditions,
multi-trigger IR or full ten-scenario P1 acceptance; those remain explicit.
