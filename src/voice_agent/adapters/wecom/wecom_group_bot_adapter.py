from __future__ import annotations

import logging

import httpx

from voice_agent.domain.call_session import CallSession
from voice_agent.ports.notifier import NotificationResult


logger = logging.getLogger(__name__)


class WeComGroupBotNotifier:
    def __init__(self, webhook_url: str | None, dry_run: bool = True) -> None:
        self._webhook_url = webhook_url
        self._dry_run = dry_run

    async def send_visitor_intake(self, session: CallSession) -> NotificationResult:
        message = self._format_message(session)
        if self._dry_run or not self._webhook_url:
            logger.info("WeCom notification skipped: %s", message)
            return NotificationResult(status="skipped", detail="dry run or missing webhook")

        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.post(
                self._webhook_url,
                json={"msgtype": "markdown", "markdown": {"content": message}},
            )
            response.raise_for_status()
        return NotificationResult(status="sent", detail="wecom webhook accepted")

    def _format_message(self, session: CallSession) -> str:
        intake = session.intake
        lines = [
            "**访客车辆待确认**",
            f"> 姓名：{intake.visitor_name or '-'}",
            f"> 手机：{intake.phone or '-'}",
            f"> 车牌：{intake.plate_number or '-'}",
            f"> 公司：{intake.company or '-'}",
            f"> 事项：{intake.visit_purpose or '-'}",
            f"> 拜访对象：{intake.host_name or '-'}",
            f"> 会话：{session.id}",
        ]
        return "\n".join(lines)

