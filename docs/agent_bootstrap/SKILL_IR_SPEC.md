# Skill IR v1: Requirements And Status

Latest status (2026-11-02): P2.1 compiler accepted at `cb536944b84d9b56e69176c6bab79f20399220d3`.
P2.2 reference-library Gate accepted on 2026-11-02 for the supported subset. The original requirements
below are retained as design intent, NOT a list of implemented features.

Existing v06 `MechanismSpec` supports an operator sequence and catalog scope,
but not the complete player action contract. Existing Gameplay `SkillBlueprint`
supports costs/materials/conditions/registry hashes but restricts effects and
uses one trigger per blueprint. Neither alone satisfies the new contract.

The v1 IR must join their capabilities WITHOUT accepting arbitrary code or
raw PMW Law bundles from a model. Required groups: Identity, Origin,
Capability, Targeting, Costs, Triggers, Conditions, Effects, Lifecycle,
Limits, Display. The canonical document includes IR/catalog versions and a
content hash; stored compiled definitions are validated on load without API.

Selectors include self, selected actor/object, current area, and bounded
matching actor/object/process/relation sets. Cross-area scope requires trusted
capabilities; a model-authored area ID grants no authority. Conditions are pure
typed comparisons/ranges/trait/discrete/process/relation/event matches with
AND/OR/NOT and bounded continuity; query and expression depth are limited.

Triggers include on_use/on_tick/on_event/on_expire and condition edges. Each
event has a causal parent and deduplication key; global per-tick and per-root
budgets prevent passive recursion. Ordered/dependency-linked effects lower to
the seven trusted operators. All costs and world steps are settled in the same
staged Gameplay transaction, never in a provider request.

Acceptance is thirty reference skills through one compiler/runtime plus
permission, budget, expiry, cross-area, save/load and replay tests. No such
acceptance is claimed by this draft.

## Implemented P2.1 Language

Public entry points: `gameplay_v04.skill_ir.parse_skill_ir(raw, statuses,
authority, condition_limits=...)` and `compile_skill_ir(parsed)`.
Protocol is `pmw-skill-ir-v1`. The exact closed-key schema and operator
mapping are documented in `P2_SKILL_IR_DESIGN.md`; code is the semantic
authority. Compiling re-parses canonical JSON with trusted authority before
lowering, so editable dataclass fields and a matching candidate hash cannot
bypass validation.

- Identity, Origin, Capability, Targeting, Costs, Entries, Lifecycle, Limits,
  Display are required closed groups. Origins are reference/generated/authored.
  Canonical JSON and SHA-256 link to all lowered blueprint identities/hashes.
- One to four entries; at most one `on_use`, with the document Mana/Tick cost.
  `on_event:damage_resolved` entries lower to separately equipped passives.
  Each lower-level Skill keeps the existing registry/loadout authorization.
- Conditions share a document budget, including effect predicates and null
  nodes. Defaults depth 16 / nodes 64 / children 16; the optional IR limits
  can only tighten them. Candidate JSON cannot raise trusted limits.
- Material authority supplies effect-kind, selector and budget permissions.
  Entry budgets are summed across the document, including passive overhead;
  capability/display prose does not grant authority.
- All seven operator families map to existing closed effects; all six state
  classes are represented. Derived is read-only condition input, not a Skill
  write. Legal selectors: self, target_actor, current_area, adjacent_area,
  linked_object, subject to actual scope resolution and material authority.
- Actions use the accepted Engine and staged Gameplay transaction. Passive
  actions have their own traces and share the bounded causal root queue;
  they do not introduce an extra paid Tick or another world clock.
- JSON ingress is bounded before recursive copying: container depth 128,
  values 65536, strings/keys 4096, safe integer magnitude at most 2**53.
  Nonfinite numbers and non-JSON objects fail closed. Hostile Python
  container subclasses are outside the plain-JSON threat model.

## Explicit Language Gaps

