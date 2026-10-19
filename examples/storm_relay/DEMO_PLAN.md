# PMW M0 Storm Relay Implementation Plan

Status: `PLANNED / PRODUCTION BLOCKED BY REQUIRED MODEL SELECTION`

This plan is based on the repository at commit
`7ee4d31cac119593a61f4a91cb9d82fe1cc360ba` on the new branch
`feature/m0-storm-relay-demo`. The working tree was clean before this file was
created. The Gameplay v0.4 test suite was executed from this branch and exited
successfully before M0 production work.

## 1. Collaboration Gate

The task requires production code to be implemented by an explicitly selected
GPT-5.6 Luna agent. The available collaboration API exposes only task name,
message, and context-fork parameters. It exposes no model selector, reasoning
effort selector, or verifiable model identity, and there is no live child agent
whose Luna identity can be verified.

Consequently, the main agent must not claim that a generic child agent is Luna.
Under the task's explicit fallback rule, repository investigation and this plan
may be completed, but production implementation must pause until either:

1. a tool exposing a verifiable GPT-5.6 Luna selection is made available; or
2. the Owner explicitly authorizes a named available agent/model as a substitute.

Once the gate is resolved, the main agent will give Luna the staged contracts
below, review every diff, rerun tests independently, and return concrete defects
to Luna rather than accepting self-reported completion.

## 2. Existing System and Protected Boundaries

### PMW Core

`src/pmw` owns `WorldState`, `Engine`, `Event`, `Law`, Scheduler execution,
snapshots, validation, observation, and `CausalTrace`. It remains frozen. M0
will not add a second mutable simulation or modify Core behavior.

### Generative Mechanics v0.6

`experiments/generative_mechanics/next_tracks_v06` supplies normalized dynamic
fields, compilation contracts, and Gameplay v0.4. Historical GM protocols,
formal benchmark assets, preregistration, collected outputs, and existing
experiments remain unchanged.

### Gameplay v0.4 APIs to reuse

The real supported flow is:

- `parse_area_blueprint` / `parse_actor_blueprint`, then `instantiate_area` /
  `instantiate_actor` for detached definitions and independent instances.
- `build_gameplay_world`, `clock_entity`, `initialize_content_world`, and
  `initialize_time_budget` for the detached initial world.
- `make_content`, `compile_content`, and `build_content_session` for PMW Laws,
  dynamics, statuses, weather, harvest, registry, and time attachment.
- `MechanismRegistryRuntime.install_blueprint`, `change_loadout`, and exact
  `SkillRef` hash/version identity for runtime-created skills.
- `resolve_action`, `resolve_harvest`, `run_combat_round`, and
  `spend_world_time` for authoritative actions and finite Tick advancement.
- actor-safe observation builders and formal traces for UI projection and event
  history.

Gameplay state is already held in PMW entities and relations. Its public
transactions stage a session and publish only on success. M0 will build one
larger trusted transaction boundary around multi-API actions such as craft +
register or equip + time, because no existing public method makes those
combinations one atomic operation.

### Existing demo and UI situation

`examples/ash_observatory` is a terminal interaction adapter over PMW data. It
is useful for command/error and observation patterns, but it is not a browser UI
and does not use the complete Gameplay v0.4 stack. No reusable web framework or
web application exists in the repository.

The M0 browser UI will therefore use Python's standard-library HTTP server plus
plain HTML, CSS, and JavaScript. This avoids a new package manager and keeps the
launch command reproducible with the repository's existing Python requirement.

## 3. Proposed Files

All production files will be isolated under `examples/storm_relay/`:

