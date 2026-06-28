from __future__ import annotations

from fastapi import FastAPI

from voice_agent.app.bootstrap import create_orchestrator
from voice_agent.config import Settings
from voice_agent.routes import browser_call, demo, health


def create_app() -> FastAPI:
    settings = Settings.from_env()

    app = FastAPI(title="Parking Voice Agent")
    app.state.settings = settings
    app.state.orchestrator = create_orchestrator(settings)
    app.include_router(health.router)
    app.include_router(browser_call.router)
    app.include_router(demo.router)
    return app