`on_tick`, `on_expire`, transition/condition-edge triggers, and other
`on_event` families are reserved, rejected as `language_gap`; no generic
event-trigger support is claimed. Non-null `lifecycle.status_duration` is
also rejected. Supported lifecycles are actual per-effect durations and
registry status definitions; owner_turn units are not World Ticks.

Selectors do not offer arbitrary bounded object queries or multi-endpoint
selection policies. `linked_object` effects require one resolved target.
Process modifications require an already-running authorized local Process;
start-plus-modify in a single entry is not supported. Movement composites
obey the existing whitelist; no arbitrary dependency graph is implemented.

## Acceptance Evidence

P2.1 independent QA accepted round 5: 87 passed / 179 subtests. Frozen
regression `p2_ir_frozen2`: 1065 passed / 4103 subtests, 317 immutable Python
hashes. This is compiler evidence, not full P2 acceptance or Alpha playtest.
The 40 reference IR documents and independent P2.2 tests already exist, but
the interrupted QA has been completed; full frozen regression and accounting passed.
See P2_REFERENCE_LIBRARY_REVIEW.md and evidence/p2_lib_main_acceptance.json.


## P3.1A Offline Catalog / Public Context Accepted (2026-11-02)

NEW skill_designer/catalog.py + context.py: full supported mechanism catalog
(15 Effect kinds / 7 Operators / 6 states / 5 selectors), exact closed-key
schemas, pure conditions, supported vs reserved triggers/lifecycle, runtime
profile boundaries and canonical hashes. Source-literal extraction is
fail-closed; manually audited value/composition descriptions are explicitly
labelled, not advertised as automatic extraction.

Public context takes validated MaterialDefinitions and an explicit public
facts/capability allowlist, derives its authority from actual material traits,
limits list/string complexity, and defensively serializes canonical copies.
Existing Skill structures are recompiled, omit identity/display/provenance,
and retain semantic references/conditions/magnitudes. Structural hash is not
behavioral equivalence; displayed authority/hash is not a capability grant.
No WorldState or hidden registry dump is passed to a model.

Independent QA James: final ACCEPT; 1 confirmed product defect fixed, 0 open
(product P3QA-D001: two finite 1e308 budgets overflowed to infinity; public
builder now rejects nonfinite/nonpositive aggregate with GameplayContractError).
The original failing expectation and red logs remain unchanged. Exact final
source hashes verified. QA combined **161 passed / 163 subtests** = 47 owner
+ 49 review + 65 selected IR. Main corrected the review's incorrect subgroup
labels via collection audit without changing tests. See
P3_CATALOG_CONTEXT_REVIEW.md and evidence/p3_catalog_main_acceptance.json.

Main complementary cross-module regression imported new public modules in
the same process as Core Engine / Observation / accounting / P1 completion /
Derived tests: **230 passed /35.84s**. All 319 previous frozen Python sources
and 130 protected files remain byte-identical. The preceding full-project
P2 regression 1076/4257 is not claimed as a new full run after this package.
A manually authored offline demo preserves authority at exactly 2 Effects /
2 scopes /budget12, despite the full catalog; no provider calls or generated
skills (`evidence/p3_catalog_main_public_example.json`).

Accounting p3_1a cutoff 2026-11-02T03:29:44.298Z: subset USD 2.05592649 / CNY 13.70562835 (already in cumulative).
Project reference CNY 494.57, safety CNY 623.19/3000, Unknown 0/malformed 0.
P3 workers are tagged P3; the existing resumed main turn remains shared P2
control accounting. Task ordinal boundaries allocate observed shared overhead,
not exact semantic per-stage attribution. Bootstrap remains separate.

P3 Gate is STILL OPEN: no provider/replay/pipeline/sandbox/registration/batch
or new Alpha UI. Next bounded task: offline ReplayProvider + strict bounded
candidate decode/normalize/parse/compile, with compiled-but-unregistered output
and no skipped sandbox/register stage labelled accepted; then actual Engine
sandbox/behavior signatures, then reviewed live usage path/pilot/batches.
