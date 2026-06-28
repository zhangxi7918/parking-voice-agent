from __future__ import annotations

import pickle
import unittest
from pathlib import Path

from voice_agent.config import Settings
from voice_agent.livekit_worker import (
    DashScopeQwenAsrSTT,
    build_server,
    create_stt,
    handle_final_transcript,
    notify_session_end,
    resolve_session_id,
    session_id_from_metadata,
)


class FakeTurnResult:
    def __init__(self, agent_text: str) -> None:
        self.agent_text = agent_text


class FakeSession:
    def __init__(self, session_id: str, text: str = "您好") -> None:
        self.id = session_id
        self.transcript = [type("Turn", (), {"text": text})]


class FakeOrchestrator:
    def __init__(self) -> None:
        self.sessions = {"session-123": FakeSession("session-123", "固定问候")}
        self.last_turn: tuple[str | None, str] | None = None
        self.started_call_sid: str | None = None
        self.notified_session_id: str | None = None

    def get_session(self, session_id: str) -> FakeSession | None:
        return self.sessions.get(session_id)

    def start_call(self, call_sid: str | None = None) -> FakeSession:
        self.started_call_sid = call_sid
        session = FakeSession("new-session", "新问候")
        self.sessions[session.id] = session
        return session

    async def handle_caller_text(self, session_id: str | None, caller_text: str) -> FakeTurnResult:
        self.last_turn = (session_id, caller_text)
        return FakeTurnResult(agent_text=f"收到：{caller_text}")

    async def notify_session_end(self, session_id: str) -> None:
        self.notified_session_id = session_id


class FakeLiveKitSession:
    def __init__(self) -> None:
        self.spoken: list[tuple[str, bool]] = []

    async def say(self, text: str, allow_interruptions: bool = True) -> None:
        self.spoken.append((text, allow_interruptions))


class LiveKitWorkerTest(unittest.IsolatedAsyncioTestCase):
    def test_build_server_registers_pickleable_process_callbacks(self) -> None:
        settings = Settings(
            app_env="test",
            database_path=Path(":memory:"),
            wecom_webhook_url=None,
            notification_dry_run=True,
            voice_agent_ai_provider="openai",
            livekit_url="wss://livekit.example",
            livekit_api_key="test-livekit-key",
            livekit_api_secret="test-livekit-secret",
            livekit_agent_name="parking-gatekeeper-test",
            openai_api_key=None,
            dashscope_api_key=None,
            dashscope_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            dashscope_asr_model="qwen3-asr-flash",
            dashscope_llm_model="qwen-plus",
            elevenlabs_api_key=None,
            elevenlabs_voice_id=None,
        )

        server = build_server(settings)

        pickle.dumps(server._entrypoint_fnc)
        pickle.dumps(server.setup_fnc)

    def test_create_stt_uses_dashscope_provider(self) -> None:
        settings = Settings(
            app_env="test",
            database_path=Path(":memory:"),
            wecom_webhook_url=None,
            notification_dry_run=True,
            voice_agent_ai_provider="dashscope",
            livekit_url="wss://livekit.example",
            livekit_api_key="test-livekit-key",
            livekit_api_secret="test-livekit-secret",
            livekit_agent_name="parking-gatekeeper-test",
            openai_api_key=None,
            dashscope_api_key="test-dashscope-key",
            dashscope_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            dashscope_asr_model="qwen3-asr-flash",
            dashscope_llm_model="qwen-plus",
            elevenlabs_api_key=None,
            elevenlabs_voice_id=None,
        )

        stt_plugin = create_stt(settings)

        self.assertIsInstance(stt_plugin, DashScopeQwenAsrSTT)
        self.assertEqual(stt_plugin.provider, "dashscope")
        self.assertEqual(stt_plugin.model, "qwen3-asr-flash")

    def test_session_id_from_metadata(self) -> None:
        self.assertEqual(
            session_id_from_metadata('{"session_id":"session-123"}'),
            "session-123",
        )
        self.assertIsNone(session_id_from_metadata("not-json"))
        self.assertIsNone(session_id_from_metadata("{}"))

    def test_resolve_session_id_reuses_metadata_session(self) -> None:
        orchestrator = FakeOrchestrator()

        session_id, greeting = resolve_session_id(orchestrator, "session-123")

        self.assertEqual(session_id, "session-123")
        self.assertEqual(greeting, "固定问候")
        self.assertIsNone(orchestrator.started_call_sid)

    def test_resolve_session_id_starts_fallback_session(self) -> None:
        orchestrator = FakeOrchestrator()

        session_id, greeting = resolve_session_id(orchestrator, None)

        self.assertEqual(session_id, "new-session")
        self.assertEqual(greeting, "新问候")
        self.assertEqual(orchestrator.started_call_sid, "livekit")

    async def test_handle_final_transcript_sends_business_reply_to_tts(self) -> None:
        orchestrator = FakeOrchestrator()
        livekit_session = FakeLiveKitSession()

        await handle_final_transcript(
            orchestrator=orchestrator,
            livekit_session=livekit_session,
            session_id="session-123",
            transcript="  我到了  ",
        )

        self.assertEqual(orchestrator.last_turn, ("session-123", "我到了"))
        self.assertEqual(livekit_session.spoken, [("收到：我到了", True)])

    async def test_handle_final_transcript_ignores_empty_text(self) -> None:
        orchestrator = FakeOrchestrator()
        livekit_session = FakeLiveKitSession()

        await handle_final_transcript(
            orchestrator=orchestrator,
            livekit_session=livekit_session,
            session_id="session-123",
            transcript="   ",
        )

        self.assertIsNone(orchestrator.last_turn)
        self.assertEqual(livekit_session.spoken, [])

    async def test_notify_session_end_delegates_to_orchestrator(self) -> None:
        orchestrator = FakeOrchestrator()

        await notify_session_end(orchestrator, "session-123")

        self.assertEqual(orchestrator.notified_session_id, "session-123")


if __name__ == "__main__":
    unittest.main()
