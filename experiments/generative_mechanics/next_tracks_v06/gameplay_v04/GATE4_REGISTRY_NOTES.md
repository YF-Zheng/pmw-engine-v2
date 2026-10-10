# Gate 4 Registry / Checkpoint Notes

## Boundary and authority

- `MechanismRegistryRuntime` accepts one registry transaction at a complete
  World Tick boundary. The clock, logical time, due Scheduler queue, and the
  previous transaction boundary are checked before dispatch.
- Install parses the complete `SkillBlueprint` against the trusted base Status
  registry and supplied `MaterialAuthority`. Versions are strictly monotonic;
  the canonical source document is SHA-256 checked.
- Version replacement and disable require all matching loadout references to
  be removed first. Therefore an old `(id, version, hash)` reference cannot
  silently select the newer action stored under the same public action ID.
- The manifest mutation is a formal `pmw.v04.registry.change` PMW event. The
  replacement Law set and a detached World attachment are preflighted before
  this event commits.

## Rebuild and lifecycle

PMW Core is unchanged. At the boundary, gameplay constructs a replacement
Engine and attaches the same authoritative WorldState. Only the enabled latest
version is exposed through `ActionRegistry`; disabled versions retain their
expiry and Status lifecycle Laws so already committed effects and Scheduler
handles finish normally.

Action Law identities and private expiry event types include action ID,
version, and the first 12 canonical-hash characters. This prevents v1/v2 Law
or Scheduler collisions while leaving the public Action ID stable.

## Checkpoint envelope

The canonical envelope contains the complete `WorldState` (including active
Status/Dynamics state and pending Scheduler events), canonical blueprint
documents, their material-authority snapshots, slot limits, the trusted static
Law configuration, and hashes for both the payload and static configuration.
Load validates the envelope, re-parses every blueprint, verifies the trusted
base registry/static content supplied by the application, reconstructs the
Engine, and checks the formal manifest against all reconstructed blueprints.

Static world content remains an application asset and must be supplied as the
trusted `CompiledGate3Content` on load. Its exact registry and Laws are checked
against the envelope; the checkpoint cannot silently replace executable static
content.
