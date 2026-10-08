from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    database_url: str = ""

    github_client_id: str = ""
    github_client_secret: str = ""
    github_token: str = ""

    gemini_api_key: str = ""
    groq_api_key: str = ""

    session_secret_key: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )


settings = Settings()