```text
examples/storm_relay/
  DEMO_PLAN.md
  README.md
  DEMO_IMPLEMENTATION_REPORT.md
  __init__.py
  content.py                 # declarative Area/Actor/material/skill definitions
  laws.py                    # M0 PMW Law documents and deterministic Tick ordering
  session.py                 # authoritative StormRelaySession and new-game factory
  commands.py                # typed player commands and legality rules
  transactions.py            # staged whole-action commit coordinator
  observations.py            # public UI projection and event summaries
  routes.py                  # fixed route runners using the same public command API
  server.py                  # localhost JSON API and static-file server
  static/index.html
  static/app.js
  static/styles.css
  static/assets/storm-relay.webp
  tests/test_content.py
  tests/test_dynamics_weather.py
  tests/test_skills_materials.py
  tests/test_combat_transactions.py
  tests/test_routes.py
  tests/test_http_ui.py
  records/direct_assault.json
  records/storm_build.json
  records/fog_build.json
  logs/...
```

Gameplay v0.4 itself will be modified only if a generally reusable defect is
proven and a focused regression test requires the change. Any such change needs
separate review against its 172-test baseline. The default design adds M0
content and adapters without editing frozen foundations.

## 4. Authoritative State Model

### Areas

Two independent Area instances contain Gameplay dynamics fields:

- Shallows: humidity 0.65 -> 0.70, charge 0.20 -> 0.20, wet moss abundance
  0.80 -> 0.70, thunder crystal abundance 0.80 -> 0.60.
- Tower: humidity 0.40 -> 0.35 and charge 0.45 -> 0.30.

Every field uses domain `[0, 1]`, curve `linear`, and rate `0.05`. Explicit
`located_in` and travel relations define scope. There is no cross-Area field
law. Both Area profiles participate in every formal world Tick.

Resource stock is separate from dynamic abundance. Stock, discoveries,
console state, encounter state, crafted receipts, terminal outcome, and action
serials live in explicit PMW components. Player inventory remains the Gameplay
material inventory component. Actor HP, Mana, attributes, traits, statuses,
shield layers, loadout, Hook cooldowns, and controller data use existing
Gameplay components.

### Weather

The existing generic weather model treats specs as independently active timed
conditions. M0 requires one exclusive `clear/storm/fog` state with hysteresis
and no arbitrary duration. M0 will compile experiment-local PMW Laws that:

1. run after the field dynamics proposals for the Tick;
2. evaluate the frozen enter/keep/transition table deterministically;
3. mutate one authoritative weather state only on a true transition;
4. emit exactly one formal `pmw.v04.weather.changed` event containing Area,
   old state, new state, source, and Tick;
5. emit a weather pulse used by local periodic effects.

The law set will be general over Area bindings, not keyed to a skill name.
Storm damage selects living `conductive` Actors related to the affected Area.
Combat attack damage selects the defender's current Area and applies the
`visual_lock` modifier only to the guard's aimed attack.

### Passive dispatch capability gap

Gameplay has `execute_hook` and registered passive Hooks, but currently has no
unified automatic dispatcher. Existing research runners call it manually after
inspecting a trace, which is forbidden for this Demo.

M0 will add a trusted, generic backend dispatcher inside the staged Tick
transaction. It consumes formal derived events from the PMW result, maps their
event type to a Gameplay trigger, filters exact equipped and enabled passive
registry references, constructs bounded `HookLineage`, and invokes the public
Hook/Effect pipeline. It is invoked by the backend transaction coordinator for
every Tick, never by UI code, route code, or tests. Hook effects and their
traces commit with the enclosing action or are discarded with it.

The Storm Glass Relay shield uses a source-owned layer and a three-subsequent-
Tick lifecycle. A new transition refreshes only that layer. Guard owns a
different source layer and is cleared after the enemy action without touching
the passive layer. Creation Tick is recorded so it is excluded from immediate
duration decrement.

This dispatcher is a documented `CORE_CAPABILITY_GAP` adapter unless a supported
automatic entry point is discovered during implementation.

## 5. Command and Transaction Flow

The browser sends only a typed command and optional target. It never sends a
field path, damage number, cost, skill effect, registry entry, or WorldState.

```text
button / POST command
  -> parse trusted CommandSpec
  -> derive legal actions from public session view
  -> clone complete runtime + registry envelope
  -> validate actor, phase, target, discovery, material, Mana, loadout and time
  -> run formal Events / public Gameplay APIs on staged runtime
  -> spend the declared number of world Ticks
  -> per Tick: dynamics -> weather -> derived event dispatch -> weather pulse
              -> lifecycle/Scheduler -> time ledger
  -> evaluate terminal priority (successful close before zero-time defeat)
  -> publish staged runtime only when the whole command succeeds
  -> return public snapshot, legal commands and causal event summaries
```

