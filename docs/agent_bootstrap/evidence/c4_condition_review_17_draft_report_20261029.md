# C4.1 Condition Parser Safety Independent Review

Status: independent QA PASS for the bounded C4.1 parser-safety source.
This is not full P1/P2 acceptance and does not accept C4.3 active-condition
gating.

## Findings

1. **Open C4.3 gap: a false top-level Skill condition does not gate an active
   timed Action.** The review fixture parses and equips a genuine
   `skill_blueprint` whose root condition evaluates false, then calls
   `submit_timed_primary_action` for a player. The process starts, two Time
   ticks are spent, and four Mana is charged. This reproduces the distinct
   omission in Main's `c4_active_condition_before.json`; it is **not** a C4.1
   parser defect, is not fixed here, and must remain open for C4.3.
2. **No C4.1 parser-safety finding remains in the tested raw-JSON surface.**
   Depth 1500 and width 100 now raise `GameplayContractError`, never
   `RecursionError`. Exact defaults and one-over boundaries, shared sibling node
   accounting, all operator/leaf kinds, trusted cap validation, caller
   immutability, and repeated parsing pass.
3. **Canonical Skill hashes from the pre-repair baseline are unchanged.**
   Five independently captured documents (null, all, any, not, mixed) retain
   their baseline hashes and normalized canonical documents.
4. **Residual gap: no public Status condition ingress exists.** Baseline
   `parse_status_spec` accepts no condition field. Claiming a Status parser
   test would require inventing schema, so Action, Effect, Skill, Hook, and
   timed Action paths are covered instead.
5. **Explicit non-claims.** This review does not establish CPU/wall-time,
   query, active-source, or generation budgets; does not add Process,
   Relation, or Discrete typed condition leaves; and does not establish full
   ten-scenario P1/P2 acceptance.

## Frozen Identity

- Starting checkpoint:
  `d613cc9391b828d764a5df6f83f9473bd72b93dc`
- Branch: `feature/alpha-v02-seventh-night`
- Stable `conditions.py` SHA256:
  `138b73a3ccaa12878028955afcbb5788b6ed5b59b66793f0b0701b4b513fafb4`
- Owner test SHA256:
  `5bc6d2cbaad49aa0f59130afa1fa6e1fdffbf0c85f8c7b8eaf8b747fefd9ff78`
- QA review test SHA256:
  `a2cc8eba6a48de0831c3897eaa5a07ae2794d2ae2a0a117251a19c8ca44a8791`
- Focused evidence log SHA256:
  `904e8ae8bb3edcbb563f6c66732778922f3408beafbd7ab10969d2e5bae2c612`
- Red fixture log SHA256:
  `4a38075813314425f2aa5621dae8040bfe98f0e95399b0972eb5e1223639696c`
- Evidence metadata:
  `docs/agent_bootstrap/evidence/c4_condition_review_focused_meta.json`

Owner-reported source hash matched the independently hashed stable source.
QA did not edit `conditions.py`, `test_sandbox_condition_limits.py`, any old
test, production code, or global configuration.

## Real Results

Focused independent suite:

```text
Ran 17 tests in 0.569s
OK
exit 0
```

The run started `2026-10-29T16:25:41.3136642+08:00` and finished
`2026-10-29T16:25:43.0718731+08:00`. The owner suite plus Action, harvest, and
time regression cross-check passed 45/45. A bounded gameplay-v04 discovery run
passed 328/328 in 98.806s. All commands used `-B`, bytecode disabled, and
PMW-local `TEMP`, `TMP`, `TMPDIR`, and cache paths under
`docs/agent_bootstrap/evidence/test_tmp`.

## Independent Coverage

The 17 focused methods exercise:

1. Defaults `max_depth=16`, `max_nodes=64`, `max_children=16`; trusted maxima
   `64`, `4096`, `256`; strict non-bool integer validation; keyword-only
   `ConditionLimits`; and rejection of untrusted limit mappings or objects.
2. Exact depth 16 and depth 17 for nested all/any/not/alternating operators.
   Depth 1500 rejects as `GameplayContractError`, with no `RecursionError`.
3. Exact 64-node acceptance, 65-node rejection, and shared 65-node sibling
   accounting. Child boundaries 16/17 and over-wide 100 reject before creating
   an over-wide child tuple.
4. Null/always and all typed leaves plus every logical operator count as nodes.
   Malformed root, scope, bool, nonfinite, and unknown-key guards remain
   product errors.
5. Repeated parsing leaves caller JSON unchanged and starts a fresh budget on
   every call. Cyclic raw dictionaries reject within the depth budget.
6. Actual Action and Effect parsers, plus formal Skill and Hook parsers,
   inherit the same default limits. The Action cost-modifier path is covered by
   the owner suite and cross-module Action regression.
7. Five baseline accepted Skill documents retain these canonical hashes:

```text
null   ecd9a0d56bcfbd07e21f3641d46766954e1598c61a734422040c0552b7197021
all    a11c2d230a5009ed30a774900c6dd992a041be0f3991ca5cba1ce6b7931ba126
any    4bb401d3f6de6d9e96eaab821091a86780b3d876fc64aa1e9558e554033a80dd
not    38a96c7c93f51c6b181cabe12cdf8d82101a5cd28608f11fa86cf1dcc8400f90
mixed  d780ea0cd0073d99668ab714149569aba2a68b1e4660770ad86e2c3453e3df39
```

These hashes were captured from the pre-repair baseline logic for the exact
review documents, independent of the repaired parser.
8. A genuine parsed and equipped Skill executes for player and NPC through
   `submit_timed_primary_action`: each pays two Time ticks and four Mana and
   starts its owned Process. This is parser/execution compatibility evidence,
   not acceptance that top-level conditions gate active execution.
9. Pathological depth, width, and cycle candidates are parsed through Action,
   Effect, Skill, and Hook surfaces before any timed execution. Session state,
   statistics, revisions, Mana, HP, shield, status, Time, and tick all remain
   unchanged. A later valid timed Action still charges correctly.

## Red Fixture Classification

An earlier draft run was `FAILED (failures=7, errors=4)`. All failures were
QA-fixture or expected-value defects, not C4.1 product defects:

- The node-boundary fixture exceeded the direct-child cap before testing nodes.
- The Process fixture omitted mandatory input/output ports.
- The all-node fixture expected 10 leaves but contained 11.
- Five expected canonical hashes belonged to a different document shape.

The preserved red log records the actual bounded limit errors that did pass,
including depth 1500 -> `GameplayContractError`. It is retained to distinguish
fixture error from product error, not cited as product-failure evidence.

## Changed Paths

- `experiments/generative_mechanics/next_tracks_v06/gameplay_v04/tests/test_sandbox_condition_limits_review.py`
- `docs/agent_bootstrap/C4_CONDITION_LIMITS_REVIEW.md`
- `docs/agent_bootstrap/evidence/c4_condition_review_red_fixture_20261029.log`
- `docs/agent_bootstrap/evidence/c4_condition_review_focused_stable_20261029.log`
- `docs/agent_bootstrap/evidence/c4_condition_review_focused_meta.json`

No commit, push, or global configuration change was made. Main still owns the
frozen full-suite gate, accounting, checkpoint, and C4.3 disposition.
