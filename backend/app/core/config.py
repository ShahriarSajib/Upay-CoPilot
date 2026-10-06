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
    frontend_origins: list[str] = []

    # --- financial policy --------------------------------------------------
    monthly_recurring_cap: float = 0.40
    minimum_balance_buffer: float = 5000.0
    buffer_floor_months: float = 1.0
    emergency_fund_months: float = 3.0

    # --- simulation --------------------------------------------------------
    monte_carlo_paths: int = 2000
    monte_carlo_seed: int = 42

    # --- data --------------------------------------------------------------
    # The generated population is the single source of truth for the product.
    data_root: Path = REPO_ROOT / "data" / "generated"
    split_path: Path = REPO_ROOT / "data" / "generated" / "splits"
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
    load_derived_tables: bool = True

 # --- auth --------------------------------------------------------------
 # ``JWT_SECRET_KEY`` is the documented name; ``AUTH_SECRET`` is kept as an
 # alias so either spelling in the environment signs the tokens.
    auth_secret: str = "change-me-in-production"
    jwt_secret_key: str = ""
    access_token_ttl_minutes: int = 720
    refresh_token_ttl_minutes: int = 43200
    password_min_length: int = 8

    model_config = SettingsConfigDict(
        env_file=str(BACKEND_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="allow",
    )

    @property
    def signing_secret(self) -> str:
        """The key that signs access tokens, whichever env var supplied it."""
        return self.jwt_secret_key or self.auth_secret

    @property
    def cors_origins(self) -> list[str]:
        """Origins allowed to send credentialed browser requests."""
        return self.frontend_origins or self.allowed_origins


settings = Settings()
