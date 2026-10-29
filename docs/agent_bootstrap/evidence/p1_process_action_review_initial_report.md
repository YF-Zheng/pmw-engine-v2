# P1 Process Action Independent Review

Scope: bounded independent QA only. No production, owner test, manifest,
global configuration, or Git changes were made. Temporary paths were forced
to `docs/agent_bootstrap/evidence/test_tmp`, inside the PMW repository.

## Deliverable

Created five high-value upstream-facing tests in
`experiments/generative_mechanics/next_tracks_v06/gameplay_v04/tests/test_sandbox_process_action_review.py`,
reusing the registered/equipped fixtures and snapshot helpers from
`test_sandbox_process_action.py`.

1. Compound Field effect plus real `process_start`: success updates both the
   Field and Process; a required input preflight failure retains neither.
2. A real emitted start-cascade Law emits a downstream event only after the
   Process has activated, then raises `ZeroDivisionError`. Full state,
   scheduler, revisions, stats, and runtime identity roll back.
3. A final quoted duration modifier raises the charge from 2 to 3, and a real
   second world-tick failure rolls back the complete action and time charge.
4. A changed trusted compiled Process profile is rejected against an otherwise
   valid checkpoint; the unchanged compiled continuation matches an ordinary
   timed Process tick.
5. The observation projection omits the private Process and Stock entities and
   the hidden action; `basic_wait` still simulates successfully from the
   actor-safe projection.

The tests use standard `ActionRequest`, registered/equipped skill flow, real
Process laws, real world ticks, and owner fixtures. The cascade test adds only
test-local Laws to the runtime; production files were not patched at runtime
and no production source was edited.

## Exact Command And Result

```powershell
$env:PYTHONPATH='src'
$env:PYTHONDONTWRITEBYTECODE='1'
$env:TEMP=(Resolve-Path 'docs/agent_bootstrap/evidence/test_tmp').Path
$env:TMP=$env:TEMP
python -m pytest -p no:cacheprovider experiments/generative_mechanics/next_tracks_v06/gameplay_v04/tests/test_sandbox_process_action_review.py -q
```

```text
.....                                                                    [100%]
5 passed in 1.58s
```

Exact saved output:
`docs/agent_bootstrap/evidence/p1_process_action_review_focused.txt`.

An additional `unittest -v` run reported `Ran 5 tests`, `OK`; its console
output was not separately persisted because no extra evidence filename was
needed.

## Findings

No production counterexample was found. The focused tests confirm:

- `actions.py:185` stages the complete action before publish, so a late
  cascade exception cannot partially publish process start, Field writes,
  scheduled expiry work, revisions, or stats.
- `actions.py:363` charges the final modified quote and stages time/ticks in
  the same transaction; a second-tick failure leaves the original runtime
  untouched.
- `checkpoint.py:68` and `checkpoint.py:90` reject Process-law/profile changes
  by trusted static-Law comparison even when the checkpoint payload hash is
  valid.
- `simulation.py:244` excludes hidden Process authority from the actor-safe
  projection without blocking ordinary basic-action simulation.

The checkpoint rejection is intentionally coarse: a changed Process profile is
rejected as a trusted static-Law configuration mismatch, not with a dedicated
profile-hash diagnostic. This is fail-closed and required no production change.

## Frozen SHA256

New test:

```text
92E40D2827969EDA52A2905C894519EC460817982B88CC285959EC12B68CF2E1  experiments/generative_mechanics/next_tracks_v06/gameplay_v04/tests/test_sandbox_process_action_review.py
```

Frozen production files reviewed by this QA:

```text
85DD7E0157B3FE81E4FADA403F5D58B2E12AE2D2B4585363DA7F0F5CE2D38045  gameplay_v04/action_compiler.py
E84D96CABE3EEE6436A185C11FE0C8018644B7F113D1D28604BA719A652996BC  gameplay_v04/actions.py
ABE021DB1A3519C98961B4EA23779BD3560D63BA22B03929DD785F2B54FD03B3  gameplay_v04/content_compiler.py
345203434320A56DF3932560FDD79ACE3AA59AE94EE016DCD06728B0DC89790D  gameplay_v04/effects.py
C7550A9FAC98381685D38633E48746E941AD66C69A1FA3AD6151850A12C43590  gameplay_v04/processes.py
C492F353896066DD3E6D4155250C8349AC488D7DC43649C06207786EDFAFBEB9  gameplay_v04/registry.py
B6C812AA0F5C13B82357686051D0F5CB7595359812B29C166B6E85A92AA7977A  gameplay_v04/simulation.py
443E4DFCDA062F39152A937381442032EFD5395B285B5EA89F0EF912EDC16CA4  gameplay_v04/transactions.py
71E83BDB00B34FB0444D58F764DE9F84C877187BB7F295223B44F6C67F6ADB2C  gameplay_v04/checkpoint.py
FCEAF8464F2A564976794BA2385550D36727EA275F8F4C7957FB355B0B2E1A3F  gameplay_v04/skills.py
```

## Residual Risk

- The divide-by-zero test uses test-local Laws to force a real downstream
  cascade failure; it does not add a malformed production Law.
- Checkpoint rejection is verified at the static-Law/profile boundary, not by
  a dedicated profile-diagnostic assertion.
- No provider/game-generation call, new clock, or broad regression was run by
  this worker. The main owner retains full frozen regression.

QA_SOURCE_FROZEN
