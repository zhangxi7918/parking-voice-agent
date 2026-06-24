from __future__ import annotations

import json
from html import escape
from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import Response

from voice_agent.app.call_session_orchestrator import CallSessionOrchestrator
from voice_agent.config import Settings
from voice_agent.routes.dependencies import get_orchestrator


router = APIRouter(prefix="/twilio", tags=["twilio"])


@router.post("/voice")
async def voice_webhook(
    request: Request,
    orchestrator: CallSessionOrchestrator = Depends(get_orchestrator),
) -> Response:
    form = parse_qs((await request.body()).decode())
    call_sid = _first(form, "CallSid")
    session = orchestrator.start_call(call_sid=call_sid)
    settings: Settings = request.app.state.settings
    stream_url = _build_stream_url(request, settings, session.id)
    greeting = escape(session.transcript[-1].text if session.transcript else "您好，请稍等。")

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Say language="zh-CN">{greeting}</Say>
  <Connect>
    <Stream url="{escape(stream_url)}" />
  </Connect>
</Response>"""
    return Response(content=xml, media_type="application/xml")


@router.websocket("/media")
async def media_stream(
    websocket: WebSocket,
    orchestrator: CallSessionOrchestrator = Depends(get_orchestrator),
) -> None:
    await websocket.accept()
    session_id = websocket.query_params.get("session_id")
    session = orchestrator.get_session(session_id) if session_id else None

    if session is None:
        await websocket.close(code=1008)
        return

    try:
        while True:
            raw_message = await websocket.receive_text()
            message = json.loads(raw_message)
            event = message.get("event")
            if event == "stop":
                break
            if event == "media":
                # Twilio sends base64 mulaw audio frames here. The Qwen realtime
                # adapter should consume these frames after codec conversion.
                continue
    except WebSocketDisconnect:
        return
    finally:
        await websocket.close()


def _first(form: dict[str, list[str]], key: str) -> str | None:
    values = form.get(key)
    return values[0] if values else None


def _build_stream_url(request: Request, settings: Settings, session_id: str) -> str:
    if settings.public_base_url:
        base = settings.public_base_url
    else:
        base = str(request.base_url).rstrip("/")

    if base.startswith("https://"):
        base = "wss://" + base.removeprefix("https://")
    elif base.startswith("http://"):
        base = "ws://" + base.removeprefix("http://")

    return f"{base}/twilio/media?session_id={session_id}"

