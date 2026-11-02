from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import unicodedata

import pytest

from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.contracts import (
    GameplayContractError,
)
from experiments.generative_mechanics.next_tracks_v06.gameplay_v04.materials import (
    MaterialAuthority,
    MaterialDefinition,
    MaterialTrait,
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
    ReplayExhaustedError,
    ReplayProvider,
    ReplayReply,
    ReplayRequest,
)


PROJECT_ROOT = Path(__file__).resolve().parents[5]
REVIEW_MODULE = (
    "experiments.generative_mechanics.next_tracks_v06."
    "gameplay_v04.skill_designer.pipeline"
)
REPLAY_MODULE = (
    "experiments.generative_mechanics.next_tracks_v06."
    "gameplay_v04.skill_designer.replay"
)
MATERIAL_ID = "p3_review_alloy"
MATERIAL_ID_2 = "p3_review_catalyst"
CANDIDATE_ID = "review_candidate"


def _material(
    material_id: str = MATERIAL_ID,
    *,
    kinds: tuple[str, ...] = ("damage",),
    selectors: tuple[str, ...] = ("target_actor",),
    budget: float = 12.0,
) -> MaterialDefinition:
    return parse_material({
        "id": material_id,
        "tier": "fine",
        "region_rarity": "uncommon",
        "traits": [{
            "id": f"{material_id}_trait",
            "effect_kinds": list(kinds),
            "selectors": list(selectors),
            "budget_points": budget,
        }],
    })


def _authority(material: MaterialDefinition) -> MaterialAuthority:
    return material_authority((material,))


def _damage_effect(
    *,
    effect_id: str = "review_pulse",
    kind: str = "damage",
    target: str = "target_actor",
    amount: float = 3,
) -> dict[str, object]:
    return {
        "id": effect_id,
        "kind": kind,
        "target": {"kind": target},
        "commitment": "required",
        "amount": amount,
    }


def _document(
    *,
    material_id: str = MATERIAL_ID,
    material_ids: list[str] | None = None,
    effects: list[dict[str, object]] | None = None,
    selector: str = "target_actor",
    selectors: list[str] | None = None,
    budget: float = 12.0,
    identity_id: str = "candidate_supplied",
    origin_source: str = "generated",
    origin_model: str | None = "candidate-model",
    context_hash: str | None = "a" * 64,
) -> dict[str, object]:
    claimed_ids = material_ids if material_ids is not None else [material_id]
    return {
        "protocol": "pmw-skill-ir-v1",
        "identity": {
            "id": identity_id,
            "version": 7,
            "name": "Review Candidate",
            "description": "Independent offline review fixture.",
        },
        "origin": {
            "source": origin_source,
            "model": origin_model,
            "context_hash": context_hash,
            "material_ids": claimed_ids,
        },
        "capability": {"traits": ["review_trait"]},
        "targeting": {
            "selectors": selectors if selectors is not None else [selector],
            "relation_types": [],
        },
        "costs": {"mana": 1, "duration": 1},
        "entries": [{
            "id": "active",
            "trigger": {"kind": "on_use"},
            "condition": None,
            "effects": effects if effects is not None else [_damage_effect()],
            "max_firings_per_root": 1,
        }],
        "lifecycle": {"status_duration": None},
        "limits": {"budget": budget},
        "display": {"summary": "Review fixture.", "tags": ["review"]},
    }


