# C4.4 Typed Dynamics Modifier Action Increment

ACCEPTED. Design: C4_DYNAMICS_ACTION_DESIGN.md. Review: C4_DYNAMICS_ACTION_REVIEW.md.

## Continuous C4.4 Frozen Acceptance

C4.4 bounded typed `dynamics_modifier` Action bridge is ACCEPTED. One closed
Effect kind (current_area only, commitment required, field_id, rate_add[-1,1],
rate_multiplier[0,8], curve linear/distance_squared/none, curve_priority 0..31,
duration 1..64; strict types, no terms/targeting extras, base cost 3, active
on_use only). Trailing EffectSpec fields keep every old Effect's canonical
hash. Preparation runs on the staged session: native validate_source against
the actual Area FieldProfile, duplicate curve priority across persistent and
temporary layers, capacity, per-Action distinct slot reservation and
same-Field source-footprint conflicts all reject before cost/time/publication.
Lowering reuses the existing modify_rate slot apply/schedule/expire Laws; no
unmanaged runtime.apply_source, no new clock. Production: effects.py,
skills.py, actions.py, action_compiler.py only.

Owner Ptolemy 01a18a9f-ba78-7123-bccf-1488c2a2c2b7: 19/44; bounded 383/355 and
183/3019. Independent Hume 01a18a9f-fe77-70b0-a392-baa4e39f8914: ACCEPT,
14/14 (red run on byte-verified HEAD archive: 13 requirement failures as
expected), legacy 395 and 183 OK; ten own-fixture corrections recorded
separately; no product findings. Hume's turn was once halted by the Magpie
loop guard (same command 8x); resumed with bounded instructions. Main cross
195/176. Main two-Area hand-calculated probe (player Area .2->.8 r.2, NPC Area
.5->.9 r.1, add .3 x1.5): exact match for d=1,2,3. Main's first hand model
assumed d effective Ticks and mismatched; the real rule (scheduler-before-
Tick, d-1 effective Ticks after the paid cast Tick; duration 1 legal but
inert, same as modify_rate) was a Main expectation error, not a product fix.

Full frozen regression c4_dynamics_frozen: **917 passed, 3,445 subtests in
395.27s**, exit0, 296 Python hashes unchanged. Protected after 7c975cb: 97
old tests, Core23, Alpha13 byte-identical. QA's ~196MB duplicate HEAD archive
is byte-identical to git archive 7c975cb; kept locally, git-excluded, recorded
in evidence/c4_dynamics_review_head_manifest.json (Main deletion was refused
by tool policy, so nothing was deleted).

Accounting c4_4 subset USD4.39985098/CNY29.33116657 (main turn actual
tencent/claude-opus-5.5 priced as Claude; workers actual DeepSeek Flash).
Project USD40.50206953/CNY270.00299631; safety 340.21738405/2000; **P1
reserve 302.5674514/400**: about two more C4-sized increments fit inside P1.
Unknown0, complete. No Alpha UI/playtest, full P1/P2 or generation claim.
