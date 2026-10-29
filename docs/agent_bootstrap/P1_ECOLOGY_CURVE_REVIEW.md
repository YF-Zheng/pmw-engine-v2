# P1 Ecology Baseline-Curve Independent Review

Date: 2026-10-29, Asia/Shanghai. Starting checkpoint: `e57b3c0`.
Status: `QA_SOURCE_FROZEN` for the independent test/review scope. This note
does not accept the increment; Main owns final acceptance and the complete
cross-module regression.

## Scope And Provenance

Independent QA wrote only:

- `experiments/generative_mechanics/next_tracks_v06/gameplay_v04/tests/test_sandbox_ecology_curve_review.py`
- this review file
- `evidence/p1_ecology_review_*.txt` and `evidence/p1_ecology_review_*.json`

No implementation file, existing `independent_qa.py`, Main-owned regression
test, provider configuration, commit, or remote was modified by QA.

`evidence/p1_ecology_review_before_fix.txt` is intermediate test-authoring
evidence, not a frozen `e57b3c0` baseline run. The implementation source was
changing concurrently while that evidence was produced. The genuine pre-fix
evidence is Main's `evidence/p1_ecology_main_before.txt` and
`evidence/p1_ecology_curve_before.json`. Obsolete failed runs are retained.

## Contract Under Test

The formal sequence is:

1. `advance_world_tick()` advances schedules to the boundary; expiry at time T
   runs before the world-tick dynamics at T.
2. Our independent contract findings are that the tick root reads one
   pre-event state. Dynamics and the `mode: event` ecology Laws do not form two
   sequential dynamics/state-close phases. A threshold reached by the root
   read-value can commit a transition in the same tick while that tick's
   dynamics proposal uses the old baseline curve. Publications become the next
   tick's read state.
3. Therefore, a transition at step N publishes the new baseline alongside
   step N's old-curve dynamics. Step N+1 selects the new baseline curve.
4. An active curve override wins over the live base selector. Expiry is
   evaluated first, so a duration-two override is present at its first
   world-tick time and gone at its second.
5. Live baseline `target` and `rate` are weighted/additive expressions evaluated
   from current state; an override changes only which formula is selected.
6. Trusted ecology input rejects unknown curves, nonzero-rate `none`, and
   reachable baseline target/rate values outside their legal domain or stability
   limit.

The independent tests assert observable state, diagnostics, Law catalog IDs,
applied/triggered Law IDs, causal trace structure, and deterministic
continuation. Quantitative formulas live only in the tests.

## Independent Coverage

| Scenario | Independent assertion |
| --- | --- |
| Two Areas, different curves | Both transitions commit from pre-dynamics `0.5`; same-tick values are `0.75` linear and `0.25` squared. The next tick selects squared and linear respectively, producing `0.1875` and `0.625`. Deliberately, the thresholds are true for pre-dynamics `0.5` and false for the same tick's published values, so pre/post read-state disagreement is observable. |
| Source target/rate | Post-transition baseline target/rate combine with a weighted target source and rate-add/multiplier sources. Expected target is `(0.2 + 3*0.8)/4 = 0.65`; expected rate is `(0.4 + 0.3)*0.5 = 0.35`; squared update from `0.75` gives `0.7234375`. |
| Override and expiry | A `none` override freezes at `0.5` in its first tick while the transition publishes new baseline values. At the second tick, expiry is first, then the live squared baseline updates `0.5 -> 0.25`. A separate `none`-baseline plus `linear` override scenario checks `0.5 -> 0.6` while active, then freezes at `0.6` after expiry with rate zero. |
| Replay identity | Live session, staged session retaining construction-time profiles, rediscovered-profile runtime, registry rebuild, and save/load continuation produce identical state. The test also compares canonical base-formula Law catalog IDs and applied IDs, including `base_distance_squared.down`, to detect causal-trace drift that numeric equality would miss. |
| Invalid trusted input | Reachable linear rate `1.01`, squared rate `1.01` (width one), target outside domain, unknown curve, and nonzero-rate `none` all fail before session construction. |

The expiry test was corrected from a mixed base-curve transition to a
transition-only target/rate case plus a separate quantitative base-curve case.
This is not a weakening: the second case explicitly checks `none` freeze at
`0.5`, then squared recovery `0.5 + 1*(0-0.5)*0.5 = 0.25` after expiry. The
worker's draft mixed simultaneous baseline/expiry effects and its expected
values did not represent the documented expiry-before-dynamics sequence.

## Frozen Independent Result

Frozen run:

```powershell
$env:PYTHONPATH='src'
$env:PYTHONDONTWRITEBYTECODE='1'
python -m pytest -q -p no:cacheprovider `
  experiments/generative_mechanics/next_tracks_v06/gameplay_v04/tests/test_sandbox_ecology_curve_review.py
```

Result: **9 passed, 5 subtests passed**. Start
`2026-10-29T10:13:42.1074353+08:00`, finish
`2026-10-29T10:13:45.0821633+08:00`; exit code `0`.

Source/test hashes:

- `dynamics.py`: `D057121D008FA5A1D4057FBF838FE4018A8D0386A72C7348664BB0EBE7D67DCB`
- review test: `E55D193658B4148086342B7872434A1CA96E5189DA7741FC12F2223D735306A3`
- `runtime.py`: `E31100617854ED61CB227475CDA50957BE8C0C8D478A3E47B7F6EBBFE26E5C6`
- `ecology.py`: `D10DC0D66E6E53BB85568D429F012CBCEDDD68AE279EC4B5373481F303C12083`

The exact timing and hashes are also in
`evidence/p1_ecology_review_frozen_meta.json`; output is in
`evidence/p1_ecology_review_frozen.txt`.

## Actionable Issues For Main

1. **Blocker in owner tests:** the owner suite
   `test_sandbox_ecology_curve.py` currently reports **1 failed, 8 passed**.
   Its two-Area test expects the changed `none` Area to freeze at `0.8` and
   then expects that value to equal the unchanged linear Area's `0.68`; the
   two assertions contradict each other. This is a worker-owned test defect,
   not an independent-test failure. The independent suite is **9 passed, 5
   subtests passed**. Main should require the owner suite to pass before
   acceptance.
2. **Naming risk resolved in current source, keep it frozen:** base variants
   are now canonically named by curve (`base` for linear, `base_none`, and
   `base_distance_squared`) rather than swapped according to `field.curve`.
   The independent catalog/applied-ID comparison passes at the frozen hash.
   Any later change to these IDs requires rerunning the identity test.
3. **Trusted-input boundary:** live baseline writes outside legal ranges may
   skip dispatch rather than be rejected on every tick. This review treats only
   trusted construction/input validation as a contract and does not claim
   corruption-proof behavior for arbitrary administrator mutation.
4. **Ordering limitation to document:** because no dynamics-to-event phase
   boundary exists, same-time baseline writes and dynamics read the same
   pre-event snapshot. The new selector honors that existing order. It does not
   invent a post-dynamics pass.

## Remaining Risks

- Main's full frozen regression and existing `independent_qa.py` run must
  confirm no cross-module behavior change.
- The expanded base Law catalog increases event candidate work. Correctness is
  covered; no performance claim is made here.
- Historical byte-for-byte Law parity does not apply to this deliberate
  routing expansion. Existing linear/squared curve values remain numerically
  covered by adjacent dynamics tests.

QA_SOURCE_FROZEN
