from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    app_env: str = "development"
    database_url: str = ""

    github_client_id: str = ""
    github_client_secret: str = ""
    github_token: str = ""

    gemini_api_key: str = ""
    groq_api_key: str = ""

    session_secret_key: str = ""

    gemini_model: str = "gemini-flash-latest"
    gemini_fallback_model: str = "gemini-flash-lite-latest"
    gemini_secondary_fallback_model: str = "gemini-3.8-flash"
    groq_model: str = "qwen/qwen3.8-27b"

    model_config = SettingsConfigDict(
        env_file=(_BACKEND_DIR / ".env", ".env"),
        extra="ignore",
    )


settings = Settings()