def _snapshot(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _fixture(profile: str = "combat"):
    return build_fixture(profile)


def _run(
    replies: list[str | ReplayReply] | tuple[str | ReplayReply, ...],
    *,
    material: MaterialDefinition | None = None,
    materials: list[MaterialDefinition] | None = None,
    statuses=None,
    profile: str = "combat",
    max_repairs: int = 0,
    replay: ReplayProvider | None = None,
) -> tuple[PipelineResult, ReplayProvider]:
    selected_materials = materials or [material or _material()]
    selected_statuses = statuses if statuses is not None else _fixture().statuses
    provider = replay or ReplayProvider(tuple(
        reply if isinstance(reply, ReplayReply) else ReplayReply(reply)
        for reply in replies
    ))
    result = run_offline_pipeline(
        materials=selected_materials,
        statuses=selected_statuses,
        profile=profile,
        complexity=1,
        public_known_rules=["public:review"],
        acquired_capabilities=["review.compile"],
        existing_skills=[],
        candidate_id=CANDIDATE_ID,
        replay=provider,
        max_repairs=max_repairs,
    )
    return result, provider


def _assert_gate_closed(payload: dict) -> None:
    assert payload["status"] == "compiled_unregistered"
    assert payload["gate_state"] == {
        "accepted": False,
        "sandbox": "not_run",
        "register": "not_available",
        "usable_pool": False,
    }
    assert payload["replay"] == {
        "provider": "offline_replay",
        "generated_skills": 0,
        "live_requests": 0,
        "actual_usage": None,
        "actual_cost": None,
        "model": None,
    }


def _assert_rejected(payload: dict, *, stage: str | None = None) -> None:
    assert payload["status"] == "rejected"
    assert payload["gate_state"] == {
        "accepted": False,
        "sandbox": "not_run",
        "register": "not_available",
        "usable_pool": False,
    }
    assert payload["ir"] is None
    assert payload["ir_hash"] is None
    assert payload["blueprint_hash"] is None
    assert payload["failure"] is not None
    if stage is not None:
        stages = {row["stage"] for row in payload["attempts"]}
        stages.add(payload["failure"]["stage"])
        assert stage in stages


def _closed_single_fence(document: object) -> str:
    return "```json\n" + _snapshot(document) + "\n```"


def test_minimal_independent_compile_is_unregistered_and_zero_accounting():
    material = _material()
    result, provider = _run([_snapshot(_document())], material=material)
    payload = result.to_dict()

    _assert_gate_closed(payload)
    assert payload["protocol"] == PIPELINE_PROTOCOL
    assert payload["candidate_id"] == CANDIDATE_ID
    assert payload["candidate_version"] == 1
    assert payload["failure"] is None
    assert payload["attempts"] == [{
        "attempt": 1,
        "stage": "compiled",
        "reason": "candidate compiled successfully",
        "context_hash": payload["context_hash"],
        "accepted": True,
        "reply_hash": payload["calls"][0]["reply_hash"],
    }]
    assert len(payload["calls"]) == 1
    assert provider.remaining == 0
    assert result.accepted is False
    assert result.parsed is not None
    assert result.compiled is not None
    assert result.parsed.id == CANDIDATE_ID
    assert result.parsed.version == 1
    assert result.parsed.origin_source == "authored"
    assert result.parsed.origin_model is None
    assert result.parsed.context_hash == payload["context_hash"]
    assert result.parsed.material_ids == (MATERIAL_ID,)
    assert result.compiled.canonical_hash == result.parsed.canonical_hash
    assert payload["ir_hash"] == result.compiled.canonical_hash

    forbidden_keys = {
        "world_state",
        "registration",
        "registry",
        "sandbox_result",
        "provider_response",
        "usage",
        "token_usage",
        "cost",
    }
    assert forbidden_keys.isdisjoint(payload)


def test_one_complete_json_fence_is_accepted_without_prose():
    result, _ = _run([_closed_single_fence(_document())])
    payload = result.to_dict()
    _assert_gate_closed(payload)
    assert payload["failure"] is None
    assert len(payload["calls"]) == 1


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ('{"protocol":1,"protocol":2}', "duplicate JSON key"),
        ('{"outer":{"x":1,"x":2}}', "duplicate JSON key"),
        ("[]", "root JSON value must be an object"),
        ('"not-an-object"', "root JSON value must be an object"),
        ("null", "root JSON value must be an object"),
        ('{"x":NaN}', "non-finite JSON number"),
        ('{"x":Infinity}', "non-finite JSON number"),
        ('{"x":-Infinity}', "non-finite JSON number"),
        ('{"x":1} trailing prose', "invalid JSON"),
        ('prose before {"x":1}', "invalid JSON"),
        (
            '```json\n{"x":1}\n```\n```json\n{"x":2}\n```',
            "only one JSON fence",
        ),
        ('```json\n{"x":1}', "fence is incomplete"),
        ('```json\n{"x":1}\n``` trailing', "fence is incomplete"),
        ('```\n{"x":1}\n```', "language must be json"),
        ('```json\n{"x":1\n```', "invalid JSON"),
    ],
)
def test_decode_rejects_strict_json_and_single_fence_violations(text, message):
    with pytest.raises(_CandidateRejection, match=re.escape(message)):
        decode_candidate(text)


