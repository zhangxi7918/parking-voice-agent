from __future__ import annotations

import asyncio
import base64
import json
import logging
from dataclasses import dataclass

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from voice_agent.adapters.qwen.qwen_realtime_adapter import QwenRealtimeProvider
from voice_agent.app.call_session_orchestrator import CallSessionOrchestrator
from voice_agent.routes.dependencies import get_orchestrator, get_realtime_voice_provider


router = APIRouter(prefix="/browser-call", tags=["browser-call"])
logger = logging.getLogger(__name__)


class BrowserTurnRequest(BaseModel):
    session_id: str = Field(min_length=1)
    caller_text: str = Field(min_length=1)


@dataclass(slots=True)
class BrowserAudioStats:
    session_id: str | None = None
    media_frames: int = 0
    media_bytes: int = 0


@router.get("", response_class=HTMLResponse)
def browser_call_page() -> str:
    return _BROWSER_CALL_HTML


@router.post("/sessions")
def create_browser_call_session(
    orchestrator: CallSessionOrchestrator = Depends(get_orchestrator),
) -> dict:
    session = orchestrator.start_call(call_sid="browser")
    return {"session": session.to_dict()}


@router.post("/turn")
async def browser_call_turn(
    payload: BrowserTurnRequest,
    orchestrator: CallSessionOrchestrator = Depends(get_orchestrator),
) -> dict:
    result = await orchestrator.handle_caller_text(
        session_id=payload.session_id,
        caller_text=payload.caller_text,
    )
    return result.to_dict()


