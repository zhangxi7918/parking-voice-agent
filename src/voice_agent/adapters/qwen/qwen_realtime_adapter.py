from __future__ import annotations

import asyncio
import base64
import json
import logging
import uuid
from dataclasses import dataclass

import websockets

from voice_agent.ports.realtime_voice import RealtimeVoiceEvent, RealtimeVoiceProvider, RealtimeVoiceSession

logger = logging.getLogger(__name__)

_REALTIME_BASE_URL = "wss://dashscope.aliyuncs.com/api-ws/v1/realtime"


@dataclass(slots=True)
class QwenRealtimeConfig:
    api_key: str
    model: str
    instructions: str = ""


class QwenRealtimeSession:
    """A DashScope Qwen-Omni-Realtime WebSocket session.

    Lazily connects on first *send_audio* or *commit_audio* call so that
    invalid session ids are rejected before opening an upstream connection.
    """

    def __init__(self, session_id: str, config: QwenRealtimeConfig) -> None:
        self._session_id = session_id
        self._config = config
        self._ws: websockets.ClientConnection | None = None
        self._event_queue: asyncio.Queue[RealtimeVoiceEvent] = asyncio.Queue()
        self._receive_task: asyncio.Task[None] | None = None
        self._connected = False
        self._pending_output_text = ""
        self._output_text_sent = False

    # ── public API ──────────────────────────────────────────────────────

    async def send_audio(self, audio: bytes) -> None:
        """Encode *audio* as base64 and append it to the Qwen input buffer."""
        await self._ensure_connected()
        payload = base64.b64encode(audio).decode("ascii")
        await self._ws.send(json.dumps({
            "event_id": _event_id(),
            "type": "input_audio_buffer.append",
            "audio": payload,
        }))

    async def commit_audio(self) -> None:
        """Signal end of caller audio and request a model response."""
        await self._ensure_connected()
        await self._ws.send(json.dumps({
            "event_id": _event_id(),
            "type": "input_audio_buffer.commit",
        }))
        await self._ws.send(json.dumps({
            "event_id": _event_id(),
            "type": "response.create",
        }))
        self._output_text_sent = False
        self._pending_output_text = ""

    async def receive_event(self) -> RealtimeVoiceEvent:
        """Block until the next domain event arrives from Qwen."""
        return await self._event_queue.get()

    async def clear_audio(self) -> None:
        """Clear the input audio buffer between turns."""
        await self._ensure_connected()
        await self._ws.send(json.dumps({
            "event_id": _event_id(),
            "type": "input_audio_buffer.clear",
        }))

    async def close(self) -> None:
        """Tear down the upstream WebSocket and background reader."""
        self._connected = False
        if self._receive_task is not None:
            self._receive_task.cancel()
            self._receive_task = None
        if self._ws is not None:
            await self._ws.close()
            self._ws = None
        # Unblock any waiter on receive_event().
        try:
            self._event_queue.put_nowait(
                RealtimeVoiceEvent(type="error", error="session closed")
            )
        except asyncio.QueueFull:
            pass

    # ── internals ───────────────────────────────────────────────────────

    async def _ensure_connected(self) -> None:
        if self._connected:
            return
        url = f"{_REALTIME_BASE_URL}?model={self._config.model}"
        self._ws = await websockets.connect(
            url,
            additional_headers={"Authorization": f"Bearer {self._config.api_key}"},
        )
        # Send session configuration.
        await self._ws.send(json.dumps({
            "event_id": _event_id(),
            "type": "session.update",
            "session": {
                "modalities": ["text", "audio"],
                "input_audio_format": "pcm",
                "output_audio_format": "pcm",
                "input_audio_transcription": {
                    "model": "qwen3-asr-flash-realtime",
                },
                "turn_detection": None,
                "instructions": self._config.instructions,
            },
        }))
        # Consume handshake events (session.created, session.updated).
        await self._consume_until_ready()
        self._receive_task = asyncio.create_task(self._receive_loop())
        self._connected = True
        logger.info(
            "qwen_session_connected session_id=%s model=%s",
            self._session_id,
            self._config.model,
        )

    async def _consume_until_ready(self) -> None:
        """Discard handshake messages until *session.updated* is received."""
        for _ in range(10):  # safety limit
            raw = await asyncio.wait_for(self._ws.recv(), timeout=10)
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if msg.get("type") == "session.updated":
                return
        raise RuntimeError("Qwen session handshake did not complete in time")

    async def _receive_loop(self) -> None:
        """Background task: read upstream messages and push domain events."""
        try:
            async for raw in self._ws:
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                self._dispatch(msg)
        except websockets.ConnectionClosed as exc:
            logger.warning("qwen_ws_closed session_id=%s code=%s", self._session_id, exc.code)
            try:
                self._event_queue.put_nowait(
                    RealtimeVoiceEvent(type="error", error="Qwen WebSocket disconnected")
                )
            except asyncio.QueueFull:
                pass
        except Exception:
            logger.exception("qwen_receive_loop_unexpected_error session_id=%s", self._session_id)
            try:
                self._event_queue.put_nowait(
                    RealtimeVoiceEvent(type="error", error="Qwen receive loop crashed")
                )
            except asyncio.QueueFull:
                pass

    def _dispatch(self, msg: dict) -> None:
        msg_type = msg.get("type", "")

        # ── audio output ────────────────────────────────────────────
        if msg_type == "response.audio.delta":
            delta = msg.get("delta", "")
            if delta:
                try:
                    audio = base64.b64decode(delta)
                    self._event_queue.put_nowait(
                        RealtimeVoiceEvent(type="audio", audio=audio)
                    )
                except Exception:
                    logger.debug("qwen_audio_decode_failed session_id=%s", self._session_id)

        # ── agent text transcription (from audio modality) ──────────
        elif msg_type == "response.audio_transcript.delta":
            delta = msg.get("delta", "")
            self._pending_output_text += delta

        # ── input transcription (caller speech) ─────────────────────
        elif msg_type == "conversation.item.input_audio_transcription.completed":
            transcript = msg.get("transcript", "")
            if transcript.strip():
                self._event_queue.put_nowait(
                    RealtimeVoiceEvent(type="input_transcription", text=transcript.strip())
                )

        # ── output transcription (model speech) ─────────────────────
        elif msg_type == "response.text.delta":
            delta = msg.get("delta", "")
            self._pending_output_text += delta

        elif msg_type == "response.done":
            if self._pending_output_text.strip() and not self._output_text_sent:
                self._output_text_sent = True
                self._event_queue.put_nowait(
                    RealtimeVoiceEvent(
                        type="output_transcription",
                        text=self._pending_output_text.strip(),
                    )
                )
                self._pending_output_text = ""

        # ── error ───────────────────────────────────────────────────
        elif msg_type == "error":
            error_body = msg.get("error", {})
            error_msg = error_body.get("message", "Unknown Qwen error")
            self._event_queue.put_nowait(
                RealtimeVoiceEvent(type="error", error=error_msg)
            )

        # ── lifecycle (logged for observability) ────────────────────
        elif msg_type in {
            "session.created",
            "session.updated",
            "response.created",
            "response.content_part.added",
            "response.content_part.done",
            "response.output_item.added",
            "response.output_item.done",
            "response.audio.done",
            "response.audio_transcript.done",
            "conversation.item.created",
            "input_audio_buffer.committed",
            "input_audio_buffer.cleared",
            "conversation.item.input_audio_transcription.delta",
        }:
            pass  # silently consumed

        else:
            logger.debug("qwen_unknown_event session_id=%s type=%s", self._session_id, msg_type)


class QwenRealtimeProvider(RealtimeVoiceProvider):
    """Creates a :class:`QwenRealtimeSession` for every call."""

    def __init__(self, config: QwenRealtimeConfig) -> None:
        self._config = config

    async def open_session(self, session_id: str) -> QwenRealtimeSession:
        return QwenRealtimeSession(session_id=session_id, config=self._config)


def _event_id() -> str:
    return f"evt_{uuid.uuid4().hex[:12]}"
