from __future__ import annotations

from typing import Protocol

from voice_agent.domain.call_session import CallSession


class VisitorRepository(Protocol):
    def create_session(self, call_sid: str | None = None) -> CallSession:
        """Create and persist a call session."""

    def get_session(self, session_id: str) -> CallSession | None:
        """Return a session by ID."""

    def save_session(self, session: CallSession) -> None:
        """Persist a session."""

    def list_sessions(self, limit: int = 50) -> list[CallSession]:
        """Return recent sessions."""

