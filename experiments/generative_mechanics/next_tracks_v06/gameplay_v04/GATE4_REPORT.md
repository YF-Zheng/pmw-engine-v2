# PMW v0.4 Gate 4 Verification Report

Status: **DONE**

Scope: full-World-Tick-boundary mechanism registration, canonical checkpoint
rebuild, actor-safe legal-action generation, production-resolver sandboxing,
bounded opponent-response planning, build analysis, explainable utility, and
newest-state revalidation. PMW Core and frozen research protocols were not
modified.

## Registry and checkpoint

- Registry install/disable is a traced `pmw.v04.registry.change` Event and may
  occur only once at a complete World Tick boundary.
- Skill versions are monotonic. Canonical documents, hashes, material authority,
  and the formal WorldState manifest are cross-checked before publication.
- Action Law IDs and expiry event types include version and hash identity. A new
  version cannot alias an old loadout reference; referenced versions must first
  be unloaded.
- Disabled definitions disappear from the active ActionRegistry while retired
  lifecycle Laws remain until scheduled effects and Status instances quiesce.
- Checkpoints include WorldState, scheduled events, every canonical blueprint,
  trusted authority, slot configuration, static Laws, and independent hashes.
  Restored execution produced the same Status trace, scheduler dispatch, and
  final WorldState as uninterrupted execution.

## Generic AI

- The controller receives an immutable canonical JSON projection, not a cloned
  WorldState. Hidden RNG, entities, Laws, thresholds, and unrevealed skills do
  not affect its decision log.
- Legal actions are enumerated by running the production resolver in a world
  reconstructed only from the observation. Formal execution revalidates against
  the newest live state.
- Build analysis derives producer/consumer edges from declared reads and writes.
  The planner evaluates a complete one-step fallback before bounded search,
  models an opponent response, and considers a second self action.
- Utility exposes HP, opponent HP, shield, Mana, own/opponent status, terminal,
  and future-potential terms. Deadlines and node budgets fall back deterministically.

## Verification

```text
python3 -m unittest discover \
  -s experiments/generative_mechanics/next_tracks_v06/gameplay_v04/tests \
  -p 'test_gate[1234]_*.py' -v

Ran 89 tests in 10.685s
OK
```

The dedicated split is 7 Registry/Checkpoint tests and 15 AI tests. The AI
Demo was run in two fresh processes and compared byte-for-byte:

```text
SHA-256: cd692ded178a288983a92d7a5d2366abf467c6bbb90d2b5bae060ddd5240c5c3
selected_action: raise_mist
nodes_used: 33
fallback_used: false
```

A 20-run local performance sample used the same 128-node configuration. Every
run selected `raise_mist`, every run used 33 nodes, median wall time was
469.39 ms, and maximum wall time was 502.64 ms. These are engineering fixtures,
not frozen balance or benchmark claims.

## Remaining boundaries

- The sandbox models disclosed state and currently active visible Status data;
  it intentionally does not infer hidden passive hooks or unknown Laws.
- Planning is bounded and deterministic, not globally optimal. Utility weights,
  node budget, discount, and opponent approximation remain configurable demo
  values for owner review.
- Registry replacement requires explicit unload and a complete Tick boundary;
  Core Law hot-install was deliberately not added.
