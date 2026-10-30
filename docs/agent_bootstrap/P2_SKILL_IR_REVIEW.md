# P2.1 Skill IR Independent Review

## Verdict

**REJECT**

The compiler correctly handles the main budget, authority, determinism,
language-gap, ID-length, input-isolation, and formal runtime paths reviewed
here. It is not ready to accept P2.1 because an accepted lifecycle capability
is silently discarded, malformed inputs escape the contract exception boundary,
and a parsed IR can be mutated so that its stable hash identifies changed
lowered semantics.

Review scope is P2.1 only. The owner suite and all focused regression tests pass
except for the independent requirement assertions below.

## Findings

### 1. PRODUCT_DEFECT: `lifecycle.status_duration` is silently discarded

**Classification:** PRODUCT_DEFECT

`parse_skill_ir` accepts and stores `status_duration`, but lowering always
emits `"duration": None` at `skill_ir.py:510`. Runtime searches find reads of
`EffectSpec.duration`, action cost duration, and other duration fields, but no
runtime consumer of `SkillBlueprint.duration`. Therefore a non-null lifecycle
value is decorative, contrary to the design principle that every accepted IR
capability maps to an accepted runtime path or is rejected with
`language_gap`.

Minimal reproduction:

```python
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.tests.test_skill_ir_review import (
    _document, _parse,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.skill_ir import (
    compile_skill_ir,
)

for unit, amount in (("world_tick", 7), ("combat_round", 2)):
    ir = _parse(_document(
        status_duration={"unit": unit, "amount": amount},
    ))
    lowered = compile_skill_ir(ir).blueprints[0]
    print(dict(ir.status_duration), lowered.duration,
          lowered.canonical_hash)
```

Observed:

```text
{'unit': 'world_tick', 'amount': 7} None 67f8bc9813354512b218709f7a895ae2e8088e8494d5ab9f2a97be630c3308c2
{'unit': 'combat_round', 'amount': 2} None 67f8bc9813354512b218709f7a895ae2e8088e8494d5ab9f2a97be630c3308c2
```

Both accepted inputs produce the same lowered hash. Required behavior is either
to preserve the requested duration into a consumed runtime path, or reject the
capability with a `language_gap` reason. The review test asserts that contract.

### 2. PRODUCT_DEFECT: malformed scalars leak raw `TypeError`

**Classification:** PRODUCT_DEFECT

Membership tests occur before scalar type checks. A list value reaches set or
dict membership and raises `TypeError` instead of
`GameplayContractError`.

Affected examples:

- `$.origin.source = []` at `skill_ir.py:171`
- `$.lifecycle.status_duration.unit = []` at `skill_ir.py:607`
- `effect.kind = []`, through delegated `effects.py:76`

Minimal reproduction:

```python
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.tests.test_skill_ir_review import (
    _document, _parse,
)

raw = _document()
raw["origin"]["source"] = []
_parse(raw)
```

Observed:

```text
TypeError: unhashable type: 'list'
```

This breaks the validator's contract-error boundary for malformed untrusted
documents. The test requires `GameplayContractError` for all three inputs.

### 3. PRODUCT_DEFECT: returned `SkillIR` does not preserve hash integrity

**Classification:** PRODUCT_DEFECT

Although `SkillIR` and `SkillEntryIR` are frozen dataclasses, parsed effect and
condition dictionaries remain mutable. `compile_skill_ir` trusts any
`isinstance(ir, SkillIR)` object and does not verify that the current entries
still match `canonical_json` / `canonical_hash`. Mutating a nested effect after
parse changes lowered semantics while the IR hash stays unchanged.

Minimal reproduction:

```python
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.tests.test_skill_ir_review import (
    _document, _parse,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.skill_ir import (
    compile_skill_ir,
)

ir = _parse(_document())
before = compile_skill_ir(ir)
ir.entries[0].effects[0]["amount"] = 999
after = compile_skill_ir(ir)

print(ir.canonical_hash == after.canonical_hash)
print(before.blueprints[0].effects[0].amount,
      after.blueprints[0].effects[0].amount)
print(before.blueprints[0].canonical_hash,
      after.blueprints[0].canonical_hash)
```

Observed:

```text
True
4.0 999.0
67f8bc9813354512b218709f7a895ae2e8088e8494d5ab9f2a97be630c3308c2
aee2cb5dc7a6db47e47e5f2d44cb0b8ba561142848589ab14ee2d361a6eccb20
```

This violates the trusted metadata guarantee that one IR hash links to the
lowered blueprints produced from that IR. The review test asserts an immutable
or revalidated trusted IR, not that the defect persists. A separate,
non-collected probe records the current failure.

### 4. SCOPE_NOTE: identity and model text are unbounded

**Classification:** SCOPE_NOTE (P3 generation/context-size responsibility
unless Main requires P2 ingress bounds)

`identity.name`, `identity.description`, and `origin.model` accept arbitrary
length. A 1,000,000-character value is accepted independently in each field;
the resulting canonical JSON is about 1 MB. This does not create a current
runtime semantic mismatch, but it is a generation-context/resource risk for P3.
It is not counted as a P2.1 blocker here.

Non-collected probe output is in
`docs/agent_bootstrap/evidence/p2_ir_review_probes.log`.

## Confirmed Passing Areas

- Condition budget: exact 64 accepted and 65 rejected when split across two
  entry conditions and two effect conditions; two separately valid 64-node
  trees rejected in one document; `None` children, `not`, max depth, and
  max children matched `parse_condition`.
- Material budget: active `2.0` plus two passives at `2.5` each equals `7.0`;
  each passive surcharge is counted once; `4.49` is rejected for a `4.5` use.
- Authority: unauthorized effect kind, unauthorized target selector, effect
  target outside declared selectors, `linked_object` without relation types,
  and material ID mismatch are rejected.
- Determinism: recursive key permutation preserved the IR hash, all lowered
  hashes, metadata, operators/state-classes, and preview. A single `on_use`
  lowering matched an independent handwritten v0.4 document hash.
- Triggers/events: `on_tick`, `on_expire`, `transition`,
  `condition_enter`, `condition_exit`, and all five reserved events produced
  `language_gap`; junk produced ordinary schema errors.
- Lowered-ID overflow and duplicate/input mutation after parse are rejected or
  isolated as required.
- Formal runtime: an independently authored two-entry IR (`on_use` damage `3`
  at Mana `5`/Tick `1`; `damage_resolved` self-shield `2`) ran through
  `make_content -> initialize_content_world -> compile_content ->
  build_content_session -> MechanismRegistryRuntime.from_compiled_content ->
  change_loadout -> submit_timed_primary_action/run_combat_round`.
  For both PLAYER and NPC: each cast spent Mana `5` and one Tick; player then
  NPC casts left each actor at Mana `25`, opponent HP `47`, shield `2`, clock
  `2/20`, remaining `18`; the combat round left each at Mana `20`, HP `46`,
  shield `2`, clock `3/20`, remaining `17`.

## Test Evidence

Focused command (same environment on every invocation):

```powershell
python -m pytest -p no:cacheprovider -q `
  experiments/generative_mechanics/next_tracks_v06/gameplay_v04/tests/test_skill_ir_review.py `
  experiments/generative_mechanics/next_tracks_v06/gameplay_v04/tests/test_skill_ir.py `
  experiments/generative_mechanics/next_tracks_v06/gameplay_v04/tests/test_p1_scenarios.py `
  experiments/generative_mechanics/next_tracks_v06/gameplay_v04/tests/test_gate4_registry_checkpoint.py
```

Focused result: **43 passed, 7 failed, 49 subtests passed**. The failures are
the three product findings above; no owner, P1, or Gate4 regression failed.
The review suite alone: **12 passed, 7 failed, 17 subtests passed**.

Evidence:

- `docs/agent_bootstrap/evidence/p2_ir_review_focused.log`
- `docs/agent_bootstrap/evidence/p2_ir_review_probes.log`

## Hashes

SHA-256 (lowercase):

```text
skill_ir.py
6680d7ad997b6aae81d6c27d2aedd0de02a4ecb8ecdb8f2aeabbc6c0cd66929d

owner test: tests/test_skill_ir.py
49807d367dd8bef2a49bd8881f0be0d5ba3ccee5eb0c68129f197d6212114d99

review test: tests/test_skill_ir_review.py
67e59d02fd6f28621e6397ffa2c10ff896c55c378d0b40e0d50d9a011bab20a7
```

