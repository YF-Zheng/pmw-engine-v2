# P0 Baseline QA

Date: 2026-10-28 (Asia/Shanghai)  
Repository: `pmw-engine-v2`  
Branch: `feature/alpha-v02-seventh-night`  
Baseline: `1433e957d5391b880b71e92da4b5cf2ebd9751cd`

## Verdict

**PASS.** The requested baseline suites pass under Python 3.12.10 / pytest
9.2.0: **644 top-level tests passed**, with no failures or skips. Core, V06
mechanics, Gameplay V04, Alpha, and Storm Relay were all exercised. The
deterministic differential tests compare the formal PMW `Engine` execution path
against independent reference simulators, rather than validating a reference
implementation alone.

No package installation or network/API access was used. This QA pass did not
modify tracked source, tests, or global configuration. The only files this QA
pass wrote are this report and the four pytest plus four unittest evidence logs
under `docs/agent_bootstrap/evidence/`. Other files in
`docs/agent_bootstrap/` belong to other agents.

## Environment and discovery

- `py -0p` selected `C:\Users\orinzheng\AppData\Local\Programs\Python\Python312\python.exe`.
- `python --version`: Python 3.12.10.
- `pytest --version`: pytest 9.2.0.
- `python3.12` and `python3` are not available as Windows command aliases; `python` is the 3.12 executable.
- `pyproject.toml` declares no runtime dependencies and `requires-python >=3.10`.
- `PYTHONPATH=src` was used for pytest. Native unittest runs also require the repo root for absolute `experiments.*`/`examples.*` imports.
- `PYTHONDONTWRITEBYTECODE=1` and `-p no:cacheprovider` prevented test-run bytecode and pytest-cache writes.

Discovery found five core modules, eleven V06 test modules, and the Alpha and
Storm Relay example test modules. Collection counts matched execution counts:
254 core, 170 V06, 172 Gameplay V04, and 48 Alpha + Storm Relay tests, for
644 total top-level tests.

## Pytest results

All pytest commands were run from the repository root with:

```powershell
$env:PYTHONPATH='src'
$env:PYTHONDONTWRITEBYTECODE='1'
python -m pytest -q -ra --durations=10 -p no:cacheprovider <suite>
```

The captured final lines and process-exit status were:

| Suite | Command target | Result | Summary time | Wall time | Exit |
|---|---|---|---:|---:|---:|
| Core | `tests` | 254 passed | 32.75s | 33.566s | 0 |
| V06 mechanics | `experiments/generative_mechanics/next_tracks_v06/tests` | 170 passed, 3,011 subtests passed | 32.13s | 33.189s | 0 |
| Gameplay V04 | `experiments/generative_mechanics/next_tracks_v06/gameplay_v04/tests` | 172 passed, 22 subtests passed | 96.91s | 97.729s | 0 |
| Alpha + Storm Relay | `examples/pmw_alpha/tests examples/storm_relay/tests` | 48 passed | 129.59s | 130.452s | 0 |

Total: **644 passed**, plus 3,033 passing subtests from the V06 and Gameplay
V04 suites.

The 48-test combined run consists of 19 Alpha and 29 Storm Relay tests, matching
separate Storm Relay collection.

Evidence logs:

- `docs/agent_bootstrap/evidence/p0_core_qa_pytest.txt`
- `docs/agent_bootstrap/evidence/p0_next_tracks_v06_qa_pytest.txt`
- `docs/agent_bootstrap/evidence/p0_gameplay_v04_qa_pytest.txt`
- `docs/agent_bootstrap/evidence/p0_alpha_storm_relay_qa_pytest.txt`

## Native unittest cross-check

The suite was also run through Python's standard-library unittest discovery:

```powershell
$env:PYTHONPATH="$PWD\src;$PWD"
$env:PYTHONDONTWRITEBYTECODE='1'
python -m unittest discover -s . -p "test_*.py" -v
```

That command was executed from each package-less test directory (`tests`,
V06 `tests`, Gameplay `tests`, Alpha `tests`, and Storm Relay `tests`).

Valid results:

| Suite | Result | Summary time | Exit |
|---|---|---:|---:|
| Core | 262 passed | 35.221s | 0 |
| V06 mechanics | 170 passed | 28.034s | 0 |
| Gameplay V04 | 172 passed | 91.653s | 0 |
| Alpha | 19 passed | 51.848s | 0 |
| Storm Relay | 29 passed | 81.436s | 0 |

