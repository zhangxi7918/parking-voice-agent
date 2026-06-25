from __future__ import annotations

from fastapi import FastAPI

from voice_agent.adapters.db.sqlite_visitor_repository import SQLiteVisitorRepository
from voice_agent.adapters.qwen.qwen_realtime_adapter import QwenRealtimeConfig, QwenRealtimeProvider
from voice_agent.adapters.wecom.wecom_group_bot_adapter import WeComGroupBotNotifier
from voice_agent.app.call_session_orchestrator import CallSessionOrchestrator
from voice_agent.app.notification_service import NotificationService
from voice_agent.app.visitor_intake_service import VisitorIntakeService
from voice_agent.config import Settings
from voice_agent.prompts.gatekeeper_system_prompt import GATEKEEPER_SYSTEM_PROMPT
from voice_agent.routes import browser_call, demo, health, twilio_webhook


def create_app() -> FastAPI:
    settings = Settings.from_env()
    repository = SQLiteVisitorRepository(settings.database_path)
    notifier = WeComGroupBotNotifier(
        webhook_url=settings.wecom_webhook_url,
        dry_run=settings.notification_dry_run,
    )
    orchestrator = CallSessionOrchestrator(
        repository=repository,
        intake_service=VisitorIntakeService(),
        notification_service=NotificationService(notifier),
    )

    realtime_voice_provider = None
    if settings.dashscope_api_key:
        realtime_voice_provider = QwenRealtimeProvider(
            QwenRealtimeConfig(
                api_key=settings.dashscope_api_key,
                model=settings.qwen_realtime_model,
                instructions=GATEKEEPER_SYSTEM_PROMPT,
            )
        )

    app = FastAPI(title="Parking Voice Agent")
    app.state.settings = settings
    app.state.orchestrator = orchestrator
    app.state.realtime_voice_provider = realtime_voice_provider
    app.include_router(health.router)
    app.include_router(browser_call.router)
    app.include_router(demo.router)
    app.include_router(twilio_webhook.router)
    return app
