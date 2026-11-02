# P3.1B Offline Replay / Compile Independent QA

Status: **ACCEPT (offline P3.1B scope only)**

Reviewed branch `feature/alpha-v02-seventh-night` at HEAD
`65926940ca48ede699df219a39ef0143df1d2118`. The owner's closed hashes
matched Main's hashes before the selected run. Review was offline and
read-only outside the exclusive reviewer test and evidence paths. This
report makes no P3 Gate, batch, live-provider, registration, Sandbox, or
world-behavior claim.

## Findings

### Resolved preliminary defect: escaped lone surrogates

Initial classification: **PRODUCT_DEFECT** (1). Final classification:
**resolved by the frozen fix**; no open product defect remains in the
reviewed offline scope.

`P2` here is defect priority only. It is not a P2 Gate regression claim or
scope. The defect is in the new P3 replay decoder boundary.

`ReplayReply` rejects raw Python surrogates because they cannot encode as
UTF-8, but `decode_candidate` accepts JSON escape sequences such as
`{"x":"\\ud800"}`. Python's `json.loads` materializes those as lone
surrogate code points; the current string-length and JSON-shape checks do
not verify Unicode scalar validity.

This is not only a decoder acceptance issue. A full legal candidate with
`display.summary = "Review <lone surrogate> fixture."` reaches
`compiled_unregistered` and preserves U+D800 in `SkillIR.canonical_json`.
The frozen P3.1B boundary says lone surrogates must fail as typed candidate
rejections. The result remains unaccepted, unregistered, and unsandboxed;
there is no world/registration side effect. The defect is that the compile
Gate accepts input that the frozen ingress contract requires it to reject.

Observed repro values:

- Reply size: 813 UTF-8 bytes.
- Reply SHA-256:
  `332162a2fd96cf6ef52ea2d61ebcd4f5df61f98cad69d6482ee61e92e490d77c`.
- Status: `compiled_unregistered`.
- Attempt: accepted, stage `compiled`.
- IR hash:
  `b3d1f2f1325cea6e3723fc914b1829f360c7d23f119509875668ca0d73aea673`.
- Result hash:
  `b1283483c8be13d8c3efe953de79d5c780ec18b625c2b63d31a74bf1cf8fffb5`.
- Stored summary contains code point U+D800 (55296).

Exact repro:

```powershell
$env:PYTHONPATH='src'
$env:PYTHONDONTWRITEBYTECODE='1'
$env:PYTHONIOENCODING='utf-8'
python -m pytest -p no:cacheprovider -q `
  experiments/generative_mechanics/next_tracks_v06/gameplay_v04/tests/test_skill_designer_offline_pipeline_review.py `
  -k lone_surrogate
```

The four direct probes and one pipeline probe were the five preliminary
failures. Their requirements were preserved unchanged and all pass in the
final run. The original red evidence remains below.

## Verified Boundaries

- Minimal independent legal IR compiles only as `compiled_unregistered`;
  `accepted=false`, Sandbox `not_run`, Register `not_available`, and usable
  pool `false` are asserted on both success and rejection.
- Replay is finite, capped at three replies, copied on construction, and
  records attempted calls with reply hashes. Exhaustion terminates
  immediately. Fixture provenance is authored/model-null, and no generation,
  token, usage, or cost evidence is fabricated.
- Strict decoding rejects duplicate keys, non-object roots, NaN/Infinity,
  excessive UTF-8 bytes, excessive depth, trailing prose, multiple fences,
  incomplete fences, and non-JSON fence languages as typed rejections.
- Unknown root and nested Effect keys are not dropped before the strict IR
  parser rejects them.
- Submitted material IDs must exactly equal the selected trusted set.
  Reordering of a two-ID selection is rejected as well as omission,
  substitution, duplication, and forged additions.
- The pipeline keeps the authority rederived from validated material traits.
  The full `MaterialAuthority` tuple (IDs, kinds, selectors, budget) is
  compared with Context readback, and any mismatch aborts before replay.
- Altered material kinds/scopes/budget and forged displayed Context metadata
  cannot grant authority. `MaterialDefinition` is defensively reparsed, and
  aggregate budget overflow and malformed traits fail closed.
- Illegal effect kinds, targets/scopes, budget, triggers, booleans in integer
  fields, and unsupported event triggers are rejected by the accepted IR
  path rather than a reviewer reimplementation.
- Normalization changes only server-owned candidate ID/version and replay
  origin (`authored`, model `null`, internal Context hash). Names,
  descriptions, displays, costs, limits, conditions, entries, and Effects
  remain candidate content and are validated, not rewritten.
- `max_repairs` accepts only strict integers 0..2, with at most three calls.
  Invalid attempts remain individually recorded with structured feedback and
  hashes. Provider exhaustion and provider-contract failure stop immediately.
- Successful and rejected readbacks are canonical, defensively copied,
  deterministic for identical inputs, and expose stable result/IR/blueprint
  hashes. No registration, WorldState, Sandbox, or live transport API is
  imported or exposed.
- Reviewer fixtures are independent minimal IR plus boundary mutations; no
  owner test classes, library documents, candidate-ID special cases, or
  tautological assertions were used.

## Preliminary Test Counts (Superseded)

This was the pre-fix selected run, preserved for history and superseded by
the post-fix 234-test run below:

```text
python -m pytest -p no:cacheprovider -q <owner pipeline> <reviewer pipeline> <catalog owner> <catalog review> <Skill IR owner>
```

