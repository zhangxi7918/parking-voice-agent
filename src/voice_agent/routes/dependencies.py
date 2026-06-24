from __future__ import annotations

from fastapi import Request

from voice_agent.app.call_session_orchestrator import CallSessionOrchestrator


def get_orchestrator(request: Request) -> CallSessionOrchestrator:
    return request.app.state.orchestrator

