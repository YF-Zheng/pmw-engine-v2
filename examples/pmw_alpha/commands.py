"""Typed public commands for the Before the Seventh Night browser client.

The browser can request a verb and stable public target ID only.  Costs,
effects, WorldState paths, and PMW law/event identities are server authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


class AlphaCommandError(ValueError):
    """Raised for malformed external commands before a transaction is staged."""


@dataclass(frozen=True, slots=True)
class AlphaCommand:
    action: str
    target: str | None = None
    slot: int | None = None
    difficulty: str | None = None

    @classmethod
    def parse(cls, raw: Mapping[str, Any]) -> "AlphaCommand":
        if not isinstance(raw, Mapping):
            raise AlphaCommandError("command must be an object")
        unknown = set(raw) - {"action", "target", "slot", "difficulty"}
        if unknown:
            raise AlphaCommandError(f"unknown command fields: {sorted(unknown)}")
        action, target, slot, difficulty = raw.get("action"), raw.get("target"), raw.get("slot"), raw.get("difficulty")
        if not isinstance(action, str) or not action:
            raise AlphaCommandError("action must be a non-empty string")
        if target is not None and (not isinstance(target, str) or not target.replace("_", "").isalnum()):
            raise AlphaCommandError("target must be a stable public identifier")
        if slot is not None and (isinstance(slot, bool) or not isinstance(slot, int) or not 0 <= slot < 6):
            raise AlphaCommandError("slot must be an integer from 0 through 5")
        if difficulty is not None and difficulty not in {"explore", "standard", "challenge"}:
            raise AlphaCommandError("difficulty must be explore, standard, or challenge")
        return cls(action, target, slot, difficulty)

