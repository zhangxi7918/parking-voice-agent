from __future__ import annotations

import re
from dataclasses import dataclass

from voice_agent.domain.conversation_state import ConversationState
from voice_agent.domain.visitor import VisitorIntake


FIELD_QUESTIONS = {
    "visitor_name": "您好，请问您怎么称呼？",
    "phone": "麻烦您留一下手机号，方便门卫核对。",
    "plate_number": "请问您的车牌号是多少？",
    "visit_purpose": "请问您这次过来是办什么事？",
    "host_name": "请问您要找哪位同事或哪个部门？",
}


@dataclass(frozen=True, slots=True)
class IntakeTurnResult:
    intake: VisitorIntake
    state: ConversationState
    agent_text: str
    completed: bool


class VisitorIntakeService:
    def process_caller_text(self, intake: VisitorIntake, caller_text: str) -> IntakeTurnResult:
        text = caller_text.strip()
        self._extract_phone(intake, text)
        self._extract_plate_number(intake, text)
        self._extract_visitor_name(intake, text)
        self._extract_host_name(intake, text)
        self._extract_company(intake, text)
        self._extract_visit_purpose(intake, text)

        missing = intake.missing_required_fields()
        if not missing:
            return IntakeTurnResult(
                intake=intake,
                state=ConversationState.CONFIRMING_INFO,
                agent_text=self._confirmation_text(intake),
                completed=True,
            )

        next_field = missing[0]
        return IntakeTurnResult(
            intake=intake,
            state=self._state_for_missing_field(next_field),
            agent_text=FIELD_QUESTIONS[next_field],
            completed=False,
        )

    def greeting(self) -> str:
        return "您好，这里是停车场门岗，请问您来访需要找哪位？"

    def _extract_phone(self, intake: VisitorIntake, text: str) -> None:
        if intake.phone:
            return
        match = re.search(r"(?:\+?86[- ]?)?(1[3-9]\d{9})", text)
        if match:
            intake.phone = match.group(1)
            intake.confidence["phone"] = 0.98

    def _extract_plate_number(self, intake: VisitorIntake, text: str) -> None:
        if intake.plate_number:
            return
        normalized = text.upper().replace(" ", "")
        match = re.search(r"([\u4e00-\u9fff][A-Z][A-Z0-9]{5,6})", normalized)
        if match:
            intake.plate_number = match.group(1)
            intake.confidence["plate_number"] = 0.9

    def _extract_visitor_name(self, intake: VisitorIntake, text: str) -> None:
        if intake.visitor_name:
            return
        patterns = [
            r"(?:我叫|我是)([\u4e00-\u9fffA-Za-z]{2,8})",
            r"([\u4e00-\u9fff]{1,4})(?:师傅|先生|女士)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                intake.visitor_name = match.group(1)
                intake.confidence["visitor_name"] = 0.82
                return

    def _extract_host_name(self, intake: VisitorIntake, text: str) -> None:
        if intake.host_name:
            return
        patterns = [
            r"(?:找|拜访|见|约了)([\u4e00-\u9fffA-Za-z]{1,8}?)(?:送货|配送|开会|面试|维修|取货|，|,|。|$)",
            r"(?:给|向)([\u4e00-\u9fffA-Za-z]{1,8}?)(?:送|交)",
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                intake.host_name = match.group(1)
                intake.confidence["host_name"] = 0.78
                return

    def _extract_company(self, intake: VisitorIntake, text: str) -> None:
        if intake.company:
            return
        match = re.search(r"(?:我是|来自)([\u4e00-\u9fffA-Za-z0-9]{2,20}(?:公司|物流|科技))", text)
        if match:
            intake.company = match.group(1)
            intake.confidence["company"] = 0.78

    def _extract_visit_purpose(self, intake: VisitorIntake, text: str) -> None:
        if intake.visit_purpose:
            return
        purpose_keywords = {
            "送货": "送货",
            "配送": "送货",
            "面试": "面试",
            "开会": "开会",
            "维修": "维修",
            "拜访": "拜访",
            "取货": "取货",
        }
        for keyword, purpose in purpose_keywords.items():
            if keyword in text:
                intake.visit_purpose = purpose
                intake.confidence["visit_purpose"] = 0.8
                return

    def _state_for_missing_field(self, field_name: str) -> ConversationState:
        return {
            "visitor_name": ConversationState.COLLECTING_VISITOR_NAME,
            "phone": ConversationState.COLLECTING_PHONE,
            "plate_number": ConversationState.COLLECTING_PLATE_NUMBER,
            "visit_purpose": ConversationState.COLLECTING_VISIT_PURPOSE,
            "host_name": ConversationState.COLLECTING_HOST,
        }[field_name]

    def _confirmation_text(self, intake: VisitorIntake) -> str:
        company_part = f"，来自{intake.company}" if intake.company else ""
        return (
            f"我确认一下，您是{intake.visitor_name}{company_part}，"
            f"手机号{intake.phone}，车牌{intake.plate_number}，"
            f"来访事项是{intake.visit_purpose}，要找{intake.host_name}。"
            "我现在发给门卫确认，请稍等。"
        )
