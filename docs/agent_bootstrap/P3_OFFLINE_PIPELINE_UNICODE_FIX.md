# P3.1B Offline Pipeline Unicode Fix

Status: first product fix implemented and verified on 2026-11-02 from
branch `feature/alpha-v02-seventh-night` at HEAD `6592694`. This note makes
no P3 Gate, batch, live-generation, registration, Sandbox, or world-behavior
claim.

## Defect

Independent P3.1B review found that JSON wire escapes such as `\ud800`
decoded into lone surrogate code points. The raw reply check encoded the
wire text (where the escape is ASCII), so it did not detect the surrogate
created by `json.loads`. A valid candidate containing that escaped surrogate
could reach `compiled_unregistered`.

## Change

Only `_bounded_json` changed in
`experiments/generative_mechanics/next_tracks_v06/gameplay_v04/skill_designer/pipeline.py`.
After decoding, every dictionary key and every string value is checked for
UTF-8 encodability. A `UnicodeEncodeError` becomes a typed
`_CandidateRejection("decode", "candidate contains invalid Unicode")`.
Keys also use the existing 4096-character bound.

The check runs on the decoded object before normalization or IR parsing.
Python's JSON decoder combines valid escaped high/low pairs into one scalar,
so escaped `\ud83d\ude80`, literal emoji, and Chinese text remain valid and
are preserved exactly. No replacement characters, stripping, or global
encoding changes are used.

## Tests

NEW focused suite:
`experiments/generative_mechanics/next_tracks_v06/gameplay_v04/tests/test_skill_designer_offline_pipeline_unicode_fix.py`

It covers:

- Escaped lone high/low surrogates in nested values and dictionary keys.
- Lone surrogates that would otherwise pass normalization in candidate
  identity, display summary, and replay/origin metadata, including bad keys.
- Typed decode-stage rejection with `max_repairs` exhausted at three attempts.
- Exact 4096-character key acceptance and 4097-character key rejection.
- Valid escaped surrogate pair, literal emoji, and Chinese text compiling
  with exact content preserved.

No public owner test class is imported. The suite uses its own minimal valid
IR and private test helpers.

## Verification

Environment: `PYTHONPATH=src`, `PYTHONDONTWRITEBYTECODE=1`,
`PYTHONIOENCODING=utf-8`, repo-local `TEMP/TMP/TMPDIR`,
`PYTHONPYCACHEPREFIX=docs/agent_bootstrap/evidence/test_tmp/pyc_offline_unicode_fix`,
and `pytest -p no:cacheprovider`.

Commands were also rerun after a compile check with a fresh cache prefix;
all four selected files were run once in each stable invocation:

```text
python -m pytest -p no:cacheprovider -q <owner pipeline> <review pipeline> <unicode fix> <Skill IR>
138 passed, 32 subtests passed in 13.47s
138 passed, 32 subtests passed in 12.41s
138 passed, 32 subtests passed in 13.30s
```

The selected files were the owner pipeline suite, old-owner review suite,
new Unicode fix suite, and `test_skill_ir.py`. The initial pre-fix run was
recorded as `5 failed, 117 passed, 32 subtests passed`; those five failures
were the existing review's lone-surrogate requirements. The earlier focused
run was `16 passed in 1.60s`; the post-compile-check focused rerun was
`16 passed in 1.65s`; the final focused rerun was `16 passed in 1.46s`.
QA failing assertions were not edited.

## Frozen Hashes

| File | SHA-256 | Lines |
|---|---|---:|
| `skill_designer/pipeline.py` final | `61350f0de577e7a39e457cea870bd57a57cf057d85e6c288e13dbf647f9712a1` | 710 |
| `test_skill_designer_offline_pipeline_unicode_fix.py` final | `8b5ad0fb8ae096a1b2adfea8799f157e81702dd05ea93d711c3096424a34208d` | 277 |

Pre-fix pipeline hash for the same NEW file:
`910ed2254c54f3dea6ef6ca4fd8fd58407fb64a2e7d1e9a2a4e32551cf83c291`.

## Evidence

All evidence names are unique under `docs/agent_bootstrap/evidence/`:

| File | SHA-256 |
|---|---|
| `p3_offline_unicode_fix_focused_attempt01_20261102.log` | `637ecc594562b247d0f6d19b23ff16e85ad7237e4ad95bbb252a823f77cdf915` |
| `p3_offline_unicode_fix_selected_attempt01_20261102.log` | `c22f619a0c98c4ecd6c57fd783bb6821f3d05b0ee4d8e9a78769d6f2354a9acd` |
| `p3_offline_unicode_fix_probe_attempt01_20261102.json` | `5223f4cbcc9ab8f703f15ff2a8ff55d32c2029a69b0e7445f57771b2a8830cfe` |
| `p3_offline_unicode_fix_focused_attempt02_20261102.log` | `03a8b81d3465ce774028dc289094a00aa2f7bb07bec3068d561286768a0cc51c` |
| `p3_offline_unicode_fix_selected_attempt02_20261102.log` | `b83f95f8c398af90dd398430361b57d3725ef6f8bf985ffb68d7cdb58aaddf69` |
| `p3_offline_unicode_fix_pre_fix_baseline_attempt00_20261102.log` | `ba356c9d76213aea4525fd6498dedf954cbbe2a7c505b48b048da3d45b0e95ea` |
| `p3_offline_unicode_fix_selected_final_20261102.log` | `5d53a023540ee8a0d69d3083c99d1111c8628490da59a1d5b4fa6b4dbb0f7f0d` |
| `p3_offline_unicode_fix_focused_final_20261102.log` | `d07eaeafa65df30e92f736a268ce4191f7c49e79d52d5675325413d4cebccace` |

The failed pre-fix run was not overwritten; its output is recorded in the
review evidence and copied into the unique baseline log above. All attempt
logs are unique and none was overwritten. Scratch/pytest temp state is
confined to `docs/agent_bootstrap/evidence/test_tmp`.

## Deliberate Limitations

- This fixes only the P3.1B offline decoder boundary.
- No P2 runtime/source file changed.
- No replay, Context, Catalog, owner test, QA test, ledger, or other document
  was edited by this fix.
- This is not a P3 Gate declaration and does not authorize live generation,
  registration, Sandbox execution, or WorldState mutation.
