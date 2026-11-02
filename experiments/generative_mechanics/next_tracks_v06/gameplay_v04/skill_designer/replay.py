"""Bounded, immutable offline replay transport for Skill candidates."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Sequence

from ..contracts import GameplayContractError


MAX_REPLY_BYTES = 65536


@dataclass(frozen=True, slots=True)
class ReplayRequest:
    """One immutable provider request assembled by the pipeline."""

    attempt: int
    feedback: str
    context_hash: str

    def __post_init__(self) -> None:
        if (
            isinstance(self.attempt, bool)
            or not isinstance(self.attempt, int)
            or self.attempt < 1
        ):
            raise GameplayContractError("replay attempt must be a positive integer")
        if not isinstance(self.feedback, str):
            raise GameplayContractError("replay feedback must be text")
        if (
            not isinstance(self.context_hash, str)
            or len(self.context_hash) != 64
            or any(character not in "0123456789abcdef" for character in self.context_hash)
        ):
            raise GameplayContractError(
                "replay context_hash must be 64 lowercase hex characters"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "attempt": self.attempt,
            "feedback": self.feedback,
            "context_hash": self.context_hash,
        }


@dataclass(frozen=True, slots=True)
class ReplayReply:
    """One fixture reply; its provenance is always authored/offline."""

    text: str
    origin_source: str = "authored"
    origin_model: None = None

    def __post_init__(self) -> None:
        if not isinstance(self.text, str):
            raise GameplayContractError("replay reply must be text")
        try:
            size = len(self.text.encode("utf-8"))
        except UnicodeEncodeError as error:
            raise GameplayContractError(
                "replay reply is not valid Unicode text"
            ) from error
        if size > MAX_REPLY_BYTES:
            raise GameplayContractError(
                f"replay reply exceeds {MAX_REPLY_BYTES} UTF-8 bytes"
            )
        if self.origin_source != "authored" or self.origin_model is not None:
            raise GameplayContractError(
                "replay provenance must be authored with no model"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "text": self.text,
            "origin_source": self.origin_source,
            "origin_model": self.origin_model,
        }


@dataclass(frozen=True, slots=True)
class ReplayCall:
    """A stable call record; it is not model usage or billing evidence."""

    attempt: int
    feedback: str
    context_hash: str
    reply_text: str | None
    reply_hash: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "attempt": self.attempt,
            "feedback": self.feedback,
            "context_hash": self.context_hash,
            "reply_text": self.reply_text,
            "reply_hash": self.reply_hash,
        }

    @property
    def canonical_json(self) -> str:
        return json.dumps(
            self.to_dict(), sort_keys=True, separators=(",", ":"), allow_nan=False
        )


class ReplayProvider:
    """Finite in-memory replay source with no transport or generation path."""

    __slots__ = ("_replies", "_cursor", "_calls")

    def __init__(self, replies: Sequence[ReplayReply]) -> None:
        if (
            isinstance(replies, (str, bytes, bytearray))
            or not isinstance(replies, Sequence)
        ):
            raise GameplayContractError("replay replies must be a finite sequence")
        if len(replies) > 3:
            raise GameplayContractError("replay provider permits at most 3 replies")
        checked = []
        for index, reply in enumerate(replies):
            if not isinstance(reply, ReplayReply):
                raise GameplayContractError(
                    f"replay replies[{index}] must be ReplayReply"
                )
            checked.append(
                ReplayReply(reply.text, reply.origin_source, reply.origin_model)
            )
        self._replies = tuple(checked)
        self._cursor = 0
        self._calls: list[ReplayCall] = []

    def __len__(self) -> int:
        return len(self._replies)

    @property
    def calls(self) -> tuple[ReplayCall, ...]:
        return tuple(self._calls)

    @property
    def remaining(self) -> int:
        return len(self._replies) - self._cursor

    def reply(self, request: ReplayRequest) -> ReplayReply:
        if not isinstance(request, ReplayRequest):
            raise GameplayContractError("replay request must be ReplayRequest")
        if self._cursor >= len(self._replies):
            response = None
            self._calls.append(
                ReplayCall(
                    request.attempt,
                    request.feedback,
                    request.context_hash,
                    None,
                    None,
                )
            )
            raise ReplayExhaustedError("replay provider exhausted")
        response = self._replies[self._cursor]
        self._cursor += 1
        digest = hashlib.sha256(response.text.encode("utf-8")).hexdigest()
        self._calls.append(
            ReplayCall(
                request.attempt,
                request.feedback,
                request.context_hash,
                response.text,
                digest,
            )
        )
        return response


class ReplayExhaustedError(GameplayContractError):
    """The finite replay sequence has no next reply."""

