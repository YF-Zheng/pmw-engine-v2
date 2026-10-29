# C4.3 Actual Active Skill Top-Level Condition Gate

Queued architecture only, after C4.1 condition safety and C4.2 actual passive
dispatch. No concurrent production authorization or full P1/P2 claim.

## Actual Gap

Main evidence/c4_active_condition_before.json at reviewed d613cc9 uses normal
parse/material/registry/equip/timed relation Skill. Top-level condition
{"not": null} evaluates False, yet the Skill activates the real Relation,
pays Mana20->19 and time20->19. Four Action/Skill/Relation source hashes remain
unchanged. This is a production semantic gap, not merely malicious parser
complexity, a browser playtest or privileged/native reference test.

parse_skill_blueprint stores the top-level condition but ActionDefinition and
its parser/lowering omit it; _resolve_action only checks individual Effect and
cost-modifier conditions. Accepted C4.1 parser budgets do not fix this gap.

## Proposed Bounded Repair

Extend the existing ActionDefinition with a trailing default always condition
and its parser with an optional typed condition. Skill->Action lowering passes
non-null top-level active condition. Null/absent always conditions need not
change legacy Action canonical hashes. Preserve canonical Skill documents/hash
and all current raw Action/Effect/Status/Hook semantics. Existing Skills with
non-null condition may correctly acquire a new compiled Action hash reflecting
new semantics; do not pretend old hash behavior is immutable here.

Within _resolve_action evaluate the Action condition once on CURRENT staged
self/target/current_area BEFORE cost quoting/debit/effect reservation. False
required active condition raises GameplayContractError, preserving complete
World/time/revisions/stats/schedule/registry. Individual conditional effects
retain their separate skip semantics. Hook false condition remains an
explainable dispatch skip, not an automatic-primary error; passive neutral
cost/Hook condition and shared low-level execution must remain compatible.
Do not implement condition via skills-name/UI/session branch or direct World
writes. Existing parser budgets apply, no new dynamic evaluator/clock.

Freeze detailed write scope and hash compatibility analysis before delegation.
Expected only actions.py, skills.py and one NEW owner test; independent QA owns
new distinct test/report. Main checks registry rebuild/checkpoint static hashes
and formal player/NPC true/false/resource boundary/current-state semantics.
Real false-condition timed casts must leave costs and persistent state intact;
accepted casts must pay exactly current costs/time. Raw untrusted condition
cannot access hidden arbitrary paths. Replays/save-load and passive dispatch
must continue identically under trusted same catalog. Full frozen regression,
independent review/account/checkpoint required before acceptance.

P1 missing typed leaves/selectors/all seven Operator and ten formal scenarios,
P2 multi-trigger IR and provider generation remain gated. Stop at20:10 +08:00
or earlier real accounting/budget/explicit blocker. Do not start this repair
until preceding accepted source freeze/checkpoint.
