# C4.4 Dynamics Modifier Action Review

## Verdict

**ACCEPT.**

I independently reviewed the four frozen production files against the full
C4.4 design, including `Real Acceptance Evidence` and `Frozen Schema And
Validation Details`. I found no genuine product defect in the reviewed scope.
The final independent review suite passes 14/14, and both bounded legacy runs
pass.

## Findings

No genuine C4.4 product findings.

The parser is closed and strict at
`experiments/generative_mechanics/next_tracks_v06/gameplay_v04/effects.py:70`
and validates the frozen ranges at
`effects.py:181`, `effects.py:209`, and `effects.py:229`. Passive Skills are
rejected at `skills.py:115`, while the three-point base cost is at
`skills.py:28`.

Staged execution, native Source validation, duplicate-priority inspection
across persistent and temporary layers, capacity handling, and deterministic
Source identity are at `actions.py:778`, `actions.py:806`, `actions.py:807`,
and `actions.py:856`. Two new source writers are prevented from reusing one
slot by `actions.py:779` and `actions.py:850`. Same-Action source-footprint
conflicts are rejected at `actions.py:344`, with parser-level footprint
conflicts at `actions.py:228`.

The existing Action transaction stages, resolves, advances real time, and only
then publishes at `actions.py:642` through `actions.py:647`, so rejection and
late-Tick failure do not leak Mana, time, revisions, schedule, or stats.
Expiry is scheduled through the existing Laws at `action_compiler.py:152`;
the owned slot is cleared and the scheduled handle canceled at
`action_compiler.py:170`.

### Duration 1 Assessment

Duration `1` is legal under the frozen schema but has no Tick in which its
override is effective. This is the accepted scheduler-before-Tick convention,
not a C4.4 product finding:

- `actions.py:827` schedules expiry at `sim_time + duration`.
- The paid Action has already advanced its duration Tick before that expiry is
  scheduled, so a duration-1 modifier never wins that first Tick.
- The next Tick runs due expiry first, leaving zero effective Ticks.

This matches the existing `modify_rate` lifecycle convention. The independent
test `test_duration_one_is_legal_and_expires_before_its_unpaid_tick` at
`experiments/generative_mechanics/next_tracks_v06/gameplay_v04/tests/test_sandbox_dynamics_action_review.py:551`
asserts the real behavior: legal one-Tick cost, no override effect, cleared
slot, no expiry handle, and no scheduled event. The design explicitly permits
duration `1..64` and specifies this scheduler-before-Tick rule; treating
`1` as a no-op is therefore convention, not a defect.

## Independent Test Coverage

The independent suite is
`experiments/generative_mechanics/next_tracks_v06/gameplay_v04/tests/test_sandbox_dynamics_action_review.py`.
It covers:

- One parsed Skill equipped by human Player and NPC, executed as real timed
  Actions in two Areas with quantitatively different Tick evolution.
- A paid `none` override freezing for duration 3, exact expiry before Tick 3,
  and restoration from the CURRENT baseline after that baseline changes.
- Hand-calculated add/multiply behavior and effective-rate clamping without
  using a reference evaluator for expected values.
- Independent lower and higher priority Sources surviving exact owner/handle
  expiry without sticky curves.
- Duplicate persistent and temporary curve priority denials with complete
  pre/post snapshots.
- Null, boolean, string, NaN, infinity, out-of-range, unknown-key, passive,
  remote-target, and capacity-full schema denials.
- Late-Tick rollback and publication-denial atomicity.
- Distinct temporary slot allocation and source-footprint conflicts.
- Save/load rebuild preserving Action and Skill hashes and continuation.
- All 13 old Effect kinds retaining their HEAD-era Action and raw Skill
  canonical hashes.

The no-publication oracle snapshots world state, runtime stats, revision,
object revision, state-closure state, scheduled events, and profiles. The
duration-1 assertion is included separately so the accepted no-op convention
is explicit rather than silently untested.

## Evidence Counts

- Independent review suite:
  `docs/agent_bootstrap/evidence/c4_dynamics_review_focused_final.log`:
  **14 tests, 14 OK.**
- Isolated HEAD archive red run:
  `docs/agent_bootstrap/evidence/c4_dynamics_review_red.log`:
  **318 tests run, 4 failures, 9 errors.** The 13 failing/erroring review
  requirements are the expected parser/material rejection of the new kind;
  all 13 old-hash subtests pass.
- Bounded `gameplay_v04/tests` legacy run:
  `docs/agent_bootstrap/evidence/c4_dynamics_review_legacy_gameplay_v04.log`:
  **395 tests, 395 OK.**
- Bounded `next_tracks_v06/tests` legacy run:
  `docs/agent_bootstrap/evidence/c4_dynamics_review_legacy_next_tracks_v06.log`:
  **183 tests, 183 OK.**

## Fixture Corrections (Not Product Defects)

I corrected only my independent test fixtures. No production or owner test was
edited during the review.

1. The first two-new-writes fixture expected runtime slot rejection but was
   first caught by the parser's same-Action footprint conflict. I changed the
   fixture to assert that earlier rejection rather than weakening the rule.
   Recorded in `c4_dynamics_review_focused_01.log`.
2. The save/load continuation fixture put an existing overlapping Source in
   the same Area, so the intended second cast correctly hit a priority
   conflict. I isolated the continuation fixture from the priority fixture.
   Recorded in `c4_dynamics_review_focused_01.log`.
