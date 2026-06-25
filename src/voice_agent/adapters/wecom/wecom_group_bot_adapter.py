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
        return await self._send_markdown(message)

    async def send_session_summary(self, session: CallSession) -> NotificationResult:
        message = self._format_summary(session)
        return await self._send_markdown(message)

    # ── internals ───────────────────────────────────────────────────

    async def _send_markdown(self, message: str) -> NotificationResult:
        if self._dry_run or not self._webhook_url:
            logger.info("WeCom notification skipped (dry_run=%s url=%s): %s",
                        self._dry_run, bool(self._webhook_url), message)
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

    def _format_summary(self, session: CallSession) -> str:
        intake = session.intake
        completeness = 5 - len(intake.missing_required_fields())
        lines = [
            "**通话结束 — 访客摘要**",
            "",
            f"完整度：{completeness}/5",
            f"> 姓名：{intake.visitor_name or '-'}",
            f"> 手机：{intake.phone or '-'}",
            f"> 车牌：{intake.plate_number or '-'}",
            f"> 事项：{intake.visit_purpose or '-'}",
            f"> 拜访对象：{intake.host_name or '-'}",
            "",
            "**对话记录**",
        ]
        for turn in session.transcript:
            role_label = "门岗" if turn.role == "agent" else "访客" if turn.role == "caller" else "系统"
            text = turn.text[:200] if turn.text else ""
            lines.append(f"> {role_label}：{text}")
        return "\n".join(lines)