@router.websocket("/audio")
async def browser_audio_stream(
    websocket: WebSocket,
    orchestrator: CallSessionOrchestrator = Depends(get_orchestrator),
    provider: QwenRealtimeProvider | None = Depends(get_realtime_voice_provider),
) -> None:
    """Bidirectional audio bridge: browser PCM <-> Qwen-Omni-Realtime.

    Receives JSON messages from the browser:

    - ``{"event":"start","session_id":"..."}`` — validates the session and
      opens an upstream Qwen realtime connection.
    - ``{"event":"media","payload":"<base64>"}`` — relays 16 kHz PCM16 mono
      audio to Qwen.
    - ``{"event":"commit"}`` — signals end of caller utterance and triggers
      the model response.
    - ``{"event":"stop"}`` — tears down.

    Sends to the browser:

    - Binary WebSocket frames — model audio (PCM16, sample rate as returned
      by Qwen, typically 24 kHz).
    - ``{"event":"turn","role":"caller"|"agent","text":"..."}``
    - ``{"event":"ready"}`` / ``{"event":"error","error":"..."}``
    """
    await websocket.accept()

    if provider is None:
        await websocket.send_json({
            "event": "error",
            "error": "Qwen realtime provider not configured — set DASHSCOPE_API_KEY.",
        })
        await websocket.close()
        return

    qwen_session = None
    session_id: str | None = None
    stats = BrowserAudioStats()
    session_ready = asyncio.Event()
    stop = asyncio.Event()

    async def receive_from_browser() -> None:
        nonlocal qwen_session, session_id

        try:
            async for raw_message in websocket.iter_text():
                try:
                    message = json.loads(raw_message)
                except json.JSONDecodeError:
                    continue
                event = message.get("event")

                if event == "start":
                    session_id = message.get("session_id")
                    if not session_id or not orchestrator.get_session(session_id):
                        await websocket.send_json({
                            "event": "error",
                            "error": f"invalid session_id: {session_id}",
                        })
                        continue
                    qwen_session = await provider.open_session(session_id)
                    session_ready.set()
                    await websocket.send_json({"event": "ready"})
                    logger.info("browser_audio_start session_id=%s", session_id)

                elif event == "media":
                    if qwen_session is None:
                        continue
                    payload = message.get("payload", "")
                    if not payload:
                        continue
                    try:
                        audio = base64.b64decode(payload, validate=True)
                    except (ValueError, base64.binascii.Error):
                        continue
                    stats.media_frames += 1
                    stats.media_bytes += len(audio)
                    try:
                        await qwen_session.send_audio(audio)
                    except Exception:
                        logger.exception("qwen_send_audio_failed session_id=%s", session_id)
                        await websocket.send_json({
                            "event": "error",
                            "error": "Failed to send audio to Qwen.",
                        })

                elif event == "commit":
                    if qwen_session is None:
                        continue
                    try:
                        await qwen_session.commit_audio()
                        logger.info(
                            "browser_audio_commit session_id=%s frames=%s bytes=%s",
                            session_id,
                            stats.media_frames,
                            stats.media_bytes,
                        )
                        stats.media_frames = 0
                        stats.media_bytes = 0
                    except Exception:
                        logger.exception("qwen_commit_failed session_id=%s", session_id)

                elif event == "stop":
                    break

                else:
                    logger.warning("browser_audio_unknown_event event=%s", event)
        except WebSocketDisconnect:
            pass
        finally:
            stop.set()

    async def forward_qwen_events() -> None:
        await session_ready.wait()
        try:
            while not stop.is_set():
                try:
                    qwen_event = await asyncio.wait_for(
                        qwen_session.receive_event(), timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue

                if qwen_event.type == "audio":
                    if qwen_event.audio:
                        await websocket.send_bytes(qwen_event.audio)

                elif qwen_event.type == "input_transcription":
                    if qwen_event.text:
                        await websocket.send_json({
                            "event": "turn",
                            "role": "caller",
                            "text": qwen_event.text,
                        })
                        if session_id:
                            try:
                                await orchestrator.handle_caller_text(
                                    session_id=session_id,
                                    caller_text=qwen_event.text,
                                )
                            except Exception:
                                logger.exception(
                                    "intake_update_failed session_id=%s", session_id
                                )

                elif qwen_event.type == "output_transcription":
                    if qwen_event.text:
                        await websocket.send_json({
                            "event": "turn",
                            "role": "agent",
                            "text": qwen_event.text,
                        })

                elif qwen_event.type == "error":
                    logger.error(
                        "qwen_session_error session_id=%s error=%s",
                        session_id,
                        qwen_event.error,
                    )
                    await websocket.send_json({
                        "event": "error",
                        "error": qwen_event.error,
                    })
                    stop.set()
        except Exception:
            logger.exception("qwen_forward_error session_id=%s", session_id)
            try:
                await websocket.send_json({
                    "event": "error",
                    "error": "Qwen session error — please try again.",
                })
            except Exception:
                pass

    browser_task = asyncio.create_task(receive_from_browser())
    qwen_task = asyncio.create_task(forward_qwen_events())

    try:
        done, _pending = await asyncio.wait(
            [browser_task, qwen_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in done:
            if (exc := task.exception()) is not None:
                logger.exception("browser_audio_task_failed", exc_info=exc)
    finally:
        stop.set()
        for task in [browser_task, qwen_task]:
            if not task.done():
                task.cancel()
        if qwen_session:
            try:
                await qwen_session.close()
            except Exception:
                pass
        logger.info(
            "browser_audio_stop session_id=%s frames=%s bytes=%s",
            session_id,
            stats.media_frames,
            stats.media_bytes,
        )
        try:
            await websocket.close()
        except RuntimeError:
            pass


_BROWSER_CALL_HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>浏览器电话接入</title>
  <link rel="icon" href="data:,">
  <style>
    :root {
      color-scheme: light;
      --ink: #14120f;
      --muted: #6b645d;
      --line: #d9d0c5;
      --paper: #f7f3ed;
      --panel: #fffaf2;
      --green: #127a48;
      --red: #b73530;
      --blue: #215f91;
      --amber: #c47a10;
      font-family: "Avenir Next", "PingFang SC", "Hiragino Sans GB", sans-serif;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0; min-height: 100vh;
      background:
        linear-gradient(90deg, rgba(20,18,15,0.04) 1px, transparent 1px),
        linear-gradient(rgba(20,18,15,0.04) 1px, transparent 1px),
        var(--paper);
      background-size: 32px 32px;
      color: var(--ink);
    }
    main {
      width: min(1120px, calc(100vw - 32px));
      margin: 0 auto; padding: 36px 0;
    }
    header {
      display: flex; align-items: end; justify-content: space-between;
      gap: 20px; margin-bottom: 28px;
    }
    h1 {
      margin: 0; font-size: clamp(30px, 5vw, 58px);
      line-height: 0.98; letter-spacing: 0;
    }
    .subtitle {
      max-width: 520px; color: var(--muted);
      line-height: 1.7; margin: 12px 0 0;
    }
    .status-pill {
      min-width: 168px; border: 1px solid var(--line);
      background: var(--panel); padding: 10px 14px;
      font-weight: 700; text-align: center;
    }
    .layout {
      display: grid;
      grid-template-columns: minmax(0, 360px) minmax(0, 1fr);
      gap: 20px; align-items: start;
    }
    .panel {
      border: 1px solid var(--line);
      background: rgba(255,250,242,0.9);
      box-shadow: 8px 8px 0 rgba(20,18,15,0.1);
    }
    .controls { padding: 20px; }
    .button-row {
      display: grid; grid-template-columns: 1fr 1fr;
      gap: 12px; margin-bottom: 18px;
    }
    button {
      min-height: 52px; border: 1px solid var(--ink);
      color: var(--ink); background: #fff;
      font: inherit; font-weight: 800; cursor: pointer;
      transition: transform 120ms ease, box-shadow 120ms ease, opacity 120ms ease;
    }
    button:not(:disabled):hover {
      transform: translate(-2px, -2px);
      box-shadow: 4px 4px 0 rgba(20,18,15,0.18);
    }
    button:disabled { cursor: not-allowed; opacity: 0.48; }
    .answer { background: var(--green); color: white; border-color: #0c4f30; }
    .hangup { background: #fff; color: var(--red); border-color: var(--red); }
    .meter {
      height: 12px; border: 1px solid var(--line);
      background: #f0e8dc; overflow: hidden; margin: 8px 0 18px;
    }
    .meter > div {
      width: 0%; height: 100%; background: var(--green);
      transition: width 80ms linear;
    }
    .facts {
      display: grid; gap: 10px;
      color: var(--muted); font-size: 14px;
    }
    .fact {
      display: flex; justify-content: space-between; gap: 12px;
      border-bottom: 1px solid rgba(217,208,197,0.8); padding-bottom: 9px;
    }
    .fact strong { color: var(--ink); text-align: right; word-break: break-all; }
    .transcript { min-height: 560px; display: flex; flex-direction: column; }
    .transcript-head {
      display: flex; justify-content: space-between; gap: 12px;
      border-bottom: 1px solid var(--line); padding: 16px 18px;
      font-weight: 800;
    }
    .log {
      flex: 1; padding: 18px; overflow: auto;
      display: flex; flex-direction: column; gap: 12px; max-height: 620px;
    }
    .turn {
      max-width: 78%; border: 1px solid var(--line);
      padding: 12px 14px; line-height: 1.55; background: white;
    }
    .turn.agent { align-self: flex-start; border-left: 5px solid var(--blue); }
    .turn.caller { align-self: flex-end; border-right: 5px solid var(--green); background: #f5fff8; }
    .turn.system { align-self: center; max-width: 92%; color: var(--muted); background: #fff7e8; border-color: #e6c17d; }
    .role { display: block; font-size: 12px; color: var(--muted); margin-bottom: 4px; font-weight: 800; }
    .draft {
      border-top: 1px solid var(--line); padding: 14px 18px;
      color: var(--muted); min-height: 54px; line-height: 1.55;
      background: rgba(255,255,255,0.55);
    }
    .draft.listening { color: var(--green); font-weight: 700; }
    .warn { color: var(--amber); font-weight: 800; }
    @media (max-width: 820px) {
      header, .layout { display: block; }
      .status-pill { margin-top: 18px; }
      .panel + .panel { margin-top: 18px; }
      .turn { max-width: 94%; }
    }
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>浏览器电话接入</h1>
        <p class="subtitle">基于 Qwen-Omni-Realtime 的端到端语音对话，浏览器仅做音频桥接。</p>
      </div>
      <div id="status" class="status-pill">未接入</div>
    </header>

    <section class="layout">
      <aside class="panel controls">
        <div class="button-row">
          <button id="answerButton" class="answer">接入</button>
          <button id="hangupButton" class="hangup" disabled>挂断</button>
        </div>
        <div class="meter" aria-label="麦克风输入电平"><div id="level"></div></div>
        <div class="facts">
          <div class="fact"><span>Session</span><strong id="sessionId">-</strong></div>
          <div class="fact"><span>状态</span><strong id="audioState">待连接</strong></div>
          <div class="fact"><span>PCM 帧</span><strong id="frameCount">0</strong></div>
          <div class="fact"><span>PCM 字节</span><strong id="byteCount">0</strong></div>
        </div>
      </aside>

      <section class="panel transcript">
        <div class="transcript-head">
          <span>通话记录</span>
          <span id="supportHint"></span>
        </div>
        <div id="log" class="log"></div>
        <div id="draft" class="draft">点击接入后，允许麦克风权限并开始说话。</div>
      </section>
    </section>
  </main>

  <script>
    const elements = {
      answerButton: document.getElementById("answerButton"),
      hangupButton: document.getElementById("hangupButton"),
      status: document.getElementById("status"),
      sessionId: document.getElementById("sessionId"),
      audioState: document.getElementById("audioState"),
      frameCount: document.getElementById("frameCount"),
      byteCount: document.getElementById("byteCount"),
      level: document.getElementById("level"),
      log: document.getElementById("log"),
      draft: document.getElementById("draft"),
      supportHint: document.getElementById("supportHint"),
    };

    const state = {
      active: false,
      sessionId: null,
      audioContext: null,
      mediaStream: null,
      mediaSource: null,
      workletNode: null,
      audioSocket: null,
      frames: 0,
      bytes: 0,
      playbackContext: null,
      nextPlayTime: 0,
    };

    // ── VAD ──────────────────────────────────────────────────────────

    const VAD = {
      speechActive: false,
      silenceStart: null,
      silenceThreshold: 0.03,
      silenceDurationMs: 800,
      waitingForResponse: true, // start true — wait for first Qwen greeting
    };

    // ── helpers ──────────────────────────────────────────────────────

    function computeRMS(samples) {
      let sum = 0;
      for (let i = 0; i < samples.length; i++) {
        sum += samples[i] * samples[i];
      }
      return Math.sqrt(sum / samples.length) / 32768;
    }

    function bufferToBase64(buffer) {
      const bytes = new Uint8Array(buffer);
      let binary = "";
      const chunkSize = 0x8000;
      for (let offset = 0; offset < bytes.length; offset += chunkSize) {
        binary += String.fromCharCode.apply(null, bytes.subarray(offset, offset + chunkSize));
      }
      return btoa(binary);
    }

    // ── UI helpers ───────────────────────────────────────────────────

    function addTurn(role, text) {
      const node = document.createElement("div");
      node.className = `turn ${role}`;
      const label = role === "agent" ? "门岗" : role === "caller" ? "访客" : "系统";
      node.innerHTML = `<span class="role">${label}</span>${escapeHtml(text)}`;
      elements.log.appendChild(node);
      elements.log.scrollTop = elements.log.scrollHeight;
    }

    function setStatus(text) {
      elements.status.textContent = text;
    }

    function escapeHtml(value) {
      return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
    }

    function updateAudioStats() {
      elements.frameCount.textContent = String(state.frames);
      elements.byteCount.textContent = String(state.bytes);
    }

    // ── Audio playback ───────────────────────────────────────────────

    function ensurePlaybackContext() {
      if (state.playbackContext) return;
      state.playbackContext = new AudioContext({ sampleRate: 24000 });
      state.nextPlayTime = state.playbackContext.currentTime;
    }

    function playAudioBuffer(pcmBytes) {
      ensurePlaybackContext();
      const ctx = state.playbackContext;
      const pcm16 = new Int16Array(pcmBytes);
      const float32 = new Float32Array(pcm16.length);
      for (let i = 0; i < pcm16.length; i++) {
        float32[i] = pcm16[i] / 32768;
      }
      const audioBuffer = ctx.createBuffer(1, float32.length, ctx.sampleRate);
      audioBuffer.getChannelData(0).set(float32);

      const source = ctx.createBufferSource();
      source.buffer = audioBuffer;
      source.connect(ctx.destination);

      const now = ctx.currentTime;
      if (state.nextPlayTime < now) {
        state.nextPlayTime = now;
      }
      source.start(state.nextPlayTime);
      state.nextPlayTime += audioBuffer.duration;

      // Reset if queue grows too long (>2s) to avoid accumulating delay.
      if (state.nextPlayTime - now > 2) {
        state.nextPlayTime = now;
      }
    }

    function interruptPlayback() {
      if (state.playbackContext) {
        state.playbackContext.close();
        state.playbackContext = null;
      }
      state.nextPlayTime = 0;
    }

    // ── Audio capture (AudioWorklet) ─────────────────────────────────

    async function startAudioCapture() {
      if (!navigator.mediaDevices?.getUserMedia) {
        elements.audioState.textContent = "不支持麦克风";
        return;
      }

      state.audioSocket = openAudioSocket();
      state.mediaStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });

      state.audioContext = new AudioContext();
      const workletUrl = URL.createObjectURL(
        new Blob([audioWorkletSource()], { type: "text/javascript" })
      );
      await state.audioContext.audioWorklet.addModule(workletUrl);
      URL.revokeObjectURL(workletUrl);

      state.mediaSource = state.audioContext.createMediaStreamSource(state.mediaStream);
      state.workletNode = new AudioWorkletNode(state.audioContext, "pcm-capture-processor");
      state.workletNode.port.onmessage = (event) => {
        const pcmBuffer = event.data;
        state.frames += 1;
        state.bytes += pcmBuffer.byteLength;
        updateLevel(new Int16Array(pcmBuffer));
        updateAudioStats();

        if (state.audioSocket?.readyState !== WebSocket.OPEN) return;

        // VAD: skip sending audio while waiting for Qwen response
        if (VAD.waitingForResponse) return;

        state.audioSocket.send(JSON.stringify({
          event: "media",
          payload: bufferToBase64(pcmBuffer),
        }));

        // VAD logic
        const samples = new Int16Array(pcmBuffer);
        const rms = computeRMS(samples);
        if (rms > VAD.silenceThreshold) {
          if (!VAD.speechActive) {
            VAD.speechActive = true;
            elements.draft.textContent = "正在听您说话...";
            elements.draft.className = "draft listening";
          }
          VAD.silenceStart = null;
        } else if (VAD.speechActive) {
          if (!VAD.silenceStart) VAD.silenceStart = Date.now();
          if (Date.now() - VAD.silenceStart > VAD.silenceDurationMs) {
            // Silence detected — commit the turn
            VAD.speechActive = false;
            VAD.silenceStart = null;
            VAD.waitingForResponse = true;
            elements.draft.textContent = "正在等待门岗回复...";
            elements.draft.className = "draft";
            state.audioSocket.send(JSON.stringify({ event: "commit" }));
          }
        }
      };
      state.mediaSource.connect(state.workletNode);
      // Don't connect workletNode to destination — we don't echo mic to speaker.
    }

    function stopAudioCapture() {
      if (state.workletNode) {
        state.workletNode.port.onmessage = null;
        state.workletNode.disconnect();
        state.workletNode = null;
      }
      if (state.mediaSource) {
        state.mediaSource.disconnect();
        state.mediaSource = null;
      }
      if (state.mediaStream) {
        for (const track of state.mediaStream.getTracks()) track.stop();
        state.mediaStream = null;
      }
      if (state.audioContext) {
        state.audioContext.close();
        state.audioContext = null;
      }
      if (state.audioSocket && state.audioSocket.readyState === WebSocket.OPEN) {
        state.audioSocket.send(JSON.stringify({ event: "stop", stop: { reason: "user-hangup" } }));
        state.audioSocket.close();
      }
      state.audioSocket = null;
      elements.level.style.width = "0%";
      interruptPlayback();
    }

    function updateLevel(samples) {
      if (!samples.length) return;
      let peak = 0;
      for (const sample of samples) {
        peak = Math.max(peak, Math.abs(sample));
      }
      const percent = Math.min(100, Math.round((peak / 32768) * 100));
      elements.level.style.width = `${percent}%`;
    }

    // ── WebSocket ────────────────────────────────────────────────────

    function openAudioSocket() {
      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      const socket = new WebSocket(`${protocol}//${window.location.host}/browser-call/audio`);
      socket.binaryType = "arraybuffer";

      socket.onopen = () => {
        elements.audioState.textContent = "已连接";
        socket.send(JSON.stringify({
          event: "start",
          session_id: state.sessionId,
        }));
      };

      socket.onmessage = (event) => {
        // Binary audio frame from Qwen
        if (event.data instanceof ArrayBuffer) {
          playAudioBuffer(event.data);
          return;
        }
        // JSON event
        let msg;
        try { msg = JSON.parse(event.data); } catch { return; }
        switch (msg.event) {
          case "ready":
            elements.audioState.textContent = "Qwen 已就绪";
            // Qwen will speak the greeting — start VAD after a short delay
            setTimeout(() => {
              if (!state.active) return;
              VAD.waitingForResponse = false;
              VAD.speechActive = false;
              elements.draft.textContent = "正在等待访客说话。";
            }, 2500);
            break;
          case "turn":
            addTurn(msg.role, msg.text);
            if (msg.role === "agent") {
              elements.draft.textContent = "门岗: " + msg.text;
              elements.draft.className = "draft";
              // Resume VAD after agent finishes speaking
              setTimeout(() => {
                if (state.active && VAD.waitingForResponse) {
                  VAD.waitingForResponse = false;
                  VAD.speechActive = false;
                  elements.draft.textContent = "正在等待访客说话。";
                  elements.draft.className = "draft";
                }
              }, 2000);
            }
            break;
          case "error":
            addTurn("system", msg.error);
            elements.audioState.textContent = "错误";
            VAD.waitingForResponse = false;
            elements.draft.textContent = "发生错误，请重试。";
            elements.draft.className = "draft";
            break;
        }
      };

      socket.onclose = () => {
        elements.audioState.textContent = state.active ? "已断开" : "已停止";
      };

      socket.onerror = () => {
        elements.audioState.textContent = "连接错误";
      };

      return socket;
    }

    // ── Call flow ────────────────────────────────────────────────────

    elements.answerButton.addEventListener("click", startCall);
    elements.hangupButton.addEventListener("click", () => endCall("user-hangup"));

    async function startCall() {
      setStatus("接入中");
      elements.answerButton.disabled = true;
      elements.hangupButton.disabled = false;
      state.active = true;
      state.frames = 0;
      state.bytes = 0;
      VAD.speechActive = false;
      VAD.silenceStart = null;
      VAD.waitingForResponse = true;
      updateAudioStats();

      try {
        const response = await fetch("/browser-call/sessions", { method: "POST" });
        if (!response.ok) throw new Error(`创建会话失败：${response.status}`);
        const payload = await response.json();
        state.sessionId = payload.session.id;
        elements.sessionId.textContent = state.sessionId;

        await startAudioCapture();
        // The WebSocket "start" event triggers Qwen session creation.
        // Qwen speaks the greeting, browser plays it via binary audio frames.
        setStatus("通话中");
      } catch (error) {
        addTurn("system", error.message || String(error));
        await endCall("startup-error");
      }
    }

    async function endCall(reason) {
      if (!state.active && !state.sessionId) return;
      state.active = false;
      setStatus("已挂断");
      elements.answerButton.disabled = false;
      elements.hangupButton.disabled = true;
      elements.draft.textContent = "通话已结束。";
      elements.draft.className = "draft";

      interruptPlayback();
      stopAudioCapture();
      elements.audioState.textContent = "已停止";
    }

    // ── AudioWorklet processor source ────────────────────────────────

    function audioWorkletSource() {
      return `
        class PcmCaptureProcessor extends AudioWorkletProcessor {
          process(inputs) {
            const input = inputs[0] && inputs[0][0];
            if (!input) return true;
            const downsampled = this.downsample(input, sampleRate, 16000);
            const pcm = this.floatToInt16(downsampled);
            this.port.postMessage(pcm.buffer, [pcm.buffer]);
            return true;
          }

          downsample(input, inputRate, outputRate) {
            if (inputRate === outputRate) return input;
            const ratio = inputRate / outputRate;
            const outputLength = Math.max(1, Math.floor(input.length / ratio));
            const output = new Float32Array(outputLength);
            for (let index = 0; index < outputLength; index += 1) {
              const start = Math.floor(index * ratio);
              const end = Math.min(input.length, Math.floor((index + 1) * ratio));
              let sum = 0;
              let count = 0;
              for (let cursor = start; cursor < end; cursor += 1) {
                sum += input[cursor];
                count += 1;
              }
              output[index] = count ? sum / count : 0;
            }
            return output;
          }

          floatToInt16(input) {
            const output = new Int16Array(input.length);
            for (let index = 0; index < input.length; index += 1) {
              const sample = Math.max(-1, Math.min(1, input[index]));
              output[index] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
            }
            return output;
          }
        }

        registerProcessor("pcm-capture-processor", PcmCaptureProcessor);
      `;
    }
  </script>
</body>
</html>
"""