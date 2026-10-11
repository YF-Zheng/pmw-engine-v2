"""Single-writer staged transactions for authoritative Gameplay operations."""

from __future__ import annotations

from copy import deepcopy

from .runtime import GameplaySession


def stage_gameplay_session(session: GameplaySession) -> GameplaySession:
    """Clone the complete managed runtime boundary for isolated execution."""
    runtime = session.runtime.engine.attach(deepcopy(session.state))
    runtime.stats = deepcopy(session.runtime.stats)
    runtime.revision = session.runtime.revision
    runtime.object_revision = session.runtime.object_revision
    runtime.state_closure_known = session.runtime.state_closure_known
    return GameplaySession(runtime, session.profiles)


def publish_gameplay_session(session: GameplaySession, staged: GameplaySession) -> None:
    """Publish a successfully completed staged transaction atomically."""
    session.runtime = staged.runtime
