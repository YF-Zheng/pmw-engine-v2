# P2.2 Reference Library Independent QA Review

Date: 2026-11-02

Verdict: **ACCEPT**

Review target: `feature/alpha-v02-seventh-night` at
`cb536944b84d9b56e69176c6bab79f20399220d3`.

This review accepts the 40-Skill reference library and its mapping to the
seven required categories. It found no PRODUCT_DEFECT and no FIXTURE_ERROR.
One non-blocking TEST_GAP remains in Mill's independent review test, and one
bounded resume test closes the meaningful part of that gap without changing
the reference content or production code.

Counts:

- PRODUCT_DEFECT: **0**
- TEST_GAP: **1**
- FIXTURE_ERROR: **0**
- SCOPE_NOTE: **3**

## Evidence And Method

The combined focused suite was **not rerun**. Mill's recorded execution in
`docs/agent_bootstrap/evidence/p2_lib_review_focused.log` is prior evidence:
`42 passed, 560 subtests passed in 643.03s`. This reviewer independently
executed the matrix method once, then three bounded resume methods once each.
No provider/generator was called, and no production, library, fixture, owner
test, Mill test, or old evidence was edited.

Independent executions:

| Probe | Result | Evidence |
|---|---|---|
| `test_02_library_cardinality_profiles_and_category_minimums` | 1 passed, 14 subtests in 0.37s | `evidence/p2_lib_review_resume_matrix.log` |
| Timed lifecycle pre-expiry/expiry | 1 passed in 5.52s | `evidence/p2_lib_review_resume_probes_final.log` |
| Passive checkpoint continuation | 1 passed in 8.90s | `evidence/p2_lib_review_resume_checkpoint_final.log` |
| Dual-owner passive cap and nested termination | 1 passed in 1.53s | `evidence/p2_lib_review_resume_cap_final.log` |

The first resume attempt is retained as
`evidence/p2_lib_review_resume_probes.log` (`1 failed, 9 passed, 154 subtests
in 345.20s`). Its failure was a review-local fixture error:
`_advance_until(expiry - 0.5)` advanced integral Ticks to the exact expiry
tick, so `active=False` was correct. The corrected test advances while the
actual clock `next_time` is strictly below expiry, asserts
`sim_time < expiry` and `active=True`, then advances one real Tick and
asserts expiry. The manual trace in
`evidence/p2_lib_review_resume_expiry_trace.log` independently agrees with
this boundary.

## Requirement Mapping

