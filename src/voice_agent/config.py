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
    public_base_url: str | None
    database_path: Path
    wecom_webhook_url: str | None
    notification_dry_run: bool
    twilio_account_sid: str | None
    twilio_auth_token: str | None
    twilio_phone_number: str | None
    twilio_validate_signature: bool
    dashscope_api_key: str | None
    qwen_realtime_model: str

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        public_base_url = os.getenv("PUBLIC_BASE_URL") or None
        wecom_webhook_url = os.getenv("WECOM_WEBHOOK_URL") or None
        dashscope_api_key = os.getenv("DASHSCOPE_API_KEY") or None
        twilio_account_sid = os.getenv("TWILIO_ACCOUNT_SID") or None
        twilio_auth_token = os.getenv("TWILIO_AUTH_TOKEN") or None
        twilio_phone_number = os.getenv("TWILIO_PHONE_NUMBER") or None

        return cls(
            app_env=os.getenv("APP_ENV", "local"),
            public_base_url=public_base_url.rstrip("/") if public_base_url else None,
            database_path=Path(os.getenv("DATABASE_PATH", ".data/voice-agent.sqlite3")),
            wecom_webhook_url=wecom_webhook_url,
            notification_dry_run=_bool_from_env("NOTIFICATION_DRY_RUN", True),
            twilio_account_sid=twilio_account_sid,
            twilio_auth_token=twilio_auth_token,
            twilio_phone_number=twilio_phone_number,
            twilio_validate_signature=_bool_from_env("TWILIO_VALIDATE_SIGNATURE", False),
            dashscope_api_key=dashscope_api_key,
            qwen_realtime_model=os.getenv("QWEN_REALTIME_MODEL", "qwen3.5-omni-plus-realtime"),
        )
