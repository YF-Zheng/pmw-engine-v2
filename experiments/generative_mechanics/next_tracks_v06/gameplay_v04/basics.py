"""Configurable fixture definitions for the three slot-free basic actions."""

from __future__ import annotations

from .actions import ActionRegistry


def basic_registry_document(*, attack_base: float = 6.0, power_scale: float = 1.0,
                            guard_base: float = 2.0, resilience_scale: float = 1.0,
                            wait_mana: float = 5.0) -> dict:
    return {
        "protocol": "pmw-gameplay-v0.4",
        "statuses": [{
            "id": "basic_guarding", "version": 1, "polarity": "buff", "max_stacks": 1,
            "stack_policy": "refresh", "duration": {"unit": "owner_turn", "amount": 1},
            "granted_traits": ["guarding"], "on_expire_resource": {"resource": "shield", "value": 0.0},
        }],
        "actions": [
            {"id": "basic_attack", "version": 1, "action_type": "attack", "builtin": True,
             "cost": {"duration": 1, "mana": 0.0}, "scope": {"selectors": ["target_actor"], "relation_types": []},
             "effects": [{"id": "strike", "kind": "damage", "target": {"kind": "target_actor"},
                          "commitment": "required", "amount": attack_base,
                          "attribute_terms": [{"kind": "scaling", "attribute": "power", "coefficient": power_scale}]}]},
            {"id": "basic_guard", "version": 1, "action_type": "guard", "builtin": True,
             "cost": {"duration": 1, "mana": 0.0}, "scope": {"selectors": ["self"], "relation_types": []},
             "effects": [
                 {"id": "guard_shield", "kind": "shield", "target": {"kind": "self"},
                  "commitment": "required", "amount": guard_base,
                  "attribute_terms": [{"kind": "scaling", "attribute": "resilience", "coefficient": resilience_scale}]},
                 {"id": "guard_duration", "kind": "apply_status", "target": {"kind": "self"},
                  "commitment": "required", "status_id": "basic_guarding"},
             ]},
            {"id": "basic_wait", "version": 1, "action_type": "wait", "builtin": True,
             "cost": {"duration": 1, "mana": 0.0}, "scope": {"selectors": ["self"], "relation_types": []},
             "effects": [{"id": "rest", "kind": "add_resource", "target": {"kind": "self"},
                          "commitment": "required", "resource": "mana", "amount": wait_mana}]},
        ],
    }


def basic_registry(**kwargs) -> ActionRegistry:
    return ActionRegistry.parse(basic_registry_document(**kwargs))
