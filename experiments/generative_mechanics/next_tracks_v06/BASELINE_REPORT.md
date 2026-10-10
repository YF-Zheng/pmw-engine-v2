# v0.6 TODO1 Baseline Report

## Repository gate

- Baseline commit: `1510b2a3a7db397b84db22ebb41d61845dd56ade`
- Feature branch: `feature/gm-v06-todo1-rich-dynamics`
- Frozen-tree SHA-256: `7e3aeb50542594cf5356963e3103d1ae52c17d7f3b1549a1eee2beeea3c6e855`
- New implementation root: `experiments/generative_mechanics/next_tracks_v06/`
- Core and prior Generative Mechanics paths were clean before this directory was
  created.

The frozen digest covers `src/pmw`, the pre-v0.6 Generative Mechanics sources and
assets, DEV pilot artifacts, and `formal_preregistration`. It is recomputed at
the final gate.

## Baseline tests

- Core suite: 254 tests, all passed.
- Existing Generative Mechanics suite: 345 tests, all passed.
- Formal collection was not started and no model request was made.

## Audited PMW capabilities

Supported and used by v0.6:

- entity and relation bindings, endpoint joins, component indexes;
- deterministic `set` and aggregated `delta` resolution;
- `add/sub/mul/div/min/max/clamp` value expressions;
- event-derived events, state closure, lifecycle create/delete;
- Scheduler schedule/cancel/reschedule and persisted scheduled events;
- WorldRuntime, WorldSnapshot, StateDelta, and CausalTrace;
- canonical WorldState serialization and save/load reconstruction.

Constraints that shape the isolated v0.6 design:

- a transaction rejects a `set` plus `delta` conflict on one address;
- the DSL has no row reduction, dynamic slot allocation, conditional value,
  string concatenation, component deletion, or dynamic ID dereference;
- state laws cannot emit/schedule/lifecycle-mutate;
- `run_event` does not advance logical time;
- a future-time derived event is queued rather than immediately cascaded;
- runtime matcher statistics require a test adapter for detailed candidate rows.

The approved data-driven workaround is bounded catalog slots, static expression
expansion, local relation joins, compiler-derived IDs, and a three-stage traced
tick. No Core modification is required for the bounded TODO1 contract.

## Agent execution disclosure

The collaboration API available in this environment does not expose a model or
reasoning-effort selector. Independent role agents were created for Dynamics,
Object/Operator Modeling, Compiler/Integration, and (after implementation)
Independent QA, but the primary agent cannot verify or claim that they are
`GPT-5.6 Luna High`. This limitation was disclosed before implementation.
