# P3.1A Catalog / Public Context Independent Review

Status: **PRELIMINARY REJECT** for the current owner hashes, pending the
owner's arithmetic fix and a stable-hash rerun. This reviews only the offline
Catalog/Context increment. It does not claim the full P3 Gate.

Date: 2026-11-02

Branch / checkpoint: `feature/alpha-v02-seventh-night`, HEAD `747fdde`

## Scope

Reviewed:

- `gameplay_v04/skill_designer/catalog.py`
- `gameplay_v04/skill_designer/context.py`
- `gameplay_v04/skill_designer/__init__.py`
- `P3_SKILL_DESIGNER_DESIGN.md` (offline scope)
- `SKILL_IR_SPEC.md`
- The accepted parser, effect, condition, selector, material, and Skill IR
  sources used as semantic authority.

Explicitly out of scope:

- provider, live generation, generator pipeline, sandbox, registration
- WorldState serialization or hidden-registry behavior
- the full cross-module P3 Gate

## Current Hashes

Owner source:

```text
10272c5ca5c20a390571084d0c65c05bab85fb2991ad2ad50fb6f23116ddcf03  __init__.py
9cf8e2c885a40ed330e99fad756afe2e17e78bc946e385ff656c438ba2b08d27  catalog.py
81045b87b9b6bfc5c77ae2dfac6032c836910efbee9e8257bf324f221b091786  context.py
```

Review tests:

```text
d07e15caa214188fd08bed7e7406a4c591c25d5bb1f4514c89b2b0a692b3679d  test_skill_designer_catalog_context.py
a010236d07997b1ce7ba3397e9d7caaef910b42b7beac7c7fe68952a5e749f54  test_skill_designer_catalog_context_review.py
```

Snapshot:

```text
catalog_hash  496a2788abdd2ba2202a99e5770a8949547fe1f4cf247268c44ae97f5d723202
context_hash  c7c365678e3c800ab3887634cccd27589386708cd5a5661576229757c2dadd5e
```

The context hash above was generated with the review fixture material
`review_evidence_material` (10 budget points). It is evidence for this
snapshot, not a universal example hash.

## Findings

### P3QA-D001 - Aggregate material budget overflow leaks raw ValueError

Classification: **PRODUCT_DEFECT** (P1 for this public builder)

`_validated_materials` correctly accepts each material when its individual
trait budget is a finite positive float. `material_authority` then sums the
traits with ordinary float addition:

```text
1e308 + 1e308 -> inf
```

The public `build_generation_context` reaches `json.dumps(..., allow_nan=False)`
and leaks:

```text
builtins.ValueError: Out of range float values are not JSON compliant: inf
```

This is not a `GameplayContractError`. It also means the builder has not
explicitly rejected an unbounded aggregate authority before serialization.

Minimal repro (parser-legal materials, distinct IDs):

```python
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.materials import (
    parse_material,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.skill_designer import (
    build_generation_context,
)

materials = [
    parse_material({
        "id": f"p3_review_overflow_{index}",
        "tier": "rare",
        "region_rarity": "scarce",
        "traits": [{
            "id": "overflow_trait",
            "effect_kinds": ["damage"],
            "selectors": ["target_actor"],
            "budget_points": 1e308,
        }],
    })
    for index in range(2)
]

build_generation_context(
    profile="combat",
    materials=materials,
    complexity=1,
    public_known_rules=(),
    acquired_capabilities=(),
)
```

Observed exception:

```text
ValueError: Out of range float values are not JSON compliant: inf
```

Required behavior: reject the aggregate as a `GameplayContractError` at the
public builder boundary, before canonical JSON generation. A finite aggregate
budget must be used for authority; no `inf`, unbounded authority, or raw
serialization exception is acceptable.

Evidence:

- `docs/agent_bootstrap/evidence/p3_catalog_review_focused_red_20261102.log`
- `docs/agent_bootstrap/evidence/p3_catalog_review_owner_plus_review_20261102.log`
- `docs/agent_bootstrap/evidence/p3_catalog_review_selected_ir_20261102.log`
- `docs/agent_bootstrap/evidence/p3_catalog_review_current_hashes_20261102.json`

### Checked and passing - move_actor schema

The current `catalog.py` snapshot correctly exposes `move_actor` as exactly
the common keys:

```text
commitment, id, kind, target
```

It does not advertise `condition`, `attribute_terms`, or `targeting`.
Parser-legal mutations adding each field are rejected by the IR parser, and
the review test asserts this mismatch cannot return.

