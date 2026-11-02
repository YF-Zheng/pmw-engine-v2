# P3.1A Offline Catalog + Public Context Increment

Status: implemented and owner-tested on 2026-11-02 from P2 Gate checkpoint
`747fdde`. This increment is offline only. It makes no live provider/API call,
does not register a Skill, and does not claim the P3 Gate.

## Scope

New package: `gameplay_v04/skill_designer/`.

- `catalog.py` builds a canonical `pmw-mechanism-catalog-v1` snapshot from the
  accepted IR/parser source. It covers all 15 `EFFECT_KINDS`, all seven
  `OPERATOR_KINDS`, all six `STATE_CLASS_KINDS`, exact `parse_effect`
  allow/require key sets, condition grammar and defaults, five selectors,
  executable and reserved triggers, lifecycle gaps, composition rules,
  numeric constraints, and source-anchored runtime caps.
- `context.py` builds a bounded public `pmw-generation-context-v1` document
  from an explicit closed profile, validated material definitions, a
  complexity tier, caller-allowlisted public facts/capabilities, and optional
  already-validated Skill structures.

No existing production, fixture, reference-library, test, ledger, manifest,
or registry file is changed by this increment.

## Public API

```python
build_mechanism_catalog() -> MechanismCatalog

build_generation_context(
    *,
    profile: str,
    materials: Sequence[MaterialDefinition],
    complexity: int,
    public_known_rules: Sequence[str],
    acquired_capabilities: Sequence[str],
    existing_skills: Sequence[ExistingSkillInput] = (),
) -> GenerationContext

ExistingSkillInput.from_compiled(compiled: CompiledSkillIR) -> ExistingSkillInput
ExistingSkillInput.from_raw(
    raw: Any,
    *,
    statuses: Mapping[str, Any],
    authority: MaterialAuthority,
) -> ExistingSkillInput
```

`MechanismCatalog` exposes `.version`, `.ir_protocol`, `.catalog_hash`
(alias `.hash`), `.canonical_json`, and `.to_dict()`.

`GenerationContext` exposes `.context_hash` (alias `.hash`),
`.catalog_hash`, `.canonical_json`, `.to_dict()`, and
`.structural_summary(skill)`.

All `to_dict()` and `structural_summary()` results are fresh JSON-native
objects. Mutating a returned object cannot change either canonical snapshot
or hash.

## Trusted Context Inputs

- `profile` is one of the closed reference profiles:
  `field`, `stock`, `process`, `relation`, `combat`, `travel`, `derived`.
- `materials` is a non-empty sequence of `MaterialDefinition` values. Each
  value is converted through its known dataclass fields, revalidated by
  `parse_material`, and bounded to 16 materials/16 traits each. Duplicate IDs
  are rejected.
- `complexity` is a strict integer in `[1, 3]`; booleans and floats are
  rejected.
- `public_known_rules` is an explicit caller allowlist, at most 32 unique
  non-empty strings of at most 512 characters. It is not a `WorldState` or
  registry serialization.
- `acquired_capabilities` is a bounded caller allowlist, at most 32 unique
  capability names of at most 128 characters.
- `existing_skills` is at most 16 explicit `ExistingSkillInput` wrappers. A
  bare mapping is rejected.

`MaterialAuthority` is derived only from the validated material traits.
Candidate tags, display text, raw permissions, names, or descriptions never
grant authority.

The aggregate authority budget is checked immediately after derivation and
must be finite and positive. Individually finite material budgets that sum to
infinity are rejected with `GameplayContractError` before canonical JSON
serialization; no unbounded authority is accepted (P3QA-D001).

## Structural Summaries

Existing Skill summaries deliberately omit Skill/entry/effect identity labels,
names, descriptions, display data, origin/provenance, and tags.

They preserve semantic references that can change a mechanism, including
effect kind, operator/state class, selector and `relation_type`, resource,
field/trait/status/process/drive/relation IDs, trigger/event, condition
operator/leaf keys/values, attribute terms, costs, budget, and numeric
magnitudes. Condition `derived` is marked as the read-only `Derived` input
class.

The summary says `summary_kind: semantic_structure_not_behavioral_identity`
and `behavioral_identity_claimed: false`. It is suitable for bounded
structural repetition context, not behavioural dedupe or runtime-equivalence
claims.

## Catalog Honesty and Fail-Closed Behavior

The catalog extracts parser literals with `ast` and checked container
operations; it does not `eval`/`exec` source or candidate data. If a source
shape or supported constant/literal changes, catalog construction raises
`CatalogSourceError` rather than silently inventing a rule.

Static manifests for conditional effect rules, post-parse value constraints,
and composition rules are explicitly marked source-anchored but not direct
single-literal extraction. `provenance` records which fields are AST-literal
extraction versus a static manifest checked against parser examples, so prose
does not imply invented automation. A source/schema parity test catches drift.

Null-sensitive scalar notes are not presented as automatic extraction. Their
`null_scope` records both parser acceptance and actual Skill IR ingress
acceptance, plus a static owner-review note. `move_actor` exposes only its
common required keys and strict `adjacent_area`/`required` target rule; it
does not advertise optional condition, targeting, or attribute-term values.

A missing required scalar key is still rejected by the underlying closed
effect schema; where parser acceptance of an explicit null is preserved by
IR ingress, the `null_scope.ir_ingress_note` states its runtime meaning and
does not present it as an omitted-field option.

Runtime profile-specific IDs are not globally enumerated. The catalog states
that parser maxima may be absent for profile-bound values and that Process,
Drive, and Relation limits are enforced by trusted runtime profiles.

Supported language is exactly the accepted subset:

- triggers: `on_use` and `on_event:damage_resolved`
- reserved lifecycle/event/trigger forms: unsupported with `language_gap`
- non-null `lifecycle.status_duration`: unsupported with `language_gap`
- selectors: `self`, `target_actor`, `current_area`, `linked_object`,
  `adjacent_area`
- `linked_object` requires `relation_type`
- non-`move_actor` effects require exactly one resolved target
- `move_actor` requires the strict adjacent target and one requested
  destination Area

## Deliberate Limitations

- No provider, generator, pipeline, sandbox, registration, or live batch is
  implemented here.
- No benchmark or P3 Gate claim is made by Catalog + Context tests alone.
- Public context contains an explicit allowlist, not a full world snapshot.
- Complexity tier is carried as context; this increment does not enforce its
  quality meaning.
- Structural identity is not behavioural identity.
- Status IDs are not globally enumerated: legal `apply_status` IDs depend on
  the trusted status registry supplied at parse/compile time.
