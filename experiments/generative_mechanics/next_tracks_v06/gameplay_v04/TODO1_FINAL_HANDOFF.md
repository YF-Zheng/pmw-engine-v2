# PMW Gameplay v0.4 TODO1 Final Handoff

Status: **READY_FOR_FINAL_OWNER_SIGNOFF**

This document is the engineering handoff for the Gate 0-5 gameplay foundation.
It describes the shipped API and boundaries; it does not authorize TODO2 model
collection, freeze a benchmark, or start TODO3 game production.

Gate 5.2 implementation commit:
`75ebe9eaaff3e7cd2349bfd33fde58fbb2c0713d`. The release archive is generated
from the final documentation commit, verified separately, and accompanied by
its SHA-256 file to avoid embedding a self-referential archive digest here.

## Authority and module boundaries

PMW Core remains the sole state-transition authority. Gameplay definitions are
immutable Python values; live Actor, Area, inventory, Status, shield, registry,
time-budget, and Scheduler state lives in `pmw.WorldState`. Gameplay adapters
validate requests and build formal Events. Compiled PMW Laws commit the changes
and PMW produces the `EventResult` and `CausalTrace`.

The dependency direction is:

```text
src/pmw (frozen Core)
  -> next_tracks_v06 Gate 0 contracts and compiler substrate (frozen)
  -> gameplay_v04 contracts/runtime/blueprints/dynamics
  -> actions/effects/status/hooks/combat
  -> weather/ecology/harvest/materials/skills/loadout
  -> registry/checkpoint/observation/simulation/planner
```

Gameplay code may reuse PMW `WorldState`, `Engine`, `Law`, Scheduler, and
`CausalTrace`; it must not fork them. The frozen Generative Mechanics research
protocols, preregistration, pilot outputs, and formal experiment assets are not
dependencies that gameplay may rewrite.

## Stable gameplay entry points

The supported construction and runtime surface is:

- `parse_area_blueprint`, `parse_actor_blueprint`, `instantiate_area`, and
  `instantiate_actor` for trusted definitions and independent instances.
- `build_gameplay_world`, `clock_entity`, `make_content`,
  `initialize_content_world`, `initialize_time_budget`, `compile_content`, and
  `build_content_session` for a detached time-zero world.
- `MechanismRegistryRuntime.from_compiled_content`, `install_blueprint`,
  `disable`, `manifest`, and `action_registry` for the formal skill registry.
- `change_loadout` and `skill_ref` for exact version/hash loadout references.
- `resolve_action` for one authorized primary action and `run_combat_round` for
  a strict sequential round with exactly one formal combat Tick charge.
- `resolve_harvest` for the complete atomic harvest, time, and Tick operation.
- `spend_world_time` for atomic `exploration`, `move`, `rest`, and `offline`
  time consumption.
- `cancel_status` for an authorized lifecycle cancellation.
- `save_registry_checkpoint` and `load_registry_checkpoint` for a complete,
  self-verifying registry/runtime checkpoint.

Private helpers such as `_resolve_action`, `_commit_harvest`, raw PMW event
construction, and direct component mutation are not gameplay APIs.

## Minimal real flow

The checked-in Gate 3 fixture builds a real World/Actor/Area/content session.
This example uses only production entry points and retains every trace:

```python
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.actions import (
    ActionRequest,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.checkpoint import (
    load_registry_checkpoint,
    save_registry_checkpoint,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.content_compiler import (
    compile_content,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.gate3_demo import (
    build_gate3_demo,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.harvest import (
    HarvestRequest,
    resolve_harvest,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.loadout import (
    change_loadout,
    skill_ref,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.registry import (
    MechanismRegistryRuntime,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.actions import (
    resolve_action,
)

session, content, skill, harvest = build_gate3_demo(time_budget_ticks=6)
compiled = compile_content(content)
runtime = MechanismRegistryRuntime.from_compiled_content(session, compiled)

change_loadout(
    runtime.session,
    runtime.manifest,
    actor_id="hero_actor",
    operation="equip_active",
    skill=skill_ref(skill),
    slot=0,
)

cast = resolve_action(
    runtime.session,
    runtime.action_registry,
    ActionRequest("cast_1", "hero_actor", skill.id, "plain_actor"),
)
cast_trace = cast.event_result.trace.to_dict()

gather = resolve_harvest(
    runtime.session,
    runtime.action_registry,
    harvest,
    HarvestRequest("harvest_1", "hero_actor", harvest.id, True),
    permissions=("lucky_harvest",),
)
harvest_trace = gather.event_result.trace.to_dict()

save_registry_checkpoint("world.json", runtime)
restored = load_registry_checkpoint("world.json", compiled)
assert restored.session.state.to_dict() == runtime.session.state.to_dict()
```

For explicit world construction, instantiate Actor and Area entities from
parsed blueprints, pass them to `build_gameplay_world`, add one `clock_entity`,
then apply the time-zero content and budget initializers before compiling and
attaching a runtime. Definitions are reusable; instantiated components are not
shared between entities.

## Transaction and authority rules

- A formal time spend preflights the complete final duration. All requested
  Ticks and Scheduler work run on a staged session and publish only on success.
- Combat validates all actor requests before any `owner_turn`, runs ordered
  owner turns/actions, the `combat_round` phase, one time charge, and one
  `world_tick`, then publishes the complete round.