### Checked and passing - parser null flags are no longer on required fields

The earlier draft's required-field `null_allowed_by_parser` claims are not
present on the current stable catalog fields checked by the review. The test
suite guards the generator-facing schema against reintroducing unqualified
null tolerance on required effect fields.

The lower-level parser can still accept some explicit nulls (for example
`damage.amount = None`) and the IR can compile that result. This is a
pre-existing upstream semantic nuance, not a catalog promise in this hash.
It remains a scope/test coverage note rather than a P3.1A product defect:
the catalog's required-key representation must stay clear about what a
generator should emit.

### Checked and passing - coverage and source anchoring

- All 15 `EFFECT_KINDS` are represented.
- All seven `OPERATOR_KINDS` families are represented.
- All six `STATE_CLASS_KINDS` are represented.
- All five accepted selectors are represented.
- `on_use` and `on_event:damage_resolved` are supported.
- Reserved triggers/events and non-null `lifecycle.status_duration` are
  explicitly unavailable with `language_gap` semantics.
- Catalog source anchors are recomputed from the accepted source files.
- Parser-legal samples for every effect kind parse and compile.
- Mutation drift in effect schema, process optionality, and reserved-trigger
  source fails closed with `CatalogSourceError`.

### Checked and passing - context authority and public boundary

- Material authority is derived from revalidated material traits.
- Caller display text does not add effect kinds, selectors, or budget.
- Duplicate material IDs, malformed dataclasses, NaN/inf trait budgets, and
  invalid profiles/capabilities/bounds fail as `GameplayContractError`.
- Context and catalog snapshots return fresh JSON-native copies.
- Context does not serialize a WorldState or hidden registry payload.
- Existing raw and compiled Skills are revalidated before summary creation.
- Identity/name/origin/display/effect IDs are omitted from structural
  summaries while semantic references, selectors, conditions, templates,
  and magnitudes are retained.

### Scope note - no candidate code execution

The catalog advertises no arbitrary candidate execution and no arbitrary
world paths. The review tests check the public metadata claims. This is not a
formal proof over every future source change.

### Test gap / limitation - not a full parser fuzzer

The review suite is adversarial but does not exhaustively enumerate every
float boundary, every malformed dataclass subclass, or every possible Python
container alias. It uses independent parser-legal documents and mutations,
not another test suite's fixtures. The aggregate budget overflow is the
confirmed defect from the requested arithmetic probe.

## Test Results

Environment:

```text
PYTHONPATH=src
PYTHONDONTWRITEBYTECODE=1
PYTHONIOENCODING=utf-8
TEMP/TMP/TMPDIR=docs/agent_bootstrap/evidence/test_tmp
PYTHONPYCACHEPREFIX=docs/agent_bootstrap/evidence/test_tmp/pyc_p3catalog_qa
pytest -p no:cacheprovider
```

Review suite only:

```text
1 failed, 48 passed
```

Owner suite + review suite:

```text
1 failed, 94 passed
```

Review suite + selected Skill IR suites:

```text
1 failed, 99 passed, 131 subtests passed
```

The single failure in every matrix is `P3QA-D001`. No other review test
fails. Test counts are pytest counts, not a claim about the full repository.

## Verdict

**REJECT** for the current stable hashes until the aggregate authority budget
overflow is rejected as a `GameplayContractError` at the public context
builder boundary and the stable-hash rerun passes.

`PRODUCT_DEFECT=1`, `TEST_GAP=0`, `FIXTURE_ERROR=0`, `SCOPE_NOTE=3`.

The review's earlier false-positive fixture assertion was corrected before
the final saved run; it is not counted as a product issue.

## Final Disposition (Fix1 Stable Hash)

Status: **ACCEPT** for the offline P3.1A Catalog/Public Context increment on
the exact fix1 hashes below.

Owner supplied hashes were independently verified before the final run:

```text
10272c5ca5c20a390571084d0c65c05bab85fb2991ad2ad50fb6f23116ddcf03  __init__.py
0ad9aa4a70956e1bd30939a36d99cb15d2e45570b3df2e7606a0d32e76d6485c  catalog.py
adf06258e75cb12ad8989658cceedf6d7277bf5cbb3ba1f6517385a2a4700213  context.py
701b3b08b415b489dfba1893d87bd47188daa5d0ef0c3f55e5fedaabe5dbc351  owner test
```

The fix adds an immediate public-builder check after
`material_authority(validated_materials)`:

```text
aggregate material authority budget must be finite and positive
```

