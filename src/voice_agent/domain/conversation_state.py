from __future__ import annotations

from enum import StrEnum


class ConversationState(StrEnum):
    GREETING = "greeting"
    COLLECTING_VISITOR_NAME = "collecting_visitor_name"
    COLLECTING_PHONE = "collecting_phone"
    COLLECTING_PLATE_NUMBER = "collecting_plate_number"
    COLLECTING_VISIT_PURPOSE = "collecting_visit_purpose"
    COLLECTING_HOST = "collecting_host"
    CONFIRMING_INFO = "confirming_info"
    PUSHING_TO_GUARD = "pushing_to_guard"
    WAITING_GUARD_APPROVAL = "waiting_guard_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    ENDED = "ended"