| Selected file or result | Collected | Pytest outcome |
|---|---:|---:|
| `test_skill_designer_offline_pipeline.py` | 49 | passed |
| `test_skill_designer_offline_pipeline_review.py` | 59 | 54 passed, 5 failed |
| `test_skill_designer_catalog_context.py` | 47 | passed |
| `test_skill_designer_catalog_context_review.py` | 49 | passed |
| `test_skill_ir.py` | 14 | passed |
| **Selected total** | **218** | **213 passed + 5 failed; 32 subtests passed** |

The five failures are the four escaped-surrogate parametrizations and the
end-to-end surrogate compile probe. No full repository run was performed;
Main owns complementary cross-module and integrity coverage.

## Preliminary Hashes (Superseded)

| File | SHA-256 | Lines |
|---|---|---:|
| `skill_designer/replay.py` | `796117306cfcce9f6f254b165d2173696dde4e27b60a7119bb5ee6a6fdb971c8` | 148 |
| `skill_designer/pipeline.py` | `910ed2254c54f3dea6ef6ca4fd8fd58407fb64a2e7d1e9a2a4e32551cf83c291` | 632 |
| `test_skill_designer_offline_pipeline.py` | `3c29497217f6c108724b0a8fdd3c19902df74b4d2b4a6b391fa37b22351bf242` | 607 |
| `test_skill_designer_offline_pipeline_review.py` | `4066cfdad4f6ac4a04e8103e684f8afa2471eb3260a038265d0cd3e0873bf0ba` | 859 |

Reviewer collection log reports 59 tests. Owner collection log reports 49
tests. The owner and reviewer hashes above are the exact reviewed inputs.
The pipeline hash shown here is the pre-fix hash; do not use it as the
current acceptance hash.

## Evidence

All raw logs are under `docs/agent_bootstrap/evidence/` and use unique names:

- `p3_offline_review_collect_20261102_01.log`
- `p3_offline_review_focused_20261102_01.log` through `_07.log`
- `p3_offline_review_stable_selected_20261102_01.log`
- `p3_offline_review_collect_final_20261102_02.log`
- `p3_offline_review_collect_per_file_20261102_03.log` through `_07.log`
- `p3_offline_owner_collect_qareview_20261102_02.log`
- `p3_offline_review_lone_surrogate_repro_20261102_01.json`
- `p3_offline_review_final_20261102.json`
- `p3_offline_review_final_20261102.log`
- `p3_offline_review_final_20261102_meta.json`

The red logs preserve earlier reviewer fixture mistakes as well as the
product defect. Scratch files and pytest temp state are confined to
`docs/agent_bootstrap/evidence/test_tmp`.

## Final Verification After Unicode Fix

The first product fix changed only `_bounded_json` in `pipeline.py`. It now
validates UTF-8 encodability for every decoded dictionary key and string
value, retaining the existing 4096-character string/key limit. The five
original failing requirements were retained unchanged and now pass. Valid
escaped surrogate pairs, literal emoji, and Chinese text remain legal and
compile with exact content.

Final selected run, executed once after the fix hashes were frozen:

| File | Collected | Outcome |
|---|---:|---:|
| `test_skill_designer_offline_pipeline.py` | 49 | passed |
| `test_skill_designer_offline_pipeline_review.py` | 59 | passed |
| `test_skill_designer_offline_pipeline_unicode_fix.py` | 16 | passed |
| `test_skill_designer_catalog_context.py` | 47 | passed |
| `test_skill_designer_catalog_context_review.py` | 49 | passed |
| `test_skill_ir.py` | 14 | passed |
| **Selected total** | **234** | **234 passed, 32 subtests passed** |

Final selected log:
`docs/agent_bootstrap/evidence/p3_offline_review_final_20261102.log`.
Machine-readable metadata:
`docs/agent_bootstrap/evidence/p3_offline_review_final_20261102_meta.json`.

Frozen final hashes:

| File | SHA-256 |
|---|---|
| `skill_designer/pipeline.py` | `61350f0de577e7a39e457cea870bd57a57cf057d85e6c288e13dbf647f9712a1` |
| `skill_designer/replay.py` | `796117306cfcce9f6f254b165d2173696dde4e27b60a7119bb5ee6a6fdb971c8` |
| `test_skill_designer_offline_pipeline.py` | `3c29497217f6c108724b0a8fdd3c19902df74b4d2b4a6b391fa37b22351bf242` |
| `test_skill_designer_offline_pipeline_review.py` | `4066cfdad4f6ac4a04e8103e684f8afa2471eb3260a038265d0cd3e0873bf0ba` |
| `test_skill_designer_offline_pipeline_unicode_fix.py` | `8b5ad0fb8ae096a1b2adfea8799f157e81702dd05ea93d711c3096424a34208d` |

Unresolved scope:

- Review evidence applies only to the frozen offline Replay/Compile boundary.
- No Sandbox execution or behavioral validation was performed.
- No registration, usable-pool admission, WorldState mutation, or live
  provider/generation call was performed or authorized.
- No P3 Gate, production batch, token, cost, or model-usage claim is made.
- Main retains complementary cross-module and repository-integrity coverage.

## Previous Preliminary Verdict

The preliminary verdict was **REJECT pending owner fix of escaped
lone-surrogate rejection**. The final offline-scope verdict is **ACCEPT**
after the fix above. Final counts are:

- `PRODUCT_DEFECT`: 0 (preliminary 1, resolved)
- `TEST_GAP`: 0
- `FIXTURE_ERROR`: 0
- `SCOPE_NOTE`: 0

The owner fix rejects lone surrogate code points in decoded JSON string
values and dictionary keys while preserving valid escaped pairs, literal
emoji, and Chinese text. Main retains the corrective hash gate. This review
does not claim that the remaining boundaries are ready for Sandbox, Register,
live generation, a P3 Gate, or a production batch.
