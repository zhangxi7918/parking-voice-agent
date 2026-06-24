from __future__ import annotations

from dataclasses import dataclass

from voice_agent.ports.realtime_voice import RealtimeVoiceProvider, RealtimeVoiceSession


@dataclass(slots=True)
class QwenRealtimeConfig:
    api_key: str
    model: str


class QwenRealtimeSession:
    def __init__(self, session_id: str, config: QwenRealtimeConfig) -> None:
        self._session_id = session_id
        self._config = config

    async def send_audio(self, audio: bytes) -> None:
        raise NotImplementedError(
            "Wire DashScope Qwen-Omni-Realtime WebSocket audio here. "
            "The provider smoke-test in tech-selection can be used as the protocol reference."
        )

    async def close(self) -> None:
        return None


class QwenRealtimeProvider(RealtimeVoiceProvider):
    def __init__(self, config: QwenRealtimeConfig) -> None:
        self._config = config

    async def open_session(self, session_id: str) -> RealtimeVoiceSession:
        return QwenRealtimeSession(session_id=session_id, config=self._config)

