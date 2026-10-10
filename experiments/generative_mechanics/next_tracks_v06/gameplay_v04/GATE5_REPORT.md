# PMW v0.4 Gate 5 Verification Report

Status: **DONE**

Gate 5 validates the integrated gameplay foundation. It does not freeze TODO2,
collect model data, or implement the complete TODO3 game.

## End-to-end and time economy

The executable scenarios cover independent instances of one AreaBlueprint;
shared weather and explicit Trait response; sequential Attack/Guard with one
World Tick per full round; harvest yield/time/depletion separation and permanent
ecology degradation; and runtime skill install, use, disable, checkpoint, and
scheduled-effect continuation.

The finite time ledger stores its budget in WorldState. Exploration, harvest,
move, rest, and offline spends use one formal PMW Event and then advance the
same World Tick/Scheduler path. Duration is a positive integer, the whole spend
is budget-preflighted, and actor count cannot accelerate a combat World Tick.

Integration testing found and fixed one production defect: binary float
subtraction made `0.7 - 0.2` slightly less than the `0.5` overharvest boundary.
The comparison now uses an explicit absolute `1e-12` boundary tolerance, so an
exact mathematical boundary does not degrade early.

## Determinism and independent QA

Two fresh formal event sequences produced identical WorldState, Event traces,
and player-facing source explanations. Numeric oracle comparisons use `1e-12`;
byte identity is claimed only for canonical output under the tested CPython
environment.

Independent Role D added six tests without editing production code. They cover
compound required/conditional atomicity, closed-form linear and
distance-squared dynamics, Status/checkpoint and Scheduler lifecycle, lethal
same-round ordering, and a parser-valid hidden Law/ability information attack.
All six pass. Full evidence is in `INDEPENDENT_QA_REPORT_V04.md`.

## Final gameplay tests

```text
PYTHONPATH=src:. python3 -m unittest discover \
  -s experiments/generative_mechanics/next_tracks_v06/gameplay_v04/tests \
  -p 'test_*.py' -v

Ran 107 tests in 22.361s
OK
failures/errors/skips/expected failures: 0/0/0/0
log: /tmp/pmw_v04_final_gameplay.log
SHA-256: f2d2fbd05ae5f29b2dab0f7448b2f6423eb8e894b5fcd779b105216364176422
```

The integrated Gate 5 Demo was also executed in two fresh processes and
compared byte-for-byte. Its SHA-256 is
`973b33e095bb8423c4125eeafc6ab79ae16775c6de4d041d48c89454174ce52c`.

## Performance evidence

The reproducible benchmark output is `/tmp/pmw_v04_gate5_bench.json`, SHA-256
`abc990dfe201b0482fc05c7da834b0cf0e6a37a97494b3a5a865b6742e58152e`.

```text
unrelated  candidates/partial/complete  cold(s)  warm tick(s)  full scans
1,000      99 / 99 / 2                  0.1731   0.00499       0
10,000     99 / 99 / 2                  0.2242   0.00504       0
100,000    99 / 99 / 2                  0.9727   0.00948       0

areas/actors  fields/modifiers  cold(s)  warm tick(s)  full scans
4 / 4         8 / 16            0.1530   0.01201       0
16 / 16       32 / 64           0.5977   0.04726       0
32 / 32       64 / 128          1.2092   0.09758       0
```

The bounded AI fixture used 33 of 128 nodes. Across 20 runs it always selected
the two-action setup `raise_mist`; median planning time was 469.39 ms and maximum
was 502.64 ms. These are environment-specific engineering measurements, not a
scientific benchmark freeze.

## Compatibility gate

- Core: 254/254, 25.821 s.
- Frozen pre-v0.6 Generative Mechanics: 345/345, 67.812 s.
- v0.6 TODO1: 170/170, 25.722 s.
- Gameplay v0.4: 107/107, 22.361 s.
- Total: 876 tests, with zero failures, errors, skips, or expected failures.
- Protected manifest: 381 entries, unchanged SHA-256
  `a20fd763cad342ac357a08d94ee96ca42075f215efcbff93c4017b65a8ddd669`.
- `git diff --check`: clean.

## Deliberate limits

Registry changes require explicit unload and one transaction per complete World
Tick boundary. Planning is bounded rather than optimal. Demo balance constants,
active replacement cost, complete game UI, world generation, and narrative
content remain owner/TODO3 work. No TODO2 collection or benchmark freeze began.
