# C4.1 Condition Parser Safety Independent Review

Status: independent QA PASS for the bounded C4.1 parser-safety source and
its frozen 16-test QA suite. The earlier 17-test draft is preserved only as
historical draft/evidence. This is not full P1/P2 acceptance and does not
accept C4.3 active-condition gating.

## Findings

1. **Open C4.3 gap: a false top-level Skill condition does not gate an active
   timed Action.** Main's `c4_active_condition_before.json` and the separate
   non-collected `probe_top_level_false_gate_omission` observe that the
   Process starts, two Time ticks are spent, and four Mana is charged. This
   is **not** a C4.1 parser defect and is not fixed here. The observed defect
   is intentionally not asserted by any collected test and remains open for
   C4.3.
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
  `6705f76f5f254fa571ba66676a37f25e4c5aac95f265f2e34c331e0c089a6092`
- Frozen 16-test focused log SHA256:
  `a4a91145b221e61890dc59c2ab6f6ff0c12fa2b5be37d3f0c41d43f738ea213c`
- Preserved original 17-test focused log SHA256:
  `904e8ae8bb3edcbb563f6c66732778922f3408beafbd7ab10969d2e5bae2c612`
- Preserved original 17-test QA file SHA256:
  `a2cc8eba6a48de0831c3897eaa5a07ae2794d2ae2a0a117251a19c8ca44a8791`
- Preserved original 17-test report SHA256:
  `73c9511bd36648692c4eee9562b35d72a5f34852a7ab5987f081c9309cc85eba`
- C4.3 standalone probe evidence SHA256:
  `b280d384f75a83485816ae0a4b2a7a731204a272dac9be264a8f87c2fa4cb944`
- Red fixture log SHA256:
  `4a38075813314425f2aa5621dae8040bfe98f0e95399b0972eb5e1223639696c`
- Evidence metadata:
  `docs/agent_bootstrap/evidence/c4_condition_review_16_meta_20261029.json`

Owner-reported source hash matched the independently hashed stable source.
QA did not edit `conditions.py`, `test_sandbox_condition_limits.py`, any old
test, production code, or global configuration.

## Real Results

Frozen independently reviewed suite:

```text
Ran 16 tests in 0.390s
OK
exit 0
```

The run started `2026-10-29T16:33:00.2983403+08:00` and finished
`2026-10-29T16:33:01.7523977+08:00`. The owner suite plus Action, harvest, and
time regression cross-check passed 45/45. A bounded gameplay-v04 discovery run
passed 328/328 in 98.806s. All commands used `-B`, bytecode disabled, and
PMW-local `TEMP`, `TMP`, `TMPDIR`, and cache paths under
`docs/agent_bootstrap/evidence/test_tmp`.

## Independent Coverage

The 16 frozen requirement methods exercise:

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
   not acceptance that top-level conditions gate active execution. All 16
   methods are true acceptance checks; none asserts the C4.3 defect persists.
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

## 17-Test Draft Cleanup

The original draft had 17 methods because it included
`test_top_level_false_gate_omission_is_explicit_c43_gap`, asserting that a
false root condition still started the Process, spent two Time ticks, and
charged four Mana. That method was out of C4.1 scope and would have made the
known defect a permanent passing regression after C4.3 repairs it.

Cleanup converted the reproduction to a non-collected
`probe_top_level_false_gate_omission`. Its observed fields are archived only
in `docs/agent_bootstrap/evidence/c4_condition_review_active_gap.json`.
No `test_*` method requires the defect to persist. The original 17-test
focused log, QA test, report, and metadata are preserved under their original
or `_17_draft_` evidence names. Parser, budget, canonical-hash, formal-entry-
point, and atomicity assertions were not weakened.

## Changed Paths

- `experiments/generative_mechanics/next_tracks_v06/gameplay_v04/tests/test_sandbox_condition_limits_review.py`
- `docs/agent_bootstrap/C4_CONDITION_LIMITS_REVIEW.md`
- `docs/agent_bootstrap/evidence/c4_condition_review_red_fixture_20261029.log`
- `docs/agent_bootstrap/evidence/c4_condition_review_focused_stable_20261029.log`
- `docs/agent_bootstrap/evidence/c4_condition_review_focused_meta.json`
- `docs/agent_bootstrap/evidence/c4_condition_review_17_draft_test_20261029.py.txt`
- `docs/agent_bootstrap/evidence/c4_condition_review_17_draft_report_20261029.md`
- `docs/agent_bootstrap/evidence/c4_condition_review_17_draft_meta_20261029.json`
- `docs/agent_bootstrap/evidence/c4_condition_review_active_gap.json`
- `docs/agent_bootstrap/evidence/c4_condition_review_16_stable_20261029.log`
- `docs/agent_bootstrap/evidence/c4_condition_review_16_final_20261029.log`
- `docs/agent_bootstrap/evidence/c4_condition_review_16_meta_20261029.json`
- `docs/agent_bootstrap/evidence/c4_condition_review_cross_module_20261029.log`

No production change, commit, push, old-test edit, or global configuration
change was made. Main still owns the frozen full-suite gate, accounting,
checkpoint, and C4.3 disposition.
