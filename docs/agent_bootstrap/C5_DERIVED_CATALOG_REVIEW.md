# C5.2 Independent Review: Read-Only Area Derived Catalog

Verdict: **ACCEPT**

The original review verdict was REJECT for C5.2-REV-01. After the fix owner
implemented the bounded observation/sandbox hydration correction, independent
fix verification passed and the final verdict was changed to ACCEPT. The
original finding and rejection evidence are preserved below.

Reviewed branch `feature/alpha-v02-seventh-night`, HEAD `db0fba2`, plus the
uncommitted C5.2 owner work. The review was finalized against the current
worktree after Main confirmed that the parallel P1 completion files and P2
design doc are authorized and outside the C5.2 review scope. The core Derived
catalog implementation matches the frozen contract and is mutation-sensitive
in independent tests. The original rejection was an integration defect at the
actor-safe observation/sandbox boundary: Derived-gated Skills could be
live-legal but were omitted from legal action enumeration, and sandbox
simulation rejected them because the reconstructed Area had no Derived state.

## Findings

### C5.2-REV-01 PRODUCT_DEFECT: Derived is absent from the actor-safe Area projection

`observation.py` projects an Area as `{"id", "fields"}` and never includes
`pmw_gameplay_derived`. `simulation.py` reconstructs the sandbox Area from that
document, so the sandbox has no Derived component. Its `_condition_context`
therefore exposes no Derived value, and `evaluate_condition` returns False for
every `derived` leaf.

As a consequence, `SandboxSimulator` and `LegalActionGenerator` disagree with
the live resolver for a Derived-gated Skill that is currently true. This is
not only a disclosure choice: the same absence breaks actor-safe preflight and
legal-action enumeration.

Minimal reproduction:

1. Parse a Skill with top-level
   `condition={"derived":{"subject":"current_area","key":"x","comparator":"gte","value":0.5}}`.
2. Initialize from `make_content(..., derived_by_area={AREA: (spec,)})`, compile,
   attach `MechanismRegistryRuntime`, equip the Skill, and drive `x` true
   through a real paid Field change.
3. `submit_timed_primary_action(...)` succeeds.
4. `ActorObservationBuilder().build(...)` produces an `area` mapping with no
   `"derived"` key.
5. `SandboxSimulator(...).simulate(observation, ActionRequest(...))` returns
   `legal=False`. With the Skill explicitly disclosed, the rejection is
   `action condition is not satisfied`; the Skill cannot appear in
   `LegalActionGenerator` output.

Without disclosure, observation can instead reject the request earlier as
`unknown registered action`. That earlier failure is a separate loadout-hash
projection behavior; the independent test uses explicit disclosure so the
C5.2-specific Derived precondition failure is isolated rather than masked.

The independent test
`test_observation_omits_derived_and_sandbox_gate_cannot_be_preflighted` covers
this behavior. The existing `test_gate4_ai_simulation.py`,
`test_gate4_ai_observation.py`, and `test_gate5_ai_contract.py` pass because
they use fixtures without Derived conditions; they do not exercise this
boundary.

Recommendation: project a read-only, actor-safe `derived` value map in the Area
observation and reconstruct it as `pmw_gameplay_derived` in `simulation.py`
(or an equally explicit trusted sandbox hydration path), then add a
Derived-gated legal-action/sandbox test. This is outside the owner's permitted
write set and was not fixed by the reviewer.

Status: FIXED. See "REV-01 fix verification" below.

### C5.2-REV-02 SCOPE_NOTE: Missing Derived key is intentionally False

An absent `current_area.derived[key]` evaluates False. This is consistent with
the frozen design's explicit missing -> False convention and is acceptable for
the read-only catalog: it fails closed for unknown Derived IDs and for Areas
without the component.

### C5.2-REV-03 SCOPE_NOTE: No independent duplicate of owner tests

The owner acceptance test contains the required formal-chain coverage, but it
is not a substitute for an independent reviewer. The new review test uses its
own weights, bias, clamp endpoints, comparator boundary matrix, parser cases,
checkpoint fixture, and mutation checks. It also imports unchanged helpers from
the accepted `test_p1_scenarios.py` and never edits that file.

## Independent test coverage

`experiments/generative_mechanics/next_tracks_v06/gameplay_v04/tests/test_sandbox_derived_catalog_review.py`

- Weighted sum with independent formula
  `0.75 + 3.5*humidity - 2.25*temperature`, clamp `[-0.5, 1.25]`; asserts both
  max and min clamp values through native Ticks.
- Threshold `gt`, `gte`, `lt`, `lte` at exact equality (0.0, 1.0, 0.0, 1.0).
- Same parsed Skill gates PLAYER and NPC: false rejection leaves WorldState,
  Mana, and spent Ticks unchanged; a real paid Field change makes it true; both
  then pay exactly the declared cost/time.
- Top-level condition evaluated before Mana cost (fixture leaves exactly enough
  Mana, so a post-cost check would fail).
- Parser rejects unknown key, wrong subject (`self`/`target_actor`), bool/NaN/
  infinity, invalid comparator, and extra fields; missing Derived key is False.
- Mutation checks: in-test removal of Derived Laws leaves the value stale;
  inverse comparator mapping is asserted independently; a deliberately loose
  range exposes raw values that prove the tight clamp is required.
- Registry checkpoint round trip preserves values and continues native updates.
- Legacy `make_content` without `derived_by_area` versus explicit `None` gives
  byte-identical Laws and equal Action/Skill hashes.
- Static scan proves only `pmw.v04.derived.*` state Laws write the Derived
  component.
- Observation/sandbox parity is now a requirement: the current-Area Derived
  map is projected, the legacy document is byte-identical, sandbox and live
  decisions agree for true and false on PLAYER and NPC, and non-finite values
  are rejected.

