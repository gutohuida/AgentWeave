"""Hub configuration — reads from environment / .env file."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class HubNotToldWhichDatabase(RuntimeError):  # noqa: N818 - "refused" is the outcome, not a fault
    """Raised when no DATABASE_URL reached the process and the Hub refuses to guess."""


def _default_database_url() -> str:
    """Same absolute, home-relative path native mode (cli.py's HUB_DIR) already computes.

    Quoted by `_refuse_to_guess_a_database`'s message; never used as a fallback. It is
    the path bare `agentweave` resolves to **on the default profile, when the
    environment carries no DATABASE_URL of its own** — `_hub_resolve_database_source`
    (`src/agentweave/cli.py`) hands a pre-existing DATABASE_URL through unchanged, and
    `--profile` computes a different path, so this function is not "the" CLI database,
    only the one CLI computation this module needs to quote. Kept here so the refusal
    message and `agentweave doctor` cannot drift apart (guarded by
    TestDatabaseUrlDriftAgainstCli).
    """
    path = Path.home() / ".agentweave" / "hub" / "data" / "agentweave.db"
    return f"sqlite+aiosqlite:///{path.as_posix()}"


def _refuse_to_guess_a_database() -> str:
    """Raised instead of silently defaulting — a caller that skips the CLI (direct
    `uvicorn hub.main:app`, or any future embedder) must name its database."""
    default_path = _default_database_url()
    raise HubNotToldWhichDatabase(
        "The Hub was not told which database to open. Checked the process "
        "environment and a .env file in the current working directory for "
        f"DATABASE_URL and found neither. It declined to open {default_path!r} "
        "without being asked to. Set DATABASE_URL explicitly, or run bare "
        "`agentweave` to use that default."
    )


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = Field(default_factory=_refuse_to_guess_a_database)
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