| Requirement | Actual implementation or test reference | Independent disposition |
|---|---|---|
| 40 Skills, 7 profiles, all category minimums | `library.json`; Mill `test_02` at `test_p2_reference_library_review.py:526`; owner `test_category_minimums_and_mechanical_coverage` at `test_p2_reference_library.py:629` | Pass. Profile counts are field 8, stock 4, process 5, relation 2, combat 9, travel 3, derived 9. All matrix keys exist. |
| Real PLAYER and NPC execution, exact cost/Tick, control delta | Mill `test_03` at review test line 694; owner `test_03` at owner test line 894 | Pass. Both actors use fresh builds, a same-profile no-Skill control, exact Mana/Tick checks, applied outcomes, and Effect-caused deltas. |
| No ID/name/display-tag branch or post-cast world fabrication | Mill `test_01` at review test line 499; `_assigned_state_paths` at review test line 523; `fixtures.py` | Pass. No library IDs or names occur as literals in fixture/owner-test source, and fixture AST contains no `session.state` assignment. Fixtures only build trusted time-zero worlds/controllers. |
| Passive firing cap, duplicate notification, no extra paid Tick | Mill `test_04` at review test line 788; resume cap method at resume test line 203; `hooks.py:209-340`; `time_ledger.py:75-102` | Pass after independent dual-owner probe. PLAYER and NPC each fire `counter_spark` once, duplicate child notifications are skipped, and only one action duration is charged. |
| Timed lifecycle through real ticks, not first-expiry-only for a multi-timed Skill | Resume lifecycle method at resume test line 74; owner lifecycle test at owner line 976; Mill lifecycle test at review test line 912 | Pass for every represented timed Effect. All five timed cases are checked strictly before and at expiry. No library Skill has two timed Effects, so ordered multi-expiry behavior is a SCOPE_NOTE rather than an unverified multi-Effect claim. |
| Cross-Area at least 6 | Mill `test_06` at review test line 1029; owner `test_05` at owner line 1130; matrix | Pass. Exactly 6 Skills are cross-region; each asserts remote Area outcomes or a moved `located_in`; 34 are explicit N/A. |
| Mid-effect checkpoint and deterministic continuation | Resume checkpoint method at resume test line 124; Mill `test_07` at review test line 1091; owner `test_06` at owner line 1167 | Pass. The resume method performs distinct first and second attacks from restored and independently continued runtimes, then compares hook outcomes, Effect outcomes, canonical state, and digests. |
| Combined condition: >=2 typed leaves including Derived | Mill `test_02` condition section at review test line 588; `_condition_shape` at review test line 460; owner category test at owner line 661 | Pass. Four condition Skills combine `all`/`any`/`not`, at least two typed leaves, and Derived read-only state. |
| All 7 Operators, 6 states, 5 selectors | `skill_ir.py:39-72`; Mill `test_02` assertions at review test line 578; owner test at owner line 650 | Pass. Sets equal the declared catalogs: impulse, drive/source, attractor_modifier, dynamics_modifier, process_start, process_modify, relation_modifier; Field, Stock, Process, Relation, Discrete, Derived; self, target_actor, current_area, adjacent_area, linked_object. |

## Findings

### TEST_GAP-1: Mill cap owner assertion is tautological

Severity: P3 / non-blocking.

Location:
`experiments/generative_mechanics/next_tracks_v06/gameplay_v04/tests/test_p2_reference_library_review.py:894`.

Repro:

```python
self.assertEqual(
    set(fired_per_owner),
    {(PLAYER, passive_hook_id(passive))} if False else set(fired_per_owner),
)
```

The false branch makes the assertion `set(x) == set(x)`. It cannot fail if no
owner fired. The following `count <= 1` and skipped-duplicate assertions are
meaningful, but the owner-set claim is not. This is classified as TEST_GAP,
not PRODUCT_DEFECT.

Closure:
`test_passive_cap_dual_owner_nested_notifications_terminate_refetched` in
`tests/test_p2_reference_library_resume_review.py` equips the same compiled
`counter_spark` passive to both Actors, attacks PLAYER as NPC, and asserts the
exact lawful firing owner set `{(PLAYER, hook), (NPC, hook)}`. It also asserts
per-owner count `<= max_firings_per_root`, a duplicate
`owner+hook source` skip, one action-duration Tick, exact spent/remaining
time budget, and `sim_time + duration`. The method passed once in 1.53s.

### TEST_ERROR-1: Review-local time overshoot in first resume lifecycle probe

Severity: P3 / review-local, corrected.

The initial probe called `_advance_until(runtime, expiry - 0.5)`. The helper
advances integral one-Tick steps while `sim_time < target`, so it reached the
expiry tick and correctly observed `active=False`. This was a fixture/timing
error in the review probe, not a product failure. The corrected probe checks
the trusted clock's actual `next_time`, passes at strict pre-expiry, then
passes at the expiry tick. The failed log is preserved unchanged.

### TEST_ERROR-2: Review-local stale clock component in cap probe

Severity: P3 / review-local, corrected.

The initial cap probe cached the clock component dictionary before
`submit_timed_primary_action`. Transaction publication replaces the state,
so the cached `remaining_ticks` remained 30 while the trusted live clock was
29. All owner/cap/notification assertions had already passed. The corrected
method refetches the live clock component after the action. This is a
review-local test error, not a product defect.

## Scope Notes

