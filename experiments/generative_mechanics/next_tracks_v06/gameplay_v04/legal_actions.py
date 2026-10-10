"""Deterministic legal action enumeration over actor-safe observations."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Iterable

from .actions import ActionRegistry, ActionRequest
from .contracts import GameplayContractError
from .observation import ActorObservation, canonical_json
from .simulation import SandboxSimulator


@dataclass(frozen=True, slots=True)
class LegalAction:
    request: ActionRequest
    action_type: str
    canonical_key: str
    legality_evidence: tuple[str, ...]


class LegalActionGenerator:
    def __init__(self, registry: ActionRegistry, *, max_candidates: int = 64):
        if isinstance(max_candidates, bool) or not isinstance(max_candidates, int) or max_candidates < 1:
            raise GameplayContractError("max_candidates must be positive")
        self.registry = registry
        self.max_candidates = max_candidates
        self.simulator = SandboxSimulator(registry)

    def generate(
        self,
        observation: ActorObservation,
        *,
        actor_id: str | None = None,
        request_namespace: str = "choice",
    ) -> tuple[LegalAction, ...]:
        document = observation.to_dict()
        actor_id = actor_id or observation.observer_id
        actor = document["actors"].get(actor_id)
        if actor is None or actor["hp"] <= 0:
            return ()
        action_ids = document["known_actions"].get(actor_id, ())
        candidates: list[LegalAction] = []
        for action_id in sorted(action_ids):
            definition = self.registry.actions.get(action_id)
            if definition is None or actor["mana"] < definition.cost.mana:
                continue
            needs_target = any(effect.target.kind == "target_actor" for effect in definition.effects)
            targets: Iterable[str | None] = (
                tuple(key for key, value in sorted(document["actors"].items()) if key != actor_id and value["hp"] > 0)
                if needs_target else (None,)
            )
            for target_id in targets:
                canonical_key = f"{action_id}|{target_id or ''}"
                request = ActionRequest(
                    _request_id(observation, request_namespace, actor_id, canonical_key),
                    actor_id, action_id, target_id,
                )
                # Production preflight is authoritative.  It runs only in a
                # fresh projected sandbox, so enumeration has no side effects.
                validation = self.simulator.simulate(observation.for_observer(actor_id), request)
                if validation.legal:
                    candidates.append(LegalAction(
                        request, definition.action_type, canonical_key,
                        ("visible_actor_alive", "visible_resources_sufficient", "production_preflight_passed"),
                    ))
        candidates.sort(key=lambda item: item.canonical_key)
        if len(candidates) > self.max_candidates:
            raise GameplayContractError("legal action candidate limit exceeded")
        return tuple(candidates)


def _request_id(
    observation: ActorObservation,
    namespace: str,
    actor_id: str,
    canonical_key: str,
) -> str:
    digest = hashlib.sha256(canonical_json({
        "observation": observation.canonical_sha256,
        "namespace": namespace,
        "actor": actor_id,
        "choice": canonical_key,
    }).encode("ascii")).hexdigest()[:24]
    return f"ai_{digest}"
