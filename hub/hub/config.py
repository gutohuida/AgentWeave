"""Hub configuration — reads from environment / .env file."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "sqlite+aiosqlite:///data/agentweave.db"
    aw_host: str = "127.0.0.1"
    aw_port: int = 8000

    # Bootstrap key inserted on first startup
    aw_bootstrap_api_key: str = ""
    aw_bootstrap_project_id: str = "proj-default"
    aw_bootstrap_project_name: str = "Default Project"

    # SSE ticket signing
    aw_ticket_secret: str = ""
    aw_ticket_ttl: int = 300  # seconds

    # Request body size cap
    aw_max_body_size: int = 1_048_576  # 1 MB

    # Explicit container workspace root (Docker mode). When set, project
    # registrations are accepted only beneath this container-visible root;
    # empty means native local mode with no containment restriction.
    aw_workspace_root: str = ""


settings = Settings()
