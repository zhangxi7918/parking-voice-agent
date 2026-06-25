from __future__ import annotations

import asyncio
import base64
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from voice_agent.config import Settings
from voice_agent.ports.realtime_voice import RealtimeVoiceEvent, RealtimeVoiceSession
from voice_agent.routes import browser_call


# ── fakes ────────────────────────────────────────────────────────────


class FakeSession:
    def __init__(self, session_id: str, transcript: list[dict] | None = None) -> None:
        self.id = session_id
        self.transcript = [
            type("Turn", (), t) for t in (transcript or [{"text": "您好"}])
        ]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "transcript": [{"text": turn.text} for turn in self.transcript],
        }


class FakeTurnResult:
    def __init__(self, session: FakeSession, agent_text: str) -> None:
        self.session = session
        self.agent_text = agent_text

    def to_dict(self) -> dict:
        return {
            "session": self.session.to_dict(),
            "agent_text": self.agent_text,
            "notification": None,
        }


class FakeOrchestrator:
    def __init__(self) -> None:
        self.sessions: dict[str, FakeSession] = {}
        self.started_call_sid: str | None = None
        self.last_turn: tuple[str | None, str] | None = None

    def start_call(self, call_sid: str | None = None) -> FakeSession:
        self.started_call_sid = call_sid
        session = FakeSession(session_id="session-123")
        self.sessions[session.id] = session
        return session

    async def handle_caller_text(
        self, session_id: str | None = None, caller_text: str = ""
    ) -> FakeTurnResult:
        self.last_turn = (session_id, caller_text)
        session = self.sessions.get(session_id or "") or self.start_call()
        return FakeTurnResult(session=session, agent_text=f"收到：{caller_text}")

    def get_session(self, session_id: str) -> FakeSession | None:
        return self.sessions.get(session_id)


class FakeRealtimeVoiceSession:
    """Captures audio chunks and lets tests inject Qwen events."""

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self.audio_chunks: list[bytes] = []
        self.committed = False
        self.cleared = False
        self.closed = False
        self._event_queue: asyncio.Queue[RealtimeVoiceEvent] = asyncio.Queue()

    async def send_audio(self, audio: bytes) -> None:
        self.audio_chunks.append(audio)

    async def commit_audio(self) -> None:
        self.committed = True

    async def receive_event(self) -> RealtimeVoiceEvent:
        return await self._event_queue.get()

    async def clear_audio(self) -> None:
        self.cleared = True

    async def close(self) -> None:
        self.closed = True
        # Unblock any waiter
        try:
            self._event_queue.put_nowait(
                RealtimeVoiceEvent(type="error", error="closed")
            )
        except asyncio.QueueFull:
            pass

    def inject_event(self, event: RealtimeVoiceEvent) -> None:
        """Push a test event into the session's receive queue."""
        self._event_queue.put_nowait(event)


class FakeRealtimeVoiceProvider:
    def __init__(self) -> None:
        self.sessions: dict[str, FakeRealtimeVoiceSession] = {}

    async def open_session(self, session_id: str) -> FakeRealtimeVoiceSession:
        session = FakeRealtimeVoiceSession(session_id)
        self.sessions[session_id] = session
        return session


# ── tests ────────────────────────────────────────────────────────────


