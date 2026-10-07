"""Explicit, resumable Codex CLI collector for the v0.5 DEV pilot.

Importing this module never contacts a provider. Only the ``collect`` CLI
subcommand invokes ``codex exec``.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Any, Callable, Iterable, Mapping, Sequence

from ...compiler import canonical_json
from .pilot import (
    DATASET_KIND,
    DATASET_NAMESPACE,
    MODELS,
    PROVIDER,
    PROVIDER_SEED_UNAVAILABLE_REASON,
    ROOT,
    PilotContractError,
    build_manual_audit_scaffold,
    finalize_pilot_artifacts,
    ingest_raw_records,
    read_jsonl,
    run_frozen_profiles,
    summarize,
    write_jsonl,
)


ALLOWED_MODELS = tuple(row["exact_model_identifier"] for row in MODELS)
REQUESTS_PATH = ROOT / "requests" / "canonical_requests.jsonl"
RAW_ROOT = ROOT / "raw_provider_responses"
Runner = Callable[..., subprocess.CompletedProcess[str]]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _slug(model: str) -> str:
    if model not in ALLOWED_MODELS:
        raise PilotContractError(f"model must be one of {ALLOWED_MODELS}")
    return model.removeprefix("gpt-5.6-")


def _atomic_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    _atomic_text(path, json.dumps(value, sort_keys=True, indent=2) + "\n")


def _atomic_rows(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    _atomic_text(path, "".join(canonical_json(dict(row)) + "\n" for row in rows))


def _claim(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise PilotContractError(
            f"request has an unresolved started marker; refusing a possible second call: {path.name}"
        ) from exc
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(json.dumps(value, sort_keys=True, indent=2) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def _events(stdout: str) -> list[Any]:
    parsed = []
    for line in stdout.splitlines():
        if not line.strip():
            continue
        try:
            parsed.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return parsed


def _walk(value: Any) -> Iterable[tuple[str, Any]]:
    if isinstance(value, dict):
        for key, child in value.items():
            yield key, child
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _extract(events: Sequence[Any], keys: set[str]) -> str | None:
    values = [
        value for event in events for key, value in _walk(event)
        if key in keys and isinstance(value, str) and value.strip()
    ]
    return values[-1] if values else None


def extract_provider_metadata(stdout: str) -> dict[str, str | None]:
    events = _events(stdout)
    return {
        "provider_thread_id": _extract(events, {"thread_id", "threadId"}),
        "provider_session_id": _extract(events, {"session_id", "sessionId"}),
        "provider_request_id": _extract(
            events, {"response_id", "responseId", "provider_request_id", "requestId"},
        ),
        "returned_model_identifier": _extract(
            events, {"model", "model_id", "modelId", "model_name"},
        ),
    }


def _unavailable(label: str) -> str:
    return f"Codex CLI JSONL events did not expose {label}"


def _command(model: str, output: Path) -> list[str]:
    return [
        "codex", "exec", "--ephemeral", "--ignore-rules", "--sandbox", "read-only",
        "--model", model, "--config", 'model_reasoning_effort="high"',
        "--json", "--output-last-message", str(output), "-",
    ]


def _run_once(
    request: Mapping[str, Any], last_message: Path, runner: Runner,
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    command = _command(request["exact_model_identifier"], last_message)
    return runner(
        command,
        input=request["prompt"], text=True, capture_output=True, check=False,
    ), command


def _rebuild_model_jsonl(model_root: Path) -> Path:
    records = []
    for path in sorted((model_root / "records").glob("*.json")):
        records.append(json.loads(path.read_text(encoding="utf-8")))
    output = model_root / "first_attempts.jsonl"
    _atomic_text(output, "".join(canonical_json(row) + "\n" for row in records))
    return output


def collect_model(
    model: str, *, root: Path = ROOT, runner: Runner = subprocess.run,
    transport_retries: int = 0,
) -> dict[str, Any]:
    """Collect all not-yet-completed requests for one model exactly once.

    A retry is permitted only after a nonzero exit with no last message. The
    default is zero. An unresolved started marker blocks automatic recovery.
    """
    if isinstance(transport_retries, bool) or transport_retries < 0:
        raise PilotContractError("transport_retries must be a non-negative integer")
    requests = [
        row for row in read_jsonl(root / "requests" / "canonical_requests.jsonl")
        if row["exact_model_identifier"] == model
    ]
    if len(requests) != 15:
        raise PilotContractError(f"expected 15 frozen requests for {model}")
    model_root = root / "raw_provider_responses" / _slug(model)
    completed, skipped = 0, 0
    for request in requests:
        request_id = request["request_id"]
        record_path = model_root / "records" / f"{request_id}.json"
        started_path = model_root / "started" / f"{request_id}.json"
        if record_path.exists():
            skipped += 1
            continue
        _claim(started_path, {
            "dataset_kind": DATASET_KIND, "dataset_namespace": DATASET_NAMESPACE,
            "request_id": request_id, "started_at_utc": _utc_now(),
            "policy": "fail_closed_no_automatic_content_retry",
        })
        event_path = model_root / "events" / f"{request_id}.stdout.jsonl"
        stderr_path = model_root / "events" / f"{request_id}.stderr.txt"
        last_path = model_root / "last_messages" / f"{request_id}.txt"
        last_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_last = last_path.with_name(f".{last_path.name}.in_progress")
        results = []
        for transport_index in range(transport_retries + 1):
            temporary_last.unlink(missing_ok=True)
            result, command = _run_once(request, temporary_last, runner)
            last = temporary_last.read_text(encoding="utf-8") if temporary_last.exists() else ""
            results.append((result, last, command))
            if result.returncode == 0 or last:
                break
        result, last, executed_command = results[-1]
        attempt_log_paths = []
        if len(results) == 1:
            attempt_log_paths.append({
                "stdout": str(event_path.relative_to(root)),
                "stderr": str(stderr_path.relative_to(root)),
            })
        else:
            for index, (attempt, _, _) in enumerate(results, 1):
                attempt_event = model_root / "events" / f"{request_id}.transport-{index}.stdout.jsonl"
                attempt_stderr = model_root / "events" / f"{request_id}.transport-{index}.stderr.txt"
                _atomic_text(attempt_event, attempt.stdout)
                _atomic_text(attempt_stderr, attempt.stderr)
                attempt_log_paths.append({
                    "stdout": str(attempt_event.relative_to(root)),
                    "stderr": str(attempt_stderr.relative_to(root)),
                })
        _atomic_text(event_path, result.stdout)
        _atomic_text(stderr_path, result.stderr)
        _atomic_text(last_path, last)
        temporary_last.unlink(missing_ok=True)
        metadata = extract_provider_metadata(result.stdout)
        provider_success = result.returncode == 0 and bool(last)
        raw = {
            "dataset_kind": DATASET_KIND,
            "dataset_namespace": DATASET_NAMESPACE,
            "request_batch_id": request["request_batch_id"],
            "request_id": request_id,
            "sample_id": request["sample_id"],
            "attempt": 1,
            "repair": False,
            "provider": PROVIDER,
            "requested_model_identifier": model,
            "requested_reasoning_effort": "high",
            "returned_model_identifier": metadata["returned_model_identifier"],
            "returned_model_identifier_unavailable_reason": (
                None if metadata["returned_model_identifier"] else _unavailable("returned model identifier")
            ),
            "provider_seed_enforced": False,
            "provider_seed_unavailable_reason": PROVIDER_SEED_UNAVAILABLE_REASON,
            "provider_request_id": metadata["provider_request_id"],
            "provider_request_id_unavailable_reason": (
                None if metadata["provider_request_id"] else _unavailable("provider request id")
            ),
            "provider_thread_id": metadata["provider_thread_id"],
            "provider_thread_id_unavailable_reason": (
                None if metadata["provider_thread_id"] else _unavailable("thread id")
            ),
            "provider_session_id": metadata["provider_session_id"],
            "provider_session_id_unavailable_reason": (
                None if metadata["provider_session_id"] else _unavailable("session id")
            ),
            "timestamp_utc": _utc_now(),
            "provider_success": provider_success,
            "transport_status": "success" if provider_success else "provider_process_failed",
            "transport_attempt_count": len(results),
            "transport_retry_limit": transport_retries,
            "response_text": last,
            "raw_provider_response": {
                "command": executed_command,
                "stdout_jsonl": result.stdout,
                "stderr": result.stderr,
                "exit_code": result.returncode,
                "transport_attempts": [
                    {
                        "transport_attempt": index + 1,
                        "command": attempt_command,
                        "stdout_jsonl": attempt.stdout,
                        "stderr": attempt.stderr,
                        "exit_code": attempt.returncode,
                        "last_message": attempt_last,
                        "event_log_paths": attempt_log_paths[index],
                    }
                    for index, (attempt, attempt_last, attempt_command) in enumerate(results)
                ],
                "event_log_path": str(event_path.relative_to(root)),
                "last_message_path": str(last_path.relative_to(root)),
            },
        }
        _atomic_json(record_path, raw)
        started_path.unlink()
        completed += 1
        _rebuild_model_jsonl(model_root)
    output = _rebuild_model_jsonl(model_root)
    return {
        "model": model, "completed_now": completed, "already_completed": skipped,
        "raw_jsonl": str(output), "provider_calls_made": sum(
            json.loads(path.read_text(encoding="utf-8"))["transport_attempt_count"]
            for path in (model_root / "records").glob("*.json")
        ),
    }


def _model_raw(root: Path, model: str) -> list[dict[str, Any]]:
    path = root / "raw_provider_responses" / _slug(model) / "first_attempts.jsonl"
    if not path.is_file():
        raise PilotContractError(f"raw collection does not exist: {path}")
    return read_jsonl(path)


def ingest_model(model: str, *, root: Path = ROOT) -> dict[str, Any]:
    rows = ingest_raw_records(_model_raw(root, model))
    output = root / "ingested" / f"{_slug(model)}.jsonl"
    _atomic_rows(output, rows)
    return {"model": model, "row_count": len(rows), "output": str(output)}


def evaluate_model(model: str, *, root: Path = ROOT) -> dict[str, Any]:
    input_path = root / "ingested" / f"{_slug(model)}.jsonl"
    updated, profiles = run_frozen_profiles(read_jsonl(input_path))
    _atomic_rows(input_path, updated)
    output = root / "profiles" / f"{_slug(model)}.jsonl"
    _atomic_rows(output, profiles)
    return {"model": model, "profile_count": len(profiles), "output": str(output)}


def _atomic_pretty_json(path: Path, value: Mapping[str, Any]) -> None:
    _atomic_text(path, json.dumps(value, sort_keys=True, indent=2) + "\n")


def analyze(*, root: Path = ROOT) -> dict[str, Any]:
    ingested, profiles = [], []
    for model in ALLOWED_MODELS:
        ingested.extend(read_jsonl(root / "ingested" / f"{_slug(model)}.jsonl"))
        profiles.extend(read_jsonl(root / "profiles" / f"{_slug(model)}.jsonl"))
    summary, distributions = summarize(ingested, profiles)
    _atomic_pretty_json(root / "analysis" / "summary.json", summary)
    _atomic_pretty_json(root / "analysis" / "metric_distributions.json", distributions)
    audit = build_manual_audit_scaffold(profiles)
    _atomic_rows(root / "manual_audit" / "manual_audit.jsonl", audit)
    return {"summary_models": len(summary["models"]), "manual_audit_rows": len(audit)}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    collect = sub.add_parser("collect")
    collect.add_argument("--model", choices=ALLOWED_MODELS, required=True)
    collect.add_argument("--transport-retries", type=int, default=0)
    for name in ("ingest", "evaluate"):
        command = sub.add_parser(name)
        command.add_argument("--model", choices=ALLOWED_MODELS, required=True)
    sub.add_parser("analyze")
    sub.add_parser("finalize")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "collect":
        result = collect_model(args.model, transport_retries=args.transport_retries)
    elif args.command == "ingest":
        result = ingest_model(args.model)
    elif args.command == "evaluate":
        result = evaluate_model(args.model)
    elif args.command == "analyze":
        result = analyze()
    else:
        manifest = finalize_pilot_artifacts()
        result = {
            "status": "COMPLETE",
            "pilot_artifact_digest": manifest["pilot_artifact_digest"],
            "artifact_count": len(manifest["artifacts"]),
        }
    print(canonical_json(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
