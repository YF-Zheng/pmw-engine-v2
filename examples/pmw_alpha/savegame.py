"""Single-slot persistence boundary for PMW Alpha.

This module deliberately does not serialize an :class:`AlphaSession` by
walking its private attributes.  The authoritative world, pending Scheduler
events, and dynamic mechanism registry are saved with Gameplay v0.4's
``save_registry_checkpoint`` envelope.  That envelope is checked against the
trusted compiled content on restore, so a save cannot supply replacement Laws
or executable skill definitions.

The Alpha session integration supplies two small hooks instead:

``export_save_metadata() -> Mapping[str, Any]``
    Return JSON-safe Alpha-owned state not represented in ``WorldState`` (for
    example the presentation event log).  Durable gameplay facts belong in
    WorldState and must not be duplicated here.

``restore(runtime, metadata) -> AlphaSession``
    Reattach a verified ``MechanismRegistryRuntime`` and the metadata to a new
    session.  The callback owns no parsing or trust decisions.

Until AlphaSession exists, these hooks keep save/load useful and testable
without creating a second world serializer.  The only supported storage shape
is one named file within a caller-owned directory; writes are atomic on the
same filesystem.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Callable, Mapping, Protocol, TypeVar

from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.checkpoint import (
    load_registry_checkpoint,
    save_registry_checkpoint,
)


SAVE_SCHEMA = "pmw-alpha-save-v0.2"
DEFAULT_SLOT_NAME = "pmw-alpha-save.json"


class SaveGameError(ValueError):
    """A save file is missing, malformed, or incompatible with trusted content."""


class SaveableSession(Protocol):
    """Minimum Alpha-facing contract; ``_registry`` is the Gameplay runtime."""

    _registry: Any

    def export_save_metadata(self) -> Mapping[str, Any]:
        """Return JSON-safe, non-authoritative Alpha session metadata."""


SessionT = TypeVar("SessionT")
RestoreSession = Callable[[Any, Mapping[str, Any]], SessionT]


@dataclass(frozen=True, slots=True)
class SaveSummary:
    """Inspectable, non-authoritative details about a successfully saved slot."""

    path: Path
    payload_sha256: str
    metadata: Mapping[str, Any]


class SingleSlotSave:
    """A bounded, atomic save slot rooted in one caller-provided directory."""

    def __init__(self, directory: str | Path, filename: str = DEFAULT_SLOT_NAME):
        if not isinstance(filename, str) or not filename or Path(filename).name != filename:
            raise ValueError("save filename must be a single non-empty filename")
        self.directory = Path(directory)
        self.path = self.directory / filename

    def exists(self) -> bool:
        return self.path.is_file()

    def save(self, session: SaveableSession) -> SaveSummary:
        return save_game(self.path, session)

    def load(self, compiled: Any, restore: RestoreSession[SessionT]) -> SessionT:
        return load_game(self.path, compiled=compiled, restore=restore)


def save_game(path: str | Path, session: SaveableSession) -> SaveSummary:
    """Atomically replace a slot with a verified Gameplay checkpoint envelope.

    The nested Gameplay document is produced by its canonical serializer.  We
    reparse it before it is embedded so malformed/incomplete third-party
    adapters never become an Alpha save.
    """

    destination = Path(path)
    # Keep the protocol static-only so AlphaSession need not inherit from a
    # persistence base class.
    if not hasattr(session, "_registry") or not hasattr(session, "export_save_metadata"):
        raise SaveGameError("session must expose _registry and export_save_metadata()")
    try:
        metadata = dict(session.export_save_metadata())
        _json_safe(metadata, "session metadata")
    except (TypeError, ValueError) as error:
        raise SaveGameError("session metadata must be JSON-safe mapping data") from error

    destination.parent.mkdir(parents=True, exist_ok=True)
    checkpoint_path = _temporary_path(destination.parent, ".gameplay-checkpoint-")
    try:
        save_registry_checkpoint(checkpoint_path, session._registry)
        checkpoint = _read_json(checkpoint_path, "Gameplay checkpoint")
    except Exception as error:
        raise SaveGameError(f"unable to save Gameplay checkpoint: {error}") from error
    finally:
        checkpoint_path.unlink(missing_ok=True)

    payload = {"schema": SAVE_SCHEMA, "gameplay_checkpoint": checkpoint, "metadata": metadata}
    envelope = {**payload, "payload_sha256": _digest(payload)}
    _atomic_json_write(destination, envelope)
    return SaveSummary(destination, envelope["payload_sha256"], metadata)


def load_game(path: str | Path, *, compiled: Any, restore: RestoreSession[SessionT]) -> SessionT:
    """Load one Alpha slot using trusted compiled content and a session factory."""

    if not callable(restore):
        raise TypeError("restore must be callable")
    source = Path(path)
    if not source.is_file():
        raise SaveGameError("save slot does not exist")
    raw = _read_json(source, "save slot")
    if set(raw) != {"schema", "gameplay_checkpoint", "metadata", "payload_sha256"}:
        raise SaveGameError("save slot envelope shape is invalid")
    payload = {key: raw[key] for key in ("schema", "gameplay_checkpoint", "metadata")}
    if payload["schema"] != SAVE_SCHEMA:
        raise SaveGameError("unsupported Alpha save schema")
    if not isinstance(raw["payload_sha256"], str) or raw["payload_sha256"] != _digest(payload):
        raise SaveGameError("save slot payload hash mismatch")
    if not isinstance(payload["metadata"], dict):
        raise SaveGameError("save slot metadata must be an object")

    checkpoint_path = _temporary_path(source.parent, ".gameplay-restore-")
    try:
        _atomic_json_write(checkpoint_path, payload["gameplay_checkpoint"])
        runtime = load_registry_checkpoint(checkpoint_path, compiled)
    except Exception as error:
        raise SaveGameError(f"unable to restore Gameplay checkpoint: {error}") from error
    finally:
        checkpoint_path.unlink(missing_ok=True)
    return restore(runtime, dict(payload["metadata"]))


def inspect_save(path: str | Path) -> SaveSummary:
    """Return verified metadata without hydrating a runtime or executing Laws."""

    source = Path(path)
    raw = _read_json(source, "save slot")
    if set(raw) != {"schema", "gameplay_checkpoint", "metadata", "payload_sha256"}:
        raise SaveGameError("save slot envelope shape is invalid")
    payload = {key: raw[key] for key in ("schema", "gameplay_checkpoint", "metadata")}
    if payload["schema"] != SAVE_SCHEMA or raw["payload_sha256"] != _digest(payload):
        raise SaveGameError("save slot is not valid")
    if not isinstance(payload["metadata"], dict):
        raise SaveGameError("save slot metadata must be an object")
    return SaveSummary(source, raw["payload_sha256"], dict(payload["metadata"]))


def _digest(value: Mapping[str, Any]) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def _json_safe(value: Any, name: str) -> None:
    try:
        json.dumps(value, sort_keys=True, allow_nan=False)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} is not JSON-safe") from error


def _read_json(path: Path, label: str) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SaveGameError(f"{label} is not readable JSON") from error
    if not isinstance(raw, dict):
        raise SaveGameError(f"{label} must be a JSON object")
    return raw


def _temporary_path(directory: Path, prefix: str) -> Path:
    handle, name = tempfile.mkstemp(prefix=prefix, suffix=".json", dir=directory)
    os.close(handle)
    return Path(name)


def _atomic_json_write(destination: Path, value: Mapping[str, Any]) -> None:
    _json_safe(value, "save envelope")
    temporary = _temporary_path(destination.parent, f".{destination.name}.")
    try:
        with temporary.open("w", encoding="utf-8") as output:
            json.dump(value, output, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
