# Subagent Invocation Log

The collaboration API exposes agent creation but no model or reasoning-effort
selector. Model and effort are therefore `unverified`; no role is claimed to be
Luna High.

| Role | Agent ID | Verified model/effort | Scope | Initial result |
|---|---|---|---|---|
| A | `/root/v04_gate0_a` | unverified | Gate 0 reproduction; Gate 0-1 substrate | Reproduced all three Gate 0 defects |
| B | `/root/v04_design_b` | unverified | Gate 2 contract audit | Read-only dependency and schema proposal |
| C | `/root/v04_design_c` | unverified | Gate 3 and registry contract audit | Read-only dependency and schema proposal |

Roles E and D are deliberately deferred until their upstream interfaces exist.
D will be invoked after integration and will use independent test logic.
