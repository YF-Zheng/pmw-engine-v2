from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.contracts import (
    GameplayContractError,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.materials import (
    MaterialAuthority,
    material_authority,
    parse_material,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.reference_skills.fixtures import (
    build_fixture,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.skill_designer.context import (
    GenerationContext,
    build_generation_context,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.skill_designer.pipeline import (
    PIPELINE_PROTOCOL,
    PipelineResult,
    _CandidateRejection,
    _authority_from_materials,
    _readback_hash,
    decode_candidate,
    normalize_candidate,
    run_offline_pipeline,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.skill_designer.replay import (
    MAX_REPLY_BYTES,
    ReplayCall,
    ReplayExhaustedError,
    ReplayProvider,
    ReplayReply,
    ReplayRequest,
)


PROJECT_ROOT = Path(__file__).resolve().parents[5]
LIBRARY_PATH = (
    PROJECT_ROOT
    / "experiments"
    / "generative_mechanics"
    / "next_tracks_v06"
    / "gameplay_v04"
    / "reference_skills"
    / "library.json"
)
PROFILE_MATERIALS = {
    profile: build_fixture(profile)
    for profile in (
        "field",
        "stock",
        "process",
        "relation",
        "combat",
        "travel",
        "derived",
    )
}


def _material(
    material_id: str = "p3_offline_material",
    *,
    kinds=("damage",),
    selectors=("target_actor",),
    budget: float = 200.0,
):
    return parse_material({
        "id": material_id,
        "tier": "rare",
        "region_rarity": "scarce",
        "traits": [{
            "id": "offline_authority",
            "effect_kinds": list(kinds),
            "selectors": list(selectors),
            "budget_points": budget,
        }],
    })


def _authority(material):
    return material_authority((material,))


def _document(
    *,
    material_id: str = "p3_offline_material",
    skill_id: str = "candidate_claimed",
    source: str = "generated",
    model: str = "claimed-model",
    context_hash: str | None = "1" * 64,
    effect_kind: str = "damage",
    effect_target: str = "target_actor",
    effects=None,
    selector: str = "target_actor",
    budget: float = 20.0,
):
    if effects is None:
        effects = [{
            "id": "pulse",
            "kind": effect_kind,
            "target": {"kind": effect_target},
            "commitment": "required",
            "amount": 4,
        }]
    return {
        "protocol": "pmw-skill-ir-v1",
        "identity": {
            "id": skill_id,
            "version": 9,
            "name": "Candidate Name",
            "description": "Candidate description.",
        },
        "origin": {
            "source": source,
            "model": model,
            "context_hash": context_hash,
            "material_ids": [material_id],
        },
        "capability": {"traits": ["offline_trait"]},
        "targeting": {"selectors": [selector], "relation_types": []},
        "costs": {"mana": 1, "duration": 1},
        "entries": [{
            "id": "active",
            "trigger": {"kind": "on_use"},
            "condition": None,
            "effects": effects,
            "max_firings_per_root": 1,
        }],
        "lifecycle": {"status_duration": None},
        "limits": {"budget": budget},
        "display": {"summary": "Offline fixture.", "tags": ["offline"]},
    }


def _profile_document(profile: str):
    rows = json.loads(LIBRARY_PATH.read_text(encoding="utf-8"))
    document = next(
        item for item in rows
        if f"fixture:{profile}" in item["display"]["tags"]
    )
    fixture = PROFILE_MATERIALS[profile]
    return document, fixture.statuses, fixture.authority


def _fixture_material(profile: str):
    fixture = PROFILE_MATERIALS[profile]
    authority = fixture.authority
    return parse_material({
        "id": fixture.material_id,
        "tier": "rare",
        "region_rarity": "scarce",
        "traits": [{
            "id": f"{profile}_authority",
            "effect_kinds": list(authority.effect_kinds),
            "selectors": list(authority.selectors),
            "budget_points": authority.budget_points,
        }],
    })


def _run(
    replies,
    *,
    material=None,
    statuses=None,
    max_repairs=0,
    context=None,
    replay=None,
):
    material = material or _material()
    fixture = PROFILE_MATERIALS["combat"]
    statuses = statuses or fixture.statuses
    context = context or build_generation_context(
        profile="combat",
        materials=[material],
        complexity=1,
        public_known_rules=[],
        acquired_capabilities=[],
        existing_skills=[],
    )
    provider = (
        replay
        if replay is not None
        else ReplayProvider(tuple(
            ReplayReply(reply) if isinstance(reply, str) else reply
            for reply in replies
        ))
    )
    result = run_offline_pipeline(
        materials=[material],
        statuses=statuses,
        profile="combat",
        complexity=1,
        public_known_rules=[],
        acquired_capabilities=[],
        existing_skills=[],
        candidate_id="server_candidate",
        replay=provider,
        max_repairs=max_repairs,
    )
    return result, provider, context


def _assert_rejected(result: PipelineResult, stage: str | None = None):
    document = result.to_dict()
    assert document["status"] == "rejected"
    assert document["gate_state"] == {
        "accepted": False,
        "sandbox": "not_run",
        "register": "not_available",
        "usable_pool": False,
    }
    assert document["ir"] is None
    assert document["ir_hash"] is None
    assert document["blueprint_hash"] is None
    assert result.parsed is None
    assert result.compiled is None
    assert result.accepted is False
    if stage is not None:
        assert stage in {
            row["stage"] for row in document["attempts"]
        } | {document["failure"]["stage"]}
    return document


@pytest.mark.parametrize("profile", ("field", "process", "relation", "combat"))
def test_current_library_field_process_relation_and_passive_compile_offline(profile):
    document, statuses, authority = _profile_document(profile)
    material = _fixture_material(profile)
    result = run_offline_pipeline(
        materials=[material],
        statuses=statuses,
        profile=profile,
        complexity=2,
        public_known_rules=["public:fact"],
        acquired_capabilities=["offline.compile"],
        existing_skills=[],
        candidate_id="server_candidate",
        replay=ReplayProvider((ReplayReply(_snapshot(document)),)),
        max_repairs=0,
    )
    payload = result.to_dict()
    assert payload["protocol"] == PIPELINE_PROTOCOL
    assert payload["status"] == "compiled_unregistered"
    assert payload["gate_state"]["accepted"] is False
    assert payload["gate_state"]["sandbox"] == "not_run"
    assert payload["gate_state"]["register"] == "not_available"
    assert payload["gate_state"]["usable_pool"] is False
    assert payload["replay"] == {
        "provider": "offline_replay",
        "generated_skills": 0,
        "live_requests": 0,
        "actual_usage": None,
        "actual_cost": None,
        "model": None,
    }
    assert result.parsed.origin_source == "authored"
    assert result.parsed.origin_model is None
    assert result.parsed.id == "server_candidate"
    assert result.parsed.version == 1
    assert result.compiled.canonical_hash == result.parsed.canonical_hash
    assert payload["ir"] == json.loads(result.parsed.canonical_json)


def test_normalization_preserves_effects_costs_conditions_and_unknown_keys():
    material = _material(kinds=("damage",), selectors=("target_actor",))
    document = _document(
        effect_kind="damage",
        effects=[{
            "id": "pulse",
            "kind": "damage",
            "target": {"kind": "target_actor"},
            "commitment": "required",
            "amount": 4.5,
            "unknown_effect_field": {"keep": True},
        }],
        budget=19.25,
    )
    context = build_generation_context(
        profile="combat",
        materials=[material],
        complexity=1,
        public_known_rules=[],
        acquired_capabilities=[],
    )
    accepted = _document(budget=19.25)
    accepted["display"]["unknown_display"] = "preserved"
    normalized = normalize_candidate(
        accepted,
        context=context,
        authority=_authority(material),
        candidate_id="server_candidate",
    )
    assert normalized["display"]["unknown_display"] == "preserved"
    assert normalized["origin"]["material_ids"] == ["p3_offline_material"]
    assert normalized["identity"]["id"] == "server_candidate"
    assert normalized["identity"]["version"] == 1
    assert normalized["origin"]["source"] == "authored"
    assert normalized["origin"]["model"] is None
    assert normalized["origin"]["context_hash"] == context.context_hash
    assert normalized["limits"]["budget"] == 19.25
    assert accepted["identity"]["id"] == "candidate_claimed"


def test_unknown_root_keys_survive_normalization_and_strict_parser_rejects():
    document = _document()
    document["unknown_root"] = {"secret": "preserved"}
    result, _, _ = _run([_snapshot(document)])
    payload = _assert_rejected(result, "parse")
    assert "root object must contain exactly the Skill IR fields" in payload[
        "attempts"
    ][0]["reason"]


def test_nested_duplicate_key_is_rejected_before_normalization():
    valid = _snapshot(_document())
    duplicate = valid.replace(
        '"effect":',
        '"amount":1,"amount":2,"effect":',
        1,
    )
    if duplicate == valid:
        duplicate = valid.replace(
            '"entries":',
            '"entries":[{"x":1,"x":2}],',
            1,
        )
    with pytest.raises(_CandidateRejection, match="duplicate JSON key"):
        decode_candidate(duplicate)


@pytest.mark.parametrize(
    "text, reason",
    (
        ("{not JSON}", "invalid JSON"),
        ('{"x":1,"x":2}', "duplicate JSON key"),
        ('{"x":NaN}', "non-finite JSON number"),
        ('{"x":Infinity}', "non-finite JSON number"),
        ("[]", "root JSON value must be an object"),
        ('{"x":1} trailing', "invalid JSON"),
        ('```json\n{"x":1}\n```\n```json\n{"x":2}\n```', "only one"),
        ('```json\n{"x":1}\n``` trailing', "incomplete"),
        ('```\n{"x":1}\n```', "fence language"),
    ),
)
def test_decode_rejects_malformed_json_and_fences(text, reason):
    with pytest.raises(_CandidateRejection, match=reason):
        decode_candidate(text)


def test_decode_accepts_one_complete_json_fence():
    decoded = decode_candidate('```json\n{"protocol":"x","value":1}\n```')
    assert decoded.document == {"protocol": "x", "value": 1}


def test_decode_rejects_oversized_deep_and_invalid_unicode_text():
    with pytest.raises(_CandidateRejection, match="65536"):
        decode_candidate(" " * (MAX_REPLY_BYTES + 1))
    nested = '{"x":' * 130 + "null" + "}" * 130
    with pytest.raises(_CandidateRejection, match="depth"):
        decode_candidate(nested)
    with pytest.raises(_CandidateRejection, match="Unicode"):
        decode_candidate("\ud800")


def test_replay_provider_is_finite_immutable_and_records_attempts():
    provider = ReplayProvider((
        ReplayReply('{"x":1}'),
        ReplayReply('{"x":2}'),
    ))
    assert len(provider) == 2
    assert provider.remaining == 2
    first = provider.reply(ReplayRequest(1, "", "0" * 64))
    second = provider.reply(ReplayRequest(2, "stage=parse; reason=bad", "1" * 64))
    assert first.text == '{"x":1}'
    assert second.text == '{"x":2}'
    assert provider.remaining == 0
    assert tuple(call.attempt for call in provider.calls) == (1, 2)
    assert provider.calls[0].feedback == ""
    assert provider.calls[1].feedback == "stage=parse; reason=bad"
    assert provider.calls[0].context_hash == "0" * 64
    assert len(provider.calls[0].reply_hash) == 64
    with pytest.raises(ReplayExhaustedError):
        provider.reply(ReplayRequest(3, "", "2" * 64))
    assert len(provider.calls) == 3
    assert provider.calls[-1].reply_text is None
    with pytest.raises(GameplayContractError, match="finite sequence"):
        ReplayProvider("not-a-sequence")
    with pytest.raises(GameplayContractError, match="at most 3"):
        ReplayProvider((ReplayReply("{}"),) * 4)
    with pytest.raises(GameplayContractError, match="exceeds"):
        ReplayReply("x" * (MAX_REPLY_BYTES + 1))
    with pytest.raises(GameplayContractError, match="provenance"):
        ReplayReply("{}", "generated", "fake-model")


def test_repair_limits_zero_one_two_and_maximum_three_calls():
    material = _material()
    bad = _snapshot(_document(material_id="forged_material"))
    good_document = _document(material_id=material.id)
    good = _snapshot(good_document)
    for repairs, expected_calls in ((0, 1), (1, 2), (2, 3)):
        replies = [bad] * expected_calls
        result, provider, _ = _run(replies, material=material, max_repairs=repairs)
        payload = _assert_rejected(result, "repairs_exhausted")
        assert len(payload["calls"]) == expected_calls
        assert len(payload["attempts"]) == expected_calls
        assert provider.remaining == 0
        if expected_calls > 1:
            assert payload["calls"][1]["feedback"].startswith("stage=validate;")

    result, provider, _ = _run(
        [bad, good], material=material, max_repairs=1
    )
    assert result.status == "compiled_unregistered"
    assert len(result.attempts) == 2
    assert result.attempts[0].accepted is False
    assert result.attempts[1].accepted is True
    assert result.to_dict()["calls"][1]["feedback"].startswith("stage=")
    assert provider.remaining == 0


@pytest.mark.parametrize("value", (True, False, -1, 3, 1.0, "1", None))
def test_max_repairs_rejects_non_integer_and_out_of_range(value):
    with pytest.raises(GameplayContractError, match="max_repairs"):
        _run([ReplayReply("{}")], max_repairs=value)


@pytest.mark.parametrize(
    "candidate_id",
    ("", "A", "Upper", "space id", "a" * 65, 7, None),
)
def test_candidate_id_fails_closed(candidate_id):
    fixture = PROFILE_MATERIALS["combat"]
    with pytest.raises(GameplayContractError, match="candidate_id"):
        run_offline_pipeline(
            materials=[_material()],
            statuses=fixture.statuses,
            profile="combat",
            complexity=1,
            public_known_rules=[],
            acquired_capabilities=[],
            existing_skills=[],
            candidate_id=candidate_id,
            replay=ReplayProvider((ReplayReply("{}"),)),
        )


def test_forged_material_claim_is_rejected_not_silently_replaced():
    document = _document(material_id="forged_material")
    result, _, _ = _run([_snapshot(document)])
    payload = _assert_rejected(result, "validate")
    assert "must exactly match selected trusted material IDs" in payload[
        "attempts"
    ][0]["reason"]


def test_context_authority_is_rederived_from_material_traits_not_displayed_json():
    material = _material(
        kinds=("damage",), selectors=("target_actor",), budget=2.0
    )
    context = build_generation_context(
        profile="combat",
        materials=[material],
        complexity=1,
        public_known_rules=[],
        acquired_capabilities=[],
    )
    assert _authority_from_materials([material]).effect_kinds == ("damage",)
    assert context.to_dict()["authority"]["effect_kinds"] == ["damage"]
    assert context.to_dict()["authority"]["budget_points"] == 2.0
    document = _document(effects=[{
        "id": "forged",
        "kind": "shield",
        "target": {"kind": "target_actor"},
        "commitment": "required",
        "amount": 4,
    }])
    result, _, _ = _run(
        [_snapshot(document)], material=material, context=context
    )
    payload = _assert_rejected(result, "parse")
    assert "material" in payload["attempts"][0]["reason"]

    budget_result, _, _ = _run(
        [_snapshot(_document(budget=999.0))],
        material=material,
        context=context,
    )
    budget_payload = _assert_rejected(budget_result, "parse")
    assert "budget" in budget_payload["attempts"][0]["reason"]


@pytest.mark.parametrize(
    "altered",
    (
        MaterialAuthority(
            ("p3_offline_material",), ("damage", "shield"),
            ("target_actor",), 20.0,
        ),
        MaterialAuthority(
            ("p3_offline_material",), ("damage",),
            ("self", "target_actor"), 20.0,
        ),
        MaterialAuthority(
            ("p3_offline_material",), ("damage",),
            ("target_actor",), 21.0,
        ),
    ),
)
def test_context_authority_mismatch_rejects_before_replay(monkeypatch, altered):
    import experiments.generative_mechanics.next_tracks_v06.gameplay_v04.skill_designer.pipeline as module

    material = _material(
        kinds=("damage",), selectors=("target_actor",), budget=20.0
    )
    context = build_generation_context(
        profile="combat",
        materials=[material],
        complexity=1,
        public_known_rules=[],
        acquired_capabilities=[],
    )

    class ObservingProvider(ReplayProvider):
        def reply(self, request):
            raise AssertionError("replay must not be called")

    provider = ObservingProvider(())
    monkeypatch.setattr(module, "build_generation_context", lambda **kwargs: context)
    monkeypatch.setattr(module, "_authority_from_context", lambda value: altered)
    with pytest.raises(GameplayContractError, match="does not match rederived"):
        run_offline_pipeline(
            materials=[material],
            statuses=PROFILE_MATERIALS["combat"].statuses,
            profile="combat",
            complexity=1,
            public_known_rules=[],
            acquired_capabilities=[],
            existing_skills=[],
            candidate_id="server_candidate",
            replay=provider,
        )
    assert provider.calls == ()


@pytest.mark.parametrize(
    "mutation",
    (
        lambda d: d["targeting"].update(selectors=["current_area"]),
        lambda d: d["entries"][0]["effects"][0].update(kind="unknown_effect"),
        lambda d: d["limits"].update(budget=9999),
        lambda d: d["entries"][0]["effects"][0].update(
            target={"kind": "unknown_scope"}
        ),
    ),
)
def test_illegal_scopes_kinds_and_budget_reject_through_ir_parser(mutation):
    document = _document()
    mutation(document)
    result, _, _ = _run([_snapshot(document)])
    payload = _assert_rejected(result, "parse")
    assert payload["attempts"][0]["stage"] == "parse"


def test_unsupported_trigger_is_a_typed_rejection():
    document = _document()
    document["entries"][0]["trigger"] = {"kind": "on_tick"}
    result, _, _ = _run([_snapshot(document)])
    payload = _assert_rejected(result, "parse")
    assert "language_gap" in payload["attempts"][0]["reason"]


def test_replay_exhaustion_and_provider_contract_failure_end_immediately():
    result, provider, _ = _run([], max_repairs=2)
    payload = _assert_rejected(result, "provider_exhausted")
    assert payload["attempts"] == []
    assert len(payload["calls"]) == 1
    assert provider.calls[-1].reply_text is None

    class ContractBrokenProvider(ReplayProvider):
        def reply(self, request):
            return "not-a-replay-reply"

    provider = ContractBrokenProvider(())
    result, _, _ = _run([], max_repairs=2, replay=provider)
    payload = _assert_rejected(result, "provider_contract")
    assert payload["attempts"] == []
    assert payload["calls"] == []
    assert provider.remaining == 0


def test_failure_preserves_causes_and_never_exposes_compiled_result():
    result, _, _ = _run([_snapshot(_document(material_id="forged"))])
    payload = _assert_rejected(result, "validate")
    assert payload["failure"]["stage"] == "repairs_exhausted"
    assert payload["attempts"][0]["reason"].startswith(
        "$.origin.material_ids must exactly match"
    )
    assert payload["calls"][0]["reply_text"] == _snapshot(
        _document(material_id="forged")
    )
    assert payload["calls"][0]["reply_hash"] == hashlib.sha256(
        payload["calls"][0]["reply_text"].encode("utf-8")
    ).hexdigest()


def test_result_and_readback_are_defensive_and_deterministic():
    material = _material()
    text = _snapshot(_document())
    first, _, _ = _run([text], material=material)
    second, _, _ = _run([text], material=material)
    assert first.canonical_json == second.canonical_json
    assert first.hash == second.hash
    assert first.to_dict()["result_hash"] == _readback_hash(first.to_dict())
    assert first.parsed.canonical_hash == second.parsed.canonical_hash
    assert first.compiled.canonical_hash == second.compiled.canonical_hash
    assert first.to_dict()["blueprint_hash"] == second.to_dict()["blueprint_hash"]
    assert first.to_dict()["calls"] == second.to_dict()["calls"]
    readback = first.to_dict()
    readback["status"] = "accepted"
    readback["gate_state"]["accepted"] = True
    assert first.to_dict()["status"] == "compiled_unregistered"
    assert first.to_dict()["gate_state"]["accepted"] is False
    with pytest.raises(Exception):
        PipelineResult(
            json.dumps({
                "status": "compiled_unregistered",
                "ir_hash": first.compiled.canonical_hash,
                "result_hash": "0" * 64,
            }),
            first.parsed,
            first.compiled,
        )


def test_pipeline_has_no_registration_world_or_transport_surface(monkeypatch):
    import experiments.generative_mechanics.next_tracks_v06.gameplay_v04.skill_designer.pipeline as module

    assert not any(
        name in module.__dict__
        for name in ("register_skill", "publish_skill", "WorldState")
    )
    result, _, _ = _run([_snapshot(_document())])
    assert result.status == "compiled_unregistered"


def test_replay_provider_override_cannot_escape_offline_boundary(monkeypatch):
    class ObservingProvider(ReplayProvider):
        def __init__(self):
            super().__init__((ReplayReply(_snapshot(_document())),))
            self.requests = []

        def reply(self, request):
            self.requests.append(request)
            return super().reply(request)

    provider = ObservingProvider()
    result, _, _ = _run([], replay=provider)
    assert result.status == "compiled_unregistered"
    assert provider.requests[0].attempt == 1
    assert provider.requests[0].feedback == ""
    assert len(provider.requests[0].context_hash) == 64
    assert not any(
        name in result.to_dict()
        for name in ("world_state", "registry", "registration")
    )


def _snapshot(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