@pytest.mark.parametrize(
    "text",
    [
        '{"x":"\\ud800"}',
        '{"x":"\\udfff"}',
        '{"x":"\\ud83d"}',
        '{"x":"\\ude00"}',
    ],
)
def test_decode_rejects_json_escaped_lone_surrogates(text):
    with pytest.raises(_CandidateRejection):
        decode_candidate(text)


def test_pipeline_rejects_escaped_lone_surrogate_before_compile():
    text = _snapshot(_document()).replace(
        '"summary":"Review fixture."',
        '"summary":"Review \\ud800 fixture."',
    )
    with pytest.raises(_CandidateRejection):
        decode_candidate(text)
    result, _ = _run([text])
    payload = result.to_dict()
    _assert_rejected(payload, stage="decode")
    assert result.compiled is None


def test_decode_bounds_utf8_depth_and_shape_with_typed_rejections():
    with pytest.raises(_CandidateRejection, match="65536 UTF-8 bytes"):
        decode_candidate(" " * (MAX_REPLY_BYTES + 1))
    with pytest.raises(_CandidateRejection, match="depth limit"):
        decode_candidate('{"x":' * 130 + "null" + "}" * 130)
    with pytest.raises(_CandidateRejection, match="string is too long"):
        decode_candidate('{"x":"' + "a" * 4097 + '"}')


def test_accepted_ir_shape_limit_remains_enforced_after_decode():
    project = pytest.importorskip(
        "experiments.generative_mechanics.next_tracks_v06."
        "gameplay_v04.skill_ir"
    )
    with pytest.raises(GameplayContractError, match="JSON value limit"):
        project._validate_json_shape(
            {"x": [None] * project.MAX_JSON_VALUES}
        )


def test_decode_accepts_maximum_utf8_boundary_and_one_non_ascii_character():
    multibyte = '{"x":"' + ("é" * 2048) + '"}'
    assert len(multibyte.encode("utf-8")) <= MAX_REPLY_BYTES
    decoded = decode_candidate(multibyte)
    assert unicodedata.is_normalized("NFC", decoded.document["x"])
    assert decoded.document["x"] == "é" * 2048

    prefix = '{"x":"'
    suffix = '"}'
    string_maximum = 4096
    exact = prefix + ("a" * string_maximum) + suffix
    assert len(exact.encode("utf-8")) < MAX_REPLY_BYTES
    assert decode_candidate(exact).document["x"] == "a" * string_maximum

    padded = (" " * (MAX_REPLY_BYTES - len(exact))) + exact
    assert len(padded.encode("utf-8")) == MAX_REPLY_BYTES
    assert decode_candidate(padded).document["x"] == "a" * string_maximum


