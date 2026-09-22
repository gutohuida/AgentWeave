"""Tests for hub.config.Settings — the refusal fix.

`openspec/changes/a-hub-that-was-not-told-which-database-refuses-to-open-one` (a): a
caller that skips the CLI (direct `uvicorn hub.main:app`, or any future embedder) and
supplies no `DATABASE_URL` — neither in the process environment nor in a `.env` in its
working directory — must not silently land on a guessed database. `Settings()` raises
`HubNotToldWhichDatabase` instead.
"""

from pathlib import Path

import pytest


class TestDatabaseUrlDefault:
    def test_no_database_url_anywhere_refuses_instead_of_guessing(self, monkeypatch):
        """Regression test for the bug itself: a caller that skips the CLI (no
        DATABASE_URL in the environment, and none in a reachable .env) must not land
        on a silently-guessed path. `Settings()` raises `HubNotToldWhichDatabase`
        whose message names the absolute path it declined to open, `DATABASE_URL`,
        and bare `agentweave` as the way to get that default.

        Mutation-checked: reverting `database_url`'s default_factory to
        `_default_database_url` makes this test fail (it stops raising).

        Constructed with `_env_file=None` — this machine's real `hub/.env` sets
        `DATABASE_URL` explicitly (the trial Hub's own override), so leaving the
        `.env` lookup in place would test that override, not the refusal this test
        targets. `monkeypatch.delenv` alone isn't enough because pydantic-settings
        falls back to the `.env` file when the OS environment doesn't have the
        variable.
        """
        monkeypatch.delenv("DATABASE_URL", raising=False)
        from hub.config import HubNotToldWhichDatabase, Settings, _default_database_url

        with pytest.raises(HubNotToldWhichDatabase) as excinfo:
            Settings(_env_file=None)

        message = str(excinfo.value)
        default_path = _default_database_url()
        assert default_path in message, message
        assert Path(default_path[len("sqlite+aiosqlite:///") :]).is_absolute(), default_path
        assert "DATABASE_URL" in message, message
        assert "agentweave" in message, message

    def test_explicit_database_url_still_overrides_the_default(self, monkeypatch):
        """DATABASE_URL, native mode's own override mechanism (`_hub_native_start`
        sets it before importing hub.main), must still win, and the refusal factory
        must not run at all — a factory that raises but is never called cannot be
        the source of the returned value."""
        monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
        from hub.config import Settings

        assert Settings(_env_file=None).database_url == "sqlite+aiosqlite:///:memory:"

    def test_database_url_from_env_file_alone_also_satisfies_the_refusal(
        self, tmp_path, monkeypatch
    ):
        """A value supplied only by a `.env` in the working directory — not the
        process environment — must also satisfy the refusal, because 1.4's message
        names `.env` as a consulted source."""
        monkeypatch.delenv("DATABASE_URL", raising=False)
        env_file = tmp_path / ".env"
        env_file.write_text("DATABASE_URL=sqlite+aiosqlite:///:memory:\n", encoding="utf-8")
        from hub.config import Settings

        assert Settings(_env_file=env_file).database_url == "sqlite+aiosqlite:///:memory:"

    def test_relative_database_url_comes_back_unchanged(self, monkeypatch):
        """A relative DATABASE_URL must come back from Settings unchanged, not
        absolutized against the home default — group 2's line is what names the
        cwd it resolves against, not this class."""
        monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///data/agentweave.db")
        from hub.config import Settings

        assert Settings(_env_file=None).database_url == "sqlite+aiosqlite:///data/agentweave.db"


class TestDatabaseUrlDriftAgainstCli:
    """D1's own stated risk: the CLI (`agentweave-ai`) and the Hub
    (`agentweave-hub`) are independently-installable distributions joined by only a
    floor version constraint (`pyproject.toml`'s `agentweave-hub>=1.1.0`), not a
    ceiling — `pip install -U agentweave-hub` can give a newer Hub with an unchanged
    CLI still satisfying that floor. `HUB_DIR`'s path and `config.py`'s default are
    two independent computations of what is supposed to be the identical path. This
    test guards them from drifting apart on the same interpreter — verified live in
    this repo's own test environment, which can import both distributions."""

    def test_hub_default_matches_cli_hub_dir(self):
        from agentweave.cli import HUB_DIR
        from hub.config import _default_database_url

        cli_path = HUB_DIR / "data" / "agentweave.db"
        expected = f"sqlite+aiosqlite:///{cli_path.as_posix()}"
        assert _default_database_url() == expected


class TestDockerComposeProjectNamePinned:
    """D2: `hub/docker-compose.yml` must pin a top-level `name:` so Compose's
    project-name prefix — and therefore the `hub-data` named volume — does not
    depend on the directory `docker compose up` was run from.

    Plain YAML parse, not a live `docker compose` invocation — this repo's test
    environment does not have Compose available to shell out to.
    """

    def test_compose_file_declares_pinned_project_name(self):
        import yaml

        compose_path = Path(__file__).resolve().parents[1] / "docker-compose.yml"
        data = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
        assert data.get("name") == "agentweave", (
            f"hub/docker-compose.yml must declare a top-level 'name: agentweave' key, "
            f"got {data.get('name')!r} -- mutation-check: removing the key should fail "
            f"this test"
        )
