from __future__ import annotations

import json
import unittest
from pathlib import Path

import jwt
from fastapi import FastAPI
from fastapi.testclient import TestClient

from voice_agent.config import Settings
from voice_agent.routes import browser_call


class FakeSession:
    def __init__(self, session_id: str, transcript: list[dict] | None = None) -> None:
        self.id = session_id
        self.transcript = [
            type("Turn", (), turn) for turn in (transcript or [{"text": "您好"}])
        ]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "transcript": [{"text": turn.text} for turn in self.transcript],
        }


class FakeOrchestrator:
    def __init__(self) -> None:
        self.sessions: dict[str, FakeSession] = {}
        self.started_call_sid: str | None = None

    def start_call(self, call_sid: str | None = None) -> FakeSession:
        self.started_call_sid = call_sid
        session = FakeSession(session_id="session-123")
        self.sessions[session.id] = session
        return session

    def get_session(self, session_id: str) -> FakeSession | None:
        return self.sessions.get(session_id)


class BrowserCallRouteTest(unittest.TestCase):
    def test_page_is_served(self) -> None:
        client, _ = self._client()

        response = client.get("/browser-call")

        self.assertEqual(response.status_code, 200)
        self.assertIn("浏览器电话接入", response.text)
        self.assertIn("livekit-client", response.text)

    def test_create_session_returns_livekit_token_with_agent_dispatch(self) -> None:
        client, orchestrator = self._client()

        response = client.post("/browser-call/sessions")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(orchestrator.started_call_sid, "browser")
        payload = response.json()
        self.assertEqual(payload["session"]["id"], "session-123")
        self.assertEqual(payload["livekit_url"], "wss://livekit.example")
        self.assertTrue(payload["room_name"].startswith("parking-"))
        self.assertTrue(payload["participant_identity"].startswith("browser-"))

        token_payload = jwt.decode(payload["token"], options={"verify_signature": False})
        self.assertEqual(token_payload["iss"], "test-livekit-key")
        self.assertEqual(token_payload["sub"], payload["participant_identity"])
        self.assertEqual(token_payload["video"]["roomJoin"], True)
        self.assertEqual(token_payload["video"]["room"], payload["room_name"])

        dispatch = token_payload["roomConfig"]["agents"][0]
        self.assertEqual(dispatch["agentName"], "parking-gatekeeper-test")
        self.assertEqual(json.loads(dispatch["metadata"]), {"session_id": "session-123"})

    def test_create_session_requires_livekit_config(self) -> None:
        client, _ = self._client(livekit_url=None)

        response = client.post("/browser-call/sessions")

        self.assertEqual(response.status_code, 500)
        self.assertIn("LIVEKIT_URL", response.json()["detail"])

    def _client(
        self,
        livekit_url: str | None = "wss://livekit.example",
    ) -> tuple[TestClient, FakeOrchestrator]:
        app = FastAPI()
        app.state.settings = Settings(
            app_env="test",
            database_path=Path(":memory:"),
            wecom_webhook_url=None,
            notification_dry_run=True,
            voice_agent_ai_provider="openai",
            livekit_url=livekit_url,
            livekit_api_key="test-livekit-key",
            livekit_api_secret="test-livekit-secret-with-enough-length",
            livekit_agent_name="parking-gatekeeper-test",
            openai_api_key=None,
            dashscope_api_key=None,
            dashscope_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            dashscope_asr_model="qwen3-asr-flash",
            dashscope_llm_model="qwen-plus",
            elevenlabs_api_key=None,
            elevenlabs_voice_id=None,
        )
        orchestrator = FakeOrchestrator()
        app.state.orchestrator = orchestrator
        app.include_router(browser_call.router)
        return TestClient(app), orchestrator


if __name__ == "__main__":
    unittest.main()
