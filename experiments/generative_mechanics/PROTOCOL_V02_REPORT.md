# Protocol v0.2 implementation report

Date: 2026-10-05

## Completed gates

- Generation v0.2: 3 baselines x 3 bands; per-sample ID, nonce, seed, prompt,
  and prompt hash are unique and deterministic.
- Prompt surface: public channel semantics and generic-law projection; six
  authoritative calibration examples; no evaluation world or Oracle state.
- Power: one horizon-aware `PowerScaleContract`; batch, CLI and build search
  share the implementation.
- Contextual power: exact scenario backpack 10 -> 11 search, active <= 6 and
  slots <= 6; CI deferral is explicit unavailable, never zero.
- Evaluation tasks: intrinsic and contextual estimands use separate Oracle
  targets and are never compared across tasks.
- Scenarios: calibration/evaluation/Oracle split; 144 deterministic Oracle
  micro-scenarios; public fields remain in `[0, 1]` under traced bounds and
  explicit dissipation laws.
- Controls: isolated direct effect, world substrate, and expression-matched
  direct outcome.
- Reporting: structural/parametric diversity and baseline-stratified
  cross-environment summaries.
- Revision terminology: deterministic controller, not LLM self-revision.
- Archives: fixed order, timestamp, Unix mode, compression, and SHA-256.

## Verification

- Generative Mechanics: 185 tests passed.
- PMW Core: 254 tests passed.
- Frozen Core manifest SHA-256:
  `0cb9271e7dcfa9b1882246190f78afddfb1f153e699c7609182cbcd921cacf5d`.
- Provider-request dry run: 135 rows across nine cells; 135 unique IDs, seeds,
  nonces, and prompt hashes; no forbidden evaluation/Oracle strings detected.
- End-to-end fixture dry run: generation, batch, v0.2 analysis, and 15 figure
  artifacts completed.
- One real PMW exact contextual context: 848 legal builds before, 1,486 after,
  2,334 total; 29.89 seconds wall time on this host.

## External blocker

No provider credential is present in the execution environment. Therefore the
135-response genuine-model pilot has not been run, and no fixture result is
reported as model evidence. The canonical pilot request JSONL is generated for
the final artifact archive and can be submitted unchanged through a provider
adapter.
