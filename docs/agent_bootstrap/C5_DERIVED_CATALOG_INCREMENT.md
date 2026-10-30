# C5.2 Bounded Read-Only Area Derived Catalog Increment

Status: implementation and owner acceptance complete. Design remains frozen in
`C5_DERIVED_CATALOG_DESIGN.md`; independent review was not run in this turn.

## What changed

- Added `gameplay_v04/derived.py` with strict `DerivedSpec` parsing, canonical
  spec hashing, initial Component construction, pure Python initial values,
  and Core `state`-mode Law lowering.
- `Gate3Content` has a trailing default `derived_by_area`; existing 8-positional
  construction remains valid. `make_content(..., derived_by_area=None)`
  normalizes trusted bindings.
- `initialize_content_world` validates every referenced Field and writes
  `pmw_gameplay_derived = {"values": ..., "spec_hash": ...}` on the Area.
- `compile_content` appends Derived Laws. With no Derived specs the Law tuple
  is unchanged.
- `conditions.py` adds only the `derived` leaf, scoped to `current_area`.
- `actions.py` changes only `_condition_context`, exposing a copy of the Area's
  Derived values without changing legacy Area context when absent.

## Law shape and fixed point

Weighted sums lower to one `state` Law:

`clamp(add(bias, field.value * weight, ...), minimum, maximum)`

The mismatch guard compares `values.<id>` to `neq` that exact expression, and
the effect writes the same expression. Core therefore writes once and reaches
an exact fixed point on the next settle scan; there is no float oscillation or
settle-limit failure.

Threshold specs lower to two `state` Laws, one per `1.0`/`0.0` outcome. The
false branch uses the inverse comparator (`gt`/`lte`, `gte`/`lt`) rather than an
extra condition operator. Both guard `values.<id> != target`, so a settled
value is a no-op.

Both shapes bind `pmw_gameplay_area`, `pmw_gameplay_dynamics`, and
`pmw_gameplay_derived`, and require Area ID plus the canonical catalog
`spec_hash` before writing.

Canonical hash: SHA-256 over compact, key-sorted JSON of the Area's specs in
ascending ID order, with `allow_nan=False`.

## Acceptance evidence

New test:
`experiments/generative_mechanics/next_tracks_v06/gameplay_v04/tests/test_sandbox_derived_catalog.py`

Result: **11 passed, 16 subtests passed in 4.84s**.

The acceptance test uses the real formal chain from `test_p1_scenarios.py`:
parsed Skill, `make_content(derived_by_area=...)`, initialization, compile,
registry runtime, loadout, timed primary action, and real `advance_world_tick`.

Coverage:

- Paid `modify_field` + hand-computed weighted sum: initial `0.3`; Field
  `0.2 -> 0.4`; Derived `0.3 -> 0.7` in the traced Derived state commit; one
  native duration Tick gives Field `0.48`, Derived `0.86`; three further
  explicit Ticks assert the native recurrence.
- One parsed gated Skill for PLAYER and NPC: false rejection leaves state,
  mana, and spent Ticks byte-identical; after a real paid opener makes the
  Derived predicate true, both controllers pay exactly once.
- Threshold `0.0 -> 1.0 -> 0.0` across a real Field crossing using the native
  Tick after a paid action.
- Two Areas with different specs/derived IDs remain independent.
- Trace contains the Derived `mode: state` match and the reported Derived
  delta; component initialization is the only non-Law write.
- Strict parse rejections (shape, types, ranges, duplicates), unknown Field,
  duplicate IDs, and more than eight specs.
- Static scan: only Law IDs under `pmw.v04.derived.` write
  `pmw_gameplay_derived`; every such Law is `state` mode.
- Legacy no-Derived content compiles to the identical Law tuple and matching
  Action/Skill hashes.
- Registry checkpoint round trip preserves the exact Derived component and
  continues native Ticks without rebuilding the catalog.
- Thirty Ticks with weighted + threshold Derived values complete without
  settle-limit errors and leave `state_closure_known=True`.
- Condition leaf scope/type/missing behavior and unchanged legacy `field`
  evaluation.
- Existing 8-positional `Gate3Content(...)` remains valid.

## Focused regression results

All Python runs used the mandated `PYTHONPATH=src`,
`PYTHONDONTWRITEBYTECODE=1`, UTF-8 I/O, shared evidence temp, pycache prefix,
and `-p no:cacheprovider`.

| Group | Result |
|---|---|
| New acceptance test | 11 passed, 16 subtests |
| P1 + move + dynamics Action + drive source | 51 passed, 81 subtests |
| Gate1-Gate4 | 89 passed, 2 subtests |
| Gate5/Gate51/Gate52 | 83 passed, 20 subtests |
| All condition-named tests | 46 passed, 88 subtests |

Total focused: **280 passed, 207 subtests**, no failures.

## Deviations and notes

- No test was weakened. The paid-action acceptance fixture initially used a
  static Field; it was changed to a native-settling Field so the required
  "later Ticks follow" evidence is real.
- A duration-1 timed action executes one native Tick as part of publication.
  The immediate trace evidence is therefore the Field/derived `state:1` commit;
  externally observed post-action values already include that Tick. This is
  existing runtime behavior, not changed here.
- Threshold false lowering uses two Laws with inverse comparators because the
  design requires two guarded Laws and permits equivalent Core-valid
  formulation.
- Initial values are computed in Python once during trusted content
  initialization; all subsequent writes are Core state Laws.
- Independent QA/review and the full frozen suite were explicitly out of scope
  for this owner turn.
