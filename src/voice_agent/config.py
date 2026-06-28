from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


def _bool_from_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True, slots=True)
class Settings:
    app_env: str
    database_path: Path
    wecom_webhook_url: str | None
    notification_dry_run: bool
    voice_agent_ai_provider: str
    livekit_url: str | None
    livekit_api_key: str | None
    livekit_api_secret: str | None
    livekit_agent_name: str
    openai_api_key: str | None
    dashscope_api_key: str | None
    dashscope_base_url: str
    dashscope_asr_model: str
    dashscope_llm_model: str
    elevenlabs_api_key: str | None
    elevenlabs_voice_id: str | None

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        wecom_webhook_url = os.getenv("WECOM_WEBHOOK_URL") or None
        livekit_url = os.getenv("LIVEKIT_URL") or None
        livekit_api_key = os.getenv("LIVEKIT_API_KEY") or None
        livekit_api_secret = os.getenv("LIVEKIT_API_SECRET") or None
        openai_api_key = os.getenv("OPENAI_API_KEY") or None
        dashscope_api_key = os.getenv("DASHSCOPE_API_KEY") or None
        elevenlabs_api_key = os.getenv("ELEVENLABS_API_KEY") or None
        elevenlabs_voice_id = os.getenv("ELEVENLABS_VOICE_ID") or None

        return cls(
            app_env=os.getenv("APP_ENV", "local"),
            database_path=Path(os.getenv("DATABASE_PATH", ".data/voice-agent.sqlite3")),
            wecom_webhook_url=wecom_webhook_url,
            notification_dry_run=_bool_from_env("NOTIFICATION_DRY_RUN", True),
            voice_agent_ai_provider=os.getenv("VOICE_AGENT_AI_PROVIDER", "openai").lower(),
            livekit_url=livekit_url.rstrip("/") if livekit_url else None,
            livekit_api_key=livekit_api_key,
            livekit_api_secret=livekit_api_secret,
            livekit_agent_name=os.getenv("LIVEKIT_AGENT_NAME", "parking-gatekeeper"),
            openai_api_key=openai_api_key,
            dashscope_api_key=dashscope_api_key,
            dashscope_base_url=os.getenv(
                "DASHSCOPE_BASE_URL",
                "https://dashscope.aliyuncs.com/compatible-mode/v1",
            ).rstrip("/"),
            dashscope_asr_model=os.getenv("DASHSCOPE_ASR_MODEL", "qwen3-asr-flash"),
            dashscope_llm_model=os.getenv("DASHSCOPE_LLM_MODEL", "qwen-plus"),
            elevenlabs_api_key=elevenlabs_api_key,
            elevenlabs_voice_id=elevenlabs_voice_id,
        )
