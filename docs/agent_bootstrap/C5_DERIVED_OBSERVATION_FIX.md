# C5.2-REV-01 Derived Observation Fix

Status: implemented as the frozen minimal fix from `C5_DERIVED_CATALOG_REVIEW.md`.

## Projection contract

`ActorObservationBuilder` adds `area.derived` only when the current Area has
`pmw_gameplay_derived` with a Mapping-valued `values` field. The projection is a
sorted ID-to-float map containing finite numbers only. Invalid or non-finite
values raise `GameplayContractError`.

The projection deliberately excludes `spec_hash`, Derived Law IDs, and the
`pmw_gameplay_derived` component name. Other Areas in `scoped_objects` remain
unchanged and do not expose Derived state.

When the component is absent, the Area document remains exactly
`{"id", "fields"}`. This preserves the legacy Observation document JSON,
revision token, and canonical SHA-256 for every world without Derived bindings.

## Sandbox hydration

`SandboxSimulator._build` reconstructs `pmw_gameplay_derived` on the current
Area only when the Observation contains `area.derived`. It accepts only a
Mapping of non-empty string IDs to finite numbers and stores:

```json
{"values": {"comfort": 0.7}}
```

No `spec_hash` is invented or copied into the sandbox.

## Scope note

Sandbox simulation does not recompute Derived values after simulated Field
writes. The actor-safe projection contains no Derived Laws, so the hydrated
value map is a read-only snapshot for condition preflight and legal-action
enumeration. The next sandbox Observation retains that snapshot even if a
simulated action changes its source Fields. Live execution continues to
recompute through the authoritative Derived state Laws.

Adding Derived Laws to sandbox projections is outside this fix. The sole change
is trusted hydration of already-projected values.

## Verification

The new test chain reuses the accepted formal Derived helpers and covers:

- exact current-Area value projection without `spec_hash`, Law IDs, or the
  component name;
- no Derived projection for other Areas in `scoped_objects`;
- false-gate rejection and true-gate acceptance for PLAYER and NPC across live
  resolution, sandbox preflight, and legal-action enumeration;
- declared sandbox cost, live cost/time, and stale-by-design sandbox Derived
  values after simulated Field writes;
- a pre-fix legacy Observation SHA-256/revision-token golden;
- rejection of malformed and non-finite projected values.

Final owner runs:

- New derived-observation test: 5 tests passed, 11 subtests passed.
- Accepted Derived catalog: 11 tests passed, 16 subtests passed.
- Required observation/simulation/gate4/AI/P1 regression: 54 tests passed,
  33 subtests passed.
- Legacy observation-focused rerun: 13 tests passed.
- Independent QA defect-assertion method: 1 expected failure at
  `assertNotIn("derived", document["area"])`.

The independent QA review method
`test_observation_omits_derived_and_sandbox_gate_cannot_be_preflighted` asserts
the defect itself. It passed before this fix and is expected to fail afterward;
it is read-only evidence and was not edited.
