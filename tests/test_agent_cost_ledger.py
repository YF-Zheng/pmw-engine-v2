from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tools"))

import agent_cost_ledger as ledger  # noqa: E402


MAIN_ID = "11111111-1111-4111-8111-111111111111"
CHILD_ID = "22222222-2222-4222-8222-222222222222"
PROJECT_TURN = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
OTHER_TURN = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"


def context(model: str | None, *, ordinal: int | None = None) -> dict:
    payload = {"turn_id": PROJECT_TURN}
    if model is not None:
        payload["model"] = model
    event = {"type": "turn_context", "payload": payload}
    if ordinal is not None:
        event["ordinal"] = ordinal
    return event


def timestamped(event: dict, timestamp: str) -> dict:
    event["timestamp"] = timestamp
    return event


def usage(
    *,
    thread_id: str | None = MAIN_ID,
    response_id: str | None = "resp_1",
    turn_id: str = PROJECT_TURN,
    input_tokens: int = 100,
    cached_input_tokens: int = 80,
    cache_write_input_tokens: int = 5,
    output_tokens: int = 10,
    reasoning_output_tokens: int = 4,
    ordinal: int | None = None,
) -> dict:
    payload = {
        "type": "token_usage_record",
        "thread_id": thread_id,
        "turn_id": turn_id,
        "response_id": response_id,
        "usage": {
            "input_tokens": input_tokens,
            "cached_input_tokens": cached_input_tokens,
            "cache_write_input_tokens": cache_write_input_tokens,
            "output_tokens": output_tokens,
            "reasoning_output_tokens": reasoning_output_tokens,
            "total_tokens": input_tokens + output_tokens,
        },
        "turn_token_usage": {
            "input_tokens": 999_999,
            "output_tokens": 999_999,
        },
        "thread_token_usage": {
            "input_tokens": 888_888,
            "output_tokens": 888_888,
        },
    }
    event = {"type": "token_usage_record", "payload": payload}
    if ordinal is not None:
        event["ordinal"] = ordinal
    return event


def write_rollout(root: Path, session_id: str, events: list[dict]) -> Path:
    path = root / f"rollout-test-{session_id}.jsonl"
    path.write_text(
        "".join(json.dumps(event) + "\n" for event in events),
        encoding="utf-8",
    )
    return path


def family(report: dict, name: str) -> dict:
    return report["families"][name]