The design contract read at review time:
`P2_SKILL_IR_DESIGN.md` SHA-256
`d1f904ea3ebb6fbc4bcd0b1c1fa03acc33725303b7f502ac3272c63d1bcea7f9`.

## Required Follow-up

1. Either lower `status_duration` into a runtime-consumed field and prove it
   through formal ticking/expiry, or reject duration capability with
   `language_gap`.
2. Validate scalar types before membership tests so malformed input always
   yields `GameplayContractError`.
3. Make the trusted IR immutable (or revalidate it in `compile_skill_ir`) so
   its canonical IR hash cannot identify altered lowered semantics.

Re-run the focused review suite after the owner fix; the review must not be
changed into an assertion that the defects are expected.

## Fix verification

**Re-verification verdict: REJECT**

The original findings above remain as the acceptance record. The fix owner's
direct-path changes were independently re-tested against the fixed
`skill_ir.py` SHA-256
`e9e12f49e54dd19c21bfd8c6e2c3a799c50fc3bbfab4f5ecd35eae08d366a4f0`.

Confirmed fixed:

- Non-null `lifecycle.status_duration` now raises
  `GameplayContractError` beginning with
  `language_gap:lifecycle.status_duration`; null remains accepted.
- All 29 independently exercised malformed-shape/scalar cases, including
  list targets, non-text target kinds, list/int conditions, bad trigger and
  membership values, raised `GameplayContractError`; none leaked another
  exception.
- A permitted `GameplayContractError` raised by delegated lowerers is not
  double-wrapped.
- Mutating reachable effect/condition dictionaries after parse no longer
  changes lowered semantics: compilation follows the hash-verified
  `canonical_json`.
- Length bounds `name=80`, `description=600`, `model=128` reject the next
  length; tested at both the accepted and over-limit boundaries.
- Handwritten v0.4 lowered-hash parity and the three prior product paths remain
  intact. The owner, fixes, P1, Gate4, and independent runtime tests pass.

Remaining PRODUCT_DEFECT: **`compile_skill_ir` does not apply the full IR
validation contract to the canonical document it now trusts.**

`_canonical_ir` in `skill_ir.py:737` uses `_strict`, `_identifier`,
`_positive_int`, texts, and per-entry shape checks, but it does not rerun
`parse_skill_ir`, and it does not recompute `condition_nodes` or shared budget.
It reads `ir.condition_nodes` directly at `skill_ir.py:820`. Therefore a
self-consistent replacement of both `canonical_json` and `canonical_hash` can
compile an invalid IR that `parse_skill_ir` itself rejects.

Minimal reproduction:

```python
import hashlib
import json
from copy import deepcopy

from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.tests.test_skill_ir_review import (
    _document, _entry, _effect, _parse,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.skill_ir import (
    compile_skill_ir,
)

ir = _parse(_document())
document = deepcopy(_document())
document["entries"] = []  # invalid: entries must contain 1..4
text = json.dumps(document, sort_keys=True, separators=(",", ":"))
object.__setattr__(ir, "canonical_json", text)
object.__setattr__(
    ir,
    "canonical_hash",
    hashlib.sha256(text.encode("utf-8")).hexdigest(),
)
compiled = compile_skill_ir(ir)
print(len(compiled.blueprints), compiled.metadata)
```

Observed:

```text
0 ()
```

The same bypass accepts duplicate entry IDs, two `on_use` entries, effect
targets outside declared selectors, `linked_object` with no relation types,
shared budget overflow (two entries using `4.5` against a `3.0` limit), an
invalid `origin.source`, and over-bound model/summary text. Forging only
`condition_nodes = 999` is also accepted and surfaces as `999` in the rebuilt
IR and preview.

This is one PRODUCT_DEFECT with several facets. It is not a regression in the
three repaired direct paths, but it leaves the frozen decision (c) incomplete:
the hash verifies the payload bytes, not that the payload is a valid IR.

### Fix verification evidence

Focused command included `test_skill_ir_review.py`, `test_skill_ir.py`,
`test_skill_ir_fixes.py`, `test_p1_scenarios.py`, and
`test_gate4_registry_checkpoint.py`.

