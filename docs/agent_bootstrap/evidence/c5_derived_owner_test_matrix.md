# C5.2 derived catalog owner test matrix

Date: 2026-10-30T13:05:38+08:00

Repo: `C:\Users\orinzheng\Documents\Codex\2026-10-28\magpie-codex-deepseek-17-21-codex\pmw-engine-v2`

Branch: `feature/alpha-v02-seventh-night`

HEAD: `db0fba2f463ac783d5b158494ba1cf71aeb2a96c`

All Python commands were run in PowerShell with, in the same command:

```text
PYTHONPATH=src
PYTHONDONTWRITEBYTECODE=1
PYTHONIOENCODING=utf-8
TEMP=TMP=TMPDIR=C:\Users\orinzheng\Documents\Codex\2026-10-28\magpie-codex-deepseek-17-21-codex\pmw-engine-v2\docs\agent_bootstrap\evidence\test_tmp
PYTHONPYCACHEPREFIX=C:\Users\orinzheng\Documents\Codex\2026-10-28\magpie-codex-deepseek-17-21-codex\pmw-engine-v2\docs\agent_bootstrap\evidence\test_tmp\pyc_c5d_owner
pytest -p no:cacheprovider
```

## Runs

1. New acceptance test:
   `experiments/generative_mechanics/next_tracks_v06/gameplay_v04/tests/test_sandbox_derived_catalog.py`
   - 11 passed, 16 subtests passed in 4.84s.

2. Formal/focused sandboxes:
   `test_p1_scenarios.py`, `test_sandbox_move_actor.py`,
   `test_sandbox_dynamics_action.py`, `test_sandbox_drive_source.py`
   - 51 passed, 81 subtests passed in 11.03s.

3. Gate1-Gate4:
   all `test_gate1*.py`, `test_gate2*.py`, `test_gate3*.py`,
   `test_gate4*.py`
   - 89 passed, 2 subtests passed in 26.22s.

4. Gate5/Gate51/Gate52:
   all `test_gate5*.py`, `test_gate51*.py`, `test_gate52*.py`
   - 83 passed, 20 subtests passed in 57.29s.

5. Condition-named tests:
   `test_sandbox_active_condition.py`,
   `test_sandbox_active_condition_review.py`,
   `test_sandbox_condition_limits.py`,
   `test_sandbox_condition_limits_review.py`
   - 46 passed, 88 subtests passed in 3.61s.

Total: 280 passed, 207 subtests, zero failures.

No full-suite run. No commit, push, stash, reset, checkout, or deletion.

## Ownership checks

- `actions.py` diff is confined to `_condition_context`; it adds only the
  Area's `derived` mapping when `pmw_gameplay_derived` exists.
- `conditions.py` preserves all existing parse/evaluation branches and adds
  the `derived` leaf after the existing leaves.
- No writes occurred in `src/`, Alpha, design files, any existing test, or the
  two pre-existing Main-edited files.