class AgentCostLedgerTest(unittest.TestCase):
    def test_mixed_model_attribution(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_rollout(
                root,
                MAIN_ID,
                [
                    context("tencent/gpt-6.1-sol"),
                    usage(response_id="resp_gpt"),
                    context("tencent/deepseek-v4-pro-ioa"),
                    usage(response_id="resp_deepseek"),
                ],
            )
            report = ledger.build_report(
                root,
                main_session=MAIN_ID,
                project_turn=PROJECT_TURN,
            )

        self.assertEqual(family(report, "GPT")["record_count"], 1)
        self.assertEqual(family(report, "DeepSeek")["record_count"], 1)
        self.assertEqual(family(report, "Unknown")["record_count"], 0)
        self.assertEqual(report["status"], "complete")
        self.assertEqual(
            family(report, "GPT")["responses"][0]["model"],
            "tencent/gpt-6.1-sol",
        )
        self.assertEqual(
            family(report, "DeepSeek")["responses"][0]["model"],
            "tencent/deepseek-v4-pro-ioa",
        )

    def test_missing_model_becomes_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_rollout(root, MAIN_ID, [usage(response_id="resp_no_model")])
            report = ledger.build_report(
                root,
                main_session=MAIN_ID,
                project_turn=PROJECT_TURN,
            )

        self.assertEqual(report["status"], "partial")
        self.assertEqual(family(report, "Unknown")["record_count"], 1)
        self.assertIsNone(family(report, "Unknown")["estimated_usd_json"])
        self.assertIsNone(report["totals"]["estimated_usd"])
        self.assertEqual(report["totals"]["known_estimated_usd"], 0.0)
        response = family(report, "Unknown")["responses"][0]
        self.assertEqual(response["model"], "unknown")
        self.assertFalse(response["pricing"]["priced"])
        self.assertIsNone(response["pricing"]["estimated_usd"])
        self.assertIsNone(response["pricing"]["estimated_cny_reference"])

    def test_cumulative_usage_ignored_and_records_deduplicated(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_rollout(
                root,
                MAIN_ID,
                [
                    context("tencent/gpt-6.1-sol"),
                    usage(response_id="resp_duplicate", input_tokens=120),
                    usage(response_id="resp_duplicate", input_tokens=120),
                    usage(thread_id=None, response_id=None, input_tokens=7),
                    usage(thread_id=None, response_id=None, input_tokens=9),
                    usage(thread_id=None, response_id=None, input_tokens=5, ordinal=99),
                    usage(thread_id=None, response_id=None, input_tokens=6, ordinal=99),
                ],
            )
            report = ledger.build_report(
                root,
                main_session=MAIN_ID,
                project_turn=PROJECT_TURN,
            )

        responses = family(report, "GPT")["responses"]
        self.assertEqual(report["totals"]["record_count"], 5)
        self.assertEqual(report["totals"]["actual_usage"]["input_tokens"], 147)
        duplicate = next(
            item for item in responses if item["response_id"] == "resp_duplicate"
        )
        self.assertEqual(duplicate["actual_usage"]["input_tokens"], 120)
        fallback_inputs = sorted(
            item["actual_usage"]["input_tokens"]
            for item in responses
            if item["response_id"] is None
        )
        self.assertEqual(fallback_inputs, [5, 6, 7, 9])

    def test_project_turn_filter_and_child_full_include(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_rollout(
                root,
                MAIN_ID,
                [
                    context("tencent/gpt-6.1-sol"),
                    usage(
                        response_id="resp_old",
                        turn_id=OTHER_TURN,
                        input_tokens=11,
                    ),
                    usage(
                        response_id="resp_project",
                        turn_id=PROJECT_TURN,
                        input_tokens=12,
                    ),
                ],
            )
            write_rollout(
                root,
                CHILD_ID,
                [
                    context("tencent/deepseek-v4.1-flash"),
                    usage(
                        thread_id=CHILD_ID,
                        response_id="resp_child_old",
                        turn_id=OTHER_TURN,
                        input_tokens=13,
                    ),
                    usage(
                        thread_id=CHILD_ID,
                        response_id="resp_child_project",
                        turn_id=PROJECT_TURN,
                        input_tokens=14,
                    ),
                ],
            )
            report = ledger.build_report(
                root,
                main_session=MAIN_ID,
                project_turn=PROJECT_TURN,
                agent_ids=[CHILD_ID],
            )

        responses = [
            response
            for bucket in report["families"].values()
            for response in bucket["responses"]
        ]
        response_ids = {response["response_id"] for response in responses}
        self.assertEqual(
            response_ids,
            {"resp_project", "resp_child_old", "resp_child_project"},
        )
        child_old = next(
            response
            for response in responses
            if response["response_id"] == "resp_child_old"
        )
        self.assertEqual(child_old["inclusion"], "agent_full")
        self.assertEqual(child_old["source_role"], "agent")

    def test_child_file_wins_duplicate_parent_attribution(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_rollout(
                root,
                MAIN_ID,
                [
                    context("tencent/gpt-6.1-sol"),
                    usage(
                        thread_id=CHILD_ID,
                        response_id="resp_shared",
                        turn_id=OTHER_TURN,
                    ),
                ],
            )
            write_rollout(
                root,
                CHILD_ID,
                [
                    context("tencent/deepseek-v4.1-flash"),
                    usage(
                        thread_id=CHILD_ID,
                        response_id="resp_shared",
                        turn_id=OTHER_TURN,
                    ),
                ],
            )
            report = ledger.build_report(
                root,
                main_session=MAIN_ID,
                project_turn=PROJECT_TURN,
                agent_ids=[CHILD_ID],
            )

        responses = [
            response
            for bucket in report["families"].values()
            for response in bucket["responses"]
        ]
        self.assertEqual(len(responses), 1)
        self.assertEqual(responses[0]["source_role"], "agent")
        self.assertEqual(responses[0]["model"], "tencent/deepseek-v4.1-flash")

    def test_97_percent_input_cache_math_preserves_recorded_cache(self) -> None:
        usage_values = {
            "input_tokens": 200_000,
            "cached_input_tokens": 160_000,
            "cache_write_input_tokens": 25_000,
            "output_tokens": 0,
            "reasoning_output_tokens": 0,
        }
        pricing = ledger.calculate_pricing(
            usage_values,
            "tencent/gpt-6.1-sol",
        )

        self.assertEqual(pricing["assumed_cached_input_tokens"], 194_000.0)
        self.assertEqual(pricing["assumed_uncached_input_tokens"], 6_000.0)
        self.assertAlmostEqual(pricing["estimated_usd"]["total"], 0.0314)
        self.assertEqual(usage_values["cached_input_tokens"], 160_000)
        self.assertEqual(usage_values["cache_write_input_tokens"], 25_000)

    def test_unknown_pricing_fails_closed_in_budget_check(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "evidence"
            write_rollout(root, MAIN_ID, [usage(response_id="resp_unknown")])
            exit_code = ledger.main(
                [
                    "--session-root",
                    str(root),
                    "--main-session",
                    MAIN_ID,
                    "--project-turn",
                    PROJECT_TURN,
                    "--output",
                    str(output),
                    "--check-budget",
                ]
            )
            report = json.loads((output / ledger.OUTPUT_FILENAME).read_text("utf-8"))

        self.assertEqual(exit_code, 2)
        self.assertEqual(report["status"], "partial")
        self.assertFalse(report["budget"]["within_budget"])
        self.assertEqual(
            report["budget"]["decision"],
            "fail_closed_incomplete_accounting",
        )

    def test_long_context_multipliers_and_reasoning_not_added(self) -> None:
        below = ledger.calculate_pricing(
            {
                "input_tokens": 272_000,
                "cached_input_tokens": 0,
                "cache_write_input_tokens": 0,
                "output_tokens": 1_000,
                "reasoning_output_tokens": 900,
            },
            "tencent/gpt-6.1-sol",
        )
        above = ledger.calculate_pricing(
            {
                "input_tokens": 272_001,
                "cached_input_tokens": 0,
                "cache_write_input_tokens": 0,
                "output_tokens": 1_000,
                "reasoning_output_tokens": 900,
            },
            "tencent/gpt-6.1-sol",
        )

        self.assertFalse(below["long_context"]["applied"])
        self.assertTrue(above["long_context"]["applied"])
        self.assertEqual(above["long_context"]["input_multiplier"], 2.0)
        self.assertEqual(above["long_context"]["output_multiplier"], 1.5)
        expected_output_cost = 1_000 * 10 * 1.5 / 1_000_000
        self.assertAlmostEqual(
            above["estimated_usd"]["output"],
            expected_output_cost,
        )

    def test_malformed_usage_is_null_and_fails_closed(self) -> None:
        malformed = usage(response_id="resp_bad")
        malformed["payload"]["usage"] = {
            "input_tokens": 100,
            "cached_input_tokens": -1,
            "cache_write_input_tokens": True,
            "output_tokens": 10,
            "reasoning_output_tokens": 20,
            "total_tokens": 999_999,
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "evidence"
            write_rollout(
                root,
                MAIN_ID,
                [
                    context("tencent/gpt-6.1-sol"),
                    malformed,
                    usage(response_id="resp_valid"),
                ],
            )
            exit_code = ledger.main(
                [
                    "--session-root",
                    str(root),
                    "--main-session",
                    MAIN_ID,
                    "--project-turn",
                    PROJECT_TURN,
                    "--output",
                    str(output),
                    "--check-budget",
                ]
            )
            report = json.loads((output / ledger.OUTPUT_FILENAME).read_text("utf-8"))

        responses = family(report, "GPT")["responses"]
        bad = next(item for item in responses if item["response_id"] == "resp_bad")
        self.assertIsNone(bad["actual_usage"]["cached_input_tokens"])
        self.assertIsNone(bad["actual_usage"]["cache_write_input_tokens"])
        self.assertFalse(bad["usage_complete"])
        self.assertIn(
            "usage_invalid:cached_input_tokens",
            bad["usage_issues"],
        )
        self.assertIn(
            "usage_invalid:cache_write_input_tokens",
            bad["usage_issues"],
        )
        self.assertIn(
            "usage_invalid:reasoning_output_tokens_gt_output_tokens",
            bad["usage_issues"],
        )
        self.assertIsNone(bad["pricing"]["estimated_usd"])
        self.assertEqual(report["status"], "partial")
        self.assertEqual(report["budget"]["incomplete_reasons"], ["malformed_usage"])
        self.assertFalse(report["budget"]["within_budget"])
        self.assertEqual(exit_code, 2)

    def test_cached_greater_than_input_marks_record_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            record = usage(response_id="resp_cache")
            record["payload"]["usage"]["cached_input_tokens"] = 101
            write_rollout(
                root,
                MAIN_ID,
                [context("tencent/gpt-6.1-sol"), record],
            )
            report = ledger.build_report(
                root,
                main_session=MAIN_ID,
                project_turn=PROJECT_TURN,
            )

        response = family(report, "GPT")["responses"][0]
        self.assertIn(
            "usage_invalid:cached_input_tokens_gt_input_tokens",
            response["usage_issues"],
        )
        self.assertIsNone(response["pricing"]["estimated_usd"])
        self.assertEqual(report["status"], "partial")

    def test_repeat_project_turns_aggregate_idempotently(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_rollout(
                root,
                MAIN_ID,
                [
                    context("tencent/gpt-6.1-sol"),
                    usage(response_id="resp_t1", turn_id=PROJECT_TURN),
                    usage(response_id="resp_t2", turn_id=OTHER_TURN),
                    usage(response_id="resp_t1", turn_id=PROJECT_TURN),
                ],
            )
            first = ledger.build_report(
                root,
                main_session=MAIN_ID,
                project_turn=PROJECT_TURN,
                project_turns=[OTHER_TURN],
            )
            second = ledger.build_report(
                root,
                main_session=MAIN_ID,
                project_turn=PROJECT_TURN,
                project_turns=[OTHER_TURN],
            )

        self.assertEqual(first, second)
        self.assertEqual(first["selection"]["project_turns"], sorted([PROJECT_TURN, OTHER_TURN]))
        self.assertEqual(first["totals"]["record_count"], 2)

    def test_phase_and_agent_stage_tag_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_rollout(
                root,
                MAIN_ID,
                [context("tencent/gpt-6.1-sol"), usage(response_id="resp_main")],
            )
            write_rollout(
                root,
                CHILD_ID,
                [
                    context("tencent/deepseek-v4.1-flash"),
                    usage(
                        thread_id=CHILD_ID,
                        response_id="resp_child",
                        turn_id=OTHER_TURN,
                    ),
                ],
            )
            report = ledger.build_report(
                root,
                main_session=MAIN_ID,
                project_turn=PROJECT_TURN,
                agent_ids=[CHILD_ID],
                phase="P1",
                agent_stages={CHILD_ID: "P2"},
            )

        responses = [
            response
            for bucket in report["families"].values()
            for response in bucket["responses"]
        ]
        by_id = {response["response_id"]: response for response in responses}
        self.assertEqual(by_id["resp_main"]["stage"], "P1")
        self.assertEqual(by_id["resp_child"]["stage"], "P2")
        self.assertEqual(report["stages"]["P1"]["record_count"], 1)
        self.assertEqual(report["stages"]["P2"]["record_count"], 1)
        self.assertEqual(report["budget"]["stage"], "P1")
        self.assertEqual(report["budget"]["tiers"]["P5"]["limit_cny"], 400.0)
        self.assertEqual(report["budget"]["tiers"]["Reserve"]["limit_cny"], 150.0)
        self.assertTrue(
            report["stage_attribution"]["reused_agents_may_span_stages"]
        )
        self.assertFalse(report["stage_attribution"]["exact_attribution_claimed"])

    def test_stage_quota_uses_stage_subtotal_not_total_reserve(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_rollout(
                root,
                MAIN_ID,
                [
                    context("tencent/gpt-6.1-sol"),
                    timestamped(
                        usage(
                            response_id="resp_p0",
                            turn_id=PROJECT_TURN,
                            input_tokens=50_000_000,
                            cached_input_tokens=0,
                            cache_write_input_tokens=0,
                            output_tokens=0,
                            reasoning_output_tokens=0,
                        ),
                        "2026-10-28T12:00:00Z",
                    ),
                    timestamped(
                        usage(
                            response_id="resp_p1",
                            turn_id=OTHER_TURN,
                            input_tokens=1_000,
                            cached_input_tokens=0,
                            cache_write_input_tokens=0,
                            output_tokens=0,
                            reasoning_output_tokens=0,
                        ),
                        "2026-10-28T13:00:00Z",
                    ),
                ],
            )
            report = ledger.build_report(
                root,
                main_session=MAIN_ID,
                project_turn=PROJECT_TURN,
                project_turns=[OTHER_TURN],
                phase="P1",
                turn_stages={PROJECT_TURN: "P0", OTHER_TURN: "P1"},
            )

        tiers = report["budget"]["tiers"]
        self.assertTrue(tiers["P1"]["within_limit"])
        self.assertFalse(tiers["P0"]["within_limit"])
        self.assertTrue(tiers["MAX"]["within_limit"])
        self.assertGreater(tiers["P0"]["reserved_cny"], tiers["P1"]["reserved_cny"])
        self.assertEqual(
            tiers["MAX"]["reserved_cny"],
            report["budget"]["reserved_cny"],
        )
        self.assertFalse(report["budget"]["within_budget"])
        self.assertEqual(report["budget"]["decision"], "over_budget")
        self.assertFalse(report["budget"]["all_stage_limits_within"])
        self.assertTrue(report["budget"]["max_limit_within"])
        self.assertTrue(report["budget"]["active_stage_within_limit"])

    def test_snapshot_timestamp_and_source_ordinals_are_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_rollout(
                root,
                MAIN_ID,
                [
                    context("tencent/gpt-6.1-sol"),
                    timestamped(
                        usage(response_id="resp_one", ordinal=10),
                        "2026-10-28T13:00:00Z",
                    ),
                    timestamped(
                        usage(response_id="resp_two", ordinal=20),
                        "2026-10-28T12:00:00Z",
                    ),
                ],
            )
            first = ledger.build_report(
                root,
                main_session=MAIN_ID,
                project_turn=PROJECT_TURN,
            )
            second = ledger.build_report(
                root,
                main_session=MAIN_ID,
                project_turn=PROJECT_TURN,
            )

        self.assertEqual(first, second)
        self.assertEqual(
            first["snapshot"]["max_observed_usage_timestamp"],
            "2026-10-28T13:00:00Z",
        )
        self.assertEqual(
            first["snapshot"]["source_max_ordinals"],
            {MAIN_ID: 20},
        )
        self.assertEqual(first["snapshot"]["usage_record_count"], 2)

    def test_turn_stage_override_splits_reused_child_history(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_rollout(
                root,
                MAIN_ID,
                [context("tencent/gpt-6.1-sol"), usage(response_id="resp_main")],
            )
            write_rollout(
                root,
                CHILD_ID,
                [
                    context("tencent/deepseek-v4.1-flash"),
                    usage(
                        thread_id=CHILD_ID,
                        response_id="resp_p0",
                        turn_id=PROJECT_TURN,
                    ),
                    usage(
                        thread_id=CHILD_ID,
                        response_id="resp_p1",
                        turn_id=OTHER_TURN,
                    ),
                ],
            )
            report = ledger.build_report(
                root,
                main_session=MAIN_ID,
                project_turn=PROJECT_TURN,
                project_turns=[OTHER_TURN],
                agent_ids=[CHILD_ID],
                phase="P0",
                agent_stages={CHILD_ID: "P1"},
                turn_stages={
                    PROJECT_TURN: "P0",
                    OTHER_TURN: "P1",
                },
            )

        responses = [
            response
            for bucket in report["families"].values()
            for response in bucket["responses"]
        ]
        by_id = {response["response_id"]: response for response in responses}
        self.assertEqual(by_id["resp_p0"]["stage"], "P0")
        self.assertEqual(by_id["resp_p1"]["stage"], "P1")
        self.assertEqual(
            report["selection"]["agent_stages"],
            {CHILD_ID: "P1"},
        )
        self.assertEqual(
            report["selection"]["turn_stages"],
            {
                PROJECT_TURN: "P0",
                OTHER_TURN: "P1",
            },
        )
        self.assertEqual(
            report["stage_attribution"]["precedence"],
            "turn_stage > agent_stage > phase",
        )
        self.assertTrue(report["stage_attribution"]["main_default_is_conservative"])

    def test_unavailable_requested_agent_fails_closed(self) -> None:
        missing_id = "33333333-3333-4333-8333-333333333333"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "evidence"
            write_rollout(
                root,
                MAIN_ID,
                [context("tencent/gpt-6.1-sol"), usage(response_id="resp_main")],
            )
            exit_code = ledger.main(
                [
                    "--session-root",
                    str(root),
                    "--main-session",
                    MAIN_ID,
                    "--project-turn",
                    PROJECT_TURN,
                    "--agent-id",
                    missing_id,
                    "--output",
                    str(output),
                    "--check-budget",
                ]
            )
            report = json.loads((output / ledger.OUTPUT_FILENAME).read_text("utf-8"))

        self.assertEqual(exit_code, 2)
        self.assertEqual(report["status"], "partial")
        self.assertFalse(report["budget"]["within_budget"])
        self.assertIn(
            f"requested_agent_unavailable:{missing_id}",
            report["budget"]["incomplete_reasons"],
        )

    def test_output_is_idempotent_and_exports_only_allowlisted_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "evidence"
            sentinel = "PROMPT_SECRET_SENTINEL"
            events = [
                context("tencent/gpt-6.1-sol"),
                {
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "content": sentinel,
                        "cwd": f"C:/private/{sentinel}",
                    },
                },
                usage(response_id="resp_safe"),
            ]
            write_rollout(root, MAIN_ID, events)
            first_exit = ledger.main(
                [
                    "--session-root",
                    str(root),
                    "--main-session",
                    MAIN_ID,
                    "--project-turn",
                    PROJECT_TURN,
                    "--output",
                    str(output),
                ]
            )
            destination = output / ledger.OUTPUT_FILENAME
            first = destination.read_bytes()
            second_exit = ledger.main(
                [
                    "--session-root",
                    str(root),
                    "--main-session",
                    MAIN_ID,
                    "--project-turn",
                    PROJECT_TURN,
                    "--output",
                    str(output),
                ]
            )
            second = destination.read_bytes()

        self.assertEqual(first_exit, 0)
        self.assertEqual(second_exit, 0)
        self.assertEqual(first, second)
        self.assertNotIn(sentinel.encode("utf-8"), first)
        decoded = first.decode("utf-8")
        self.assertNotIn('"cwd"', decoded)
        self.assertNotIn('"content"', decoded)


if __name__ == "__main__":
    unittest.main()
