# PMW Gameplay v0.4 Independent QA Report

Role: **D (independent adversarial QA)**
Production baseline reviewed: `4c7271bb120ce16ba7ea59a7d672ef974c2d8525`
Branch: `feature/pmw-v04-gameplay-foundations`
Verdict: **PASS**

Role D reviewed the implementation before adding tests. It changed no production
module. The only Role-D artifacts are this report and
`tests/test_gate5_independent_qa.py`.

## Agent provenance

The available subagent API exposed no model selector and no reasoning-effort
selector. Model and effort are therefore **unverified**. This report does not
claim that Luna High, or any other named model, executed the audit.

## Independent counterexamples and oracles

### Compound action atomicity

An adversarial skill first passes and simulates a conditional Area field write,
then fails a required target-HP condition, with a later conditional heal still
present. The action also has a Mana cost. The raised error leaves the canonical
`WorldState.to_dict()` byte-for-byte equivalent as a Python value, leaves Mana
unchanged, commits no field write, and creates no scheduled event.

### Dynamics closed-form oracle

Role D computed the result without calling a second gameplay helper. For domain
`[-2, 2]`, value `-1`, baseline target `1`, baseline rate `0.2`, and one source
with target `2`, weight `3`, rate add `0.05`, and multiplier `0.5`:

```text
effective target = (1 + 3*2) / (1 + 3) = 1.75
effective rate   = (0.2 + 0.05) * 0.5 = 0.125
difference       = 2.75
linear value     = -1 + 0.125*2.75 = -0.65625
squared value    = -1 + 0.125*2.75*2.75 = -0.0546875
```

Both production results matched within `1e-12`.

### Status, checkpoint, and Scheduler lifecycle

The independent status oracle starts from Guard shield `2 + resilience(3) = 5`
and one owner-turn remaining. A registry checkpoint is saved and rebuilt. The
next owner turn clears exactly that slot and sets shield to zero in both the
uninterrupted and restored sessions; their traces and final worlds are equal.

A separately installed two-tick dynamics modifier schedules exactly:

```text
pmw:v04:action-expiry:qa_timed:qa_slow_recovery @ 2.0
```

After checkpoint rebuild, advancing to `1.999` dispatches nothing and preserves
the queue. Advancing to `2.0` dispatches that one event, clears its owned slot,
empties the queue, and produces the same final world as uninterrupted execution.

### Strict sequential combat order

With Actor 1 at one HP, Actor 0 acting first kills Actor 1; Actor 1 is skipped
and cannot submit its already-provided request. Reversing order lets Actor 1
deal 14 damage before dying. Both rounds advance exactly one World Tick. This
confirms that order is a real sequential-commit semantic, not a simultaneous
batch accidentally dependent on iteration order.

### AI information boundary

The adversarial world adds both an unequipped 9,999-damage trusted action and a
real parser-valid hidden PMW Law capable of setting the AI Actor's HP to zero.
Neither is disclosed. The safe Observation JSON, selected action, canonical
decision log, and every visible-registry-derived planner input remain identical
to the control world. The planner cannot inspect either hidden surface.

## Commands and logs

Dedicated independent suite:

```text
PYTHONPATH=src:. python3 -m unittest \
  experiments.generative_mechanics.next_tracks_v06.gameplay_v04.tests.test_gate5_independent_qa -v

Ran 6 tests in 1.918s
OK
wall: 2.05s
failures: 0
errors: 0
skipped: 0
expected failures: 0
log: /tmp/pmw_v04_gate5_independent_qa.log
log SHA-256: e66b12531f73738106593c8841dbe4d4164583bb45cf24969a48f6dd0115ef24
```

Integrated Gate 1-5 gameplay suite as present in the shared worktree:

```text
PYTHONPATH=src:. python3 -m unittest discover \
  -s experiments/generative_mechanics/next_tracks_v06/gameplay_v04/tests \
  -p 'test_gate*.py' -v

Ran 105 tests in 20.628s
OK
wall: 20.77s
failures: 0
errors: 0
skipped: 0
expected failures: 0
log: /tmp/pmw_v04_gate1_to_gate5_qa.log
log SHA-256: 258c0e3965863e00c4457af7210297b90976691bb8df3dfe87844643014b1af8
```

The integrated command included the main agent's Gate-5 tests that were present
in the shared worktree at execution time; Role D did not author or modify those
files.

## Raw findings

- No production defect was found by these counterexamples.
- During test authoring, the first Guard assertion incorrectly expected `4`.
  Inspection showed the public formula is base `2 + resilience 3 = 5`; Role D
  corrected only its test oracle and reran from a clean process. This was a QA
  assertion error, not a production failure.
- Hidden information invariance is intentional: a hidden Law may change later
  live execution, but cannot change planning until disclosed. Live execution
  still passes through newest-state revalidation.
- Registry checkpoint reconstruction remains deliberately tied to the same
  trusted compiled base registry and static Law set; it is not a cross-content
  migration format.
- Sequential actor order can materially change a battle result. The order must
  therefore remain an explicit, deterministic encounter input.

## Final assessment

All requested independent adversarial checks pass. There are no Role-D blockers
for the Gate 0-5 gameplay foundation freeze. The remaining boundaries above are
documented design limits, not failures observed in this audit.
