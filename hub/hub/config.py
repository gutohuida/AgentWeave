"""Hub configuration — reads from environment / .env file."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "sqlite+aiosqlite:///data/agentweave.db"
    aw_port: int = 8000

    # Bootstrap key inserted on first startup
    aw_bootstrap_api_key: str = ""
    aw_bootstrap_project_id: str = "proj-default"
    aw_bootstrap_project_name: str = "Default Project"


settings = Settings()
