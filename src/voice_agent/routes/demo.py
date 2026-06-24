from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from voice_agent.app.call_session_orchestrator import CallSessionOrchestrator
from voice_agent.routes.dependencies import get_orchestrator


router = APIRouter(prefix="/demo", tags=["demo"])


class DemoTurnRequest(BaseModel):
    caller_text: str = Field(min_length=1)
    session_id: str | None = None


@router.post("/turn")
async def demo_turn(
    payload: DemoTurnRequest,
    orchestrator: CallSessionOrchestrator = Depends(get_orchestrator),
) -> dict:
    result = await orchestrator.handle_caller_text(
        session_id=payload.session_id,
        caller_text=payload.caller_text,
    )
    return result.to_dict()


@router.get("/sessions/{session_id}")
def get_demo_session(
    session_id: str,
    orchestrator: CallSessionOrchestrator = Depends(get_orchestrator),
) -> dict:
    session = orchestrator.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    return session.to_dict()


@router.get("/sessions")
def list_demo_sessions(
    orchestrator: CallSessionOrchestrator = Depends(get_orchestrator),
) -> dict:
    return {"sessions": [session.to_dict() for session in orchestrator.list_sessions()]}

