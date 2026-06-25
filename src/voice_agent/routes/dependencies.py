from __future__ import annotations

from starlette.requests import HTTPConnection

from voice_agent.adapters.qwen.qwen_realtime_adapter import QwenRealtimeProvider
from voice_agent.app.call_session_orchestrator import CallSessionOrchestrator


def get_orchestrator(connection: HTTPConnection) -> CallSessionOrchestrator:
    return connection.app.state.orchestrator


def get_realtime_voice_provider(connection: HTTPConnection) -> QwenRealtimeProvider | None:
    return getattr(connection.app.state, "realtime_voice_provider", None)