Result: **53 passed, 10 failed, 82 subtests passed**. The failures are the
single remaining defect's ten requirement probes: nine self-consistent
invalid-document cases and one forged `condition_nodes` case. All owner,
fix-owner, P1, Gate4, and ordinary independent tests passed.

Evidence:

- `docs/agent_bootstrap/evidence/p2_ir_review_fixverify.log`

Class counts for this addendum: **1 remaining PRODUCT_DEFECT, 0
FIXTURE_ERROR, 0 remaining SCOPE_NOTE** (the original unbounded-text scope note
is resolved by the new bounds).

Post-fix SHA-256:

```text
fixed skill_ir.py
e9e12f49e54dd19c21bfd8c6e2c3a799c50fc3bbfab4f5ecd35eae08d366a4f0

owner test: tests/test_skill_ir.py
49807d367dd8bef2a49bd8881f0be0d5ba3ccee5eb0c68129f197d6212114d99

fix-owner test: tests/test_skill_ir_fixes.py
bc875a78a5764f96d352c229f92bb4b9c42567cf5e0e2c8962e8f509b023f930

updated independent review test: tests/test_skill_ir_review.py
e013a040053ae1995f22c788bde2384e4c76ec3f5e4473b1706b2005a941d821
```

Required follow-up: make `compile_skill_ir` reload and fully validate the
canonical document under the same trusted statuses/authority/condition limits
used at parse time, or store an authoritative immutable parse result that
cannot be replaced independently of its hash. It must recompute
`condition_nodes`, enforce entries/IDs/selector/lifecycle/budget/authority and
length rules, while preserving accepted IR and v0.4 lowered hashes.

## Round-3 verification

**Round-3 verdict: REJECT**

The round-3 reparse design fixes the prior canonical-payload forgery defect.
`compile_skill_ir` now reloads `json.loads(ir.canonical_json)` through the full
`parse_skill_ir`, applies the recorded trusted condition limits, requires
matching hashes, and lowers only from that fresh parse. The previous
self-consistent invalid-document and forged-derived-field reproductions now
raise `GameplayContractError`.

The new attack matrix confirms:

- `dataclasses.replace` of every semantic `SkillIR` field (`id`, version,
  name, description, origin, material IDs, traits, selectors, relation types,
  costs, entries, lifecycle, budget, summary, tags, and condition node count)
  is ignored; output equals a fresh legal parse. Replacing `canonical_hash`,
  `canonical_json`, authority, statuses, or a non-`ConditionLimits` object
  fails closed with `GameplayContractError`.
- Self-consistent invalid canonical documents are rejected, including empty
  entries, duplicate IDs, two `on_use` entries, selector/relation violations,
  shared budget overflow, invalid origin, over-bound text, malformed nested
  conditions, list targets, non-text target kinds, and list/int conditions.
- Non-object JSON, malformed JSON, and excessive JSON nesting are wrapped as
  `GameplayContractError`. Duplicate-key JSON compiles exactly its fresh legal
  parse; that is semantic equivalence, not a bypass. A fully legal replacement
  with a consistent hash is likewise equivalent to legitimate parsing.
- Forged condition limits cannot exceed the frozen `ConditionLimits` hard caps
  (depth 64, nodes 4096, children 256). Tight limits are re-applied by the
  parser. Looser limits within those caps are accepted only because the design
  explicitly treats `condition_limits` as trusted input; this is a threat-model
  boundary, not a bypass of parser rules.
- Hash/key-order determinism, handwritten v0.4 lowered-hash parity, the
  independent Player/NPC formal-runtime run, lowered-ID overflow, and the
  original lifecycle `language_gap` behavior remain intact.

### Remaining PRODUCT_DEFECT: deep untrusted input leaks `RecursionError`

`parse_skill_ir` performs `deepcopy(raw)` at `skill_ir.py:135` before any
closed-schema validation. A deeply nested payload therefore raises raw
`RecursionError` instead of `GameplayContractError`. This is outside
`compile_skill_ir`'s try/except and breaks the frozen decision that all
malformed untrusted inputs stay behind the contract exception boundary.

