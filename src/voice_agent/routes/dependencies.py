from __future__ import annotations

from starlette.requests import HTTPConnection

from voice_agent.app.call_session_orchestrator import CallSessionOrchestrator
from voice_agent.config import Settings


def get_orchestrator(connection: HTTPConnection) -> CallSessionOrchestrator:
    return connection.app.state.orchestrator


def get_settings(connection: HTTPConnection) -> Settings:
    return connection.app.state.settings