def test_unknown_root_and_nested_effect_keys_are_not_dropped(monkeypatch):
    material = _material()
    context = build_generation_context(
        profile="combat",
        materials=[material],
        complexity=1,
        public_known_rules=[],
        acquired_capabilities=[],
    )
    unknown_root = _document()
    unknown_root["unknown_root"] = {"sentinel": 17}
    with pytest.raises(_CandidateRejection) as root_error:
        normalize_candidate(
            unknown_root,
            context=context,
            authority=_authority(material),
            candidate_id=CANDIDATE_ID,
        )
    assert "root object must contain exactly" in str(root_error.value)

    unknown_effect = _document(effects=[{
        **_damage_effect(),
        "unknown_effect_key": {"nested": ["kept"]},
    }])
    normalized = normalize_candidate(
        unknown_effect,
        context=context,
        authority=_authority(material),
        candidate_id=CANDIDATE_ID,
    )
    assert normalized["entries"][0]["effects"][0]["unknown_effect_key"] == {
        "nested": ["kept"],
    }

    calls = []

    class ObservingProvider(ReplayProvider):
        def reply(self, request):
            calls.append(request)
            return super().reply(request)

    result, _ = _run(
        [],
        material=material,
        replay=ObservingProvider((ReplayReply(_snapshot(unknown_effect)),)),
    )
    payload = result.to_dict()
    _assert_rejected(payload)
    assert payload["attempts"][0]["stage"] == "parse"
    assert "unknown" in payload["attempts"][0]["reason"]
    assert len(calls) == 1


def test_submitted_material_ids_must_match_the_exact_trusted_selection():
    first = _material(MATERIAL_ID)
    second = _material(
        MATERIAL_ID_2,
        kinds=("shield",),
        selectors=("self",),
        budget=7.0,
    )
    base = _document(
        material_ids=[MATERIAL_ID, MATERIAL_ID_2],
        effects=[
            _damage_effect(),
            {
                "id": "review_guard",
                "kind": "shield",
                "target": {"kind": "self"},
                "commitment": "required",
                "amount": 2,
            },
        ],
            selector="target_actor",
            selectors=["self", "target_actor"],
        budget=12.0,
    )
    result, _ = _run([_snapshot(base)], materials=[first, second])
    payload = result.to_dict()
    _assert_gate_closed(payload)
    assert result.parsed is not None
    assert result.parsed.material_ids == (MATERIAL_ID, MATERIAL_ID_2)
    assert result.compiled is not None

    rejected_claims = [
        [MATERIAL_ID],
        [MATERIAL_ID_2],
        [MATERIAL_ID, "forged_material"],
        [MATERIAL_ID, MATERIAL_ID, MATERIAL_ID_2],
    ]
    for claimed in rejected_claims:
        document = deepcopy(base)
        document["origin"]["material_ids"] = claimed
        result, _ = _run([_snapshot(document)], materials=[first, second])
        payload = result.to_dict()
        _assert_rejected(payload, stage="validate")
        assert "material IDs" in payload["attempts"][0]["reason"]


def test_context_authority_rederivation_is_full_and_replay_never_runs_on_mismatch(
    monkeypatch,
):
    material = _material(budget=12.0)
    context = build_generation_context(
        profile="combat",
        materials=[material],
        complexity=1,
        public_known_rules=[],
        acquired_capabilities=[],
    )
    rederived = _authority_from_materials([material])
    assert rederived == MaterialAuthority(
        (MATERIAL_ID,), ("damage",), ("target_actor",), 12.0
    )

    class ReplaySpy(ReplayProvider):
        def __init__(self):
            super().__init__((ReplayReply(_snapshot(_document())),))
            self.reply_count = 0

        def reply(self, request):
            self.reply_count += 1
            return super().reply(request)

    pipeline = pytest.importorskip(REVIEW_MODULE)
    mismatches = [
        MaterialAuthority(
            (MATERIAL_ID,), ("damage", "shield"), ("target_actor",), 12.0
        ),
        MaterialAuthority(
            (MATERIAL_ID,), ("damage",), ("self", "target_actor"), 12.0
        ),
        MaterialAuthority(
            (MATERIAL_ID,), ("damage",), ("target_actor",), 12.01
        ),
        MaterialAuthority(
            (MATERIAL_ID,), ("damage",), ("target_actor",), 11.99
        ),
        MaterialAuthority(
            ("other_material",), ("damage",), ("target_actor",), 12.0
        ),
    ]
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(pipeline, "build_generation_context", lambda **kwargs: context)
        for mismatch in mismatches:
            spy = ReplaySpy()
            patch.setattr(pipeline, "_authority_from_context", lambda _: mismatch)
            with pytest.raises(
                GameplayContractError,
                match="does not match rederived material authority",
            ):
                _run([], material=material, replay=spy)
            assert spy.reply_count == 0


