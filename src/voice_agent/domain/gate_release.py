from __future__ import annotations

from enum import StrEnum


class GateReleaseStatus(StrEnum):
    ACTIVE = "active"
    PENDING_GUARD = "pending_guard"
    APPROVED = "approved"
    REJECTED = "rejected"
    ENDED = "ended"

