"""Runtime configuration for the API, loaded from the environment and `.env`."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[2]
ENV_FILE = ROOT_DIR / ".env"

DEFAULTS = {
    "APP_ENV": "development",
    "API_HOST": "127.0.0.1",
    "API_PORT": "8000",
}

# Frontend dev servers allowed to call the API.
CORS_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]


@dataclass(frozen=True)
class Settings:
    app_env: str
    api_host: str
    api_port: int

    @property
    def is_development(self) -> bool:
        return self.app_env.lower() in {"development", "dev", "local"}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    load_dotenv(ENV_FILE, override=False)
    return Settings(
        app_env=os.getenv("APP_ENV", DEFAULTS["APP_ENV"]),
        api_host=os.getenv("API_HOST", DEFAULTS["API_HOST"]),
        api_port=int(os.getenv("API_PORT", DEFAULTS["API_PORT"])),
    )