class BrowserCallRouteTest(unittest.TestCase):
    def test_page_is_served(self) -> None:
        client, _, _ = self._client()

        response = client.get("/browser-call")

        self.assertEqual(response.status_code, 200)
        self.assertIn("浏览器电话接入", response.text)

    def test_create_session_uses_orchestrator(self) -> None:
        client, orchestrator, _ = self._client()

        response = client.post("/browser-call/sessions")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(orchestrator.started_call_sid, "browser")
        payload = response.json()
        self.assertEqual(payload["session"]["id"], "session-123")

    def test_turn_reuses_existing_session(self) -> None:
        client, orchestrator, _ = self._client()
        orchestrator.start_call(call_sid="browser")

        response = client.post(
            "/browser-call/turn",
            json={"session_id": "session-123", "caller_text": "我到了"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(orchestrator.last_turn, ("session-123", "我到了"))
        self.assertEqual(response.json()["agent_text"], "收到：我到了")

    def test_audio_stream_rejects_unknown_session(self) -> None:
        client, _, _ = self._client()

        with client.websocket_connect("/browser-call/audio") as websocket:
            websocket.send_json({
                "event": "start",
                "session_id": "missing",
            })
            response = websocket.receive_json()
            self.assertEqual(response["event"], "error")
            self.assertIn("invalid session_id", response["error"])

    def test_audio_stream_relays_audio_and_transcription(self) -> None:
        """Full integration: browser sends audio, receives transcription and agent turn."""
        client, orchestrator, provider = self._client()
        orchestrator.start_call(call_sid="browser")

        with client.websocket_connect("/browser-call/audio") as websocket:
            # Start — should trigger Qwen session creation.
            websocket.send_json({
                "event": "start",
                "session_id": "session-123",
            })
            ready = websocket.receive_json()
            self.assertEqual(ready["event"], "ready")

            # Verify that the Qwen session was opened.
            qwen_session = provider.sessions.get("session-123")
            self.assertIsNotNone(qwen_session)

            # Send PCM audio frames.
            payload = base64.b64encode(b"\x00\x00" * 160).decode()
            websocket.send_json({"event": "media", "payload": payload})
            websocket.send_json({"event": "media", "payload": payload})

            # Small delay to let the async task process.
            import time
            time.sleep(0.05)

            self.assertGreaterEqual(len(qwen_session.audio_chunks), 2)
            self.assertFalse(qwen_session.committed)

            # Commit the audio.
            websocket.send_json({"event": "commit"})
            time.sleep(0.05)
            self.assertTrue(qwen_session.committed)

            # Inject a Qwen transcription event.
            qwen_session.inject_event(
                RealtimeVoiceEvent(type="input_transcription", text="我是送货的")
            )
            # Inject a Qwen response text event.
            qwen_session.inject_event(
                RealtimeVoiceEvent(type="output_transcription", text="请问您的车牌号是多少？")
            )

            # The browser should receive turn events.
            turn1 = websocket.receive_json()
            self.assertEqual(turn1["event"], "turn")
            self.assertEqual(turn1["role"], "caller")
            self.assertEqual(turn1["text"], "我是送货的")

            turn2 = websocket.receive_json()
            self.assertEqual(turn2["event"], "turn")
            self.assertEqual(turn2["role"], "agent")
            self.assertEqual(turn2["text"], "请问您的车牌号是多少？")

            # Verify the orchestrator was called for intake tracking.
            self.assertEqual(
                orchestrator.last_turn,
                ("session-123", "我是送货的"),
            )

            # Clean stop.
            websocket.send_json({"event": "stop", "stop": {"reason": "done"}})

        # After WebSocket close, the Qwen session should be closed.
        self.assertTrue(qwen_session.closed)

    def _client(self) -> tuple[TestClient, FakeOrchestrator, FakeRealtimeVoiceProvider]:
        app = FastAPI()
        app.state.settings = Settings(
            app_env="test",
            public_base_url=None,
            database_path=Path(":memory:"),
            wecom_webhook_url=None,
            notification_dry_run=True,
            twilio_account_sid=None,
            twilio_auth_token=None,
            twilio_phone_number=None,
            twilio_validate_signature=False,
            dashscope_api_key="test-key",
            qwen_realtime_model="qwen-omni-turbo-realtime",
        )
        orchestrator = FakeOrchestrator()
        provider = FakeRealtimeVoiceProvider()
        app.state.orchestrator = orchestrator
        app.state.realtime_voice_provider = provider
        app.include_router(browser_call.router)
        return TestClient(app), orchestrator, provider


if __name__ == "__main__":
    unittest.main()
