from __future__ import annotations

from fastapi import FastAPI

from voice_agent.adapters.db.sqlite_visitor_repository import SQLiteVisitorRepository
from voice_agent.adapters.wecom.wecom_group_bot_adapter import WeComGroupBotNotifier
from voice_agent.app.call_session_orchestrator import CallSessionOrchestrator
from voice_agent.app.notification_service import NotificationService
from voice_agent.app.visitor_intake_service import VisitorIntakeService
from voice_agent.config import Settings
from voice_agent.routes import demo, health, twilio_webhook


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

    app = FastAPI(title="Parking Voice Agent")
    app.state.settings = settings
    app.state.orchestrator = orchestrator
    app.include_router(health.router)
    app.include_router(demo.router)
    app.include_router(twilio_webhook.router)
    return app

