# PMW v0.4 Gate 3 Verification Report

Status: **DONE**

Scope: Weather, Ecology, Harvest, Materials, SkillBlueprint/PassiveBlueprint,
6+6/6 loadouts, content compilation, explanations, and the deterministic Gate 3 demo.
PMW Core, legacy GM assets, Gate 0-2 implementation, and Gate 4 AI files were not modified.

## Integration fixes

- Active skills now move in both directions between the six equipped and six
  stowed slots. `move_active` performs equipped-to-stowed and `unstow_active`
  performs stowed-to-equipped. Empty sources, occupied destinations, invalid
  slots, duplicate refs, and combat-time changes fail closed.
- Weather trait interactions retain the detached base-trait projection and now
  also compile explicit laws for every trusted Status that grants the trait.
  These laws inspect bounded Status slots at runtime, exclude actors that
  already own the base trait, and select only the first matching slot, so one
  effective trait produces one weather contribution.
- Weather compilation receives the trusted Status registry from Gate 3 content;
  controller input still cannot inject traits or effects.

## Automated tests

Gate 3 only:

```text
python3 -m unittest discover \
  -s experiments/generative_mechanics/next_tracks_v06/gameplay_v04/tests \
  -p 'test_gate3_*.py' -v

Ran 12 tests in 1.047s
OK
```

Gate 1-3 integration regression:

```text
python3 -m unittest discover \
  -s experiments/generative_mechanics/next_tracks_v06/gameplay_v04/tests \
  -p 'test_gate[0123]_*.py' -v

Owner rerun:

```text
Ran 67 tests in 4.222s
OK
```

The Gate 3 tests cover selective/bounded weather, Status-granted trait lowering,
deterministic/reachable ecology, sustained transition and baseline replacement,
lucky-harvest time/yield/consumption independence, failed-harvest atomicity,
material tier versus regional rarity, compound shared budgets, reversible
loadout moves, empty-source atomicity, combat loadout locking, traces, and the
absence of unexpected scheduled events.

## Deterministic demo

```text
PYTHONPATH=src:. python3 -m \
  experiments.generative_mechanics.next_tracks_v06.gameplay_v04.gate3_demo
```

Two independent processes produced byte-identical output (`cmp` exit 0).

```text
SHA-256: 62ddd6a1d395e769fcb95fab41026d8e67a2b36c10da74413831df45d3d05515
```

The output demonstrates one trusted runtime containing traced weather pulses,
trait-selective mana, lucky and ordinary harvests with constant depletion,
overharvest-driven ecology transition, a generated compound skill, a trusted
loadout transaction, and zero leaked scheduled events.

## Remaining risks

- Gate 3 uses a bounded eight-slot scan when projecting Status-granted traits.
  This is deliberate and deterministic, but future status-capacity changes must
  update this compiler contract.
- Skill registry manifests are immutable snapshots. Hot replacement/migration
  of an already installed version is outside Gate 3 and must not be inferred
  from the current runtime registration support.
- No Gate 4 AI claim is made by this report. Gate 4 files present in the shared
  worktree were neither edited nor included in these commands.

The Gate commit and archive identity are recorded in the repository history and
delivery summary rather than embedded here, so creating the commit does not
make this report self-referential.

The frozen v0.6 regression suite was also rerun by the owner:

```text
Ran 170 tests in 25.581s
OK
```