Minimal reproduction:

```python
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.tests.test_skill_ir_review import (
    _document, _parse,
)

raw = _document()
nested = None
for _ in range(500):
    nested = [nested]
raw["entries"][0]["effects"][0]["payload"] = nested
_parse(raw)
```

Observed:

```text
RecursionError: maximum recursion depth exceeded
```

The round-3 review test asserts the correct requirement (contract error, not
the observed failure) and is therefore a failing requirement test until the
parser guards deep input.

### Round-3 evidence

Focused command included `test_skill_ir_review.py`, `test_skill_ir.py`,
`test_skill_ir_fixes.py`, `test_skill_ir_fix3.py`, `test_p1_scenarios.py`, and
`test_gate4_registry_checkpoint.py`.

Result: **66 passed, 1 failed, 134 subtests passed**. The sole failure is the
deep-input requirement test above; all owner, fix, round-3 owner, P1, Gate4,
and prior independent requirement tests pass.

Evidence:

- `docs/agent_bootstrap/evidence/p2_ir_review_fix3verify.log`
- `docs/agent_bootstrap/evidence/p2_ir_review_fix3verify_detail.log`

Class counts for this addendum: **1 remaining PRODUCT_DEFECT, 0
FIXTURE_ERROR, 0 remaining SCOPE_NOTE**.

Round-3 SHA-256:

