# PMW Build Synergy Pilot v0.1 Report

## Experimental result

All six candidate Builds achieved legal same-Session joint execution. Eleven
preregistered scenario variants produced 66 equal-time arms and 264 formal
combat rounds. Every selected skill passed material authorization, combined
content compilation, Registry construction, Loadout authorization, Action or
trusted Hook execution, and trace retention.

This is not the same as six good Builds. The final distribution is:

```text
PLAYABLE_BUILD             1  (C; qualified by the tested task)
MECHANICALLY_INTERESTING   3  (A, B, F)
EXECUTABLE_ONLY            2  (D, E)
```

## Build findings

### A — Mercy and Execution

There is genuine interaction. #051 creates `mercy_mark` on an initially
unmarked enemy; after the intervening enemy action and Tick, #052 reads the
Status-granted `recently_spared` Trait and deals 11 damage. The target was first
healed 8, so the sequence deals 3 net damage. B-only deals zero and still pays
its action/Mana; B→A ends at +8 enemy HP. Two basic attacks deal 24. Interaction
on target damage is `3 - (-8) - 0 + 0 = 11`, but the strategy is a trap.

### B — Artificial rain and Paper Armor

At initial wetness 0.55, B-only cannot satisfy its 0.70 condition and prevents
no damage. #041 moves wetness above the gate in the same Session; #055 then
creates a real shield and consumes wetness. A→B loses 39 HP versus 48 for no
skill, a 9 HP conditional interaction. Two Guards lose only 34. The mechanism
works, while the tested action economy does not justify it.

### C — Storm to defense

#041 crosses the electric threshold and produces formal weather-changed events.
The runner explicitly routes each such event through the trusted #049 Hook and
records `manual_trusted_hook_dispatch`. A→B loses 38 HP, versus 48 for either
skill alone and 41 for the one-Guard matched alternative. The corresponding
final-HP interaction is `42 - 32 - 32 + 32 = 10`.

The defense is not free: relay discharge lowers final electric field from
0.658 (A-only) to 0.454. The Build can protect the player while pushing the
storm toward its 0.42 exit boundary. This feedback makes C the strongest
general gameplay result here, subject to the missing automatic Hook router.

### D — Smoke accumulation

Both orders execute and enter the smoke-weather path in the sensitive variant. However, #053 alone
already crosses the threshold on its first action, deals the same single point
of damage as the pair, and A→B retains only #005's existing shield benefit. In
the counterexample variant `smoke_heat_front` is disabled at detached time zero
for every arm: the pair still raises smoke, but its final temperature is exactly
the no-skill value (24.5196032) and no smoke-weather feedback occurs. The pair
is same-direction accumulation with threshold saturation, not a new mechanical
dependency.

### E — Defense and ecology maintenance

At biomass 0.30, no skill becomes `stressed`. A-only, B-only, and both orders
remain `balanced`; #042 alone also provides the same final defensive benefit as
the combination. The two temporary rate modifiers coexist and raise final
biomass, but no new regime outcome appears. Biomass interaction at the edge is
approximately `0.4904 - 0.4642 - 0.4146 + 0.3332 = -0.0552`, showing diminishing
returns. At initial biomass 0.78, both rates accelerate movement downward toward
the 0.55 attractor, an instructive environmental counterexample.

### F — Future life for present agency

At 80 HP, zero Mana, and temperature 55, an immediate #060 is rejected
atomically. #056 can supply Mana immediately, after which #060 crosses the heat
threshold and the hero survives at 66 HP. Independent review found the omitted
legal alternative: Wait once for natural Mana recovery, then use #060. It
reaches the same final temperature (61.2997888) and `heat_haze`, while ending at
75 HP. The combination is therefore a real resource-enabling interaction but
not a strategically positive Build under the four-action horizon. At 14 HP the
combination dies, and at temperature 20 it spends 14 HP without reaching heat
haze.

## Required questions

1. **Same-Session joint execution:** 6/6 Builds.
2. **Real mechanical interaction:** A, B, C, and F. D and E are additive or
   redundant under the tested objectives.
3. **Positive strategic value after opportunity/resource cost:** only C in its
   storm-defense task. F's apparent narrow success disappears against the legal
   Wait→Fever Key alternative.
4. **Simple numeric accumulation:** D and E. E additionally shows diminishing
   return around a threshold.
5. **Negative synergy or side effects:** A heals more than its follow-up can
   efficiently recover; C drains the storm it creates; D worsens public heat;
   E pulls abundant biomass downward faster; F can kill its user.
6. **Most limiting Engine surface:** there is no automatic event-to-Hook
   dispatcher. Manual trusted dispatch can validate causal compatibility but
   cannot establish production passive ergonomics. The action resolver also
   does not advance time itself, so correct combat/time orchestration is
   essential.
7. **Are 60 skills enough for meaningful RPG Builds?** Enough to demonstrate
   several real build patterns and one qualified playable case, but not enough
   to claim broad build depth. Four of six hypotheses fail strategic or
   non-additivity gates, which is exactly why joint execution matters.

## Conclusion

The strongest non-inflated conclusion is that PMW already supports genuine
state-setting/state-consuming Builds, shared-world threshold play, and risky
resource conversion. It also makes weak combinations fail visibly. The next
useful step would be broader scenario replication and an automatic Hook routing
design, not more hand-authored claims or a premature balance benchmark.
