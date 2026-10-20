from __future__ import annotations

import http.client
import json
import threading
import unittest

from examples.storm_relay.observations import project_public_state
from examples.storm_relay.server import create_server


class FakeSession:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None, int | None]] = []
        self.restarts = 0

    @classmethod
    def new_game(cls):
        return cls()

    def public_state(self):
        return {
            "outcome": "playing",
            "time": {"remaining": 7},
            "current_area": "shallows",
            "player": {"hp": 10, "mana": 4},
            "areas": [{"id": "shallows", "weather": "storm"}],
            "inventory": [{"id": "moss", "count": 2}],
            "discoveries": ["tower"],
            "recipes": [{"id": "relay"}],
            "registered_skills": [{"id": "spark"}],
            "equipped_skills": [{"id": "spark", "slot": 0}],
            "combat": {"active": False},
            "recent_events": [{"type": "weather.changed", "source": "weather", "trace": {"private": True}}],
            "legal_actions": [{"action": "travel", "target": "tower"}],
            "world_state": {"entities": "must not escape"},
            "causal_trace": {"must": "not escape"},
            "registry": {"must": "not escape"},
        }

    def legal_actions(self):
        return self.public_state()["legal_actions"]

    def perform(self, action, target=None, slot=None):
        self.calls.append((action, target, slot))
        return self.public_state()

    def restart(self):
        self.restarts += 1


class HttpUiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.session = FakeSession()
        self.server = create_server(self.session, port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.thread.join(timeout=2)
        self.server.server_close()

    def request(self, method: str, path: str, body=None):
        host, port = self.server.server_address[:2]
        payload = None if body is None else json.dumps(body)
        conn = http.client.HTTPConnection(host, port, timeout=2)
        conn.request(method, path, body=payload, headers={"Content-Type": "application/json"})
        response = conn.getresponse()
        result = json.loads(response.read())
        conn.close()
        return response.status, result

    def test_state_is_allowlisted_projection(self) -> None:
        status, response = self.request("GET", "/api/state")
        self.assertEqual(status, 200)
        state = response["state"]
        self.assertEqual(state["recent_events"][0], {"type": "weather.changed", "source": "weather"})
        self.assertNotIn("world_state", state)
        self.assertNotIn("causal_trace", state)
        self.assertNotIn("registry", state)

    def test_malformed_action_never_calls_session(self) -> None:
        status, response = self.request("POST", "/api/action", {"action": "travel", "slot": True})
        self.assertEqual(status, 400)
        self.assertIn("slot", response["error"]["message"])
        self.assertEqual(self.session.calls, [])

    def test_valid_action_and_restart(self) -> None:
        status, response = self.request("POST", "/api/action", {"action": "travel", "target": "tower"})
        self.assertEqual(status, 200)
        self.assertEqual(response["state"]["current_area"], "shallows")
        self.assertEqual(self.session.calls, [("travel", "tower", None)])
        status, _ = self.request("POST", "/api/new-game", {})
        self.assertEqual(status, 200)
        self.assertEqual(self.session.restarts, 1)

    def test_static_traversal_is_rejected(self) -> None:
        status, _ = self.request("GET", "/../server.py")
        self.assertEqual(status, 404)

    def test_projection_rejects_unknown_top_level_fields(self) -> None:
        projected = project_public_state({"outcome": "playing", "raw": object()})
        self.assertEqual(set(projected), {
            "outcome", "time", "current_area", "player", "areas", "inventory", "discoveries",
            "recipes", "registered_skills", "equipped_skills", "combat", "recent_events", "feedback", "legal_actions",
        })
