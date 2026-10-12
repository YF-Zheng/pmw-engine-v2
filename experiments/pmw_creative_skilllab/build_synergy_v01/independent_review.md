# Independent Counterexample Review

An independent sub-agent reviewed the Pilot without editing its files. The
review checked same-Session execution, initial-state fairness, time and resource
accounting, causal interaction claims, and simpler legal alternatives.

## First review

The first pass independently reran all 8 tests in 114.358 seconds. It accepted
Builds A, B, C, and E, but found two problems:

- Build D's original cold counterexample still activated `smoke_heat_front`, so
  it did not isolate a world insensitive to smoke feedback.
- Build F's claimed playable window omitted the legal sequence Wait -> Fever
  Key. Natural Mana recovery made that sequence reach the same outcome while
  retaining more HP, invalidating the original `PLAYABLE_BUILD` judgment.

The Lead corrected the experiment rather than defending the original result.
Build D now disables `smoke_heat_front` for every arm at detached time zero.
Build F now includes Wait -> Fever Key as its matched alternative and is
classified `MECHANICALLY_INTERESTING` with no established strategic value.

## Final review

The reviewer independently reran the corrected 8-test suite: 8/8 passed in
114.455 seconds (114.81 seconds elapsed). Fresh D/F runs additionally confirmed:

- **Build D PASS:** all six weather-absent arms remained at final temperature
  24.5196032 and saw no active weather, while smoke still varied by the actual
  skill sequence. The counterexample removes only the feedback law, not the
  skills' field writes.
- **Build F PASS:** in the low-Mana near-threshold case, A -> B ended at HP 66,
  temperature 61.2997888, and `heat_haze`; Wait -> Fever Key reached the same
  temperature and weather at HP 75. Both used four rounds and had no rejection.

The reviewer found no remaining semantic or evidence-chain defect. Build C
remains the sole `PLAYABLE_BUILD`, explicitly under
`manual_trusted_hook_dispatch`; the review does not claim production automatic
Hook routing.
