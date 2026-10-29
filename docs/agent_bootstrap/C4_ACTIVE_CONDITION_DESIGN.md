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

## Prepared Temporal And Compatibility Review

Top-level Action condition reads PRE-COST current staged self/target/Area.
Cost-modifier and Effect conditions retain existing distinct timings (quote on
pre-cost context; Effect predicates use progressively updated shadow after
cost/effects). A mana>=5 top condition with Mana5/cost4 must accept and pay to1;
it is not implicitly converted into the post-cost Effect predicate. False top
condition rejects before insufficient-mana/effect reservation so no costs/time
or mutation leak. Conditions remain existing typed side-effect-free specs,
not arbitrary string paths, source expressions, Catalog mutation or code.
No extra authorized information may be exposed in exceptions/results.

Preserve Basic Action exact canonical identities. An untrusted conditional
variant under basic_attack/guard/wait cannot gain slot-free privilege. Carry
ConditionSpec as a trailing default always field; null/absent condition means
legacy action_raw/hash unchanged. For non-null ACTIVE Skill conditions, pass
its typed raw predicate into Action parser/canonical data: new Action hashes
are appropriate and Skill document/hash/version remain unchanged. Passive
Hook condition remains separate, preserving C4.2 Hook/action/equipment hashing
and skip behavior unless a concrete semantic reason is independently reviewed.
Do not silently add irrelevant null condition to every old Action hash.

Positive and false tests should equip ONE same-ID parsed Skill to player and
NPC with compatible current-Area Field infrastructure (or existing template
resolver), not silently replace it with two owner-profile variants then claim
same Skill reuse. All support mutations are clearly labelled initial state or
real World Laws; actual casts use normal registration/equipment and timed
primary authority. Different pre-cost Actor resources/traits can demonstrate
same definition true for one owner and false for another. Changing legitimate
World state between casts must change eligibility without registry rebuild.

Every accepted old test (including C4.1 QA) remains immutable. Known C4.3
probe is non-collected evidence, not a test freezing the wrong behavior. Avoid
adding tests that require unfixed out-of-scope bugs to remain; preserve their
standalone evidence instead. Preserve passive/manual hooks, current Dynamics,
Process/Drive/Relation transactions/expiry and all previous source gates.

## Frozen Implementation Scope

After C4.2 checkpoint, one implementation worker owns actions.py,skills.py,
and NEW gameplay_v04/tests/test_sandbox_active_condition.py only. Independent
QA owns NEW gameplay_v04/tests/test_sandbox_active_condition_review.py and
C4_ACTIVE_CONDITION_REVIEW.md/evidence/c4_active_review* only. No overlapping
production writes, accepted old test changes, or Engine/Alpha/global edits.
Main owns source review, extra formal evidence, fullfreeze, accounting and
checkpoint. Worker must edit directly and report exact changed paths/hashes.

ConditionSpec("always") is immutable and may be the trailing default. Parser
accepts only optional typed condition via current bounded parse_condition.
Omit null condition from canonical Action data (legacy absent/null equivalent)
without mutating caller raw input; preserve other canonical behavior. Existing
non-null ACTIVE Skill predicate is copied to action_raw; passive Action remains
always with separate Hook predicate. Skill canonical_text/hash stays original.
Gate in _resolve_action after current Actor/target validation and shadow/context
creation, before quote/debit/reservation/Engine execution. No per-effect-only
substitution, cached condition result or global-config workaround. Reject
false condition with a bounded generic GameplayContractError (no World values).
Always hook actions keep existing neutral cost and Hook false-skip semantics.
Exercise null/absent basic identities, new conditional-basic privilege rejection,
same parsed Skill player/NPC pre-cost mana5/cost4 boundary, current-state change,
normal save/load rebuild, false rollback and C4.2 passive compatibility.
