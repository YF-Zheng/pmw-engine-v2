"""Loopback-only HTTP adapter for the Storm Relay browser demo."""

from __future__ import annotations

import argparse
import json
import re
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Protocol, runtime_checkable
from urllib.parse import unquote, urlparse

from .observations import session_view


@runtime_checkable
class StormRelaySession(Protocol):
    """Stable backend contract consumed by the browser adapter."""

    @classmethod
    def new_game(cls) -> "StormRelaySession": ...

    def public_state(self) -> dict[str, Any]: ...

    def legal_actions(self) -> list[dict[str, Any]]: ...

    def perform(
        self, action: str, target: str | None = None, slot: int | None = None
    ) -> dict[str, Any]: ...

    def restart(self) -> Any: ...


_ACTION_RE = re.compile(r"^[a-z][a-z0-9_:-]{0,63}$")
_MAX_BODY_BYTES = 64 * 1024
_STATIC_ROOT = Path(__file__).with_name("static").resolve()
_CONTENT_TYPES = {
    ".css": "text/css; charset=utf-8",
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".webp": "image/webp",
}


class StormRelayApplication:
    """Small synchronized holder around the single authoritative session."""

    def __init__(self, session: StormRelaySession) -> None:
        if not isinstance(session, StormRelaySession):
            raise TypeError("session does not satisfy the StormRelaySession protocol")
        self.session = session
        self.lock = threading.RLock()

    def state(self) -> dict[str, Any]:
        with self.lock:
            return session_view(self.session)

    def action(self, *, action: str, target: str | None, slot: int | None) -> dict[str, Any]:
        with self.lock:
            self.session.perform(action, target=target, slot=slot)
            return session_view(self.session)

    def new_game(self) -> dict[str, Any]:
        with self.lock:
            self.session.restart()
            return session_view(self.session)


def _state_response(state: dict[str, Any]) -> dict[str, Any]:
    """Keep the canonical state nested while supporting the UI feed fields."""

    return {
        "state": state,
        "legal_actions": state["legal_actions"],
        "events": state["recent_events"],
    }


def _parse_action_payload(payload: Any) -> tuple[str, str | None, int | None]:
    if not isinstance(payload, dict):
        raise ValueError("JSON body must be an object")
    if set(payload) - {"action", "target", "slot"}:
        raise ValueError("unknown action argument")
    action = payload.get("action")
    if not isinstance(action, str) or not _ACTION_RE.fullmatch(action):
        raise ValueError("action must be a lowercase command identifier")
    target = payload.get("target")
    if target is not None and (not isinstance(target, str) or not target.strip() or len(target) > 128):
        raise ValueError("target must be a non-empty string or null")
    slot = payload.get("slot")
    if slot is not None and (isinstance(slot, bool) or not isinstance(slot, int) or not 0 <= slot <= 11):
        raise ValueError("slot must be an integer from 0 to 11 or null")
    return action, target, slot


def _load_session() -> StormRelaySession:
    try:
        from .session import StormRelaySession as ConcreteSession
    except ImportError as error:  # clear launch error while parallel implementation lands
        raise RuntimeError("Storm Relay session is not implemented yet") from error
    return ConcreteSession.new_game()


def make_handler(application: StormRelayApplication) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "StormRelay/0.1"

        def log_message(self, format: str, *args: object) -> None:
            # Keep demo terminal output focused on launch URL and explicit errors.
            return

        def _json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _error(self, status: HTTPStatus, message: str) -> None:
            self._json(status, {"error": {"message": message}})

        def _body(self, *, allow_empty: bool = False) -> Any:
            raw_length = self.headers.get("Content-Length")
            if raw_length is None:
                if allow_empty:
                    return None
                raise ValueError("Content-Length is required")
            try:
                length = int(raw_length)
            except ValueError as error:
                raise ValueError("invalid Content-Length") from error
            if length < 0 or length > _MAX_BODY_BYTES:
                raise ValueError("request body is too large")
            if length == 0 and allow_empty:
                return None
            try:
                return json.loads(self.rfile.read(length).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise ValueError("malformed JSON body") from error

        def _serve_static(self, route: str) -> None:
            relative = "index.html" if route == "/" else unquote(route.lstrip("/"))
            # HTML refers to assets as /static/app.js, while _STATIC_ROOT is
            # already the static directory itself.
            if relative.startswith("static/"):
                relative = relative.removeprefix("static/")
            candidate = (_STATIC_ROOT / relative).resolve()
            if _STATIC_ROOT not in candidate.parents and candidate != _STATIC_ROOT:
                self._error(HTTPStatus.NOT_FOUND, "not found")
                return
            if not candidate.is_file():
                self._error(HTTPStatus.NOT_FOUND, "not found")
                return
            data = candidate.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", _CONTENT_TYPES.get(candidate.suffix, "application/octet-stream"))
            self.send_header("Content-Length", str(len(data)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path == "/api/state":
                try:
                    self._json(HTTPStatus.OK, _state_response(application.state()))
                except Exception:
                    self._error(HTTPStatus.INTERNAL_SERVER_ERROR, "unable to read game state")
                return
            if path.startswith("/api/"):
                self._error(HTTPStatus.NOT_FOUND, "unknown API endpoint")
                return
            self._serve_static(path)

        def do_POST(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path not in {"/api/action", "/api/new-game"}:
                self._error(HTTPStatus.NOT_FOUND, "unknown API endpoint")
                return
            try:
                payload = self._body(allow_empty=path == "/api/new-game")
                if path == "/api/action":
                    action, target, slot = _parse_action_payload(payload)
                    state = application.action(action=action, target=target, slot=slot)
                else:
                    if payload not in ({}, None):
                        raise ValueError("new-game does not accept arguments")
                    state = application.new_game()
            except ValueError as error:
                self._error(HTTPStatus.BAD_REQUEST, str(error))
                return
            except Exception:
                self._error(HTTPStatus.INTERNAL_SERVER_ERROR, "game action failed")
                return
            self._json(HTTPStatus.OK, _state_response(state))

    return Handler


def create_server(
    session: StormRelaySession | None = None, *, host: str = "127.0.0.1", port: int = 8000
) -> ThreadingHTTPServer:
    """Create, but do not start, a loopback server (convenient for tests)."""

    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("Storm Relay server must bind to loopback only")
    application = StormRelayApplication(session or _load_session())
    return ThreadingHTTPServer((host, port), make_handler(application))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Storm Relay local demo")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    httpd = create_server(port=args.port)
    address, actual_port = httpd.server_address[:2]
    print(f"Storm Relay running at http://{address}:{actual_port}/")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