Core's 262 count includes eight `test_agent_cost_ledger` tests that were
concurrently added outside this baseline and are not among the 254 pytest core
tests. They are not part of this QA verdict. None of the game source, game
tests, or global configuration was modified by this pass.

The Gameplay V04 pytest and unittest logs were both produced before concurrent
P1 edits to `gameplay_v04/blueprints.py`, `contracts.py`, and `dynamics.py`
(source timestamps 20:25:01; QA Gameplay logs 20:17:12 and 20:24:11). Those
edits are outside this sidecar's baseline measurement and were not reviewed
here.

Evidence logs:

- `docs/agent_bootstrap/evidence/p0_core_qa_unittest.txt`
- `docs/agent_bootstrap/evidence/p0_next_tracks_v06_qa_unittest.txt`
- `docs/agent_bootstrap/evidence/p0_gameplay_v04_qa_unittest.txt`
- `docs/agent_bootstrap/evidence/p0_alpha_storm_relay_qa_unittest.txt`

## Windows runner failures, not semantic regressions

1. **Logon shell failure:** the sandboxed login shell failed before command
   execution with `CreateProcessWithLogonW failed: 1385`. The same narrow
   read/test commands were rerun outside the sandbox so the baseline could be
   measured.
2. **Package-less test directories:** `unittest discover -s <dir> -t .` reports
   `Start directory is not importable` when the directory has no `__init__.py`.
   This affected core, Gameplay V04, and Storm Relay. Running discovery from the
   directory itself resolved the layout issue.
3. **Import path:** from those directories, absolute `experiments.*` and
   `examples.*` imports initially raised
   `ModuleNotFoundError`. Adding the repo root to `PYTHONPATH` resolved this.
   The resulting 24 Gameplay and 6 Storm Relay loader errors were runner
   failures, not test assertions or engine behavior.

Pytest on the same code and test targets passed without these wrapper issues.
The failed wrapper attempts remain in the evidence logs for auditability.

## Meaningful formal-Engine coverage

The following tests materially exercise the production engine and its
downstream gameplay/demo integration, rather than only a reference toy:

- **Core engine correctness:** `tests/test_engine.py` runs `Engine.run_event`
  and `runtime.run_event` across event laws, state closure, lifecycle,
  scheduler, COW, observation, and trace paths. It includes large randomized
  differential tests such as
  `test_incremental_closure_differential_1000_cases`,
  `test_randomized_reactive_closure_differential_1000_cases`, and
  `test_generated_state_program_differential_1000_cases`.
- **Formal-vs-reference V06 differentials:** `tests/test_differential.py`
  constructs compiled PMW laws, attaches them to `pmw.Engine`, executes the
  formal event path, and compares the resulting state to an independent
  `normalized_network_step` oracle:
  `test_reference_matches_pmw_for_1000_deterministic_cases` and
  `test_1000_randomized_lifecycles_match_independent_reference`.
- **V06 runtime semantics:** `tests/test_runtime.py` verifies impulse,
  attractor, drive, process, stock, relation, temporal handle, cancellation,
  and save/load behavior through the runtime path.
- **Gameplay integration:** `gameplay_v04/tests/test_gate5_end_to_end.py`
  executes `resolve_action`, `advance_world_tick`, weather/dynamics, combat,
  harvesting, time accounting, deterministic replay, and readable causal
  sources in one formal world. `test_gate52_integration.py` exercises the full
  authoritative limited-world chain, including resolution and checkpointing.
- **Alpha and Storm Relay:** `examples/pmw_alpha/tests/test_session.py` performs
  Alpha session actions that mutate the live PMW world; `test_content.py` in
  Storm Relay asserts the factory returns a live PMW gameplay session and that
  stock is distinct from dynamic abundance. The end-to-end/demo tests also
  include explicit formal-runtime and deterministic replay checks.

Reference-only tests exist alongside these, particularly the unit tests labeled
`ReferenceDynamicsTest` and closed-form oracles. The differential and integration
tests above are the key evidence that the formal engine agrees with those
references at the boundaries.

## Limitations

- This is a baseline regression and contract QA pass, not a Gameplay audit or
  architecture review. Those remain owned by the other agents.
- No remote dependencies were installed; the environment had no third-party
  runtime dependencies to exercise.
- The native unittest core count includes concurrently added non-baseline ledger
  tests; use the 254-test pytest result for the authoritative baseline count.
- The Gameplay measurements are baseline results from before the concurrent P1
  source edits. They do not claim post-edit validation.
- No independent P1 patch review was performed by this sidecar.
