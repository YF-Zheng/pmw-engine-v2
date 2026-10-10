# Subagent Invocation Log

The collaboration API exposes agent creation but no model or reasoning-effort
selector. Model and effort are therefore `unverified`; no role is claimed to be
Luna High.

| Role | Agent ID | Verified model/effort | Scope | Initial result |
|---|---|---|---|---|
| A | `/root/v04_gate0_a` | unverified | Gate 0 reproduction/fix; Gate 1 substrate | Gate 0 complete; Gate 1 implementation produced, then agent stopped on service usage limit; owner reviewed, fixed selector endpoint validation, tested and integrated |
| B | `/root/v04_design_b` | unverified | Gate 2 contract audit and implementation | G2.01-G2.10 implemented; owner corrected one audit payload value, reran tests, and integrated |
| C | `/root/v04_design_c` | unverified | Gate 3 Weather/Ecology/Harvest/Skills implementation | Production implementation and tests produced, then agent stopped on service usage limit; Role B and owner reviewed and integrated it |
| B (takeover) | `/root/v04_design_b` | unverified | Gate 3 integration and adversarial fixes | Fixed reversible active loadout moves and Status-granted weather traits; Gate 3 and integration suites passed |
| E | `/root/v04_design_e` | unverified | Gate 4 observation, simulation, and AI implementation | Production implementation and tests produced, then agent stopped on service usage limit; owner fixed version-ref and utility gaps, reviewed, tested, and integrated |
| C2 | `/root/v04_gate4_registry` | unverified | Gate 4 runtime registry and checkpointing | Implemented G4.01-G4.02 with seven focused tests; owner independently reviewed and ran the combined Gate 1-4 suite |
| D | `/root/v04_gate5_qa` | unverified | Independent Gate 5 adversarial QA | Added six independent counterexamples/oracles, changed no production code, and reported PASS |

Role D was invoked after Gate 4 integration. Its six tests cover atomicity,
closed-form dynamics, Status/checkpoint/Scheduler lifecycle, combat ordering,
and hidden-information isolation. Full provenance and raw findings are in
`INDEPENDENT_QA_REPORT_V04.md`.