Craft is one two-Tick transaction: validate recipe, consume exact materials by
formal Event, parse and validate the deterministic Skill Blueprint, install it
through `MechanismRegistryRuntime`, advance two Ticks, then commit. Equip and
unequip use `change_loadout`, advance one Tick, and commit together. A registry
or Tick failure leaves materials, registry manifest, loadout, Scheduler, and
time unchanged.

Exploration active-skill use resolves the equipped registered action, spends
Mana, applies immediate field changes, advances one Tick, then evaluates
weather. In combat it occupies the player's action and the enclosing combat
round advances exactly one Tick, with no second time charge.

## 6. Combat Contract

Player and tower guard are normal Gameplay Actor instances. `basic_attack`,
`basic_guard`, and `basic_wait` remain slot-free. Their M0 definitions are:

- Attack: deterministic `4 + Power` damage.
- Guard: source-owned `2 * Resilience + 2` shield until the enemy action ends.
- Wait: capped `+2 HP/+2 Mana`, followed by enemy action and the round Tick.

The guard Controller submits an ordinary registered attack request through the
same resolver. A combat transaction stages player action, skips the enemy if it
died, otherwise resolves one enemy action, clears only remaining Guard shield,
then advances one world Tick. Storm periodic damage occurs in the Tick after
both actor actions. Death, victory, and time exhaustion are evaluated after the
atomic round.

Starting the core creates the guard before that action's world Tick, so an
already active storm damages it on the start-core Tick. Closing is legal only
after guard defeat. A close begun with one remaining Tick commits victory before
the zero-remaining failure check.

## 7. UI and Local Launch

`python3 -m examples.storm_relay.server` will bind to loopback and print the
actual URL. The first screen is the playable game, not a landing page.

The responsive interface contains:

- compact Area/time/HP/Mana/attribute status bar;
- Area fields, weather, stock, discoveries and contextual actions;
- inventory, recipes, validated registry entries and active/passive slots;
- combat Actor rows, shield sources and legal combat actions;
- chronological source-labelled world events;
- terminal result, route facts and restart action.

The visual asset will depict the relay tower and storm-lit wetlands and will be
used as scene media, not as an unreadable decorative background. Controls use
icons where familiar, semantic buttons for commands, accessible focus states,
and no nested card layout. Every render comes from `GET /api/state`; every
mutation uses `POST /api/action`; `POST /api/new-game` creates a fresh runtime.

## 8. Luna Work Packages

After verifiable Luna access is available, production work will be assigned in
dependency order rather than with conflicting parallel edits.

### Luna Stage A: content and world physics

- Add Area/Actor Blueprints, relations, materials and initial state.
- Add field dynamics, exclusive weather state machine, weather events and
  local periodic effects.
- Add focused unit tests for independent Areas, thresholds, hysteresis,
  abundance recovery and Tick ordering.

Acceptance: deterministic snapshots and traces; no UI/session shortcuts; Stage
A tests pass alongside Gameplay baseline.

### Luna Stage B: authoritative session and skills

- Add typed commands and staged transaction coordinator.
- Add investigation, harvest, travel, start-core and close-core actions.
- Add the three deterministic Blueprint recipes, material consumption,
  registration, equip/unload and active use.
- Add backend automatic passive-event dispatch and source-owned shield expiry.

Acceptance: failure atomicity hashes match before/after; unsupported or
unequipped skill use is rejected; no direct UI mutation; passive fires only on
real weather conversion.

### Luna Stage C: combat and route closure

- Add shared player/guard combat actions and guard Controller.
- Enforce one world Tick per complete round and terminal priority.
- Add route runner and the exact direct, storm and fog route tests.

Acceptance: actual 10/19/23 Tick wins with the required damage, Mana, shield,
weather and HP records.

