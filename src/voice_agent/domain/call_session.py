from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from uuid import uuid4

from voice_agent.domain.conversation_state import ConversationState
from voice_agent.domain.gate_release import GateReleaseStatus
from voice_agent.domain.visitor import VisitorIntake


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(slots=True)
class TranscriptTurn:
    role: str
    text: str
    at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "TranscriptTurn":
        return cls(role=data["role"], text=data["text"], at=data.get("at") or utc_now_iso())


@dataclass(slots=True)
class CallSession:
    id: str = field(default_factory=lambda: str(uuid4()))
    call_sid: str | None = None
    status: GateReleaseStatus = GateReleaseStatus.ACTIVE
    state: ConversationState = ConversationState.GREETING
    intake: VisitorIntake = field(default_factory=VisitorIntake)
    transcript: list[TranscriptTurn] = field(default_factory=list)
    notification_sent: bool = False
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    def add_turn(self, role: str, text: str) -> None:
        self.transcript.append(TranscriptTurn(role=role, text=text))
        self.updated_at = utc_now_iso()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "call_sid": self.call_sid,
            "status": self.status.value,
            "state": self.state.value,
            "intake": self.intake.to_dict(),
            "transcript": [turn.to_dict() for turn in self.transcript],
            "notification_sent": self.notification_sent,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CallSession":
        return cls(
            id=data["id"],
            call_sid=data.get("call_sid"),
            status=GateReleaseStatus(data.get("status", GateReleaseStatus.ACTIVE.value)),
            state=ConversationState(data.get("state", ConversationState.GREETING.value)),
            intake=VisitorIntake.from_dict(data.get("intake") or {}),
            transcript=[TranscriptTurn.from_dict(turn) for turn in data.get("transcript") or []],
            notification_sent=bool(data.get("notification_sent", False)),
            created_at=data.get("created_at") or utc_now_iso(),
            updated_at=data.get("updated_at") or utc_now_iso(),
        )