def test_altered_material_kind_scope_or_budget_fails_before_replay(monkeypatch):
    base = _material(kinds=("damage",), selectors=("target_actor",), budget=12.0)

    def fake_context(**kwargs):
        context_hash = "c" * 64
        return GenerationContext(
            context_hash,
            _snapshot({
                "version": "pmw-generation-context-v1",
                "catalog": {"hash": _catalog_hash()},
                "authority": {},
            }),
            _catalog(),
        )

    pipeline = pytest.importorskip(REVIEW_MODULE)
    monkeypatch.setattr(pipeline, "build_generation_context", fake_context)

    altered = [
        MaterialDefinition(
            base.id,
            base.tier,
            base.region_rarity,
            (MaterialTrait("review_trait", ("damage", "shield"), ("target_actor",), 12.0),),
        ),
        MaterialDefinition(
            base.id,
            base.tier,
            base.region_rarity,
            (MaterialTrait("review_trait", ("damage",), ("target_actor", "self"), 12.0),),
        ),
        MaterialDefinition(
            base.id,
            base.tier,
            base.region_rarity,
            (MaterialTrait("review_trait", ("damage",), ("target_actor",), 12.5),),
        ),
    ]
    for selected in altered:
        class FailIfCalled(ReplayProvider):
            def reply(self, request):
                raise AssertionError("replay must not be called after authority mismatch")

        spy = FailIfCalled(())
        with pytest.raises(GameplayContractError):
            _run([], material=selected, replay=spy)
        assert spy.calls == ()


def _catalog():
    return build_generation_context(
        profile="combat",
        materials=[_material()],
        complexity=1,
        public_known_rules=[],
        acquired_capabilities=[],
    ).catalog


def _catalog_hash():
    return _catalog().catalog_hash


def test_forged_context_metadata_never_grants_effect_authority():
    material = _material(kinds=("damage",), selectors=("target_actor",), budget=12.0)
    context = build_generation_context(
        profile="combat",
        materials=[material],
        complexity=1,
        public_known_rules=[],
        acquired_capabilities=[],
    )
    displayed = context.to_dict()
    displayed["authority"] = {
        "material_ids": [MATERIAL_ID],
        "effect_kinds": ["damage", "shield"],
        "selectors": ["self", "target_actor"],
        "budget_points": 999.0,
        "derivation": "candidate_forged",
    }
    forged_json = _snapshot(displayed)
    forged_context = GenerationContext(
        hashlib.sha256(forged_json.encode("utf-8")).hexdigest(),
        forged_json,
        context.catalog,
    )
    assert forged_context.to_dict()["authority"]["effect_kinds"] == [
        "damage",
        "shield",
    ]

    pipeline = pytest.importorskip(REVIEW_MODULE)
    observed = {}

    def fake_context(**kwargs):
        observed["context"] = forged_context
        return forged_context

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(pipeline, "build_generation_context", fake_context)
        with pytest.raises(
            GameplayContractError,
            match="does not match rederived material authority",
        ):
            _run(
                [],
                material=material,
                replay=ReplayProvider((ReplayReply(_snapshot(_document())),)),
            )
    assert observed["context"] is forged_context


