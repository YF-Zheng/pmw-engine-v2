# Failure and Unsupported-Concept Log

The pilot keeps failed ideas because they expose the present expression
boundary. None of these twelve concepts is counted among the 60 validated
skills.

## Unsupported concepts

| Creator | Concept | Why it was not implemented |
|---|---|---|
| A | `lightning_position_exchange` | No public Effect swaps or moves Actor placement relations. |
| A | `delayed_remote_detonation` | No Effect schedules an arbitrary delayed Area write. |
| B | `mirror_of_exact_pain` | Hook effects cannot bind resolved event damage as a dynamic amount. |
| B | `sealed_rebuke` | Status expiry supports bounded resource writes, not delayed arbitrary-target damage. |
| C | `migratory_compass` | Skills cannot rewrite an Ecology transition graph or move a population entity. |
| C | `storm_calendar` | Skills cannot extend a live WeatherSpec timer or reorder weather events. |
| D | `adjacent_aquifer_bridge` | There is no paired source/destination field-transfer transaction. |
| D | `portable_material_refinery` | `add_resource` is closed to actor resources; inventory conversion is not an Effect. |
| E | `borrowed_future` | No historical snapshot read or arbitrary scheduled Action effect. |
| E | `migrating_grove` | No placement rewrite or ecology-owned inventory transfer Effect. |
| F | `yesterdays_refund` | No historical action-cost read plus conditional future refund. |
| F | `door_that_hates_owners` | No Effect changes or swaps `located_in` relations. |

## Repaired during iteration

- `blood_mortgage`: an early same-target damage/shield write conflict was
  correctly rejected. The final design uses a mana mortgage and does not bypass
  the conflict checker.
- `deferred_dividend`: an unowned status could not create a shield on expiry.
  The final design uses supported periodic HP loss and expiry mana behavior.
- `dead_tide_clock`: the original negative rate slowed travel toward the low
  attractor. It was corrected to a positive rate; during integration, the rate
  write moved to `wind` so it did not contend with the same temporary slot as
  the `wetness` attractor write.
- Several Creator-local prototypes only compiled or sampled three behaviors.
  The Lead runner subsequently rebuilt and behavior-tested all 60 selected
  cases; the final claim is based on those integrated runs, not Creator notes.
- Creator field names such as `rain`, `ash`, `fertility`, `resonance`, and
  `salinity` were mapped to published shared-world fields. Each mapping is
  disclosed in the affected skill's `limitations_zh`.

## Audit gap

After integration, a fresh Reviewer plus separate test and diversity auditors
were launched. All three calls failed before work began because the sub-agent
service reported its usage limit. The Lead performed deterministic structural
checks and full runtime tests, but that is not independent review. Therefore:

```text
Creator collaboration: COMPLETE
Integrated behavior validation: COMPLETE
Independent Reviewer gate: PARTIAL / BLOCKED BY PLATFORM QUOTA
```
