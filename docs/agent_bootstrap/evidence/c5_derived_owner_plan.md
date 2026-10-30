# C5.2 Derived Catalog Implementation Plan

1. Read the frozen design and existing compiler, relations, conditions, actions, DSL, and validation paths.
2. Implement the trailing `Gate3Content.derived_by_area` field, compiler support, initialization, and state-mode runtime wiring.
3. Add the `derived` condition leaf using only the current-area context mapping.
4. Add real-chain acceptance tests covering player/NPC behavior, mismatch guards, initialization, fixed-point settling, and static ownership.
5. Run the focused requested test set with the mandated environment and record evidence.