def test_material_validation_rejects_overflow_unknowns_and_duplicate_selection():
    overflow_materials = [
        _material("p3_review_overflow_a", budget=1e308),
        _material("p3_review_overflow_b", budget=1e308),
    ]
    with pytest.raises(
        GameplayContractError,
        match="aggregate material authority budget must be finite and positive",
    ):
        _run([], materials=overflow_materials)

    malformed = MaterialDefinition(
        "p3_review_malformed",
        "fine",
        "uncommon",
        (
            MaterialTrait(
                "review_trait",
                ("damage",),
                ("world_admin",),
                12.0,
            ),
        ),
    )
    with pytest.raises(GameplayContractError, match="unknown scope"):
        _run([], material=malformed)

    duplicate = _material()
    with pytest.raises(GameplayContractError, match="unique IDs"):
        _run([], materials=[duplicate, duplicate])


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d["entries"][0]["effects"][0].update(kind="unknown_effect"),
        lambda d: d["entries"][0]["effects"][0].update(kind="shield"),
        lambda d: d["entries"][0]["effects"][0]["target"].update(kind="self"),
        lambda d: d["targeting"].update(selectors=["current_area"]),
        lambda d: d["limits"].update(budget=13.0),
        lambda d: d["entries"][0].update(trigger={"kind": "on_tick"}),
        lambda d: d["entries"][0].update(trigger={"kind": "on_event", "event": "attack_applied"}),
        lambda d: d["entries"][0].update(max_firings_per_root=True),
        lambda d: d["costs"].update(duration=True),
    ],
)
def test_actual_ir_rejects_illegal_kinds_scopes_budgets_and_triggers(mutate):
    document = _document()
    mutate(document)
    result, _ = _run([_snapshot(document)])
    payload = result.to_dict()
    _assert_rejected(payload)
    assert payload["attempts"][0]["stage"] in {"parse", "validate"}
    assert result.parsed is None
    assert result.compiled is None


def test_only_permitted_identity_and_provenance_fields_are_normalized():
    material = _material()
    document = _document()
    document["identity"]["name"] = "Candidate supplied name"
    document["identity"]["description"] = "Candidate supplied description."
    document["display"]["summary"] = "Candidate supplied summary."
    document["display"]["tags"] = ["candidate_tag"]
    document["costs"]["mana"] = 2.5
    document["costs"]["duration"] = 3
    document["limits"]["budget"] = 11.75
    before = deepcopy(document)
    result, _ = _run([_snapshot(document)], material=material)
    payload = result.to_dict()
    _assert_gate_closed(payload)
    assert result.parsed is not None
    parsed = json.loads(result.parsed.canonical_json)

    assert parsed["identity"]["id"] == CANDIDATE_ID
    assert parsed["identity"]["version"] == 1
    assert parsed["origin"] == {
        "source": "authored",
        "model": None,
        "context_hash": payload["context_hash"],
        "material_ids": [MATERIAL_ID],
    }
    assert parsed["identity"]["name"] == before["identity"]["name"]
    assert parsed["identity"]["description"] == before["identity"]["description"]
    assert parsed["display"] == before["display"]
    assert parsed["costs"] == before["costs"]
    assert parsed["limits"] == before["limits"]
    assert parsed["entries"] == before["entries"]
    assert before == document


def test_replay_is_finite_immutable_and_preserves_calls():
    replies = (_default_reply("one"), _default_reply("two"))
    original = tuple(replies)
    provider = ReplayProvider(replies)
    assert original == replies
    assert provider.remaining == 2
    first = provider.reply(ReplayRequest(1, "", "1" * 64))
    second = provider.reply(ReplayRequest(2, "stage=parse", "2" * 64))
    assert first.text == _default_reply("one").text
    assert second.text == _default_reply("two").text
    assert provider.remaining == 0
    assert [call.attempt for call in provider.calls] == [1, 2]
    assert provider.calls[0].reply_hash == provider.calls[0].reply_hash
    assert provider.calls[0].reply_hash != provider.calls[1].reply_hash
    with pytest.raises(ReplayExhaustedError):
        provider.reply(ReplayRequest(3, "", "3" * 64))
    assert provider.calls[-1].reply_text is None
    assert provider.calls[-1].reply_hash is None

    with pytest.raises(GameplayContractError, match="finite sequence"):
        ReplayProvider("not-a-sequence")
    with pytest.raises(GameplayContractError, match="at most 3"):
        ReplayProvider((_default_reply("x"),) * 4)
    with pytest.raises(GameplayContractError, match="exceeds"):
        ReplayReply("x" * (MAX_REPLY_BYTES + 1))
    with pytest.raises(GameplayContractError, match="provenance"):
        ReplayReply("{}", "generated", "fake-model")


