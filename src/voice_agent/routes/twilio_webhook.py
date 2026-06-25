from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass
from html import escape
from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import Response

from voice_agent.app.call_session_orchestrator import CallSessionOrchestrator
from voice_agent.config import Settings
from voice_agent.routes.dependencies import get_orchestrator


router = APIRouter(prefix="/twilio", tags=["twilio"])
logger = logging.getLogger(__name__)


@dataclass(slots=True)
class TwilioMediaStreamStats:
    session_id: str | None = None
    call_sid: str | None = None
    stream_sid: str | None = None
    media_frames: int = 0
    media_bytes: int = 0
    stop_reason: str | None = None


@router.post("/voice")
async def voice_webhook(
    request: Request,
    orchestrator: CallSessionOrchestrator = Depends(get_orchestrator),
) -> Response:
    body = await request.body()
    form = parse_qs(body.decode(), keep_blank_values=True)
    settings: Settings = request.app.state.settings
    _validate_twilio_signature(request, settings, form)

    call_sid = _first(form, "CallSid")
    session = orchestrator.start_call(call_sid=call_sid)
    stream_url = _build_stream_url(request, settings)
    greeting_text = session.transcript[-1].text if session.transcript else "您好，请稍等。"
    greeting = escape(greeting_text)
    session_id = escape(session.id)

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Say language="zh-CN">{greeting}</Say>
  <Connect>
    <Stream url="{escape(stream_url)}">
      <Parameter name="session_id" value="{session_id}" />
    </Stream>
  </Connect>
</Response>"""
    return Response(content=xml, media_type="application/xml")


@router.websocket("/media")
async def media_stream(
    websocket: WebSocket,
    orchestrator: CallSessionOrchestrator = Depends(get_orchestrator),
) -> None:
    await websocket.accept()
    stats = TwilioMediaStreamStats()
    session_validated = False

    try:
        while True:
            raw_message = await websocket.receive_text()
            message = json.loads(raw_message)
            event = message.get("event")

            if event == "connected":
                logger.info("twilio_media_connected")
                continue

            if event == "start":
                session_validated = _handle_start_event(message, stats, orchestrator)
                if not session_validated:
                    await websocket.close(code=1008)
                    return
                logger.info(
                    "twilio_media_start session_id=%s call_sid=%s stream_sid=%s",
                    stats.session_id,
                    stats.call_sid,
                    stats.stream_sid,
                )
                continue

            if event == "stop":
                stop = message.get("stop") or {}
                stats.stop_reason = stop.get("reason")
                break

            if event == "media":
                if not session_validated:
                    await websocket.close(code=1008)
                    return
                _handle_media_event(message, stats)
                continue

            if event in {"dtmf", "mark"}:
                logger.info(
                    "twilio_media_%s session_id=%s stream_sid=%s payload=%s",
                    event,
                    stats.session_id,
                    stats.stream_sid,
                    json.dumps(message.get(event) or {}, ensure_ascii=False),
                )
                continue

            logger.warning("twilio_media_unknown_event event=%s", event)
    except WebSocketDisconnect:
        return
    except (ValueError, json.JSONDecodeError):
        await websocket.close(code=1003)
        return
    finally:
        logger.info(
            "twilio_media_stop session_id=%s call_sid=%s stream_sid=%s "
            "frames=%s bytes=%s reason=%s",
            stats.session_id,
            stats.call_sid,
            stats.stream_sid,
            stats.media_frames,
            stats.media_bytes,
            stats.stop_reason,
        )
        try:
            await websocket.close()
        except RuntimeError:
            pass


def _first(form: dict[str, list[str]], key: str) -> str | None:
    values = form.get(key)
    return values[0] if values else None


def _build_stream_url(request: Request, settings: Settings) -> str:
    if settings.public_base_url:
        base = settings.public_base_url
    else:
        base = str(request.base_url).rstrip("/")

    if base.startswith("https://"):
        base = "wss://" + base.removeprefix("https://")
    elif base.startswith("http://"):
        base = "ws://" + base.removeprefix("http://")

    return f"{base}/twilio/media"


def _handle_start_event(
    message: dict,
    stats: TwilioMediaStreamStats,
    orchestrator: CallSessionOrchestrator,
) -> bool:
    start = message.get("start") or {}
    custom_parameters = start.get("customParameters") or {}
    session_id = custom_parameters.get("session_id")
    if not session_id:
        return False

    session = orchestrator.get_session(session_id)
    if session is None:
        return False

    stats.session_id = session_id
    stats.call_sid = start.get("callSid")
    stats.stream_sid = start.get("streamSid") or message.get("streamSid")
    return True


def _handle_media_event(message: dict, stats: TwilioMediaStreamStats) -> None:
    media = message.get("media") or {}
    payload = media.get("payload")
    if not payload:
        return
    audio = base64.b64decode(payload, validate=True)
    stats.media_frames += 1
    stats.media_bytes += len(audio)


def _validate_twilio_signature(
    request: Request,
    settings: Settings,
    form: dict[str, list[str]],
) -> None:
    if not settings.twilio_validate_signature:
        return
    if not settings.twilio_auth_token:
        raise HTTPException(status_code=500, detail="TWILIO_AUTH_TOKEN is required")

    try:
        from twilio.request_validator import RequestValidator
    except ImportError as exc:
        raise HTTPException(status_code=500, detail="twilio package is required") from exc

    signature = request.headers.get("X-Twilio-Signature")
    if not signature:
        raise HTTPException(status_code=403, detail="Missing Twilio signature")

    validator = RequestValidator(settings.twilio_auth_token)
    url = _public_request_url(request, settings)
    params = {key: values[0] if len(values) == 1 else values for key, values in form.items()}
    if not validator.validate(url, params, signature):
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")


def _public_request_url(request: Request, settings: Settings) -> str:
    if not settings.public_base_url:
        return str(request.url)
    url = settings.public_base_url.rstrip("/") + request.url.path
    if request.url.query:
        url += f"?{request.url.query}"
    return url
