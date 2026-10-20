# Storm Relay

Storm Relay is a local, browser-playable PMW M0 demo.  It is a strict
turn-based expedition through the Storm Shallows and the Old Relay Tower.
Every click is converted into a typed server command; the server advances the
real PMW WorldState, Laws, Scheduler time ledger, and causal trace.

## Run

From the repository root, use Python 3.10 or newer:

```bash
PYTHONPATH=src:. python3 -m examples.storm_relay.server --port 8010
```

Open `http://127.0.0.1:8010/` in a browser.  The server intentionally binds
only to loopback.  Stop it with `Ctrl+C`.

On Windows PowerShell, the equivalent is:

```powershell
$env:PYTHONPATH = "src;."
py -3 -m examples.storm_relay.server --port 8010
```

## Demo Contract

- A new run has 23 World Ticks, 32 HP, and 8/10 Mana.
- The player has Attack (6 damage), Guard (6 temporary shield), and Wait
  (+2 capped HP/Mana) without consuming a skill slot.
- Tower Guard starts at 42 HP.  Its return attack is 5 in clear weather, 7 in
  storm, and 2 in fog.
- Lightning Seed costs 3 Mana and immediately adds humidity `+0.25` and
  charge `+0.30` to the current Area.  Mist Echo costs 3 Mana and adds
  humidity `+0.35`.
- Storm Glass Relay owns its own shield layer: 6 in storm, 4 in fog, refreshed
  only by that source and expiring after three later World Ticks.

The obvious route is intentionally not the only route.  The three regression
routes in `routes.py` are useful reproducible examples:

```bash
PYTHONPATH=src:. python3 -m unittest examples.storm_relay.tests.test_routes -v
```

They verify direct assault in 10 ticks, the storm build in 19 ticks, and the
fog build closing the core on tick 23.

## Development Checks

```bash
PYTHONPATH=src:. python3 -m unittest discover -s examples/storm_relay/tests -v
PYTHONPATH=src:. python3 -m unittest discover -s tests -v
PYTHONPATH=src:. python3 -m unittest discover -s experiments/generative_mechanics/next_tracks_v06/tests -v
PYTHONPATH=src:. python3 -m unittest discover -s experiments/generative_mechanics/next_tracks_v06/gameplay_v04/tests -v
```

The browser receives only a safe observation projection.  It cannot submit
damage, field paths, material counts, WorldState, or Law IDs.