- Harvest computes the condition/luck-adjusted duration and atomically commits
  Mana, yield, depletion, ecological effects, receipt, time, and all Ticks.
- A non-basic action must be an enabled exact ID/version/hash/kind reference in
  the acting Actor's equipped active slots. Attack, Guard, and Wait are the
  only canonical slot-free actions. Human and AI controllers share this rule.
- Temporary shield layers have source and Status-instance ownership. Refresh,
  damage, cancellation, replacement, and expiry preserve deterministic,
  source-local lifecycle behavior.
- A repeated harvest request ID cannot produce a second reward, including
  after checkpoint restoration.

Do not call `resolve_harvest` and then charge time again. Do not invoke private
action executors, submit a caller-selected Hook execution mode, hand-edit
loadout/registry components, mutate `WorldState` after runtime attachment, or
advance the PMW Scheduler separately from the attached Gameplay runtime.
Transactions use the documented single-writer session model. Runtime-external
irreversible side effects must occur only after a successful commit.

## Checkpoint contract

`save_registry_checkpoint` writes an atomic canonical envelope containing the
WorldState, scheduled Events, immutable installed blueprint documents, registry
configuration, and a payload SHA-256. `load_registry_checkpoint` validates the
entire envelope against the trusted compiled content and rebuilds one coherent
Engine/Scheduler/WorldState runtime.

Current checkpoints preserve time-budget continuity, harvest receipts, active
Status identity, shield ownership and consumption, registry versions, and
scheduled lifecycle continuation. The shared attach boundary performs the
documented idempotent migration of legacy scalar shields and older Status slot
shapes. It conservatively retains an unowned legacy shield because historical
provenance cannot be reconstructed.

## SkillLab-reusable capability

The following parts can be reused by a future SkillLab without changing PMW
Core: strict Blueprint parsers and canonical hashes; trusted material authority
and effect budgets; compound Skill/Passive compilation; exact registry and
loadout identity; safe selectors; legal-action generation; actor-safe
observations; causal explanations; checkpointed runtime registration; projected
sandbox simulation; read/write build-synergy analysis; and bounded explainable
planning. SkillLab should call these interfaces and inspect formal traces, not
write gameplay components or manufacture registry entries directly.

This is capability reuse, not a frozen SkillLab product or evaluation protocol.
Balance tuning, content authoring, user interface work, and formal model
collection remain separate owner decisions.

## Known limits and non-TODO1 scope

- Sessions are single-writer; concurrent optimistic transaction merging is not
  implemented.
- External network/file side effects are not rolled back and must not occur
  before gameplay commit.
- Historical scalar shields have no recoverable source provenance.
- Planning is deliberately bounded, deterministic over the supplied view, and
  not globally optimal.
- Complete game content, narrative/NPC systems, UI/HUD, final balance,
  unrestricted world generation, full solvability search, dynamic timeline or
  cast-time combat, and production multiplayer are outside TODO1.
- TODO2 model collection and benchmark freezing, and TODO3 complete game
  production, are not authorized by this handoff.

## Reproducible verification

Run from the repository root with the checked-in Python environment:

```bash
PYTHONPATH=src:. python3 -m unittest discover -s tests -p 'test_*.py' -v
PYTHONPATH=src:. python3 -m unittest discover -s experiments/generative_mechanics/tests -p 'test_*.py' -v
PYTHONPATH=src:. python3 -m unittest discover -s experiments/generative_mechanics/next_tracks_v06/tests -p 'test_*.py' -v
PYTHONPATH=src:. python3 -m unittest discover -s experiments/generative_mechanics/next_tracks_v06/gameplay_v04/tests -p 'test_*.py' -v
PYTHONPATH=src:. python3 -m experiments.generative_mechanics.next_tracks_v06.gameplay_v04.gate5_demo
git diff --check
```

Protected compatibility scope is the sorted `git ls-tree -r` manifest for
`src/pmw` plus `experiments/generative_mechanics`, excluding
`next_tracks_v06`. Its frozen 381-entry SHA-256 is:

```text
a20fd763cad342ac357a08d94ee96ca42075f215efcbff93c4017b65a8ddd669
```

Final verification:

```text
Core:                 254/254
Old GM:               345/345
v0.6:                 170/170
Gameplay v0.4:        172/172
Total:                941/941
Gate 5 demo digest:   89c9e21b676c2079967634339954ebf698a04397bf8b385198032a212a7b74b9
Gate 5.2 commit:      75ebe9eaaff3e7cd2349bfd33fde58fbb2c0713d
Protected manifest:   a20fd763cad342ac357a08d94ee96ca42075f215efcbff93c4017b65a8ddd669
```

All four final suites completed with zero failures, errors, skips, or expected
failures. Independent QA passed 5/5 adversarial tests and the complete Gate 5.2
set passed 27/27. Detailed commands, wall times, log hashes, RED evidence, and
residual boundaries are recorded in `GATE52_FINAL_REPAIR_REPORT.md`,
`GATE52_INDEPENDENT_QA_REPORT.md`, and `GATE52_COMPATIBILITY_REPORT.md`.

This status is an engineering handoff recommendation. Only the Owner may mark
TODO1 `ACCEPTED` or `CLOSED`.
