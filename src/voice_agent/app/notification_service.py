from __future__ import annotations

from voice_agent.domain.call_session import CallSession
from voice_agent.ports.notifier import NotificationResult, Notifier


class NotificationService:
    def __init__(self, notifier: Notifier) -> None:
        self._notifier = notifier

    async def notify_guard(self, session: CallSession) -> NotificationResult:
        return await self._notifier.send_visitor_intake(session)

    async def notify_session_end(self, session: CallSession) -> NotificationResult:
        return await self._notifier.send_session_summary(session)

