"""Hub configuration — reads from environment / .env file."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_database_url() -> str:
    """Same absolute, home-relative path native mode (cli.py's HUB_DIR) already computes.

    Only consulted by callers that skip the CLI (direct `uvicorn hub.main:app`, or any
    future embedder) — native mode sets DATABASE_URL in os.environ before this class is
    ever instantiated, so this default never fires there.
    """
    path = Path.home() / ".agentweave" / "hub" / "data" / "agentweave.db"
    return f"sqlite+aiosqlite:///{path.as_posix()}"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = Field(default_factory=_default_database_url)
    aw_host: str = "127.0.0.1"
    aw_port: int = 8000

    # Instance operator credential, minted on first startup if the database has none.
    # There is deliberately no bootstrap *project* setting: startup creates no project,
    # so there is nothing for one to name.
    aw_bootstrap_api_key: str = ""

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
