"""Application settings loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    exchange_rate_access_key: str
    database_path: str
    log_level: str


def load_settings() -> Settings:
    settings = Settings(
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
        exchange_rate_access_key=os.getenv("EXCHANGE_RATE_ACCESS_KEY", "").strip(),
        database_path=os.getenv("DATABASE_PATH", "traveler_wallet.sqlite3").strip(),
        log_level=os.getenv("LOG_LEVEL", "INFO").strip().upper(),
    )
    return settings


SETTINGS = load_settings()

