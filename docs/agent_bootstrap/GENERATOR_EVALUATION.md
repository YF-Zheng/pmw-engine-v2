# Skill Designer Evaluation

P3 not started. No skill-generation corpus or success rate is claimed.

Confirmed local route from bootstrap: `tencent/deepseek-v4.1-flash` through
Magpie. This route differs from official public API alias `deepseek-flash`;
version/structured-output support must be tested on the actual route in P3.
Reference billing maps the route to public V4.1-Flash under user authorization,
not an assertion that the intranet billing or exact weights are identical.

Pipeline: Context -> Generate -> Parse -> Normalize -> Type Check -> Capability
Check -> Budget Check -> Compile -> Sandbox Test -> Register. Limit candidates,
request timeout and repair attempts. No model request in a world transaction.

Record batch/request IDs, model route/version, exact actual counters, canonical
IR/catalog hashes, parse rate, first-pass/repair compile rates, seven-operator
coverage, structure deduplication, complexity distribution, rejection reason,
normal-state triggerability and actual formal Engine trajectories.

Use behavior-based equivalence as well as AST hashes. A generated name or
description is not evidence of novelty or successful execution. If results
collapse to impulses/templates, fix the language/context/authority before
spending budget on more samples. Generate 200-500 only after P1/P2 gates pass.
