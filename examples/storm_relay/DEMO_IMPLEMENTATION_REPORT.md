# Storm Relay M0 Implementation Report

## Delivered

The demo is isolated under `examples/storm_relay/`; PMW Core and the existing
Generative Mechanics research assets are not changed.

- Two independent PMW Areas use the declared linear attractors and a real
  `located_in` relation for both player and guard.
- Exclusive clear/storm/fog state is decided by PMW Laws.  Transition events
  are emitted only when the state changes; local storm pulse damage selects a
  living conductive Actor in the affected Area.
- Material collection, recipe discovery, crafting, runtime skill registration,
  equipment, travel, core state, combat, and terminal state use staged PMW
  events or public Gameplay APIs.  Invalid commands discard the staged clone.
- The M0 combat resolver is a narrow Demo extension because Gameplay's frozen
  slot-free basic identities have different numeric parameters.  It commits
  both actors and their source-owned shield components through a formal PMW
  event; the browser never supplies a combat value.
- Storm Glass Relay is backend-dispatched from weather transitions, uses the
  existing shield-layer component, refreshes only its own source, and has a
  three-subsequent-Tick lifetime.  Equipping it into already-active weather
  invokes the same backend dispatcher.
- The local HTML/CSS/JS client has no replica simulation.  It renders the
  allowlisted observation and invokes `/api/action` or `/api/new-game` only.

## Reproducible Route Results

| Route | World Ticks spent | Result |
| --- | ---: | --- |
| Direct assault | 10 | Victory, 2 HP remaining |
| Lightning/storm build | 19 | Victory, 4 ticks remaining |
| Mist/fog build | 23 | Victory on the final tick |

The route tests execute exclusively through `StormRelaySession.perform`, the
same command surface used by the HTTP server.

## Known Scope

This is M0 only: there is no open-ended map, save system, dynamic timeline,
casting delay, nor per-monster authored combat script.  The guard uses the
same Actor/combat resolver as the player with only controller selection and
weather-sensitive attack values differing.  Automated visual browser capture
is not recorded because Playwright/Chromium is not installed in this workspace;
the HTTP API and static assets are covered by server tests and a live curl
smoke test.