## Commands and evidence

All commands used the mandated evidence temp directory, pycache prefix,
`PYTHONPATH=src`, `PYTHONDONTWRITEBYTECODE=1`, UTF-8 I/O, and
`-p no:cacheprovider`.

Focused review test result on the current worktree:

`10 passed, 6 subtests passed in 5.80s`

Mandated combined regression on the current worktree:

`75 passed, 69 subtests passed in 24.62s`

Files in that run:

- `test_sandbox_derived_catalog_review.py`
- `test_sandbox_derived_catalog.py`
- `test_p1_scenarios.py`
- `test_sandbox_move_actor.py`
- `test_sandbox_move_actor_review.py`
- `test_gate2_actions.py`
- `test_gate4_registry_checkpoint.py`

Log: `docs/agent_bootstrap/evidence/c5_derived_review_focused.log`

Additional targeted observation/simulation regression:

`12 passed in 36.21s` for `test_gate4_ai_simulation.py`,
`test_gate4_ai_observation.py`, and `test_gate5_ai_contract.py`.

The in-progress `test_p1_scenarios_completion.py` was intentionally excluded
from the mandated regression as directed by Main.

## SHA256 reviewed

- `test_sandbox_derived_catalog_review.py`:
  `AB7A9EBE6AC40466774BE4D19D8A4E55A50F97FE2ABA3DA163193130B4F35424`
- `derived.py`:
  `BCC9DE894AAA789EB7C4CBA76072C56AC94D8D1D26AC62378A5E352A4D366325`
- `content_compiler.py`:
  `366AFBFDE51F6B6044A9C1DC9789C509202BA4E326352D6BB24231115AD2E821`
- `conditions.py`:
  `A750139BBAD3547D58FD3E8E258FC10A1E73A5C7A51ACC78FC120DCBCD7DD373`
- `actions.py`:
  `8DF813143DD4F70921F96D300CA0945157FD2AE465D42C56AE56A947DEF1E91A`

No production file was edited, and no existing test was edited.

## REV-01 fix verification

The defect was fixed in `observation.py` and `simulation.py`, not by changing
the production behavior reviewed in the original increment. The fix owner's
test is `test_sandbox_derived_observation.py`; this reviewer independently
inspected the diff and added requirement assertions to the review test.

The original review method
`test_observation_omits_derived_and_sandbox_gate_cannot_be_preflighted`
asserted the defect itself and was correctly failing after the fix. It was
replaced, as policy requires, with
`test_observation_projects_derived_and_sandbox_matches_live`. The replacement
asserts the corrected contract and does not freeze the old behavior.

### Independent fix checks

- Current-Area `derived` is a sorted, finite ID-to-float map and is the only
  new field in `area`.
- Legacy Observation without a Derived component remains
  `{"id": ..., "fields": ...}` and its canonical SHA-256 is unchanged:
  `766cf7daed2e0346b066081ef14630b99c26da1bf064524d9e604f893a36f722`;
  revision token:
  `d20da7f1a84f076eaab75b66a0c8571a83851fb68d2808f3169b224dd19b1bd6`.
- `spec_hash`, `pmw_gameplay_derived`, and Derived Law IDs do not appear in
  the Observation JSON. Sandbox hydration invents no `spec_hash`.
- Live NaN, +infinity, and -infinity values are rejected with
  `GameplayContractError`; a tampered projected NaN is also rejected by
  `SandboxSimulator._build`.
- For both PLAYER and NPC, a false Derived gate is rejected by live resolution,
  sandbox simulation, and legal-action enumeration. After a real paid Field
  change makes the gate true, live submission succeeds, sandbox simulation is
  legal, and `LegalActionGenerator` offers the Skill, with matching declared
  cost/time.
- The other Area in `scoped_objects` does not expose Derived state.

### Fix verification runs

The review test alone:

`10 passed, 13 subtests passed in 9.21s`

Requested combined run:

`43 passed, 40 subtests passed in 62.50s (0:01:02)`

Files in the combined run:

- `test_sandbox_derived_catalog_review.py`
- `test_sandbox_derived_catalog.py`
- `test_sandbox_derived_observation.py`
- `test_gate4_ai_observation.py`
- `test_gate4_ai_simulation.py`
- `test_gate4_ai_planner.py`
- `test_gate5_ai_contract.py`

Log: `docs/agent_bootstrap/evidence/c5_derived_review_fixverify.log`

### Post-fix SHA256 reviewed

- `test_sandbox_derived_catalog_review.py`:
  `92729306DE3C77417D8469B058A0C2142E816D755FAF4CBC87A567AB31F64650`
- `observation.py`:
  `6F18EB694B9DF5CEFDB4A2849D2365FC9930205EC77C2AB510DB943FBDC75312`
- `simulation.py`:
  `A21A42A7B278D7F09750EC5FC7A07234F1EF33F4A0139784D73812B1597F18BD`
- `derived.py`:
  `BCC9DE894AAA789EB7C4CBA76072C56AC94D8D1D26AC62378A5E352A4D366325`
- `content_compiler.py`:
  `366AFBFDE51F6B6044A9C1DC9789C509202BA4E326352D6BB24231115AD2E821`
- `conditions.py`:
  `A750139BBAD3547D58FD3E8E258FC10A1E73A5C7A51ACC78FC120DCBCD7DD373`
- `actions.py`:
  `8DF813143DD4F70921F96D300CA0945157FD2AE465D42C56AE56A947DEF1E91A`

Final classification of C5.2-REV-01: **PRODUCT_DEFECT, FIXED AND VERIFIED**.
No unresolved product defect was found in the fix.
