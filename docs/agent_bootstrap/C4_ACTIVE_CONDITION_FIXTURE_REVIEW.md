# C4 Active Condition Legacy Fixture Review

## Verdict

**ACCEPT**

The sole legacy-fixture edit is the explicitly authorized truth-value
correction. On the real parsed, equipped, timed Process Skill path, the
original false condition is rejected atomically for both actors, while the
corrected true condition preserves the original positive Mana and Tick
expectations. The focused pytest files pass.

## Patch Surface

- `git show HEAD:<path>` versus the working file shows one changed assignment:
  `{"all": [None, {"not": None}]}` became
  `{"all": [None, {"not": {"not": None}}]}`.
- The diff is one insertion and one deletion. There is exactly one `condition`
  assignment in the target method in each revision.
- With that assignment removed from both ASTs, every other AST node is
  identical. Both trees contain 2,114 nodes. No helper, runtime assertion,
  cost, Tick, or Mana expectation changed.
- The new expression is logically true: `None` is the always-true leaf,
  `not None` is false, and `not(not(None))` is true; `all(true, true)` is true.
  The original expression is logically false because its second child is false.

## Original False Expression

The probe imports the test module and uses its own `_blueprint_with_condition`,
`_profile`, `_runtime`, and actor IDs. Each attempt uses the normal
`submit_timed_primary_action` path.

| Actor | Result | Error | Mana | Time budget | Tick / sim time | Schedule |
|---|---|---:|---:|---:|---:|---|
| player_actor | rejected | `action condition is not satisfied` | 20.0 -> 20.0 | 0 spent / 6 remaining | 0 / 0.0 | unchanged |
| npc_actor | rejected | `action condition is not satisfied` | 20.0 -> 20.0 | 0 spent / 6 remaining | 0 / 0.0 | unchanged |

For both attempts, a complete before/after snapshot is identical, including
serialized World state, runtime revision and object revision, runtime stats and
closure flag, schedule, profiles, full actor components, clock and time budget,
tick, simulation time, direct Process components, and all four ore/ingot
stocks. The initial ore is 10.0 and ingot is 0.0 for both actors after
rejection. Thus the gate rejects before cost, time, Process start, stock
conversion, scheduling, or persistent mutation.

## Corrected True Expression

Both actors cast the same parsed Skill through the normal timed primary action
path and budget of six Ticks:

| Actor | Duration | Mana | Final budget |
|---|---:|---:|---|
| player_actor | 2 Ticks | 20.0 -> 16.0 | 4 spent / 2 remaining |
| npc_actor | 2 Ticks | 20.0 -> 16.0 | 4 spent / 2 remaining |

The second cast reports 4 before / 2 after remaining time. Final world time is
4.0 with tick 1. Each actor's ore falls from 10.0 to 6.0 and ingot rises from
0.0 to 2.0. The player Process completed two of three Ticks and stopped; the
NPC Process has one Tick remaining and retains its expiry event at time 5.0.
These side effects are consistent with the two independent two-Tick casts and
do not contradict the accepted fixture's Mana, duration, or budget assertions.
Revision advances to 19 only on the accepted path.

## Focused Tests

Command:

```text
python -m pytest -p no:cacheprovider \
  experiments/generative_mechanics/next_tracks_v06/gameplay_v04/tests/test_sandbox_condition_limits.py \
  experiments/generative_mechanics/next_tracks_v06/gameplay_v04/tests/test_sandbox_active_condition.py -vv
```

Result: **22 passed, 16 subtests passed in 1.60s**. The target corrected fixture
and all active-condition tests passed.

## Findings

No genuine finding in the reviewed fixture correction. The test was historically
incorrect as a positive eligibility fixture because parser acceptance was
mistaken for truth; C4.3's real gate exposed that error. Replacing only the
condition with an always-true expression is the narrow authorized repair and
does not weaken the runtime expectations. The pre-change positive behavior
should not be preserved because it depended on ignoring a false top-level
condition.

Residual scope: this review covers the specified legacy fixture and the two
focused test files. It does not broaden the C4.3 full-suite, P1/P2, provider, or
other open gate claims.

## Evidence

- `docs/agent_bootstrap/evidence/c4_active_fixture_review_probe.py`
- `docs/agent_bootstrap/evidence/c4_active_fixture_review.json`
- `docs/agent_bootstrap/evidence/c4_active_fixture_review.log`
- `docs/agent_bootstrap/evidence/c4_active_fixture_review_pytest.log`
