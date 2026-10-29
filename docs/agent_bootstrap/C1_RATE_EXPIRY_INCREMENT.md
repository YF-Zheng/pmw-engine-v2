# C1 Process Expiry And Optional Controls

Continuous run parent 0e4e45b, feature/alpha-v02-seventh-night. Independent
review and complete frozen regression ACCEPTED. Full P1 remains open.
Proceed directly to C2 after saving this reviewed local checkpoint.

## Genuine Before Evidence

1. Original native _prepare_modify at clock2 computes now2 + storedremaining3
   against harddeadline3 and rejects a pure rate-only request, despite retaining
   the intended actual expiry3. A normal equipped paid start and real saturated
   ticks produced the state; no time/progress reset or fake game flags.
   Evidence: `evidence/c1_rate_expiry_before.json`.
2. Original parse_effect strict key equality makes BOTH process_rate and
   process_remaining_ticks mandatory, contradicting the either/or contract.
   Rate-only and remaining-only reject; both accept. Evidence:
   `evidence/c1_optional_fields_before.json`. This production defect was found
   by independent pure-rate QA, not dismissed as a fixture problem.

## Frozen Repair And Ownership

Lagrange owns processes.py and new test_sandbox_process_rate_expiry.py;
Linnaeus separately owns effects.py and new test_sandbox_process_optional_fields.py.
Russell owns new test_sandbox_process_rate_expiry_review.py, its review/report
and c1_rate_expiry_review evidence only. All workers are frozen and closed.
Actual child IDs and P1 assignments are in project_run.json. Main remains
tencent/gpt-6.1-sol; actual child response/model records identify Flash routes.

Rate-only preparation validates the actual future scheduled expiry against
harddeadline and retains exact stored duration/remaining/progress. Explicit
remaining changes still use now + remaining and elapsed + remaining. No new
clock, conversion policy, extended lifetime, reset or weakened ownership.
The parser requires template plus at least one valid numeric control, permits
omission of the other, rejects explicit nulls/unknown keys and retains strict
schemas for every other Effect. Existing numeric/material/time limits remain.

Frozen SHA256:

```text
4f5f3b6941913b68ff3badac0d57e1c0c24cadb6516b1ea17a23d6488b78815b processes.py
79d383be2a80dceea385a7a067b079ae8f341baf71721ff003e8944249f0df3e effects.py
3c0d7bf7f7f8e6c44bb1b52f37fbdf066ab7b53ab68b6208e2354e785ddec7de rate-expiry owner test
da5f3d7f90bb7be6829c8df24913fcbb3820931eefe62de56f91c71a5a79b2c9 optional-schema owner test
fcb243cdbfe6d55584f13f6b3cf945c9fbb2f80494dd38e61daeedbec115db23 independent review test
```

## Actual Review And Tests

- Native owner: 8 passed / 4 subtests in1.56s; related old suites 51/11 in9.03s.
- Optional schema plus old modify/start: 34/19 in5.66s; related48/34 in9.12s;
  broad Gameplay excluding live independent review:265/159 in97.40s.
- Independent frozen combined three-new-suite run:17 passed / 28 subtests in
  3.45s, of which four methods are independent QA. Original red logs retained.
- Independent positive pure-rate document omits remaining key; cold trusted
  catalog and normal player/NPC equipment/start reach now2 remaining3 hard3.
  Primary resolution pays Mana and preserves exact lifecycle; manual tick3
  verifies expiry. This is not by itself modifier time-budget payment.
- Main complementary genuine timed pure-rate calls for player/NPC: clock2->3,
  budget spent2->3/remaining10->9, Mana1, unchanged full Stock, exact expiry3.
  Evidence: `evidence/c1_rate_expiry_main_timed.json`.
- Invalid schedule, explicit extension, actual cascade/late-tick rollback and
  checkpoint continuation are covered. Duplicate schedule IDs reject at world
  validation, not specifically controller preparation.

Owner tests retaining maxduration slack or authoring both keys are supporting
coverage, not the original pure-rate defect reproduction. Independent formal
proof closes that gap. Prior both-parameter acceptance must not be described as
proof that optional controls already worked. Main corrected the review report's
timing prose only; all frozen code/test hashes remain unchanged.

## Frozen Gate, Accounting And Next

Reproduce full gate from repository root:

```powershell
.\tools\frozen_regression.ps1 -EvidencePrefix c1_rate_expiry_frozen
```

The script refuses to overwrite evidence, sets every temporary path inside PMW,
disables bytecode/cache and records all Python before/after hashes and command.
Raw log CRLF/traceback whitespace is retained rather than sanitizing evidence.
Outcome: **776 passed, 3,180 subtests passed in407.04s**, exit0. All276 Python
before/after hashes match; no source changes during execution. Exact metadata:
`evidence/c1_rate_expiry_frozen_full_regression_meta.json`; raw output:
`evidence/c1_rate_expiry_frozen_full_regression.txt`. No old tests changed.

After a green immutable full run, capture current main response ordinal range
and three actual children with continuous_accounting.ps1. `evidence/c1_cost_snapshot.json`
contains separate GPT/Flash actual counters, per-response prices and cumulative
budget. The subset is already in cumulative ledger, never added twice. Actual
cache is untouched; 97% only for pinned official-reference estimate. Bootstrap
stays separate; closing usage carries into the next refresh. Unknown stops spend.

Local checkpoint subject: `fix: preserve process expiry and accept optional controls`.
Then immediately proceed to C2 finite Stock-to-Field source per
`C2_STOCK_FIELD_DRIVE_DESIGN.md`; no end-of-chat handoff after one item. The
20:10 deadline and stage/MAX budget gates remain in force. P1/P2 are not complete
and no game-generation requests are permitted yet.
