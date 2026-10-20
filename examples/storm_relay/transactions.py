"""Small transaction helpers shared by the M0 session implementation.

Gameplay's public APIs already stage individual operations.  Storm Relay needs
to compose several of them (for example recipe receipt, registry installation,
loadout, and time) into one command-level all-or-nothing operation.  The session
uses these helpers to stage an entire runtime envelope and publishes it only
after the command and all resulting world ticks have succeeded.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Callable, TypeVar


T = TypeVar("T")


class TransactionError(RuntimeError):
    """Wrap an action failure after discarding the working session."""


def staged_call(clone: Callable[[], T], operation: Callable[[T], object]) -> tuple[T, object]:
    """Execute an operation on a complete detached clone.

    `clone` belongs to the Session because it owns the registry/runtime rebuild
    details.  The helper deliberately has no PMW-specific mutation shortcuts.
    """

    working = clone()
    result = operation(working)
    return working, result


def immutable_snapshot(value: object) -> object:
    """Create reportable before-state evidence without aliases into a runtime."""

    return deepcopy(value)

