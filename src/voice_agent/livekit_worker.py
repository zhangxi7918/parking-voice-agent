from __future__ import annotations

import asyncio
import base64
import json
import logging
import warnings
from typing import Any, cast

import httpx
from livekit import rtc
from livekit import agents
from livekit.agents import (
    APIConnectionError,
    APIConnectOptions,
    APIStatusError,
    APITimeoutError,
    Agent,
    AgentServer,
    AgentSession,
    JobProcess,
    TurnHandlingOptions,
    stt,
)
from livekit.agents.types import NOT_GIVEN, NotGivenOr
from openai import APIStatusError as OpenAIAPIStatusError
from openai import APITimeoutError as OpenAIAPITimeoutError
from openai import AsyncClient

from voice_agent.app.bootstrap import create_orchestrator
from voice_agent.app.call_session_orchestrator import CallSessionOrchestrator
from voice_agent.config import Settings
from voice_agent.prompts.gatekeeper_system_prompt import GATEKEEPER_SYSTEM_PROMPT

warnings.filterwarnings(
    "ignore",
    message=r"livekit-plugins-silero is deprecated.*",
    category=DeprecationWarning,
)
warnings.filterwarnings(
    "ignore",
    message=r"`livekit.plugins.turn_detector` is deprecated.*",
    category=DeprecationWarning,
)

from livekit.plugins import elevenlabs, openai, silero  # noqa: E402
from livekit.plugins.turn_detector.multilingual import MultilingualModel  # noqa: E402


logger = logging.getLogger(__name__)


class GatekeeperAgent(Agent):
    def __init__(self) -> None:
        super().__init__(instructions=GATEKEEPER_SYSTEM_PROMPT)


class DashScopeQwenAsrSTT(stt.STT):
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        language: str = "zh",
    ) -> None:
        super().__init__(
            capabilities=stt.STTCapabilities(
                streaming=False,
                interim_results=False,
                aligned_transcript=False,
            )
        )
        self._client = AsyncClient(api_key=api_key, base_url=base_url, max_retries=0)
        self._model = model
        self._language = language

    @property
    def model(self) -> str:
        return self._model

    @property
    def provider(self) -> str:
        return "dashscope"

    async def _recognize_impl(
        self,
        buffer: stt.AudioBuffer,
        *,
        language: NotGivenOr[str] = NOT_GIVEN,
        conn_options: APIConnectOptions,
    ) -> stt.SpeechEvent:
        audio_data = rtc.combine_audio_frames(buffer).to_wav_bytes()
        data_uri = "data:audio/wav;base64," + base64.b64encode(audio_data).decode("ascii")
        request_language = language if isinstance(language, str) else self._language

        try:
            completion = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_audio",
                                "input_audio": {"data": data_uri},
                            }
                        ],
                    }
                ],
                stream=False,
                timeout=httpx.Timeout(30, connect=conn_options.timeout),
                extra_body={
                    "asr_options": {
                        "language": request_language,
                        "enable_itn": False,
                    }
                },
            )
        except OpenAIAPITimeoutError:
            raise APITimeoutError() from None
        except OpenAIAPIStatusError as exc:
            raise APIStatusError(
                exc.message,
                status_code=exc.status_code,
                request_id=exc.request_id,
                body=exc.body,
            ) from exc
        except Exception as exc:
            raise APIConnectionError(str(exc)) from exc

        text = self._completion_text(completion)
        speech_data = stt.SpeechData(text=text, language=request_language)
        return stt.SpeechEvent(
            type=stt.SpeechEventType.FINAL_TRANSCRIPT,
            alternatives=[speech_data],
        )

    async def aclose(self) -> None:
        await self._client.close()

    @staticmethod
    def _completion_text(completion: Any) -> str:
        if not completion.choices:
            return ""

        content = completion.choices[0].message.content
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            text_parts: list[str] = []
            for item in content:
                if isinstance(item, dict) and isinstance(item.get("text"), str):
                    text_parts.append(item["text"])
                elif hasattr(item, "text") and isinstance(item.text, str):
                    text_parts.append(item.text)
            return "".join(text_parts).strip()
        return str(content or "").strip()


def setup_job_process(proc: JobProcess) -> None:
    settings = Settings.from_env()
    proc.userdata["settings"] = settings
    proc.userdata["orchestrator"] = create_orchestrator(settings)


def process_settings(proc: JobProcess) -> Settings:
    settings = proc.userdata.get("settings")
    if isinstance(settings, Settings):
        return settings

    # Some test and thread modes may call the entrypoint without running setup first.
    settings = Settings.from_env()
    proc.userdata["settings"] = settings
    return settings


def process_orchestrator(proc: JobProcess) -> CallSessionOrchestrator:
    orchestrator = proc.userdata.get("orchestrator")
    if orchestrator is not None:
        return cast(CallSessionOrchestrator, orchestrator)

    settings = process_settings(proc)
    orchestrator = create_orchestrator(settings)
    proc.userdata["orchestrator"] = orchestrator
    return orchestrator


