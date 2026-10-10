# Subagent Invocation Log

The collaboration API exposes agent creation but no model or reasoning-effort
selector. Model and effort are therefore `unverified`; no role is claimed to be
Luna High.

| Role | Agent ID | Verified model/effort | Scope | Initial result |
|---|---|---|---|---|
| A | `/root/v04_gate0_a` | unverified | Gate 0 reproduction/fix; Gate 1 substrate | Gate 0 complete; Gate 1 implementation produced, then agent stopped on service usage limit; owner reviewed, fixed selector endpoint validation, tested and integrated |
| B | `/root/v04_design_b` | unverified | Gate 2 contract audit and implementation | G2.01-G2.10 implemented; owner corrected one audit payload value, reran tests, and integrated |
| C | `/root/v04_design_c` | unverified | Gate 3 and registry contract audit | Read-only dependency and schema proposal |
| E | `/root/v04_design_e` | unverified | Gate 4 observation, simulation, and AI audit | Read-only contract and adversarial-test proposal |

Role E implementation and Role D independent QA are deliberately deferred until
their upstream interfaces exist. D will be invoked after integration and will
use independent test logic.