### Luna Stage D: browser UI

- Add loopback server, public snapshot API, static playable UI and restart.
- Connect every visible action to the same session command endpoint.
- Add HTTP/UI contract tests, responsive layout checks and browser screenshots.

Acceptance: a fresh game can complete all three routes using normal HTTP/UI
actions; displayed state equals backend public snapshot; reload does not mutate
the session; restart has no prior-state residue.

For every stage Luna must report files, contract coverage, exact test commands,
test output, known issues, and next dependencies. The main agent will inspect
the diff and independently reproduce the tests before accepting the stage.

## 9. Automated Verification

M0 tests will cover all 19 requested categories, split as follows:

- `test_content.py`: seeded initialization, two Area identity, recipes, Actor
  stats, stock versus abundance.
- `test_dynamics_weather.py`: recovery equation/clamp, all weather transitions,
  no repeated event, all-Area advance, locality and storm pulse.
- `test_skills_materials.py`: unlock/harvest/craft/register/equip/use, material
  and Mana rejection, passive dispatch, source refresh and three-Tick expiry.
- `test_combat_transactions.py`: Attack/Guard/Wait, fog/storm modifiers,
  conductive damage, one-Tick rounds, skip dead enemy, atomic failures, death,
  timeout and close-at-last-Tick priority.
- `test_routes.py`: exact action-by-action 10/19/23 route records and outcomes.
- `test_http_ui.py`: state/action/restart API, legal action parity, static page
  load and backend/display schema.

Regression gates:

```bash
PYTHONPATH=src:. python3 -m unittest discover -s tests -p 'test_*.py' -v
PYTHONPATH=src:. python3 -m unittest discover -s experiments/generative_mechanics/tests -p 'test_*.py' -v
PYTHONPATH=src:. python3 -m unittest discover -s experiments/generative_mechanics/next_tracks_v06/tests -p 'test_*.py' -v
PYTHONPATH=src:. python3 -m unittest discover -s experiments/generative_mechanics/next_tracks_v06/gameplay_v04/tests -p 'test_*.py' -v
PYTHONPATH=src:. python3 -m unittest discover -s examples/storm_relay/tests -p 'test_*.py' -v
```

Browser verification will use desktop and mobile viewports. It must check for
no overlap, text overflow, blank media, dead controls, console errors, and
state parity after every action. If browser automation is unavailable, that is
reported as unverified rather than replaced by an HTTP-only claim.

## 10. Full Playthrough Evidence

`routes.py` uses only the same public command method exposed to HTTP. It starts
a fresh game for each route and writes canonical JSON records containing every
action, cost, legal result, player resources, both Area states, passive shield
changes, all guard damage/attacks, remaining time, and terminal reason.

Required assertions:

- Direct assault: 10 Ticks, seven 6-damage attacks, six 5-damage responses,
  player ends at 2 HP, then closes the relay.
- Storm build: 19 Ticks, pre-combat storm, automatic 6 shield, guard takes the
  start-core storm pulse, storm attack damage is 7, guard dies within four
  complete combat rounds, then relay closes.
- Fog build: 23 Ticks, pre-combat fog, automatic 4 shield, visual-lock attack
  damage is 2, close commits at Tick 23 and wins.

The final report will quote measured records, not the prompt's expected values.
Any lawful deviation is investigated and documented before balance changes.

## 11. Delivery and Acceptance

The final delivery contains source, browser asset, tests, route records, raw
logs, `README.md`, and `DEMO_IMPLEMENTATION_REPORT.md`. README launch commands
will be executed from a clean checkout. The report will identify the verified
Luna invocation, main-agent review rounds, changed files, exact tests and
counts, real route results, contract deviations, capability gaps, screenshots,
commit hash, archive path, and SHA-256.

M0 is not complete until the server starts, all UI actions mutate the real PMW
backend, all three routes pass from fresh sessions, protected regressions pass,
and no blocking defect is hidden. F3/L1, runtime LLM generation, procedural
world generation, benchmark freezing, and broader game production remain out
of scope.