1. **No multiple-timed-Effect row.** Every multi-Effect synergy has one timed
   Effect plus one immediate Effect. Lifecycle code and tests prove each
   represented timed Effect reaches its exact expiry, but the library does not
   exercise two distinct timed Effects with staggered deadlines in one
   action. This is not required by the frozen minimum and is recorded as a
   scope limitation.
2. **Passive cap range is 1.** All library passives use
   `max_firings_per_root = 1`; the accepted range is 1..8. The library proves
   the cap behavior it actually declares, not a sequence of caps 2..8.
3. **`linked_object` single-endpoint limitation.** The accepted Effect
   executor requires exactly one resolved target. The library correctly
   records multi-link selection as a language gap and uses a fixture with one
   lawful endpoint; adding a second endpoint fails closed with "exactly one
   resolved target". This is a documented boundary, not Skill-specific
   production branching.

## Source Integrity And Coverage

The generated coverage matrix has 40 Skills, all seven category keys per
Skill, and totals: positive execution 40, illegal permission 40, budget
overflow 40, lifecycle 24 pass/16 N/A, cross-region 6 pass/34 N/A,
checkpoint 40, and deterministic replay 40.

The source review also confirmed:

- `fixtures.py` contains no library Skill IDs and no post-action state writes.
- There is no Skill-ID branch in fixture code; fixtures key only on the
  closed profile set.
- `hooks.py` dispatches from validated damage notifications and terminates
  duplicate `owner+hook` sources; it does not fabricate world state after a
  cast.
- `time_ledger.py` charges exactly `duration` Ticks once and advances real
  World Ticks.
- Per-Effect transition sources carry explicit expiry handles; the expiry
  law clears the source and its scheduled event.
- The resource ledger and derived conditions are read-only from Skill
  perspective; Derived appears only in condition classification.

## Hashes (SHA-256)

| Artifact | SHA-256 |
|---|---|
| `docs/agent_bootstrap/P2_SKILL_IR_DESIGN.md` | `4e3ea6584b0ddde6b6540d24290d1d802f5823228470c8ad0a04f3d8bc4b3b6c` |
| `docs/agent_bootstrap/P2_REFERENCE_LIBRARY_INCREMENT.md` | `82b3e2dc7ff82c7a21e6dca77d5cb7ec5853d2e47666102cf725c5d014556d79` |
| `library.json` | `ec1aae45d189b96d8ec8e439cee60dea3562468dd0222292fd29a94d9f388ff9` |
| `fixtures.py` | `2da5268d0c1431c20af2cde8f4639a5387167a733ed1e52fc2518f3da916b4fb` |
| Owner test | `2d940d2632506c7ece7a013875e05e81e47b502106f190bd3efd0b22bad9b1c3` |
| Mill review test | `ad261771941f6c36efbd1b3bb473f6a709649458a8965c83144a2856365d2bbc` |
| Mill focused log | `36831e3efbabbeb5379ac6e84f526f62c2690b33dfa88e769d29e56e1894c5f4` |
| Coverage matrix | `74ecadd99b9eae21d25f81606baa283cc89959f22cf97424a9d3e9171cb62041` |
| Resume test | `79adb898c687eb940d9ca3b0ba69e39c24a150909e55f558f570f0414175feaf` |
| Matrix resume log | `3ed6fc7531cf1751017bb495f46e6f3199a29342fed058e1b467b38657f04a1b` |
| Lifecycle final log | `8193115ecd2c8942ef40cf05cb46d5b2ee3cc244fafffc3b8c9f90710cc65117` |
| Checkpoint final log | `0078789569c26376e7b3bad17dd0a3f959bada20f1165c709e5488284da3338d` |
| Cap final log | `bd1002509398d4a38afb95a45bc11f7c828158bdc15fdd36f1fe2d0df02b4e3f` |
| Initial failed resume log | `99510cabe2b0b1127399b02b0b70c674f0cacf262facd8bad04575cae772d17e` |
| Expiry trace | `08bc48237ee52ba3ab9df24000aa253cf7b0bc18187726f45ece7f37924feb29` |
| Lifecycle trace | `0141dcab8aaaa0acebc401126de5a5047d54ff1ff3e21a1d18b2dacf93c96ed3` |
| Source trace | `cba740d635442e1f8730a0f1c4729c1631701444a988c3d73b390ac74a6b14e7` |

