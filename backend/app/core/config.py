from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/core/config.py -> backend -> repo root
BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_ROOT.parent


class Settings(BaseSettings):
    app_name: str = "upay-financial-life-copilot"
    debug: bool = False
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    allowed_origins: list[str] = ["*"]

    # --- financial policy --------------------------------------------------
    monthly_recurring_cap: float = 0.40
    minimum_balance_buffer: float = 5000.0
    buffer_floor_months: float = 1.0
    emergency_fund_months: float = 3.0

    # --- simulation --------------------------------------------------------
    monte_carlo_paths: int = 2000
    monte_carlo_seed: int = 42

    # --- data --------------------------------------------------------------
    # ``data_root`` is the approved development dataset. ``generated_dir`` is
    # named only so code can *refuse* to read it: the development dataset is the
    # source of truth and the generated population is explicitly out of bounds.
    data_root: Path = REPO_ROOT / "data" / "dev"
    split_path: Path = REPO_ROOT / "data" / "dev" / "splits"
    generated_dir: Path = REPO_ROOT / "data" / "generated"

    # --- artifacts ---------------------------------------------------------
    artifacts_dir: Path = BACKEND_ROOT / "artifacts"

    # --- LLM providers (REST, no SDK required) -----------------------------
    gemini_api_key: str = ""
    gemini_base_url: str = "https://generativelanguage.googleapis.com"
    gemini_model: str = "gemini-2.5-flash"
    groq_api_key: str = ""
    groq_base_url: str = "https://api.groq.com"
    groq_model: str = "llama-3.1-70b-versatile"

    # --- voice (env-pluggable) --------------------------------------------
    stt_provider: str = "env"
    tts_provider: str = "env"
    stt_api_key: str = ""
    tts_api_key: str = ""
    stt_base_url: str = ""
    tts_base_url: str = ""
    stt_model: str = ""
    tts_model: str = ""

    # --- storage -----------------------------------------------------------
    use_postgres: bool = False
    database_url: str = ""

    model_config = SettingsConfigDict(
        env_file=str(BACKEND_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="allow",
    )


settings = Settings()
