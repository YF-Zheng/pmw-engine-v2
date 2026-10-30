# C4.3 Independent Active Condition Review

Date: 2026-10-29. Branch:
`feature/alpha-v02-seventh-night`. Baseline:
`576048b0f4796695a63883b46c6c62b03ef92b8b`.

## Verdict

ACCEPT the bounded C4.3 implementation at the independently tested scope.
No genuine current production finding remains in the eight-method independent
QA suite. Production stayed frozen at the Main-supplied hashes:

- `actions.py`: `f94afaed4e1d225eb15e48151436f2480b6701754b7be362b9a9b24bfc87bb6a`
- `skills.py`: `2ce87fe45d8964ef5ef16bd76df8e2132a1f24d27fe5ae33192bb98e8678443c`
- Owner test: `8aeb6b43e690cbcb87a3c70438b63c4dd1de9ec32c21cb4393cb4ce0eaae01d8`
- Independent QA test:
  `387429fa72e554d23fd2c7bb547d3fe5b5cea599b57a5b5b80e24dafabd3b53f`

The final fresh-process hash guard imported both modules from the current PMW
tree and matched the frozen hashes. Main additionally verified that loaded
bytecode matches the exact current compile. No production or owner-test edit
was made by QA.

## Real Baseline Red

The real `576048b` Git archive was exported only beneath PMW
`evidence/test_tmp`, with child `cwd` and `PYTHONPATH` at the export. Imported
module paths were asserted under that export, and imported hashes were checked:

- Historical `actions.py`:
  `9e2d3589990d7dbf915af00a9a0434241f831903fa92d49ebc542cb8e1f89530`
- Historical `skills.py`:
  `5e6569c1ad5bbe3304077f8dcdc0e54349f9a75140a470059fa09d5d32b1102a`

The ordinary parsed/material/registry/equipped timed Skill had a false typed
top-level condition. It nevertheless cast: Mana `5.0 -> 4.0`, HP
`40.0 -> 42.0`, and one paid Tick changed sim time `0.0 -> 1.0`. `before` was
an immutable deep snapshot taken before actual execution. This is a real
historical baseline failure.

Evidence:

- `evidence/c4_active_review_baseline_real_576048b.log`
  (`2ecd2f9e4bab970193b6ea70909d37759a66fb548e36ad291493257fa639248b`)
- `evidence/c4_active_review_baseline_real_576048b.json`
  (`0d86d5c18423deee4b0ed50980aee10eda35366f780de9549d7ae505ba5fa1b8`)
- `evidence/c4_active_review_baseline_real_probe_576048b.py`
  (`f93336cc90214d9918af993df2b17ae94cda93b8aff3e9a042d1ca3a0fd1a275`)

Main's separate finite-combat fixture is distinct: false condition paid two
Ticks and Mana `20 -> 16`, not the baseline archive probe's one Tick and
`1` Mana. Main's `92/27` cross result, combat rollback, and historical
Basic/AST parity are Main evidence, not QA claims.

## Baseline Attribution Correction

The earlier `c4_active_review_baseline_576048b.json` and probe were mixed or
current-module evidence and were overwritten during correction. The original
JSON size `3250` and probe size `11574` were **not bytewise preserved by QA**.
No bytewise-preservation claim is made. The surviving older invalid baseline
log remains at `c4_active_review_baseline_576048b.log`, hash
`d522d1083d5b463b4d0b314698172fd58e4e1896f0b874d13a64b1f1558026f8`.
Main preserved the actual invalid baseline outputs at
`evidence/c4_active_main_baseline_attribution_outputs.json`.

The corrected real-only outputs above are not a claim that the overwritten
files still exist. The earlier mixed-baseline output and the old
`PYTHONPATH`/module-cache test failures are invalid attribution, not product
regressions.

## Independent Current Coverage

Final command, from PMW with fresh `PYTHONPATH=<PMW>/src;<PMW>`, explicit
PMW-local `TEMP/TMP/TMPDIR`, empty PMW-local `PYTHONPYCACHEPREFIX`,
`PYTHONDONTWRITEBYTECODE=1`, `PYTHONIOENCODING=utf8`, and `-B`:

```text
python -B docs/agent_bootstrap/evidence/c4_active_review_current_hashcheck.py
python -B -m pytest -q -p no:cacheprovider experiments/generative_mechanics/next_tracks_v06/gameplay_v04/tests/test_sandbox_active_condition_review.py
```

Result: hash guard matched; `8 passed, 8 subtests passed in 1.74s`.
Evidence:

- `evidence/c4_active_review_hashcheck_final_18.log`
  (`20ae08c976d8f165c7f947c1dcc14624ff870713b9f20142bbdc5b5d7d46d3da`)
- `evidence/c4_active_review_focused_final_18.log`
  (`b5ea5d542fb19904a0431c148e12e03494415e9328f79626912e0482dff8ee8c`)

The eight methods cover:

1. One parsed Skill reference shared by player and NPC; Mana `5`, cost `4`
   accepts to `1`; false actor rejects before cost/time.
2. Same player transitions `5 -> 1`, false rejection, then the real same-player
   `basic_wait` restores `1 -> 6`, and the unchanged Skill reaccepts `6 -> 2`
   with no registry rebuild or hash change.
3. Player/NPC actor IDs, same Skill canonical hash/version, compatible
   current-area Field and target/current-area/typed-condition bounds.
4. Raw absent and explicit-null Basic conditions preserve exact historical
   document SHA256 identities. The expected values come from Main's independent
   Git-baseline algorithm output, not from invoking the new parser twice.
5. A non-null forged conditional `basic_attack` gets a different hash, is
   denied without gaining slot-free authority, and parsing does not mutate the
   candidate. The immutable comparison snapshot is taken after deliberate
   forgery and immediately before parsing.
6. Cost-modifier quote timing and conditional-Effect post-cost timing remain
   distinct in a real compiled session.
7. Checkpoint save/load preserves Skill/Action hashes and condition; after
   load, `5 -> 1` accepts and the following call rejects for the condition
   before mutation.
8. C4.2 passive dispatch remains separate: passive Action condition is
   `always`, victim-player false passive records a condition skip, and genuine
   dispatch still applies the shield without Mana debit.

Earlier failed methods were fixture/environment issues, not product findings:
the forged snapshot preceded forgery; direct timing used an uninstalled
Action; NPC passives were not the damage victim; checkpoint used HP rather than
the resource boundary; stale/mixed imports were possible; and focused11 used
the wrong same-player "reenable" expectation. Those logs remain preserved.

## Cross And Regression Results

Fresh current-process owner test:
`7 passed, 2 subtests passed in 1.14s`
(`evidence/c4_active_review_owner_final_18.log`).

Fresh bounded pre-existing Gameplay regression subset (blueprints, dynamics,
actions, effects/hooks, loadout integration, registry checkpoint):
`58 passed, 2 subtests passed in 12.84s`
(`evidence/c4_active_review_legacy_final_18.log`).

Main's frozen full regression/checkpoint remain required before acceptance.
This review does not claim full P1/P2, UI/browser/public playtest, arbitrary
trigger support, or a new production change.

## QA-Owned Files And Freeze

- `experiments/generative_mechanics/next_tracks_v06/gameplay_v04/tests/test_sandbox_active_condition_review.py`
  (`387429fa72e554d23fd2c7bb547d3fe5b5cea599b57a5b5b80e24dafabd3b53f`)
- `docs/agent_bootstrap/C4_ACTIVE_CONDITION_REVIEW.md`
- `docs/agent_bootstrap/evidence/c4_active_review*` unique evidence only

QA is frozen. No further source edits or speculative extensions.
