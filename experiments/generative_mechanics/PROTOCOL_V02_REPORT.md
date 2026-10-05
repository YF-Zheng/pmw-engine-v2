# Protocol v0.2-Controlled implementation report

Date: 2026-10-05

## Completed gates

- Generation `gm-generation-v0.2-controlled`: 3 baselines x 3 bands;
  master-seed/sample-index coordinates deterministically bind each sample ID,
  nonce, seed, prompt, and prompt hash.
- Prompt surface: public channel semantics and generic-law projection; six
  authoritative examples matching the current baseline schema, selected from
  a frozen 18-example calibration artifact; no evaluation world or Oracle state.
- Compatibility: archived `gm-generation-v0.2` responses rebuild their original
  shared-six-example prompt. Legacy and Controlled hashes are not interchangeable.
- Power: one horizon-aware `PowerScaleContract`; batch, CLI and build search
  share the implementation.
- Contextual power: exact scenario backpack 10 -> 11 search, active <= 6 and
  slots <= 6; CI deferral is explicit unavailable, never zero.
- Evaluation tasks: intrinsic and contextual estimands use separate Oracle
  targets and are never compared across tasks.
- Scenarios: calibration/evaluation/Oracle split; 144 deterministic Oracle
  micro-scenarios for intrinsic utility; exact contextual utility defaults to
  a preregistered stratified 24-case subset, with nested 12/18 sensitivity
  profiles. Public fields remain in `[0, 1]` under traced bounds and explicit
  dissipation laws.
- Controls: isolated direct effect, world substrate, and expression-matched
  direct outcome.
- Reporting: structural/parametric diversity and baseline-stratified
  cross-environment summaries.
- Revision terminology: deterministic controller, not LLM self-revision.
- Archives: fixed order, timestamp, Unix mode, compression, and SHA-256.

## Verification

- Generative Mechanics: 214 tests passed in the final integrated run.
- PMW Core: 254 tests passed.
- Frozen Core manifest SHA-256:
  `0cb9271e7dcfa9b1882246190f78afddfb1f153e699c7609182cbcd921cacf5d`.
- Controlled provider-request dry run: 135 rows across nine cells; 135 unique
  IDs, seeds, nonces, and prompt hashes. Each prompt exposes only the six
  examples for its matching baseline. Request artifact SHA-256:
  `0beff04a675139519c0c3055427338027c66851576c45ba43db6ef456f230a58`.
- Controlled response dry run: one response per baseline passed strict CLI
  ingestion and the matching trusted compiler with zero ingestion errors.
- Free-Invention request dry run: 45 rows across three baselines; identity and
  prompt fields are unique and generation prompts contain no scored examples,
  target bands, power objectives, evaluator dimensions, or revision controller.
- End-to-end fixture dry run: generation, batch, v0.2 analysis, and 15 figure
  artifacts completed.
- One real PMW exact contextual context: 848 legal builds before, 1,486 after,
  2,334 total; 29.89 seconds wall time on this host.

## External blocker

No provider credential is present in the execution environment. Therefore the
135-response genuine-model pilot has not been run, and no fixture result is
reported as model evidence. A fresh Controlled request JSONL must be generated
for the final artifact archive before submission through a provider adapter.

Protocol v0.3-Free-Invention is a separate scaffold for coordinate-bound
requests, strict ingestion, trusted compilation, and static evidence. Its
dynamic invention dimensions are not yet implemented and are not reported as a
completed benchmark.

Oracle power means realized utility under the formal scorer and preregistered
world-state distribution. It is not an objective human ground truth for game
balance.
