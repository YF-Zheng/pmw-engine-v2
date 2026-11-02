# P2.2 Reference Library Increment

## Scope

P2.2 adds a reference-only library and conformance harness over the accepted
Gameplay v0.4 runtime and the P2.1 compiler:

- `gameplay_v04/reference_skills/library.json`: 40 `pmw-skill-ir-v1`
  documents, all with `origin.source = "reference"` and exactly one
  `fixture:<profile>` display tag.
- `gameplay_v04/reference_skills/fixtures.py`: trusted time-zero worlds,
  materials, and Process/Drive/Relation controllers for the closed profiles
  `field`, `stock`, `process`, `relation`, `combat`, `travel`, and `derived`.
- `gameplay_v04/tests/test_p2_reference_library.py`: one compiler/runtime
  chain for every document and the seven required test categories.
- `docs/agent_bootstrap/evidence/p2_reference_coverage_matrix.json`: generated
  per-Skill profile, Operator, state-class, selector, Effect, trigger, and
  category results.

Fixtures select only by the closed profile. They contain no library Skill ID
and do not branch on Skill semantics. The test statically scans the fixture
source against every library ID.

## Library

The 40 documents are split across the trusted profiles as follows:

| Profile | Skills |
|---|---:|
| field | 8 |
| stock | 4 |
| process | 5 |
| relation | 2 |
| combat | 9 |
| travel | 3 |
| derived | 9 |

Every runnable document is parsed by `parse_skill_ir`, lowered by
`compile_skill_ir`, and built through:

`make_content -> initialize_content_world -> compile_content ->
build_content_session -> MechanismRegistryRuntime.from_compiled_content`.

The test then equips the lowered blueprint through the accepted loadout API
and resolves the generated `<skill_id>__active` action through
`submit_timed_primary_action`.

## Frozen Category Minimums

The following counts are mechanically asserted from compiler/parser outputs,
not inferred from display prose:

| Category | Minimum | Actual |
|---|---:|---:|
| instant Field change (`modify_field`) | 3 | 7 |
| attractor investment (`modify_attractor`) | 2 | 4 |
| recovery-rate change (`modify_rate` / `dynamics_modifier`) | 3 | 5 |
| resource consume/produce (`add_resource` / Process Stock / `drive_source`) | 3 | 9 |
| Process start and modify | 3 | 5 |
| Relation change (`relation_modifier` / `move_actor`) | 3 | 5 |
| event-driven passive (`damage_resolved`) | 3 | 4 |
| condition combination (`all`/`any`/`not` plus typed leaves and Derived) | 4 | 4 |
| multi-Effect synergy (at least two Effects and two Operators) | 4 | 7 |
| selector `self` | 1 | 9 |
| selector `target_actor` | 1 | 12 |
| selector `current_area` | 1 | 21 |
| selector `adjacent_area` | 1 | 6 |
| selector `linked_object` | 1 | 1 |

Across the compiled library, the mechanical coverage sets equal:

- all seven Operators: `impulse`, `drive/source`,
  `attractor_modifier`, `dynamics_modifier`, `process_start`,
  `process_modify`, `relation_modifier`;
- all six state classes: `Field`, `Stock`, `Process`, `Relation`,
  `Discrete`, `Derived`;
- all five selectors: `self`, `target_actor`, `current_area`,
  `adjacent_area`, `linked_object`.

`Derived` is a read-only condition state class; no Skill writes Derived
state.

## Per-Skill Conformance

Each of the 40 Skills has all seven category keys in the generated matrix.

1. **Positive execution:** fresh PLAYER and NPC builds run the same document
   through the formal chain. Each asserts the exact Mana cost/delta, the exact
   action and ledger Tick delta, all required Effect outcomes as `applied`,
   and an Effect-caused world delta against a same-profile no-Skill control
   that spends the same duration. The one self-Mana refund case is handled by
   the generic formula `mana cost - self add_resource mana`.
2. **Illegal permission:** removing one used Effect kind from trusted material
   authority rejects at parse with an effect-authorization error; removing one
   used selector rejects with a scope-authorization error.
3. **Budget overflow:** setting `limits.budget` exactly `0.01` below the
   compiled usage rejects at parse with a budget error. The document is not
   otherwise mutated.
4. **Lifecycle:** scheduled Effect/Drive/Process/Relation expiry is advanced
   through real World Ticks and verified to clear; status/trait durations are
   consumed by real `owner_turn` phase events; passive firing is verified
   against `max_firings_per_root`. Sixteen instantaneous Skills have an
   explicit N/A reason in the matrix.
5. **Cross-region:** six Skills exercise `adjacent_area` or `move_actor` and
   assert a remote Area target or a moved `located_in` relation. The other 34
   record an explicit N/A reason.
6. **Checkpoint:** after the Skill Effect, the test saves a registry
   checkpoint, restores it against the trusted Gate 3 content, performs the
   same continuation on restored and uninterrupted runs, and compares the
   complete canonical world documents and digests.
7. **Deterministic replay:** two independent compiler/content/runtime builds
   with identical request IDs and action sequences produce identical Effect
   outcomes and canonical world digests.

## Results

Focused owner command:

```powershell
python -m pytest -p no:cacheprovider `
  gameplay_v04/tests/test_p2_reference_library.py `
  gameplay_v04/tests/test_skill_ir.py `
  gameplay_v04/tests/test_p1_scenarios.py `
  gameplay_v04/tests/test_gate4_registry_checkpoint.py -q
```

Result: **41 passed, 406 subtests passed** in 301.47 seconds. The exact output
is in `docs/agent_bootstrap/evidence/p2_lib_owner_focused.log`.

Matrix totals:

- positive execution: 40 pass;
- illegal permission: 40 pass;
- budget overflow: 40 pass;
- lifecycle: 24 pass, 16 N/A;
- cross-region: 6 pass, 34 N/A;
- checkpoint: 40 pass;
- deterministic replay: 40 pass.

## Language Gaps

These are recorded boundaries, not production defects and not Skill-specific
special cases:

- `linked_object` can resolve several endpoint IDs, while the accepted Effect
  executor requires exactly one resolved target. There is no language-level
  policy for deterministic multi-link selection, so the reference library
  uses a fixture where exactly one endpoint is legally resolvable.
- `lifecycle.status_duration` is rejected by P2.1 because the accepted runtime
  does not consume `SkillBlueprint.duration`. Per-Effect `duration` and
  registry status `duration` are the supported lifecycle paths.
- `move_actor` cannot be combined with damage, Process/Drive control, or
  Relation-modifier Effects in one accepted action. Cross-region composites
  are therefore limited to the accepted whitelist (`heal`, `shield`,
  `add_resource`, status/trait, and Field modifiers).
- Automatic passive dispatch supports `damage_resolved` as the usable event;
  other trigger/event families remain `language_gap:` rejections in the IR.
- Process modification can target only an already-running trusted local
  Process. The fixture starts that Process through the trusted controller
  before the Skill action; the IR has no effect that both starts and then
  modifies a Process within one entry.
- Scheduled expiry is observed through real Ticks, but a status/trait with
  `owner_turn` duration is consumed by explicit owner-turn phase events, not
  World Tick time. The library treats these as distinct lifecycle units
  rather than pretending one is the other.

## Production Boundary

No production module, existing test, or `skill_ir.py` was edited. The library
uses only public parser/compiler, content compiler, registry, action, Tick,
status, and checkpoint APIs. No Skill-ID branch exists in fixture or
production code.
