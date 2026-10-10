# Gate 0 Baseline

- Date: 2026-10-10 (Asia/Shanghai)
- Base branch: `feature/gm-v06-todo1-rich-dynamics`
- Base commit: `a98ff51561760f87689093c815508fa93120807d`
- Development branch: `feature/pmw-v04-gameplay-foundations`
- Python: CPython 3.10.12
- Platform: Linux x86_64, kernel 5.15.0-91-generic

Fresh baseline runs:

- PMW Core: 254/254 passed in 25.792 s.
- Pre-v0.6 Generative Mechanics: 345/345 passed in 67.744 s.
- v0.6 TODO1: 162/162 passed in 25.566 s.
- Failures, skips, expected failures: 0, 0, 0.

The protected-path manifest is the sorted `git ls-tree -r` output for `src/pmw`
plus `experiments/generative_mechanics` excluding `next_tracks_v06`. It contains
381 entries and has SHA-256:

`a20fd763cad342ac357a08d94ee96ca42075f215efcbff93c4017b65a8ddd669`

This manifest definition is reproducible and will be checked again at Gate 5.
The older report's digest remains recorded but used an undocumented construction,
so it is not substituted for this explicit coverage proof.

The four handoff artifacts were read. The 44-page Player Journey is treated as
experience guidance only; its numeric fixtures are not frozen balance values.
