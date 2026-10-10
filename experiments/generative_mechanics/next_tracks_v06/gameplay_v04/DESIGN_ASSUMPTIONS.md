# Configurable Demo Assumptions

These are minimal implementation defaults, not owner-approved balance values.

- Controllers submit requests; trusted registered definitions supply costs and
  effects. A request cannot inject arbitrary writes.
- Exploration actions consume positive world ticks. Combat actions consume one
  main-action opportunity; a complete combat round advances exactly one world
  tick, independent of participant count.
- Attribute modifiers use stable source order: additive terms, then
  multiplicative terms, then clamp.
- Encounter fixtures define deterministic turn priority. Agility does not imply
  global initiative, hit chance, evasion, or defense.
- Required effects form the action transaction. Conditional effects may skip
  only after all required preconditions pass.
- Hook effects are conditional follow-ups with bounded depth and firing count;
  transaction-critical outcomes must be part of the root action.
- Status and Guard expiry use explicit clock-boundary events. Guard is replaced,
  not freely accumulated, and expires at the owner's next turn start.
- A full passive loadout rejects a new equip request rather than deleting an
  existing passive implicitly.
- Skill versions are monotonic integers plus a canonical content hash.
