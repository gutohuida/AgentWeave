"""Tests for hub.config.Settings — the global-instance-state fix.

`openspec/changes/2026-08-16-one-hub-and-a-window-of-its-own` D1: config.py's
`database_url` default must be the same absolute, home-relative path native mode
(`src/agentweave/cli.py`'s `HUB_DIR`) already computes, so a caller that skips the CLI
(direct `uvicorn hub.main:app`, or any future embedder) lands on the same database
regardless of its launch directory.
"""

from pathlib import Path


class TestDatabaseUrlDefault:
    def test_default_is_absolute_home_relative_path_not_the_old_relative_default(self, monkeypatch):
        """Regression test for the bug itself: a caller that skips the CLI (no
        DATABASE_URL set in the environment) must not land on a directory-relative
        path — the old default `sqlite+aiosqlite:///data/agentweave.db` resolves
        differently depending on the process's cwd, which is the bug D1 fixes.

        Mutation-checked below (task 2.2's own instruction): temporarily revert the
        default to the old relative string and confirm this test fails.

        Constructed with `_env_file=None` — this machine's real `hub/.env` sets
        `DATABASE_URL` explicitly (the trial Hub's own override), so leaving the
        `.env` lookup in place would test that override, not the field default this
        test targets. `monkeypatch.delenv` alone isn't enough because
        pydantic-settings falls back to the `.env` file when the OS environment
        doesn't have the variable.
        """
        monkeypatch.delenv("DATABASE_URL", raising=False)
        from hub.config import Settings

        url = Settings(_env_file=None).database_url
        assert url.startswith("sqlite+aiosqlite:///"), url
        raw_path = url[len("sqlite+aiosqlite:///") :]
        assert Path(raw_path).is_absolute(), f"database_url is not absolute: {url!r}"
        home = Path.home().as_posix()
        assert raw_path.startswith(
            home
        ), f"database_url {url!r} is not under the home directory {home!r}"
        assert raw_path == (
            (Path.home() / ".agentweave" / "hub" / "data" / "agentweave.db").as_posix()
        )

    def test_explicit_database_url_still_overrides_the_default(self, monkeypatch):
        """DATABASE_URL, native mode's own override mechanism (`_hub_native_start`
        sets it before importing hub.main), must still win — D1 changes the default,
        not the override precedence."""
        monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
        from hub.config import Settings

        assert Settings(_env_file=None).database_url == "sqlite+aiosqlite:///:memory:"


class TestDatabaseUrlDriftAgainstCli:
    """D1's own stated risk: the CLI (`agentweave-ai`) and the Hub
    (`agentweave-hub`) are independently-installable distributions with no
    dependency edge between them, so `HUB_DIR`'s path and `config.py`'s default are
    two independent computations of what is supposed to be the identical path. This
    test guards them from drifting apart on the same interpreter — verified live in
    this repo's own test environment, which can import both distributions."""

    def test_hub_default_matches_cli_hub_dir(self, monkeypatch):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        from agentweave.cli import HUB_DIR
        from hub.config import Settings

        cli_path = HUB_DIR / "data" / "agentweave.db"
        expected = f"sqlite+aiosqlite:///{cli_path.as_posix()}"
        assert Settings(_env_file=None).database_url == expected


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