```text
skill_ir.py
b43850a9537b0524f5cde057cd60bfb9c91d7f01637a0870ccc9872ac2627d65

owner test: tests/test_skill_ir.py
49807d367dd8bef2a49bd8881f0be0d5ba3ccee5eb0c68129f197d6212114d99

fix-owner test: tests/test_skill_ir_fixes.py
bc875a78a5764f96d352c229f92bb4b9c42567cf5e0e2c8962e8f509b023f930

round-3 owner test: tests/test_skill_ir_fix3.py
bef9390e0812426b90bfe15d2e1bc1e528305aa36ef16ddb4db86bc04d3d1521

updated independent review test: tests/test_skill_ir_review.py
dec1697948aa73485746f0d2b074c39bd956d2a5a55b193e5800e5b07017fee4

## Round-4 verification

**Verdict: REJECT**

Round 4 added the iterative `_validate_json_shape` guard and exercised it
independently of the owner's round-4 tests. The guard itself closes the prior
deep-input `RecursionError`: cyclic lists and dicts fail with
`GameplayContractError`, shared-reference DAGs reach the value cap rather than
expanding without bound, plain `dict`/`list` subclasses behave as JSON
containers, non-finite values are rejected, and the 128-container-depth and
65,536-value bounds are enforced. The prior canonical-forgery, determinism,
authority, material-budget, lifecycle, lowered-ID, mutation-isolation, and
Player/NPC runtime checks remain green.

Two requirements nevertheless fail.

### PRODUCT_DEFECT 1: trusted condition caps are not passed to delegated lowering

A document using trusted
`ConditionLimits(max_depth=64, max_nodes=4096, max_children=256)` passes the
input-shape guard and the document-wide condition-node count, but
`parse_skill_ir` then delegates shared-budget evaluation to
`parse_skill_blueprint`; that delegated path calls `parse_condition(...)`
without the recorded limits and therefore applies the defaults `16/64/16`.
Consequently, documents that are legal at the trusted caps cannot parse or
compile. This contradicts the requirement that the new shape bounds admit
every legal document under the trusted condition caps.

Minimal reproduction:

```python
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.conditions import (
    ConditionLimits,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.tests.test_skill_ir_review import (
    _document, _entry, _not_chain, _parse,
)

_parse(
    _document(entries=[_entry(condition=_not_chain(63))]),
    limits=ConditionLimits(max_depth=64, max_nodes=4096, max_children=256),
)
```

Observed:

```text
GameplayContractError: $.skill.condition.not... exceeds condition max_depth 16
```

The same failure occurs for a legal 255-child root (`$.skill.condition.all
exceeds condition max_children 16`) and for the 4,096-node legal tree. The
round-4 requirement test
`test_documents_at_trusted_condition_caps_parse_and_compile` asserts the
correct behavior and fails only because this path is still short-circuited by
the default delegated limits.

### PRODUCT_DEFECT 2: oversized integers leak raw `OverflowError`

The JSON-shape guard accepts arbitrary-size Python integers as JSON integers.
Semantic numeric checks then call `math.isfinite()` (and in delegated code
`float()`), which raises `OverflowError` rather than the required
`GameplayContractError`. This affects `costs.mana`, effect `amount`, and
condition `value`; `compile_skill_ir` can leak the same error while reparsing
a forged canonical document.

Minimal reproduction:

```python
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.tests.test_skill_ir_review import (
    _document, _entry, _effect, _parse,
)

raw = _document()
raw["costs"]["mana"] = 10 ** 400
_parse(raw)
```

Observed:

```text
OverflowError: int too large to convert to float
```

Replacing `costs.mana` with an effect `amount` or a resource condition
`value` produces the same leaked exception at `effects.py:292` or
`conditions.py:127`. The round-4 test
`test_oversized_integers_fail_closed_as_contract_errors` asserts the required
contract-error boundary and fails only because the implementation still leaks
the raw exception.

### SCOPE_NOTE: hostile container subclasses

Plain `dict` and `list` subclasses are accepted as intended. A malicious
subclass overriding `items()` or `__len__()` can cause arbitrary exceptions
from `_validate_json_shape`; this is outside the documented JSON-input threat
model and is recorded as a scope note, not a blocker.

### Round-4 evidence

Focused command included `test_skill_ir_review.py`, `test_skill_ir.py`,
`test_skill_ir_fixes.py`, `test_skill_ir_fix3.py`, `test_skill_ir_fix4.py`,
`test_p1_scenarios.py`, and `test_gate4_registry_checkpoint.py`.

Result: **6 failed, 81 passed, 146 subtests passed**. The six failures are the
independent requirement checks for the two defects above; all owner, fix,
round-3, round-4 owner, P1, Gate4, and prior independent checks pass.

Evidence:

- `docs/agent_bootstrap/evidence/p2_ir_review_fix4verify.log`

Class counts for this addendum: **2 PRODUCT_DEFECT, 0 FIXTURE_ERROR, 1
SCOPE_NOTE**.

Round-4 SHA-256:

```text
skill_ir.py
7d02fd59efbe6b6afaa2b80317cc081aa33fa4720e22c66c98079cc90471575d

owner test: tests/test_skill_ir.py
49807d367dd8bef2a49bd8881f0be0d5ba3ccee5eb0c68129f197d6212114d99

fix-owner test: tests/test_skill_ir_fixes.py
bc875a78a5764f96d352c229f92bb4b9c42567cf5e0e2c8962e8f509b023f930

round-3 owner test: tests/test_skill_ir_fix3.py
bef9390e0812426b90bfe15d2e1bc1e528305aa36ef16ddb4db86bc04d3d1521

round-4 owner test: tests/test_skill_ir_fix4.py
b2ab62da05086bfee18ecbca4a0da5fe46d1a12c456378ae2ef3daeaa8bf2afe

updated independent review test: tests/test_skill_ir_review.py
97ece00f76fe02437af5aca8ddccce964c4e27e005916e96faa2431814a71b0a

round-4 focused evidence log
7b8b3c12b0efec4b1f1765c957014325226d8774253bdaa92645a571887f772a
```

## Round-4 test governance

The prior requirement
`test_documents_at_trusted_condition_caps_parse_and_compile` is superseded by
Main's tighten-only decision in
`docs/agent_bootstrap/P2_SKILL_IR_DESIGN.md` under "Main Decision After
Round-4 QA". I do not disagree: admitting `64/4096/256` IR documents would
produce lowered blueprints that `SkillRegistry.install` and checkpoint restore
cannot re-parse under the runtime's `16/64/16` defaults, leaving accepted
Skills un-restorable. A runtime-wide cap increase must therefore change the
registry, checkpoint, and IR paths together; it is not a P2.1 narrowing.

As the independent test owner, I replaced only that test with
`test_condition_limits_are_tighten_only_and_default_caps_are_restorable`.
It requires:

- any field looser than `ConditionLimits()` defaults to be rejected at
  `parse_skill_ir` and at `compile_skill_ir` after `dataclasses.replace`;
- documents exactly at depth 16, 64 nodes, and 16 children under default
  limits to parse and compile, with one-over documents rejected; and
- each accepted lowered blueprint to install into an independent Gate 3
  runtime and restore through a saved checkpoint.

`test_oversized_integers_fail_closed_as_contract_errors` remains unchanged
for the separate pending integer-bound fix. Targeted execution of the
replacement test passed. Full focused verification is deferred to round 5,
when the parallel `skill_ir.py` fix is complete.
```

## Round-5 verification

**Verdict: ACCEPT**

Round 5 implements the two frozen decisions without reopening the prior
contract findings. `parse_skill_ir` now rejects any `ConditionLimits` field
above the runtime defaults, and `compile_skill_ir` revalidates that rule while
reparsing the canonical document. `_validate_json_shape` rejects non-boolean
integers outside `[-2**53, 2**53]` before numeric conversion, closing the
`OverflowError` boundary.

Independent probes confirmed:

- `bool` is still accepted as JSON shape and then rejected by semantic
  validators where a numeric value is required.
- `2**53` and `-2**53` are accepted; adjacent out-of-range integers in either
  direction fail with `GameplayContractError`.
- finite `1e300` floats remain legal and parse in mana, effect amount,
  budget, and resource-condition paths; negative mana still fails by the
  normal non-negative rule.
- limits equal to but not identical to `ConditionLimits()` are accepted and
  preserve the caller's object as `SkillIR.condition_limits`.
- looser limits forged with `dataclasses.replace` fail closed at compile with
  the tighten-only contract error.
- invalid limits including negative and boolean values fail during
  `ConditionLimits` construction.

The reinforced default boundaries match the runtime's `16/64/16` limits.
Exact-depth, exact-node, and exact-child documents parse and compile; one-over
documents are rejected. The independent replacement test also installs each
lowered boundary blueprint and round-trips it through checkpoint save/restore.
All prior determinism, authority, material-budget, lifecycle, forgery,
deep-input, and Player/NPC formal-runtime checks remain green.

### Round-5 evidence

Focused command included `test_skill_ir_review.py`, `test_skill_ir.py`,
`test_skill_ir_fixes.py`, `test_skill_ir_fix3.py`, `test_skill_ir_fix4.py`,
`test_skill_ir_fix5.py`, `test_p1_scenarios.py`, and
`test_gate4_registry_checkpoint.py`.

Result: **87 passed, 179 subtests passed**.

Evidence:

- `docs/agent_bootstrap/evidence/p2_ir_review_fix5verify.log`

Class counts for this addendum: **0 PRODUCT_DEFECT, 0 FIXTURE_ERROR, 1
SCOPE_NOTE**. The retained scope note is hostile `dict`/`list` subclasses that
override methods such as `items()` or `__len__()`; the contract remains JSON
input from `json.loads`, and ordinary subclasses are accepted.

Round-5 SHA-256:

```text
skill_ir.py
3d807d9f6d40dd6d631688824a21d295409ec94c01c72a4194cbc191364b61bb

owner test: tests/test_skill_ir.py
49807d367dd8bef2a49bd8881f0be0d5ba3ccee5eb0c68129f197d6212114d99

fix-owner test: tests/test_skill_ir_fixes.py
bc875a78a5764f96d352c229f92bb4b9c42567cf5e0e2c8962e8f509b023f930

round-3 owner test: tests/test_skill_ir_fix3.py
bef9390e0812426b90bfe15d2e1bc1e528305aa36ef16ddb4db86bc04d3d1521

round-4 owner test: tests/test_skill_ir_fix4.py
b2ab62da05086bfee18ecbca4a0da5fe46d1a12c456378ae2ef3daeaa8bf2afe

round-5 owner test: tests/test_skill_ir_fix5.py
1e34cc341c95535d6b8f2ef4e2d37c19268e4e2b5691dda8a387610d5003c915

independent review test: tests/test_skill_ir_review.py
3ecfe95dd9ed6f7103c66bd3e075766e1610d3e120fe27cda9e91c426aa517dc

round-5 focused evidence log
fe833cb6a997cab8bcf38b5f8128bc7e03bca83a174980f207ff491558086564
```
