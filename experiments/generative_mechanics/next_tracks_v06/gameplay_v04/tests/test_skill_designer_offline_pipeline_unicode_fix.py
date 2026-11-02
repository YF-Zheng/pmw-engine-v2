from __future__ import annotations

import json

import pytest

from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.materials import (
    MaterialDefinition,
    parse_material,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.skill_designer.pipeline import (
    PipelineResult,
    _CandidateRejection,
    decode_candidate,
    run_offline_pipeline,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.skill_designer.replay import (
    ReplayProvider,
    ReplayReply,
)


MATERIAL_ID = "p3_unicode_material"
CANDIDATE_ID = "unicode_candidate"


def _material() -> MaterialDefinition:
    return parse_material({
        "id": MATERIAL_ID,
        "tier": "fine",
        "region_rarity": "uncommon",
        "traits": [{
            "id": "unicode_authority",
            "effect_kinds": ["damage"],
            "selectors": ["target_actor"],
            "budget_points": 12.0,
        }],
    })


def _document() -> dict[str, object]:
    return {
        "protocol": "pmw-skill-ir-v1",
        "identity": {
            "id": "candidate_supplied",
            "version": 9,
            "name": "Unicode Fixture",
            "description": "Unicode fixture description.",
        },
        "origin": {
            "source": "generated",
            "model": "candidate_model",
            "context_hash": "a" * 64,
            "material_ids": [MATERIAL_ID],
        },
        "capability": {"traits": ["unicode_trait"]},
        "targeting": {
            "selectors": ["target_actor"],
            "relation_types": [],
        },
        "costs": {"mana": 1, "duration": 1},
        "entries": [{
            "id": "active",
            "trigger": {"kind": "on_use"},
            "condition": None,
            "effects": [{
                "id": "unicode_pulse",
                "kind": "damage",
                "target": {"kind": "target_actor"},
                "commitment": "required",
                "amount": 3,
            }],
            "max_firings_per_root": 1,
        }],
        "lifecycle": {"status_duration": None},
        "limits": {"budget": 12.0},
        "display": {
            "summary": "Unicode summary.",
            "tags": ["unicode_fixture"],
        },
    }


def _snapshot(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _run(
    replies: list[str] | tuple[str, ...],
    *,
    max_repairs: int = 0,
) -> tuple[PipelineResult, ReplayProvider]:
    provider = ReplayProvider(tuple(ReplayReply(reply) for reply in replies))
    result = run_offline_pipeline(
        materials=[_material()],
        statuses={},
        profile="combat",
        complexity=1,
        public_known_rules=[],
        acquired_capabilities=[],
        existing_skills=[],
        candidate_id=CANDIDATE_ID,
        replay=provider,
        max_repairs=max_repairs,
    )
    return result, provider


def _replace_once(text: str, old: str, new: str) -> str:
    assert text.count(old) == 1
    return text.replace(old, new)


def _wire_document(location: str, escape: str) -> str:
    text = _snapshot(_document())
    if location == "identity_value":
        return _replace_once(
            text,
            '"name":"Unicode Fixture"',
            f'"name":"Identity {escape}"',
        )
    if location == "identity_key":
        return _replace_once(
            text,
            '"name":"Unicode Fixture"',
            f'"name":"Unicode Fixture","{escape}":null',
        )
    if location == "display_value":
        return _replace_once(
            text,
            '"summary":"Unicode summary."',
            f'"summary":"Display {escape}"',
        )
    if location == "display_key":
        return _replace_once(
            text,
            '"summary":"Unicode summary."',
            f'"summary":"Unicode summary.","{escape}":null',
        )
    if location == "origin_value":
        return _replace_once(
            text,
            '"model":"candidate_model"',
            f'"model":"Origin {escape}"',
        )
    if location == "origin_key":
        return _replace_once(
            text,
            '"model":"candidate_model"',
            f'"model":"candidate_model","{escape}":null',
        )
    if location == "nested_effect_key":
        return _replace_once(
            text,
            '"target":{"kind":"target_actor"}',
            f'"target":{{"kind":"target_actor","{escape}":null}}',
        )
    raise AssertionError(f"unknown location {location}")


@pytest.mark.parametrize(
    "text",
    [
        r'{"x":"\ud800"}',
        r'{"x":"\udfff"}',
        r'{"outer":{"items":[{"value":"\ud83d"}]}}',
        r'{"outer":{"items":[{"value":"\ude00"}]}}',
        r'{"\ud800":1}',
        r'{"outer":{"\udfff":1}}',
    ],
)
def test_decode_rejects_lone_surrogates_in_values_and_keys_at_any_depth(text):
    with pytest.raises(_CandidateRejection, match="invalid Unicode") as caught:
        decode_candidate(text)
    assert caught.value.stage == "decode"


@pytest.mark.parametrize(
    ("location", "escape"),
    [
        ("identity_value", r"\ud800"),
        ("identity_key", r"\udfff"),
        ("display_value", r"\ud800"),
        ("display_key", r"\udfff"),
        ("origin_value", r"\ud800"),
        ("origin_key", r"\udfff"),
        ("nested_effect_key", r"\ud800"),
    ],
)
def test_pipeline_rejects_wire_lone_surrogates_before_normalize_or_parse(
    location, escape
):
    result, provider = _run([_wire_document(location, escape)])
    payload = result.to_dict()

    assert result.parsed is None
    assert result.compiled is None
    assert payload["status"] == "rejected"
    assert payload["ir"] is None
    assert payload["ir_hash"] is None
    assert payload["attempts"][0]["stage"] == "decode"
    assert "invalid Unicode" in payload["attempts"][0]["reason"]
    assert provider.calls[0].reply_text == payload["calls"][0]["reply_text"]


def test_max_repairs_cannot_bypass_bad_unicode_decode_rejection():
    bad = _wire_document("display_value", r"\ud800")
    result, provider = _run([bad, bad, bad], max_repairs=2)
    payload = result.to_dict()

    assert result.parsed is None
    assert result.compiled is None
    assert payload["failure"]["stage"] == "repairs_exhausted"
    assert [row["stage"] for row in payload["attempts"]] == [
        "decode",
        "decode",
        "decode",
    ]
    assert all(not row["accepted"] for row in payload["attempts"])
    assert len(provider.calls) == 3
    assert provider.remaining == 0


def test_decode_applies_string_limit_to_keys():
    exact_key = "k" * 4096
    decoded = decode_candidate('{"' + exact_key + '":null}')
    assert next(iter(decoded.document)) == exact_key

    oversized_key = "k" * 4097
    with pytest.raises(_CandidateRejection, match="string is too long"):
        decode_candidate('{"' + oversized_key + '":null}')


def test_valid_escaped_pair_literal_emoji_and_chinese_compile_exactly():
    text = _replace_once(
        _snapshot(_document()),
        '"name":"Unicode Fixture"',
        r'"name":"Escaped \ud83d\ude80"',
    )
    text = _replace_once(
        text,
        '"description":"Unicode fixture description."',
        '"description":"Literal 🚀 中文"',
    )
    text = _replace_once(
        text,
        '"summary":"Unicode summary."',
        '"summary":"摘要 🚀 exact."',
    )
    text = _replace_once(
        text,
        '"tags":["unicode_fixture"]',
        '"tags":["标签_中文"]',
    )

    decoded = decode_candidate(text)
    assert decoded.document["identity"]["name"] == "Escaped 🚀"
    assert decoded.document["identity"]["description"] == "Literal 🚀 中文"

    result, _ = _run([text])
    assert result.parsed is not None
    assert result.compiled is not None
    payload = result.to_dict()
    assert payload["status"] == "compiled_unregistered"
    assert payload["attempts"][0]["stage"] == "compiled"
    assert payload["ir"]["identity"]["name"] == "Escaped 🚀"
    assert payload["ir"]["identity"]["description"] == "Literal 🚀 中文"
    assert payload["ir"]["display"] == {
        "summary": "摘要 🚀 exact.",
        "tags": ["标签_中文"],
    }