## Reproduction Commands

All Python commands used `PYTHONPATH=src;.`,
`PYTHONDONTWRITEBYTECODE=1`, UTF-8 I/O, the permitted scratch TEMP/TMP/
TMPDIR, `PYTHONPYCACHEPREFIX=docs/agent_bootstrap/evidence/test_tmp/
pyc_qa_resume`, and `pytest -p no:cacheprovider`.

```text
python -m pytest -p no:cacheprovider --tb=short \
  experiments/generative_mechanics/next_tracks_v06/gameplay_v04/tests/test_p2_reference_library_review.py::ReferenceLibraryReviewTests::test_02_library_cardinality_profiles_and_category_minimums

python -m pytest -p no:cacheprovider --tb=short \
  experiments/generative_mechanics/next_tracks_v06/gameplay_v04/tests/test_p2_reference_library_resume_review.py::ReferenceLibraryResumeReviewTests::test_timed_effect_remains_active_until_expiry_tick_and_then_clears

python -m pytest -p no:cacheprovider --tb=short \
  experiments/generative_mechanics/next_tracks_v06/gameplay_v04/tests/test_p2_reference_library_resume_review.py::ReferenceLibraryResumeReviewTests::test_checkpoint_passive_cap_continuation_matches_uninterrupted_run

python -m pytest -p no:cacheprovider --tb=short \
  experiments/generative_mechanics/next_tracks_v06/gameplay_v04/tests/test_p2_reference_library_resume_review.py::ReferenceLibraryResumeReviewTests::test_passive_cap_dual_owner_nested_notifications_terminate_refetched
```

Final disposition: **ACCEPT**, subject to the recorded non-blocking TEST_GAP
and scope notes. No implementation change is requested for P2.2.

## Main Acceptance Addendum (2026-11-02)

The independent report above was completed by Rawls with no product/library
changes. Main reviewed the three new probes and found an unused import of
`ReferenceLibraryReviewTests` in the resume module. Pytest collected that
imported class's eight methods again during the first resume command.
Thus "the combined focused suite was not rerun" means the original 42-test
combined command was not repeated; the initial 10-test resume run DID
recollect eight original review methods. Those calls are charged in the
rollout ledger, not erased or counted as zero overhead.

Main removed ONLY that unused import to prevent duplicate collection. The
original eight requirements remain in Mill's original file; none of their
assertions or the three new assertions were changed. Main re-ran the new
class: **3 passed in 15.11s**. Source SHA-256 after this hygiene edit:
`ef73d64ea7f99128c2dab603f5d26e665debf4575f089d31eb2d2d16a2d837b4`. Evidence:
`evidence/p2_lib_main_resume_hygiene.log` and `_meta.json`.
The report's original resume-test hash remains the pre-hygiene QA hash.

Original tool-output strings for the collection/timing/stale-component
failures are preserved with their actual rollout ordinals in
`evidence/p2_lib_resume_review_failure_outputs.json`. These are rollout
strings, not a claim of raw pytest stdout bytes. They are review-local
fixture errors, not product fixes. The ineffective-iteration product rule
is not reset or bypassed by changing a product expectation.

Main accepts the independent review's bounded evidence. The original
non-blocking tautological assertion is preserved as a documented historical
test-quality issue; the exact dual-owner assertion in the new module is the
actual cap-owner proof. Full P2 Gate acceptance still requires the frozen
cross-module regression and accounting to pass. No Alpha UI or generation
success is inferred from these mechanics tests.

## Main Final Gate Outcome

Frozen cross-module regression p2_lib_frozen_20261102: 1076 passed / 4257 subtests, exit 0, 319 unchanged Python hashes and 130 unchanged protected files. Accounting p2_2 passed with Unknown 0 and all budget limits within. P2 Gate accepted for the explicitly supported subset; scope notes remain.
