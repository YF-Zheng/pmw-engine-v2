# C5.2 Bounded Read-Only Area Derived Catalog

Architecture by Main. Target: P1 scenario 9 ("Derived state updates correctly
when its underlying state changes"), classified PARTIAL because only Field
diagnostics exist and there is no trusted, candidate-readable Derived value.
Contract audit: Derived must be a World-Law output; generated content may read
but never write it. This slice adds trusted per-Area Derived values computed by
Core `state`-mode Laws (re-settled by the Engine after every commit), stored in
one dedicated component, and readable through one new typed condition leaf.
No Alpha/UI/playtest claim, no generic expression language, no generation.

## Trusted Spec (new module `gameplay_v04/derived.py`)

`DerivedSpec` (frozen): `id` (lowercase `[a-z][a-z0-9_]{1,47}`), `kind` in
{`weighted_sum`, `threshold`}, plus:
- `weighted_sum`: `terms` = 1..8 tuples `(field_id, weight)` with finite
  weight in [-8, 8], distinct field ids; `bias` finite in [-8, 8];
  `minimum` < `maximum`, both finite in [-1000, 1000]. Value =
  clamp(bias + sum(weight * field.value), minimum, maximum).
- `threshold`: one `field_id`, comparator in {gt,gte,lt,lte}, finite
  `value`. Value = 1.0 when the comparison holds, else 0.0 (numeric so the
  existing numeric condition comparators apply).
`parse_derived_spec(raw)` accepts exactly these keys (strict types, no bool
for numbers, unknown keys reject). Max 8 specs per Area; ids unique per Area.
Trusted world/content authoring only; Skill/candidate JSON cannot declare
Derived specs.

Component `pmw_gameplay_derived` on the Area entity:
`{"values": {derived_id: float}, "spec_hash": <sha256 of canonical specs>}`.

## Content Integration

- `Gate3Content` gains trailing field `derived_by_area: Mapping[str,
  tuple[DerivedSpec, ...]] = MappingProxyType({})` (trailing default so all
  existing positional constructions keep working). `make_content` gains
  keyword `derived_by_area=None`.
- `initialize_content_world` validates Area exists, every referenced field
  exists on that Area, and writes the component with values computed from the
  current Field values (pure Python initial computation, same formula).
- `compile_content` appends `build_derived_laws(derived_by_area)`.
- Laws: per (area, spec) one `state` Law, binding `area` entity requiring
  `pmw_gameplay_area`, `pmw_gameplay_dynamics`, `pmw_gameplay_derived`, with
  `$area.id == area_id`, `spec_hash` equality, and a mismatch guard
  (`values.<id>` neq computed expression) so settling terminates; effect
  `set $area.pmw_gameplay_derived.values.<id>` to the computed value
  expression using Core `add/mul/clamp` value ops (weighted_sum) or two
  guarded laws for 1.0/0.0 (threshold). Use only Core-validated Law grammar
  (`parse_law`/`validate_laws`); if a value expression is not allowed as a
  comparator operand, use an equivalent Core-valid formulation and document it.
- Precision: guard must not oscillate on floating rounding; the Law writes
  exactly the expression the guard compares, so a fixed point is reached in
  one step. Verify no settle-limit error over many Ticks.

## Read Path

- `conditions.py`: new leaf `derived` with fields exactly
  `subject` (only `current_area`), `key` (derived id), `comparator`
  (eq/neq/gt/gte/lt/lte), `value` (finite number). Counts toward the
  existing ConditionLimits. Existing leaves, parse results and evaluator
  branches unchanged. Evaluation reads
  `context["current_area"]["derived"][key]`; missing -> False (same
  convention as `field`).
- `actions.py` `_condition_context`: include `"derived": dict(values)` in
  the area mapping when the component exists. Nothing else in actions.py.
  Existing hooks reuse `_condition_context` automatically.
- No Effect can target the component: verify all compiled Laws other than
  the Derived Laws never write `pmw_gameplay_derived` (static scan test).

## Proposed Write Ownership

Owner (DeepSeek Flash): NEW `gameplay_v04/derived.py`, `content_compiler.py`,
`conditions.py`, `actions.py` (only `_condition_context`), NEW
`gameplay_v04/tests/test_sandbox_derived_catalog.py`,
`docs/agent_bootstrap/C5_DERIVED_CATALOG_INCREMENT.md`, evidence
`c5_derived_owner*`. Forbidden: Engine `src/`, Alpha, Core, old tests,
observation.py, checkpoint.py, registry.py, effects.py, skills.py.
Independent QA: NEW `test_sandbox_derived_catalog_review.py`,
`C5_DERIVED_CATALOG_REVIEW.md`, evidence `c5_derived_review*`.

## Required Real Acceptance Evidence

- Formal chain (parsed Skill, make_content(derived_by_area=...), compile,
  registry runtime, change_loadout, submit_timed_primary_action, real
  advance_world_tick): a paid `modify_field` changes humidity and the Derived
  value equals the hand-computed formula immediately after publication; later
  Ticks move the Field via native dynamics and Derived follows each Tick.
- Same parsed Skill with top-level `derived` condition gates for PLAYER and
  NPC (false -> atomic rejection, no cost/time; true -> pays once).
- Threshold kind flips 0.0 -> 1.0 -> 0.0 across a real Field crossing.
- Two Areas with different specs remain independent.
- Engine trace shows the Derived state Law (`mode: state`) produced the
  delta; no Python mutation after initialization.
- Strict parse rejections; unknown field; duplicate ids; >8 specs; no Law
  besides Derived writes the component; legacy content with no Derived specs
  compiles to the identical Law set and identical Action/Skill hashes.
- Save/load (`checkpoint` round trip of the WorldState via existing helpers)
  continues with identical Derived values; no catalog rebuild needed.
- All old tests, Core 23, Alpha 13 byte-identical; full frozen suite;
  independent review before checkpoint.
