# PMW v0.4 Gate 1 Report

Status: `DONE` for G1.01-G1.08. This is gameplay infrastructure evidence,
not a benchmark freeze or a claim that TODO2/TODO3 has started.

## Implemented contracts

- Immutable, strict `FieldDefinition`, `AreaBlueprint`, and `ActorBlueprint`
  parsers instantiate independent PMW Entities. Human and AI Actors have the
  same state shape except for their Controller value.
- Capability-gated selectors support `self`, `target_actor`, `current_area`,
  `adjacent_area`, and typed linked objects. Unknown fields, unauthorized
  relation types, missing endpoints, and non-Area adjacency endpoints fail
  closed.
- Area fields and optional Actor Mana use one domain-aware Dynamics contract.
  HP does not receive implicit recovery. Adjacency creates no implicit Field
  diffusion.
- Linear recovery uses `rate * (target - x)`. Distance-squared recovery uses
  `rate * (target - x) * abs(target - x)`. Their stable rate limits are `1`
  and `1 / domain_width`, respectively.
- The effective target is a non-negative weighted mean of the baseline and
  active sources. Rate is `(baseline + sum(add)) * product(multiplier)`, then
  clamped to the selected curve's stability range. A live curve override must
  have a unique priority.
- Persistent patches and temporary modifiers have separate bounded slots,
  explicit owner/source identity, exact removal, and Scheduler-backed expiry.
  PMW Event/Law effects perform every authoritative state write.
- One `world_tick` advances every registered Field once and then advances the
  gameplay clock once. `combat_round` and `owner_turn` are distinct phases and
  do not implicitly run Dynamics.
- Checkpoint reload discovers Field profiles from formal WorldState and rebuilds
  the same deterministic Law bundle. Continued execution is state-equivalent.

## Automated verification

Command:

```text
PYTHONPATH=src:. python3 -m unittest discover -s experiments/generative_mechanics/next_tracks_v06/gameplay_v04/tests -v
```

CPython 3.10.12 result: `21/21`, zero failures/skips/expected failures,
unittest time `2.525 s`. The suite includes 600 fixed-seed differential cases
covering both curves, lifecycle/ownership failures, save/load continuation,
PMW Law execution, non-diffusion, selector capabilities, and multi-subject
ticks. Raw log: `/tmp/pmw_gate1_tests_final.log`, SHA-256
`f4f9e18b4e339a54feae8c26b455935d2b88e73f601d973839942acd61e661b0`.

The unchanged v0.6 suite was also rerun after Gate 1: `170/170` in `25.910 s`,
zero failures/skips/expected failures. Raw log:
`/tmp/pmw_gate1_v06_regression.log`, SHA-256
`cf6958f38d1a0eb603b2c793b5744f861d71216842f9fbf209dc02fd3ab95517`.

## Reproducible demo and scale evidence

Command:

```text
PYTHONPATH=src:. python3 -m experiments.generative_mechanics.next_tracks_v06.gameplay_v04.benchmarks --output /tmp/pmw_gate1_demo_benchmark.json
```

The two-Area Demo applies a source only to the west Area. After four ticks,
west is `0.4954679117660119` and east is `0.44576000000000005`, proving the
adjacency alone did not copy or diffuse either trajectory. Repeated in-process
runs produce the same canonical object.

Unrelated Skill Definition locality:

| Unrelated entities | Candidate rows | Partial | Complete | Matches | Index builds | Full scans | Cold s | Warm tick s |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1,000 | 99 | 99 | 2 | 2 | 0 | 0 | 0.1706 | 0.0051 |
| 10,000 | 99 | 99 | 2 | 2 | 0 | 0 | 0.2219 | 0.0051 |
| 100,000 | 99 | 99 | 2 | 2 | 0 | 0 | 0.9610 | 0.0097 |

With 16 active sources on one Field, structural matching remained 99 candidate
rows, 99 partial bindings, 2 complete bindings, 2 matches, and zero index
builds/full scans. The warm tick was `0.0050 s`.

Real active-world scaling, with two active modifiers per Field:

| Areas | Actors | Fields | Modifiers | Triggered laws | Full scans | Cold s | Warm tick s |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 4 | 4 | 8 | 16 | 9 | 0 | 0.1494 | 0.0120 |
| 16 | 16 | 32 | 64 | 33 | 0 | 0.5921 | 0.0478 |
| 32 | 32 | 64 | 128 | 65 | 0 | 1.1974 | 0.0954 |

The benchmark JSON SHA-256 is
`2b2780bc50ee32efb8e3943e96161509f5fc04ba1adc50f902fd237d2c851cea`.
Wall time was `5.34 s`; peak RSS was `167596 KiB`.

## Review notes and remaining boundary

The integration owner added an adversarial adjacency endpoint test after the
implementation agent stopped because its service usage limit was reached. The
collaboration API exposed no model selector, so the agent model/effort remains
`unverified`; no Luna High claim is made.

Gate 1 deliberately does not implement Action/Effect/Status, Weather/Ecology,
runtime Skill registration, AI, final balance, or TODO2 data collection. Those
belong to later Gates.
