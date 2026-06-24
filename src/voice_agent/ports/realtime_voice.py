from __future__ import annotations

from typing import Protocol


class RealtimeVoiceSession(Protocol):
    async def send_audio(self, audio: bytes) -> None:
        """Send caller audio to the realtime provider."""

    async def close(self) -> None:
        """Close provider resources."""


class RealtimeVoiceProvider(Protocol):
    async def open_session(self, session_id: str) -> RealtimeVoiceSession:
        """Open one realtime voice session."""