def _default_reply(text: str) -> ReplayReply:
    return ReplayReply(text, "authored", None)


@pytest.mark.parametrize("max_repairs", (True, False, -1, 3, 1.0, "1", None))
def test_max_repairs_is_strict_integer_in_range(max_repairs):
    with pytest.raises(GameplayContractError, match="max_repairs"):
        _run([_snapshot(_document())], max_repairs=max_repairs)


@pytest.mark.parametrize(
    ("repairs", "calls"),
    [(0, 1), (1, 2), (2, 3)],
)
def test_repairs_use_at_most_three_calls_and_keep_each_invalid_attempt(repairs, calls):
    invalid = _snapshot(_document(material_id="forged_material"))
    result, provider = _run([invalid] * calls, max_repairs=repairs)
    payload = result.to_dict()
    _assert_rejected(payload, stage="repairs_exhausted")
    assert len(payload["attempts"]) == calls
    assert len(payload["calls"]) == calls
    assert provider.remaining == 0
    assert [row["attempt"] for row in payload["attempts"]] == list(
        range(1, calls + 1)
    )
    assert all(row["accepted"] is False for row in payload["attempts"])
    assert all(row["stage"] == "validate" for row in payload["attempts"])
    assert all(
        row["reply_hash"] == payload["calls"][index]["reply_hash"]
        for index, row in enumerate(payload["attempts"])
    )
    assert payload["calls"][0]["feedback"] == ""
    assert all(
        call["feedback"].startswith("stage=validate;")
        for call in payload["calls"][1:]
    )


def test_repair_can_recover_and_retains_failed_attempt():
    bad = _snapshot(_document(material_id="forged_material"))
    good = _snapshot(_document())
    result, provider = _run([bad, good], max_repairs=1)
    payload = result.to_dict()
    _assert_gate_closed(payload)
    assert len(payload["attempts"]) == 2
    assert payload["attempts"][0]["accepted"] is False
    assert payload["attempts"][0]["stage"] == "validate"
    assert payload["attempts"][1]["accepted"] is True
    assert payload["attempts"][1]["stage"] == "compiled"
    assert provider.remaining == 0


def test_provider_exhaustion_and_contract_failure_stop_immediately():
    result, provider = _run([], max_repairs=2)
    payload = result.to_dict()
    _assert_rejected(payload, stage="provider_exhausted")
    assert payload["attempts"] == []
    assert len(payload["calls"]) == 1
    assert provider.calls[-1].reply_text is None

    class NonReplayReplyProvider(ReplayProvider):
        def __init__(self):
            super().__init__((ReplayReply('{"x":1}'),))

        def reply(self, request):
                self._cursor += 1
                return "not-a-replay-reply"

    broken = NonReplayReplyProvider()
    result, provider = _run([], max_repairs=2, replay=broken)
    payload = result.to_dict()
    _assert_rejected(payload, stage="provider_contract")
    assert payload["attempts"] == []
    assert payload["calls"] == []
    assert provider.remaining == 0


def test_result_readback_and_compiler_artifacts_are_deterministic_and_copied():
    material = _material()
    text = _snapshot(_document())
    first, _ = _run([text], material=material)
    second, _ = _run([text], material=material)
    first_document = first.to_dict()
    second_document = second.to_dict()

    assert first.canonical_json == second.canonical_json
    assert first.hash == second.hash
    assert first.compiled is not None and second.compiled is not None
    assert first.parsed is not None and second.parsed is not None
    assert first.parsed.canonical_hash == second.parsed.canonical_hash
    assert first.compiled.canonical_hash == second.compiled.canonical_hash
    assert first_document["blueprint_hash"] == second_document["blueprint_hash"]
    assert first_document["result_hash"] == _readback_hash(first_document)

    first_document["status"] = "accepted"
    first_document["gate_state"]["accepted"] = True
    first_document["ir"]["identity"]["id"] = "mutated"
    first_document["calls"][0]["reply_text"] = "mutated"
    assert first.to_dict()["status"] == "compiled_unregistered"
    assert first.to_dict()["gate_state"]["accepted"] is False
    assert first.to_dict()["ir"]["identity"]["id"] == CANDIDATE_ID
    assert first.to_dict()["calls"][0]["reply_text"] == text
    assert first.parsed.canonical_json == text_ir(first)