3. The legacy-footprint fixture used a material that authorized only the new
   kind, causing an earlier material-authorization failure. I used an Action
   parser fixture without that material gate. Recorded in
   `c4_dynamics_review_focused_01.log`.
4. The schema matrix initially treated the valid existing `field_id="heat"`
   as invalid. I removed that invalid case from the rejection set. Recorded in
   `c4_dynamics_review_focused_01.log`.
5. The lower/higher priority fixture accidentally supplied an explicit
   `distance_squared` curve to its lower Source. I changed the fixture to the
   intended lower linear Source. Recorded in
   `c4_dynamics_review_focused_01.log`.
6. The `none`-curve fixture initially expected one too many evolution steps
   in the second Area. I recomputed the hand arithmetic and corrected the
   expected value, then corrected the subsequent value as well. Recorded in
   `c4_dynamics_review_focused_01.log` and
   `c4_dynamics_review_focused_02.log`.
7. The same-Skill fixture initially expected only the immediately paid Tick
   for Player while the real path had already advanced further. I recomputed
   both Areas' full trajectories and corrected the expected values. Recorded
   in `c4_dynamics_review_focused_01.log`, `_02.log`, `_03.log`, and
   `_04.log`.
8. The trace assertion initially looked for a nonexistent law-ID shape. I
   changed it to assert the actual accepted dynamics law prefix and
   temporary-slot match. Recorded in `c4_dynamics_review_focused_05.log`.
9. The final schedule assertion expected both Action expiry handles after the
   Player's expiry had already fired and been removed. I corrected it to assert
   the remaining NPC handle. Recorded in
   `c4_dynamics_review_focused_06.log`.
10. The new publication-denial fixture placed its conflicting priority Source
    in the NPC's Area instead of the Player's cast Area. I corrected the Area;
    this was a fixture error, not a product defect. (Focused evidence predates
    this added assertion; the final 14-test run covers it.)

All fixture issues were resolved without changing production behavior,
lowering the frozen schema, or suppressing a requirement.

## HEAD Archive And Baseline Rationale

The HEAD archive evidence is:

- `docs/agent_bootstrap/evidence/c4_dynamics_review_head/tree.tar`
  - **1 file**, **98,549,760 bytes**
  - SHA256 `587F21C3A05ABF67F0B7FA5EEF510575C9A5CE27E67FBD7F66739302CB990364`
- `docs/agent_bootstrap/evidence/c4_dynamics_review_head_repo/`
  - **1,081 files**, **97,701,415 bytes**

`tree.tar` is an isolated `git archive` snapshot of HEAD
`7c975cb88def0eebf7c137e0b9305b74b8be1257`, created before the owner's
`dynamics_modifier` work was reviewed. `c4_dynamics_review_head_repo/` is that
archive extracted into a separate workspace copy. The independent review test
was copied into that extracted tree only for the red reproduction. This avoided
trusting the working tree or the owner's new test, and let me verify that the
requirements reject the absent kind on clean HEAD while old canonical hashes
still pass.

The 13 old Effect Action and raw Skill hash oracles embedded in the review
test were generated independently from that HEAD archive, before reading the
owner's new test. The red run confirms those old hashes remain green on HEAD;
the final run confirms they are unchanged under the accepted implementation.

## Reviewed Production SHA256

All values below were recomputed after the owner froze the production files.

- `effects.py`: `63DA4D1B21D582D0C2BAD8E4FFCF1FD323FBCCAAC65610A42E678A8C54D983CC`
- `skills.py`: `65E56628614B649E47BEE5E10875F5E114213250BF8676EE6B34E68DADF4AFBF`
- `actions.py`: `2E379BEF9E9180B4465D03F7D3086D7F25209A60A7BE9A25AAA47A411241BFA9`
- `action_compiler.py`: `DBB9A938C8CCD79D7084219B14C31242F5BA2BD38578F73AE45820B59400802E`
- Owner test `test_sandbox_dynamics_action.py`: `44AF4FB9FB65FF1B93C7597BEDE62EC563BE7E4580DDF4CE15FF6D331363A600`
- Independent review test `test_sandbox_dynamics_action_review.py`: `746FCC351DA8E10E6FF3FBB243ED8AAE00ED743CFC8DBA98A76BEAC42E9E4739`

The owner's test source was not read; I verified its existence and hash only.

## Critical Diff Assessment

- **Transaction/publication:** accepted. Staging wraps authorization,
  resolution, hook dispatch, and real time spending; publication occurs only
  after all stages succeed. Rejection snapshots and late-failure tests show no
  cost, time, revision, stats, schedule, or world mutation leak.
- **Slot reuse:** accepted. Temporary slot selection skips both active slots
  and slots already reserved by another new write in the same staged Action.
- **Priority checks:** accepted. Both persistent and temporary active Sources
  are scanned before publication; duplicate priorities deny atomically.
- **Footprint conflicts:** accepted. Dynamics modifier reserves both rate and
  target source footprints, conflicts with legacy source writers, and prevents
  two new writes from sharing a slot.
- **Old-kind hashes:** accepted. All 13 old Effect Action and raw Skill hashes
  remain exactly equal to the independently generated HEAD oracles.
- **Save/load:** accepted. Checkpoint rebuild preserves new Action and Skill
  hashes and continues with identical state.

No publication or slot-reuse defect was found in the reviewed diff.
