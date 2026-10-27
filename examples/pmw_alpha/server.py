"""Loopback HTTP host for the PMW Alpha browser client."""

from __future__ import annotations

import argparse
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from .commands import AlphaCommand, AlphaCommandError
from .session import AlphaSession, AlphaSessionError


STATIC_ROOT = Path(__file__).with_name("static")
SAVE_ROOT = Path.home() / ".pmw-alpha"
MAX_BODY = 16_384
CONTENT_TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
                 ".css": "text/css; charset=utf-8", ".png": "image/png", ".svg": "image/svg+xml"}


class AlphaApplication:
    def __init__(self, session: AlphaSession | None = None, *, save_root: Path = SAVE_ROOT) -> None:
        self.session = session or AlphaSession.new_game()
        self.save_root = save_root

    def state(self) -> dict[str, Any]: return self.session.public_state()
    def action(self, raw: dict[str, Any]) -> dict[str, Any]:
        command = AlphaCommand.parse(raw)
        return self.session.perform(command.action, target=command.target, slot=command.slot)
    def new_game(self, raw: dict[str, Any] | None) -> dict[str, Any]:
        if raw not in (None, {}): raise AlphaCommandError("new-game does not accept arguments")
        self.session = AlphaSession.new_game()
        return self.state()
    def save(self) -> dict[str, Any]:
        self.session.save(self.save_root)
        return self.state()
    def load(self) -> dict[str, Any]:
        self.session = AlphaSession.load(self.save_root)
        return self.state()


def create_server(session: AlphaSession | None = None, *, host: str = "127.0.0.1", port: int = 8020) -> ThreadingHTTPServer:
    if host not in {"127.0.0.1", "localhost", "::1"}: raise ValueError("Alpha server must bind to loopback")
    app = AlphaApplication(session)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None: return
        def send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            self.send_response(status); self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body))); self.send_header("Cache-Control", "no-store"); self.end_headers(); self.wfile.write(body)
        def error_json(self, status: HTTPStatus, message: str) -> None: self.send_json(status, {"error": {"message": message}})
        def body(self, *, allow_empty: bool = False) -> dict[str, Any] | None:
            length = self.headers.get("Content-Length")
            if length is None:
                if allow_empty: return None
                raise AlphaCommandError("Content-Length is required")
            try: size = int(length)
            except ValueError as error: raise AlphaCommandError("invalid Content-Length") from error
            if size < 0 or size > MAX_BODY: raise AlphaCommandError("request body is too large")
            if size == 0 and allow_empty: return None
            try: data = json.loads(self.rfile.read(size).decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as error: raise AlphaCommandError("malformed JSON body") from error
            if not isinstance(data, dict): raise AlphaCommandError("request body must be an object")
            return data
        def static(self, route: str) -> None:
            relative = "index.html" if route == "/" else unquote(route.lstrip("/"))
            if relative.startswith("static/"): relative = relative.removeprefix("static/")
            candidate = (STATIC_ROOT / relative).resolve()
            if STATIC_ROOT not in candidate.parents or not candidate.is_file(): self.error_json(HTTPStatus.NOT_FOUND, "not found"); return
            data = candidate.read_bytes(); self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", CONTENT_TYPES.get(candidate.suffix, "application/octet-stream")); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)
        def do_GET(self) -> None:
            path = urlparse(self.path).path
            if path == "/api/state": self.send_json(HTTPStatus.OK, {"state": app.state()}); return
            if path.startswith("/api/"): self.error_json(HTTPStatus.NOT_FOUND, "unknown API endpoint"); return
            self.static(path)
        def do_POST(self) -> None:
            path = urlparse(self.path).path
            if path not in {"/api/action", "/api/new-game", "/api/save", "/api/load"}: self.error_json(HTTPStatus.NOT_FOUND, "unknown API endpoint"); return
            try:
                raw = self.body(allow_empty=path != "/api/action")
                if path == "/api/action": state = app.action(raw or {})
                elif path == "/api/new-game": state = app.new_game(raw)
                elif path == "/api/save":
                    if raw not in (None, {}): raise AlphaCommandError("save does not accept arguments")
                    state = app.save()
                else:
                    if raw not in (None, {}): raise AlphaCommandError("load does not accept arguments")
                    state = app.load()
            except (AlphaCommandError, AlphaSessionError, ValueError) as error: self.error_json(HTTPStatus.BAD_REQUEST, str(error)); return
            except Exception: self.error_json(HTTPStatus.INTERNAL_SERVER_ERROR, "game action failed"); return
            self.send_json(HTTPStatus.OK, {"state": state})
    return ThreadingHTTPServer((host, port), Handler)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run PMW Alpha: Before the Seventh Night")
    parser.add_argument("--port", type=int, default=8020); args = parser.parse_args()
    server = create_server(port=args.port); host, port = server.server_address[:2]
    print(f"PMW Alpha running at http://{host}:{port}/")
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()


if __name__ == "__main__": main()
