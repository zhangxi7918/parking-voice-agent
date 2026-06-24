from __future__ import annotations

from dataclasses import asdict, dataclass

from voice_agent.app.notification_service import NotificationService
from voice_agent.app.visitor_intake_service import VisitorIntakeService
from voice_agent.domain.call_session import CallSession
from voice_agent.domain.gate_release import GateReleaseStatus
from voice_agent.ports.notifier import NotificationResult
from voice_agent.ports.visitor_repository import VisitorRepository


@dataclass(frozen=True, slots=True)
class AgentTurnResult:
    session: CallSession
    agent_text: str
    notification: NotificationResult | None = None

    def to_dict(self) -> dict:
        return {
            "session": self.session.to_dict(),
            "agent_text": self.agent_text,
            "notification": None if self.notification is None else asdict(self.notification),
        }


class CallSessionOrchestrator:
    def __init__(
        self,
        repository: VisitorRepository,
        intake_service: VisitorIntakeService,
        notification_service: NotificationService,
    ) -> None:
        self._repository = repository
        self._intake_service = intake_service
        self._notification_service = notification_service

    def start_call(self, call_sid: str | None = None) -> CallSession:
        session = self._repository.create_session(call_sid=call_sid)
        greeting = self._intake_service.greeting()
        session.add_turn("agent", greeting)
        self._repository.save_session(session)
        return session

    async def handle_caller_text(self, session_id: str | None, caller_text: str) -> AgentTurnResult:
        session = self._load_or_create_session(session_id)
        session.add_turn("caller", caller_text)

        intake_result = self._intake_service.process_caller_text(session.intake, caller_text)
        session.intake = intake_result.intake
        session.state = intake_result.state
        session.add_turn("agent", intake_result.agent_text)

        notification = None
        if intake_result.completed and not session.notification_sent:
            session.status = GateReleaseStatus.PENDING_GUARD
            notification = await self._notification_service.notify_guard(session)
            session.notification_sent = notification.status in {"sent", "skipped"}

        self._repository.save_session(session)
        return AgentTurnResult(
            session=session,
            agent_text=intake_result.agent_text,
            notification=notification,
        )

    def get_session(self, session_id: str) -> CallSession | None:
        return self._repository.get_session(session_id)

    def list_sessions(self, limit: int = 50) -> list[CallSession]:
        return self._repository.list_sessions(limit=limit)

    def _load_or_create_session(self, session_id: str | None) -> CallSession:
        if session_id:
            session = self._repository.get_session(session_id)
            if session:
                return session
        return self.start_call()
