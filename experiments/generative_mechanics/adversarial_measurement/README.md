# Free Evaluation v0.4 Adversarial Measurement Audit

This directory is a red-team measurement audit, not a green regression suite.
It targets the `de5451ceaeb020b2ceac1ce6b87752ade0988244` implementation candidate.

## Evidence layers

The preregistered suite contains 48 human-judged cases: 16 causal-depth, 16
cross-environment, and 16 structural-novelty attacks. Eight cases additionally
carry a `cross_metric` tag; this is an overlapping analysis label, not eight
extra cases. Expectations were serialized before execution and are bound by:

```text
adversarial_cases.jsonl SHA-256
4330f15b294c8b5ee255b95c70476eec0b37c3d8543384cea63970274927088f
```

The causal and cross-environment cases use controlled synthetic evaluator
inputs where exact causal graphs or DiD values must be known before execution.
They call the production v0.4 measurement functions but do not claim to be
complete world executions. `results/production_validation.json` is the
separate end-to-end layer: twelve validated SkillSpecs run through the trusted
compiler, fresh PMW worlds, registered environment assets, and production
evaluators.

The language cannot directly author generic world laws, alternate event ids,
or redundant hidden paths. Therefore the redundant-path and identity-shift
attacks remain synthetic unit attacks. This is an explicit construct-language
limitation, not concealed end-to-end evidence.

## Files

- `case_registry.py`: human-authored preregistration source.
- `adversarial_cases.jsonl`: frozen expectations; no observations.
- `cases/preregistration.json`: suite digest and one-shot execution state.
- `results/pre_fix_raw.jsonl`: immutable original `de5451c` evaluator output.
- `results/post_fix_raw.jsonl`: output after the two scoped corrections.
- `adversarial_results.jsonl`: per-case expectations, actual evidence,
  judgement, issue class, and pre/post comparison.
- `production_validation.py`: full-stack validation supplement.
- `summary.json`: machine-readable counts, findings, and recommendation.
- `ADVERSARIAL_AUDIT_REPORT.md`: scientific interpretation.

## Reproduction

Registration is intentionally one-shot. Do not rerun it over preserved audit
artifacts. In a clean copy, the sequence is:

```bash
PYTHONPATH=src:. python3 -m experiments.generative_mechanics.adversarial_measurement.run_audit register
PYTHONPATH=src:. python3 -m experiments.generative_mechanics.adversarial_measurement.run_audit execute
PYTHONPATH=src:. python3 -m experiments.generative_mechanics.adversarial_measurement.run_audit post-fix
PYTHONPATH=src:. python3 -m experiments.generative_mechanics.adversarial_measurement.production_validation
```

The pre-fix run was `36 PASS / 9 SUSPECT / 3 FAIL`. The scoped corrections
produce `39 PASS / 9 SUSPECT / 0 FAIL`; this does not make the protocol freeze
ready because the nine suspects are construct-level findings, not failing unit
tests to erase.