The original `1e308 + 1e308` repro now fails as a
`GameplayContractError`; the review test
`test_material_authority_overflow_is_fail_closed_at_public_builder` passes
without changing its expectation. No existing material, Skill IR, or runtime
source was edited for this fix.

### Final Fix1 Test Matrix

One invocation, with the required environment:

```text
PYTHONPATH=src
PYTHONDONTWRITEBYTECODE=1
PYTHONIOENCODING=utf-8
TEMP/TMP/TMPDIR=docs/agent_bootstrap/evidence/test_tmp
PYTHONPYCACHEPREFIX=docs/agent_bootstrap/evidence/test_tmp/pyc_p3catalog_qa
pytest -p no:cacheprovider
```

Selected files:

```text
tests/test_skill_designer_catalog_context.py
tests/test_skill_designer_catalog_context_review.py
tests/test_skill_ir.py
tests/test_skill_ir_fix3.py
tests/test_skill_ir_fix4.py
tests/test_skill_ir_fix5.py
tests/test_skill_ir_review.py
```

Result:

```text
161 passed, 163 subtests passed
```

This is 114 P3 owner/review tests plus 47 selected IR checkpoint tests.

The raw green log is preserved at:

```text
docs/agent_bootstrap/evidence/p3_catalog_review_final_fix1_20261102.log
```

All prior red logs and `p3_catalog_review_current_hashes_20261102.json` remain
unchanged and continue to describe the pre-fix snapshot.

### Frozen Source Integrity Check

The 317 recorded source hashes in
`p2_ir_frozen2_full_regression_meta.json` were rechecked after the fix:

```text
checked: 317
missing: 0
mismatch: 0
```

This is hash-integrity evidence only, not a rerun of the long frozen runtime
library. Main will perform the complementary cross-module regression and
integrity verification.

### Source-Derived vs Audited Manual Notes

The catalog distinguishes direct extraction from manually audited descriptions:

- `allowed_keys`, `required_keys`, options, parser limits, enums, operator and
  state mappings, and source anchors are derived from closed source literals
  and checked imports.
- Conditional effect rules, value constraints, composition notes, and
  selector/runtime-profile narrative are explicit static manifests labelled
  as manually audited/source-anchored where not directly representable as one
  AST literal.
- Static manifests are exercised by parser-legal samples and mutation tests,
  not presented as automatically extracted rules.

### Residual Scope

This ACCEPT covers only offline Catalog/Public Context behavior and its
selected checkpoint tests. It does not claim:

- provider, network, live generation, replay, pipeline, sandbox execution,
  registration, batches, or accounting
- full P3 Gate or Alpha acceptance
- a full long-library or all-runtime regression
- behavioral equivalence from structural summaries

Final review-owned hashes after this disposition:

```text
A010236D07997B1CE7BA3397E9D7CAAEF910B42B7BEAC7C7FE68952A5E749F54  review test
report hash: recorded in p3_catalog_review_final_fix1_20261102.json
1685EC5435F518EA4D7ABA4998BEB75234F1AE5BCBFC7101CC96F61A04E2DBA3  final_fix1 log
```

Final counts for this fix1 disposition:

```text
PRODUCT_DEFECT=0 open (1 confirmed and fixed)
TEST_GAP=0
FIXTURE_ERROR=0
SCOPE_NOTE=4
```

## Main Count And Acceptance Audit (2026-11-02)

The final pytest total **161 passed / 163 subtests** is correct. The report's
labelled 114 P3 + 47 IR breakdown is an arithmetic classification error:
Main --collect-only audit counts **47 owner + 49 independent review = 96 P3**
and **14 + 8 + 10 + 6 + 27 = 65 selected IR**, totaling 161. No assertions,
test selection or raw green log were changed. Collection evidence is not
claimed as another execution (`evidence/p3_catalog_main_collection_audit.json`).

Main separately imported the new public modules in the same process as Core
Engine, Observation, cost ledger, real P1-completion and Derived tests:
**230 passed / 35.84s**, unique cross-regression log/metadata. All previous
319 frozen Python files and 130 protected files are unchanged. New owner and
reviewer hashes match the independent final fix1 snapshot.

This accepts the OFFLINE increment only. The long all-project regression
1076/4257 remains the preceding P2 checkpoint result, not a rerun after this
new package. Provider, offline replay/pipeline, game generation, registration,
batch metrics and the P3 Gate are still unimplemented/pending. Catalog/hash
objects and displayed permissions are not authentication or capability grants;
future pipeline must rederive permissions from trusted material/runtime state.