def create_agent_session(settings: Settings) -> AgentSession:
    stt_plugin = create_stt(settings)
    llm_kwargs: dict[str, Any] = {
        "model": "qwen-plus"
        if settings.voice_agent_ai_provider == "dashscope"
        else "gpt-4o-mini"
    }
    tts_kwargs: dict[str, Any] = {}

    if settings.voice_agent_ai_provider == "dashscope":
        if not settings.dashscope_api_key:
            raise ValueError("DASHSCOPE_API_KEY is required when VOICE_AGENT_AI_PROVIDER=dashscope")
        llm_kwargs["api_key"] = settings.dashscope_api_key
        llm_kwargs["base_url"] = settings.dashscope_base_url
        llm_kwargs["model"] = settings.dashscope_llm_model
    elif settings.openai_api_key:
        llm_kwargs["api_key"] = settings.openai_api_key

    if settings.elevenlabs_api_key:
        tts_kwargs["api_key"] = settings.elevenlabs_api_key
    if settings.elevenlabs_voice_id:
        tts_kwargs["voice_id"] = settings.elevenlabs_voice_id

    return AgentSession(
        vad=silero.VAD.load(),
        stt=stt_plugin,
        llm=openai.LLM(**llm_kwargs),
        tts=elevenlabs.TTS(**tts_kwargs),
        turn_handling=TurnHandlingOptions(
            turn_detection=MultilingualModel(),
        ),
    )


def create_stt(settings: Settings) -> stt.STT:
    if settings.voice_agent_ai_provider == "dashscope":
        if not settings.dashscope_api_key:
            raise ValueError("DASHSCOPE_API_KEY is required when VOICE_AGENT_AI_PROVIDER=dashscope")
        return DashScopeQwenAsrSTT(
            api_key=settings.dashscope_api_key,
            base_url=settings.dashscope_base_url,
            model=settings.dashscope_asr_model,
        )

    stt_kwargs: dict[str, Any] = {
        "model": "gpt-4o-mini-transcribe",
        "language": "zh",
    }
    if settings.openai_api_key:
        stt_kwargs["api_key"] = settings.openai_api_key
    return openai.STT(**stt_kwargs)


def session_id_from_metadata(metadata: str | None) -> str | None:
    if not metadata:
        return None
    try:
        payload = json.loads(metadata)
    except json.JSONDecodeError:
        logger.debug("livekit_metadata_invalid metadata=%s", metadata)
        return None
    session_id = payload.get("session_id")
    return session_id if isinstance(session_id, str) and session_id else None


def resolve_session_id(
    orchestrator: CallSessionOrchestrator,
    metadata_session_id: str | None,
) -> tuple[str, str]:
    if metadata_session_id:
        existing_session = orchestrator.get_session(metadata_session_id)
        if existing_session is not None:
            greeting = existing_session.transcript[-1].text if existing_session.transcript else ""
            return existing_session.id, greeting

    session = orchestrator.start_call(call_sid="livekit")
    greeting = session.transcript[-1].text if session.transcript else ""
    return session.id, greeting


async def handle_final_transcript(
    *,
    orchestrator: CallSessionOrchestrator,
    livekit_session: AgentSession,
    session_id: str,
    transcript: str,
) -> None:
    caller_text = transcript.strip()
    if not caller_text:
        return
    result = await orchestrator.handle_caller_text(
        session_id=session_id,
        caller_text=caller_text,
    )
    await livekit_session.say(result.agent_text, allow_interruptions=True)


async def notify_session_end(
    orchestrator: CallSessionOrchestrator,
    session_id: str,
) -> None:
    try:
        await orchestrator.notify_session_end(session_id)
    except Exception:
        logger.exception("livekit_session_end_notify_failed session_id=%s", session_id)


async def gatekeeper_entrypoint(ctx: agents.JobContext) -> None:
    settings = process_settings(ctx.proc)
    orchestrator = process_orchestrator(ctx.proc)

    await ctx.connect()
    metadata_session_id = session_id_from_metadata(getattr(ctx.job, "metadata", None))
    session_id, greeting = resolve_session_id(orchestrator, metadata_session_id)
    livekit_session = create_agent_session(settings)

    @livekit_session.on("user_input_transcribed")
    def on_user_input_transcribed(event) -> None:
        if not event.is_final:
            return
        asyncio.create_task(
            handle_final_transcript(
                orchestrator=orchestrator,
                livekit_session=livekit_session,
                session_id=session_id,
                transcript=event.transcript,
            )
        )

    @livekit_session.on("metrics_collected")
    def on_metrics_collected(event) -> None:
        logger.info(
            "livekit_metrics session_id=%s metrics=%s",
            session_id,
            event.metrics,
        )

    ctx.add_shutdown_callback(lambda: notify_session_end(orchestrator, session_id))
    await livekit_session.start(
        room=ctx.room,
        agent=GatekeeperAgent(),
    )
    if greeting:
        await livekit_session.say(greeting, allow_interruptions=False)


def build_server(settings: Settings | None = None) -> AgentServer:
    settings = settings or Settings.from_env()
    server = AgentServer(
        ws_url=settings.livekit_url,
        api_key=settings.livekit_api_key,
        api_secret=settings.livekit_api_secret,
        setup_fnc=setup_job_process,
    )

    server.rtc_session(gatekeeper_entrypoint, agent_name=settings.livekit_agent_name)
    return server


if __name__ == "__main__":
    agents.cli.run_app(build_server())
