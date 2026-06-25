from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class RealtimeVoiceEvent:
    """A discrete event emitted by a realtime voice session."""

    type: str  # "audio" | "input_transcription" | "output_transcription" | "error"
    text: str | None = None
    audio: bytes | None = None
    error: str | None = None


class RealtimeVoiceSession(Protocol):
    async def send_audio(self, audio: bytes) -> None:
        """Send caller audio to the realtime provider."""

    async def commit_audio(self) -> None:
        """Signal end of audio input and request a model response."""

    async def receive_event(self) -> RealtimeVoiceEvent:
        """Block until a session event arrives (audio chunk, transcription, or error)."""

    async def clear_audio(self) -> None:
        """Clear the input audio buffer between turns."""

    async def close(self) -> None:
        """Close provider resources."""


class RealtimeVoiceProvider(Protocol):
    async def open_session(self, session_id: str) -> RealtimeVoiceSession:
        """Open one realtime voice session."""
