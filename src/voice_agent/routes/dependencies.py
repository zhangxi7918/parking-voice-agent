from __future__ import annotations

from starlette.requests import HTTPConnection

from voice_agent.app.call_session_orchestrator import CallSessionOrchestrator


def get_orchestrator(connection: HTTPConnection) -> CallSessionOrchestrator:
    return connection.app.state.orchestrator
