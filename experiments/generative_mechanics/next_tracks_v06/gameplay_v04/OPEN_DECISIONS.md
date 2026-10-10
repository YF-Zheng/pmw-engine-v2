# Open Decisions

The implementation keeps these values configurable and labels them as demo
fixtures until owner review:

- actor starting HP, Mana, attributes, and progression coefficients;
- Attack, Guard, and Wait coefficients;
- active loadout replacement time outside combat;
- weather concurrency policy beyond one channel per Area;
- ecology transition and harvest balance values;
- AI node budget, discount, and opponent-response approximation;
- final combat fallback-path metrics.

Gate 1 freezes the composition order for dynamics target/rate/curve sources.
Gate 2 freezes status phases and action transaction boundaries. Gate 3 freezes
the high-level compilation contracts, and Gate 4 freezes full-Tick-boundary
registry replacement plus actor-safe bounded planning. The following remain
deliberately open: final numeric balance, active replacement cost, AI weights
and node budget, multi-weather-channel policy, cross-content checkpoint
migration, and complete TODO3 world-solvability constraints.
