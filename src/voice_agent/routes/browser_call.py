from __future__ import annotations

import json
import uuid
from dataclasses import dataclass

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from livekit.api import AccessToken, RoomAgentDispatch, RoomConfiguration, VideoGrants

from voice_agent.app.call_session_orchestrator import CallSessionOrchestrator
from voice_agent.config import Settings
from voice_agent.routes.dependencies import get_orchestrator, get_settings


router = APIRouter(prefix="/browser-call", tags=["browser-call"])


@dataclass(frozen=True, slots=True)
class BrowserLiveKitSession:
    room_name: str
    participant_identity: str
    token: str


@router.get("", response_class=HTMLResponse)
def browser_call_page() -> str:
    return _BROWSER_CALL_HTML


@router.post("/sessions")
def create_browser_call_session(
    orchestrator: CallSessionOrchestrator = Depends(get_orchestrator),
    settings: Settings = Depends(get_settings),
) -> dict:
    _ensure_livekit_configured(settings)
    session = orchestrator.start_call(call_sid="browser")
    livekit_session = _create_livekit_session(settings=settings, session_id=session.id)
    return {
        "session": session.to_dict(),
        "room_name": livekit_session.room_name,
        "participant_identity": livekit_session.participant_identity,
        "livekit_url": settings.livekit_url,
        "token": livekit_session.token,
    }


def _ensure_livekit_configured(settings: Settings) -> None:
    missing = [
        name
        for name, value in {
            "LIVEKIT_URL": settings.livekit_url,
            "LIVEKIT_API_KEY": settings.livekit_api_key,
            "LIVEKIT_API_SECRET": settings.livekit_api_secret,
        }.items()
        if not value
    ]
    if missing:
        raise HTTPException(
            status_code=500,
            detail=f"LiveKit is not configured: {', '.join(missing)}",
        )


def _create_livekit_session(settings: Settings, session_id: str) -> BrowserLiveKitSession:
    room_name = f"parking-{uuid.uuid4().hex[:12]}"
    participant_identity = f"browser-{uuid.uuid4().hex[:12]}"
    agent_metadata = json.dumps({"session_id": session_id}, ensure_ascii=False)
    token = (
        AccessToken(settings.livekit_api_key, settings.livekit_api_secret)
        .with_identity(participant_identity)
        .with_grants(VideoGrants(room_join=True, room=room_name))
        .with_room_config(
            RoomConfiguration(
                agents=[
                    RoomAgentDispatch(
                        agent_name=settings.livekit_agent_name,
                        metadata=agent_metadata,
                    )
                ],
            )
        )
        .to_jwt()
    )
    return BrowserLiveKitSession(
        room_name=room_name,
        participant_identity=participant_identity,
        token=token,
    )


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
      max-width: 560px; color: var(--muted);
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
    .warn { color: var(--amber); font-weight: 800; }
    #remoteAudio { display: none; }
    @media (max-width: 820px) {
      header, .layout { display: block; }
      .status-pill { margin-top: 18px; }
      .panel + .panel { margin-top: 18px; }
      .turn { max-width: 94%; }
    }
  </style>
  <script src="https://cdn.jsdelivr.net/npm/livekit-client/dist/livekit-client.umd.min.js"></script>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>浏览器电话接入</h1>
        <p class="subtitle">基于 LiveKit WebRTC 房间的门岗语音链路，浏览器只负责麦克风接入和远端音频播放。</p>
      </div>
      <div id="status" class="status-pill">未接入</div>
    </header>

    <section class="layout">
      <aside class="panel controls">
        <div class="button-row">
          <button id="answerButton" class="answer">接入</button>
          <button id="hangupButton" class="hangup" disabled>挂断</button>
        </div>
        <div class="facts">
          <div class="fact"><span>Session</span><strong id="sessionId">-</strong></div>
          <div class="fact"><span>Room</span><strong id="roomName">-</strong></div>
          <div class="fact"><span>身份</span><strong id="identity">-</strong></div>
          <div class="fact"><span>状态</span><strong id="audioState">待连接</strong></div>
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
    <div id="remoteAudio"></div>
  </main>

  <script>
    const elements = {
      answerButton: document.getElementById("answerButton"),
      hangupButton: document.getElementById("hangupButton"),
      status: document.getElementById("status"),
      sessionId: document.getElementById("sessionId"),
      roomName: document.getElementById("roomName"),
      identity: document.getElementById("identity"),
      audioState: document.getElementById("audioState"),
      log: document.getElementById("log"),
      draft: document.getElementById("draft"),
      supportHint: document.getElementById("supportHint"),
      remoteAudio: document.getElementById("remoteAudio"),
    };

    const state = {
      room: null,
      active: false,
      sessionId: null,
    };

    const LK = window.LivekitClient || window.livekitClient;
    if (!LK) {
      elements.supportHint.innerHTML = '<span class="warn">LiveKit SDK 加载失败</span>';
      elements.answerButton.disabled = true;
    }

    elements.answerButton.addEventListener("click", startCall);
    elements.hangupButton.addEventListener("click", endCall);

    async function startCall() {
      setStatus("接入中");
      elements.answerButton.disabled = true;
      elements.hangupButton.disabled = false;
      state.active = true;

      try {
        const response = await fetch("/browser-call/sessions", { method: "POST" });
        if (!response.ok) throw new Error(`创建会话失败：${response.status}`);
        const payload = await response.json();
        state.sessionId = payload.session.id;
        elements.sessionId.textContent = state.sessionId;
        elements.roomName.textContent = payload.room_name;
        elements.identity.textContent = payload.participant_identity;

        await connectLiveKit(payload.livekit_url, payload.token);
        addTurn("system", "已接入 LiveKit 房间。");
        setStatus("通话中");
        elements.draft.textContent = "正在等待门岗问候。";
      } catch (error) {
        addTurn("system", error.message || String(error));
        await endCall();
      }
    }

    async function connectLiveKit(url, token) {
      const room = new LK.Room({ adaptiveStream: true, dynacast: true });
      state.room = room;

      room.on(LK.RoomEvent.TrackSubscribed, (track) => {
        if (track.kind !== LK.Track.Kind.Audio) return;
        const audio = track.attach();
        audio.autoplay = true;
        elements.remoteAudio.appendChild(audio);
      });

      room.on(LK.RoomEvent.TrackUnsubscribed, (track) => {
        track.detach().forEach((element) => element.remove());
      });

      room.on(LK.RoomEvent.Disconnected, () => {
        elements.audioState.textContent = "已断开";
      });

      if (LK.RoomEvent.TranscriptionReceived) {
        room.on(LK.RoomEvent.TranscriptionReceived, (segments, participant) => {
          for (const segment of segments || []) {
            if (!segment.final) continue;
            const role = participant?.isAgent ? "agent" : "caller";
            addTurn(role, segment.text || segment.finalText || "");
          }
        });
      }

      await room.connect(url, token);
      elements.audioState.textContent = "已连接";
      await room.localParticipant.setMicrophoneEnabled(true);
      elements.audioState.textContent = "麦克风已开启";
    }

    async function endCall() {
      state.active = false;
      if (state.room) {
        state.room.disconnect();
        state.room = null;
      }
      elements.remoteAudio.replaceChildren();
      setStatus("已挂断");
      elements.answerButton.disabled = false;
      elements.hangupButton.disabled = true;
      elements.audioState.textContent = "已停止";
      elements.draft.textContent = "通话已结束。";
    }

    function addTurn(role, text) {
      if (!text) return;
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
  </script>
</body>
</html>
"""
