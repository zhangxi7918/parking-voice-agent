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
    dashscope_api_key: str | None
    qwen_realtime_model: str

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        public_base_url = os.getenv("PUBLIC_BASE_URL") or None
        wecom_webhook_url = os.getenv("WECOM_WEBHOOK_URL") or None
        dashscope_api_key = os.getenv("DASHSCOPE_API_KEY") or None

        return cls(
            app_env=os.getenv("APP_ENV", "local"),
            public_base_url=public_base_url.rstrip("/") if public_base_url else None,
            database_path=Path(os.getenv("DATABASE_PATH", ".data/voice-agent.sqlite3")),
            wecom_webhook_url=wecom_webhook_url,
            notification_dry_run=_bool_from_env("NOTIFICATION_DRY_RUN", True),
            dashscope_api_key=dashscope_api_key,
            qwen_realtime_model=os.getenv("QWEN_REALTIME_MODEL", "qwen-omni-turbo-realtime"),
        )
