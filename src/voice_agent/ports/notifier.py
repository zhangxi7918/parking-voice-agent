from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from voice_agent.domain.call_session import CallSession


@dataclass(frozen=True, slots=True)
class NotificationResult:
    status: str
    detail: str | None = None


class Notifier(Protocol):
    async def send_visitor_intake(self, session: CallSession) -> NotificationResult:
        """Send a completed visitor intake record to the guard."""

    async def send_session_summary(self, session: CallSession) -> NotificationResult:
        """Send an end-of-session summary with whatever info was collected."""

