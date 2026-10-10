# Open Decisions

The implementation will keep these values configurable and label them as demo
fixtures until owner review:

- actor starting HP, Mana, attributes, and progression coefficients;
- Attack, Guard, and Wait coefficients;
- active loadout replacement time outside combat;
- weather concurrency policy beyond one channel per Area;
- ecology transition and harvest balance values;
- AI node budget, discount, and opponent-response approximation;
- final combat fallback-path metrics.

Gate 1 freezes the composition order for dynamics target/rate/curve sources.
Gate 2 freezes status phases and action transaction boundaries. Those semantic
decisions will be recorded before dependent modules are implemented.