def text_ir(result: PipelineResult) -> str:
    assert result.parsed is not None
    return result.parsed.canonical_json


def test_public_pipeline_has_no_live_world_registration_or_transport_imports():
    pipeline = pytest.importorskip(REVIEW_MODULE)
    replay = pytest.importorskip(REPLAY_MODULE)
    forbidden_names = {
        "register_skill",
        "publish_skill",
        "WorldState",
        "requests",
        "httpx",
        "urllib",
        "socket",
        "subprocess",
        "run_batch",
    }
    assert forbidden_names.isdisjoint(pipeline.__dict__)
    assert forbidden_names.isdisjoint(replay.__dict__)

    source_root = PROJECT_ROOT / "experiments" / "generative_mechanics" / "next_tracks_v06" / "gameplay_v04"
    for name in ("replay.py", "pipeline.py"):
        tree = __import__("ast").parse(
            (source_root / "skill_designer" / name).read_text(encoding="utf-8")
        )
        imported = {
            alias.name
            for node in __import__("ast").walk(tree)
            if isinstance(node, __import__("ast").Import)
            for alias in node.names
        }
        imported.update(
            node.module or ""
            for node in __import__("ast").walk(tree)
            if isinstance(node, __import__("ast").ImportFrom)
        )
        assert not any(
            blocked in item
            for item in imported
            for blocked in ("requests", "httpx", "urllib", "socket", "subprocess")
        )


def test_candidate_id_and_identity_special_cases_do_not_alter_validation():
    material = _material()
    for candidate_id in ("first_candidate", "second_candidate", "review_candidate"):
        result = run_offline_pipeline(
            materials=[material],
            statuses=_fixture().statuses,
            profile="combat",
            complexity=1,
            public_known_rules=[],
            acquired_capabilities=[],
            existing_skills=[],
            candidate_id=candidate_id,
            replay=ReplayProvider((ReplayReply(_snapshot(_document())),)),
            max_repairs=0,
        )
        payload = result.to_dict()
        _assert_gate_closed(payload)
        assert result.parsed is not None
        assert result.parsed.id == candidate_id
        assert payload["attempts"][0]["reason"] == "candidate compiled successfully"

    with pytest.raises(GameplayContractError, match="candidate_id"):
        run_offline_pipeline(
            materials=[material],
            statuses=_fixture().statuses,
            profile="combat",
            complexity=1,
            public_known_rules=[],
            acquired_capabilities=[],
            existing_skills=[],
            candidate_id="BadCandidate",
            replay=ReplayProvider((ReplayReply(_snapshot(_document())),)),
        )


def test_library_catalog_documents_are_not_reimported_by_review():
    review_source = Path(__file__).read_text(encoding="utf-8")
    assert "library" + ".json" not in review_source
    assert "PROFILE_" + "MATERIALS" not in review_source
    assert "from " + ".test_" not in review_source
    assert "import " + "test_skill_designer_offline_pipeline" not in review_source


def test_exact_failure_taxonomy_has_no_success_or_world_side_effects():
    result, _ = _run([_snapshot(_document(material_id="forged_material"))])
    payload = result.to_dict()
    _assert_rejected(payload, stage="repairs_exhausted")
    assert set(payload["failure"]) == {"stage", "reason"}
    assert payload["failure"]["stage"] == "repairs_exhausted"
    assert payload["attempts"][0]["stage"] == "validate"
    assert payload["attempts"][0]["accepted"] is False
    assert payload["calls"][0]["reply_text"] == _snapshot(
        _document(material_id="forged_material")
    )
    assert payload["calls"][0]["reply_hash"] is not None
    assert result.compiled is None
    assert result.parsed is None

